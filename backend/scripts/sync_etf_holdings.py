"""
Sync biotech ETF holdings into the ``etf_holdings`` table.

Fetches the daily holdings files published by the issuers for four biotech
ETFs (XBI, IBB, LABU, SBIO), matches each constituent's ticker against our
``companies`` table, and upserts into ``etf_holdings``.

Run standalone::

    cd backend
    python -m scripts.sync_etf_holdings
    # or
    python scripts/sync_etf_holdings.py [XBI IBB ...]

The SUPABASE_DB_PASSWORD env var must be set (same pattern as the rest of
the backend).
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession

# Make backend/ importable when run directly as `python scripts/sync_etf_holdings.py`
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.database import async_session  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.etf import ETFHolding  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# ── Known URLs ──────────────────────────────────────────────────────────────

XBI_HOLDINGS_URL = (
    "https://www.ssga.com/library-content/products/fund-data/etfs/us/"
    "holdings-daily-us-en-xbi.xlsx"
)
XBI_LANDING_URL = (
    "https://www.ssga.com/us/en/intermediary/etfs/spdr-sp-biotech-etf-xbi"
)

IBB_HOLDINGS_URL = (
    "https://www.ishares.com/us/products/239699/ishares-nasdaq-biotechnology-etf/"
    "1467271812596.ajax?fileType=json&fileName=IBB_holdings&dataType=fund"
)

LABU_HOLDINGS_URL = "https://www.direxion.com/holdings/LABU.csv"

# SBIO holdings link lives on the product page; the CSV path changes
# periodically. We fetch the product page, grab the first CSV that links to
# holdings, and then parse it.
SBIO_LANDING_URL = "https://www.alpsfunds.com/exchange-traded-funds/sbio"


# ── Fetch helpers ──────────────────────────────────────────────────────────

async def _fetch_xbi(client: httpx.AsyncClient) -> list[dict]:
    """Download the XBI daily holdings .xlsx and return constituent rows."""
    # Warm up the landing page so the CDN sets any required cookies.
    try:
        await client.get(XBI_LANDING_URL, timeout=30)
    except Exception:
        pass

    resp = await client.get(XBI_HOLDINGS_URL, timeout=60)
    resp.raise_for_status()
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas is required to parse the XBI .xlsx file")
        return []

    # SSGA files typically have a few header rows we need to skip.
    df = None
    for header_row in range(0, 8):
        try:
            df = pd.read_excel(io.BytesIO(resp.content), header=header_row)
        except Exception:
            continue
        cols = {str(c).strip().lower() for c in df.columns}
        if "ticker" in cols and any("weight" in c for c in cols):
            break
    if df is None:
        logger.warning("Could not parse XBI xlsx (no header row with Ticker + Weight)")
        return []

    def _col(name_options: Iterable[str]) -> str | None:
        for col in df.columns:
            lc = str(col).strip().lower()
            for name in name_options:
                if name in lc:
                    return col
        return None

    ticker_col = _col(["ticker"])
    weight_col = _col(["weight"])
    shares_col = _col(["shares held", "shares"])
    value_col = _col(["market value"])

    rows: list[dict] = []
    for _, row in df.iterrows():
        ticker = str(row.get(ticker_col, "") if ticker_col else "").strip().upper()
        if not ticker or ticker == "NAN":
            continue
        rows.append({
            "ticker": ticker,
            "weight": _to_float(row.get(weight_col)) if weight_col else None,
            "shares": _to_float(row.get(shares_col)) if shares_col else None,
            "market_value": _to_float(row.get(value_col)) if value_col else None,
        })
    return rows


async def _fetch_ibb(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(IBB_HOLDINGS_URL, timeout=60)
    resp.raise_for_status()
    try:
        data = resp.json()
    except Exception:
        logger.error("Could not parse IBB JSON response")
        return []

    # iShares ajax returns something like {"aaData": [[ticker, name, sector, ...], ...]}
    rows = data.get("aaData") or data.get("results") or []
    parsed: list[dict] = []
    for entry in rows:
        # Legacy iShares layout: the first element is the ticker, the 7th is weight %
        # New layout: dict with keys. Try both.
        if isinstance(entry, dict):
            ticker = str(entry.get("ticker") or entry.get("tickerSymbol") or "").upper()
            weight = _to_float(entry.get("weight") or entry.get("Weight"))
            shares = _to_float(entry.get("quantity") or entry.get("sharesHeld"))
            value = _to_float(entry.get("marketValue") or entry.get("MarketValue"))
        else:
            # entry is a list
            ticker = str(entry[0] if entry else "").upper()
            weight = _to_float(entry[5] if len(entry) > 5 else None)
            shares = _to_float(entry[4] if len(entry) > 4 else None)
            value = _to_float(entry[3] if len(entry) > 3 else None)
        if not ticker or ticker == "NAN":
            continue
        parsed.append({"ticker": ticker, "weight": weight, "shares": shares, "market_value": value})
    return parsed


async def _fetch_labu(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(LABU_HOLDINGS_URL, timeout=60)
    resp.raise_for_status()
    text = resp.text
    rows = list(csv.DictReader(io.StringIO(text)))

    def _field(row: dict, *names: str) -> str | None:
        for n in names:
            for key in row:
                if key and key.strip().lower() == n:
                    return row[key]
        return None

    parsed: list[dict] = []
    for row in rows:
        ticker = _field(row, "stockticker", "ticker", "symbol")
        if not ticker:
            continue
        ticker = ticker.strip().upper()
        if not ticker or ticker in {"CASH", "--", "N/A"}:
            continue
        parsed.append({
            "ticker": ticker,
            "weight": _to_float(_field(row, "% of net assets", "weight", "weighting")),
            "shares": _to_float(_field(row, "shares held", "shares")),
            "market_value": _to_float(_field(row, "market value", "marketvalue")),
        })
    return parsed


async def _fetch_sbio(client: httpx.AsyncClient) -> list[dict]:
    # The SBIO landing page typically embeds a link to a daily holdings .csv.
    try:
        resp = await client.get(SBIO_LANDING_URL, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"SBIO landing fetch failed: {e}")
        return []

    html = resp.text
    # Look for any link ending in .csv that mentions holdings.
    match = re.search(r'href=[\'"]([^\'"]+holdings[^\'"]*\.csv)[\'"]', html, re.IGNORECASE)
    csv_url = match.group(1) if match else None
    if not csv_url:
        # Fall back: any .csv on the page
        match = re.search(r'href=[\'"]([^\'"]+\.csv)[\'"]', html, re.IGNORECASE)
        csv_url = match.group(1) if match else None
    if not csv_url:
        logger.warning("Could not locate SBIO holdings CSV link on landing page")
        return []
    if csv_url.startswith("/"):
        csv_url = "https://www.alpsfunds.com" + csv_url
    try:
        csv_resp = await client.get(csv_url, timeout=60)
        csv_resp.raise_for_status()
    except Exception as e:
        logger.warning(f"SBIO CSV fetch failed: {e}")
        return []

    rows = list(csv.DictReader(io.StringIO(csv_resp.text)))

    def _field(row: dict, *names: str) -> str | None:
        for n in names:
            for key in row:
                if key and key.strip().lower() == n:
                    return row[key]
        return None

    parsed: list[dict] = []
    for row in rows:
        ticker = _field(row, "ticker", "symbol", "holdingticker")
        if not ticker:
            continue
        ticker = ticker.strip().upper()
        if not ticker or ticker in {"CASH", "--", "N/A"}:
            continue
        parsed.append({
            "ticker": ticker,
            "weight": _to_float(_field(row, "weight", "weighting", "% of net assets")),
            "shares": _to_float(_field(row, "shares", "shares held", "quantity")),
            "market_value": _to_float(_field(row, "market value", "marketvalue")),
        })
    return parsed


_FETCHERS: dict[str, callable] = {
    "XBI": _fetch_xbi,
    "IBB": _fetch_ibb,
    "LABU": _fetch_labu,
    "SBIO": _fetch_sbio,
}


# ── Utilities ──────────────────────────────────────────────────────────────

_NUM_CLEAN = re.compile(r"[^\d.\-]")


def _to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            f = float(value)
            return f if f == f else None  # guard against NaN
        except Exception:
            return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "n/a", "--"}:
        return None
    s = _NUM_CLEAN.sub("", s)
    if not s or s in {"-", "."}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ── Upsert ─────────────────────────────────────────────────────────────────

async def _load_ticker_set(db: AsyncSession) -> set[str]:
    result = await db.execute(select(Company.ticker))
    return {t.upper() for (t,) in result.all()}


async def _upsert_holdings(
    db: AsyncSession,
    etf_ticker: str,
    rows: list[dict],
    known_tickers: set[str],
) -> int:
    count = 0
    now = datetime.utcnow()
    for row in rows:
        ticker = row["ticker"]
        if ticker not in known_tickers:
            continue
        values = {
            "etf_ticker": etf_ticker,
            "ticker": ticker,
            "weight": row.get("weight"),
            "shares": row.get("shares"),
            "market_value": row.get("market_value"),
            "updated_at": now,
        }
        stmt = pg_upsert(ETFHolding).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[ETFHolding.etf_ticker, ETFHolding.ticker],
            set_={
                "weight": stmt.excluded.weight,
                "shares": stmt.excluded.shares,
                "market_value": stmt.excluded.market_value,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await db.execute(stmt)
        count += 1
    await db.commit()
    return count


# ── Orchestrator ───────────────────────────────────────────────────────────

async def sync_etf(etf_ticker: str, client: httpx.AsyncClient, db: AsyncSession,
                   known_tickers: set[str]) -> int:
    fetcher = _FETCHERS.get(etf_ticker)
    if not fetcher:
        logger.error(f"No fetcher registered for {etf_ticker}")
        return 0
    logger.info(f"Fetching {etf_ticker} holdings …")
    try:
        rows = await fetcher(client)
    except Exception as e:
        logger.error(f"Fetch failed for {etf_ticker}: {e}")
        return 0
    logger.info(f"{etf_ticker}: {len(rows)} constituents returned")
    matched = await _upsert_holdings(db, etf_ticker, rows, known_tickers)
    logger.info(f"{etf_ticker}: {matched} holdings upserted (matched to companies table)")
    return matched


async def main(etf_tickers: list[str] | None = None) -> None:
    targets = [t.upper() for t in (etf_tickers or ["XBI", "IBB", "LABU", "SBIO"])]
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        async with async_session() as db:
            known = await _load_ticker_set(db)
            logger.info(f"Loaded {len(known)} tickers from companies table")
            totals = {}
            for t in targets:
                totals[t] = await sync_etf(t, client, db, known)
    logger.info(f"Done. Upserts: {totals}")


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(main(args or None))
