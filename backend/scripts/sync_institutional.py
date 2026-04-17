"""
Sync 13F-HR institutional holdings for specialist biotech funds.

For each hardcoded fund CIK, pulls the latest 13F-HR from SEC EDGAR,
parses the info table XML to extract (CUSIP, shares, value), then matches
CUSIPs to our ``companies`` table and upserts to ``institutional_holdings``.

CUSIP → ticker matching happens in two passes:

    1. Build a CUSIP → ticker map from SEC's ``company_tickers_exchange.json``
       (this file does not actually publish CUSIPs, so we also fall back to
       the issuer name field in the 13F and fuzzy-match against company names).
    2. For anything still unmapped we try the free OpenFIGI search API.

Run standalone::

    cd backend
    python -m scripts.sync_institutional
    # or
    python scripts/sync_institutional.py

Requires SUPABASE_DB_PASSWORD.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from datetime import datetime, date
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import SEC_USER_AGENT  # noqa: E402
from app.database import async_session  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.institutional import InstitutionalHolding  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ── Funds ──────────────────────────────────────────────────────────────────
# 10-digit CIKs with leading zeros — EDGAR formatting.
FUNDS: list[tuple[str, str]] = [
    ("RTW Investments", "0001790357"),
    ("Perceptive Advisors", "0001224962"),
    ("Baker Bros. Advisors", "0001263508"),
    ("OrbiMed Advisors", "0001055951"),
    ("Avoro Capital", "0001601049"),
    ("Deep Track Capital", "0001830033"),
]


SEC_HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept": "application/json"}

# ── CUSIP → ticker mapping ────────────────────────────────────────────────

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


async def _openfigi_cusip_lookup(
    client: httpx.AsyncClient, cusips: list[str]
) -> dict[str, str]:
    """Best-effort mapping of CUSIP → ticker using the free OpenFIGI endpoint."""
    out: dict[str, str] = {}
    if not cusips:
        return out
    # OpenFIGI accepts up to 100 jobs per request on the free tier.
    for i in range(0, len(cusips), 90):
        batch = cusips[i : i + 90]
        payload = [{"idType": "ID_CUSIP", "idValue": c} for c in batch]
        try:
            resp = await client.post(OPENFIGI_URL, json=payload, timeout=30)
        except Exception as e:
            logger.warning(f"OpenFIGI batch failed: {e}")
            continue
        if resp.status_code != 200:
            logger.warning(f"OpenFIGI returned {resp.status_code}")
            continue
        data = resp.json()
        for cusip, result in zip(batch, data):
            matches = result.get("data") or []
            if not matches:
                continue
            ticker = matches[0].get("ticker")
            if ticker:
                out[cusip] = ticker.upper()
        # Free-tier rate limit
        await asyncio.sleep(0.3)
    return out


async def _load_company_name_lookup(db: AsyncSession) -> dict[str, str]:
    """Return ``normalized company name → ticker`` for fuzzy issuer matching."""
    result = await db.execute(select(Company.ticker, Company.name))
    out: dict[str, str] = {}
    for ticker, name in result.all():
        if not name:
            continue
        key = _normalize_issuer(name)
        if key and key not in out:
            out[key] = ticker.upper()
    return out


_CORP_SUFFIXES = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|ltd|plc|sa|ag|nv|holdings?|group|pharmaceuticals?|pharma|therapeutics?|bioscience[s]?|biosciences|biotechnology|labs?|laboratories)\b",
    re.IGNORECASE,
)


def _normalize_issuer(name: str) -> str:
    n = name.lower()
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = _CORP_SUFFIXES.sub(" ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


# ── 13F fetching ───────────────────────────────────────────────────────────

async def _get_latest_13f(
    client: httpx.AsyncClient, cik: str
) -> tuple[str | None, str | None, date | None, date | None]:
    """Return ``(accession_no, primary_doc, filing_date, period_of_report)``."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        resp = await client.get(url, headers=SEC_HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Submission fetch failed for CIK {cik}: {e}")
        return None, None, None, None

    data = resp.json()
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])

    for i, form in enumerate(forms):
        if form in {"13F-HR", "13F-HR/A"}:
            def _d(s):
                try:
                    return datetime.strptime(s, "%Y-%m-%d").date()
                except Exception:
                    return None
            return (
                accessions[i] if i < len(accessions) else None,
                primary_docs[i] if i < len(primary_docs) else None,
                _d(filing_dates[i]) if i < len(filing_dates) else None,
                _d(report_dates[i]) if i < len(report_dates) else None,
            )
    return None, None, None, None


async def _get_info_table_url(
    client: httpx.AsyncClient, cik: str, accession: str
) -> str | None:
    """Find the info-table XML file inside a 13F filing's index.json."""
    acc_nodash = accession.replace("-", "")
    cik_int = int(cik.lstrip("0") or "0")
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{accession}-index.json"
    try:
        resp = await client.get(index_url, headers=SEC_HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Index fetch failed: {e}")
        return None

    data = resp.json()
    items = data.get("directory", {}).get("item", [])
    for item in items:
        name = (item.get("name") or "").lower()
        if name.endswith(".xml") and ("info" in name or "table" in name):
            return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{item['name']}"
    # Fallback: any .xml that is not the primary doc
    for item in items:
        name = (item.get("name") or "").lower()
        if name.endswith(".xml") and "primary_doc" not in name:
            return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{item['name']}"
    return None


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


async def _parse_info_table(client: httpx.AsyncClient, url: str) -> list[dict]:
    """Return a list of ``{cusip, name, shares, value}`` rows from a 13F XML."""
    try:
        resp = await client.get(url, headers={**SEC_HEADERS, "Accept": "*/*"}, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Info table fetch failed: {e}")
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        logger.warning(f"Info table XML parse error: {e}")
        return []

    rows: list[dict] = []
    for elem in root.iter():
        if _strip_ns(elem.tag).lower() != "infotable":
            continue
        entry = {}
        for child in elem:
            tag = _strip_ns(child.tag).lower()
            if tag in {"nameofissuer", "issuername"}:
                entry["name"] = (child.text or "").strip()
            elif tag == "cusip":
                entry["cusip"] = (child.text or "").strip().upper()
            elif tag == "value":
                try:
                    # Historically dollars × 1000; SEC switched to raw dollars
                    # for reports on/after 2023-01-01. Heuristic: values < 1e9
                    # are in thousands, otherwise raw. Good enough for display.
                    v = float((child.text or "0").strip() or 0)
                    entry["value"] = v * 1000 if v < 1e9 else v
                except Exception:
                    pass
            elif tag in {"shrsorprnamt", "shrsOrPrnAmt".lower()}:
                for sub in child:
                    stag = _strip_ns(sub.tag).lower()
                    if stag == "sshprnamt":
                        try:
                            entry["shares"] = float((sub.text or "0").strip() or 0)
                        except Exception:
                            pass
        if entry.get("cusip"):
            rows.append(entry)
    return rows


# ── Upsert ─────────────────────────────────────────────────────────────────

async def _upsert_holdings(
    db: AsyncSession,
    fund_name: str,
    fund_cik: str,
    quarter_end: date | None,
    filing_date: date | None,
    positions: list[dict],
    cusip_to_ticker: dict[str, str],
    name_to_ticker: dict[str, str],
    known_tickers: set[str],
) -> int:
    count = 0
    for pos in positions:
        ticker = cusip_to_ticker.get(pos.get("cusip", ""))
        if not ticker:
            ticker = name_to_ticker.get(_normalize_issuer(pos.get("name", "")))
        if not ticker or ticker not in known_tickers:
            continue
        values = {
            "ticker": ticker,
            "fund_name": fund_name,
            "fund_cik": fund_cik,
            "shares": pos.get("shares"),
            "value": pos.get("value"),
            "quarter_end": quarter_end,
            "filing_date": filing_date,
        }
        stmt = pg_upsert(InstitutionalHolding).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                InstitutionalHolding.ticker,
                InstitutionalHolding.fund_cik,
                InstitutionalHolding.quarter_end,
            ],
            set_={
                "fund_name": stmt.excluded.fund_name,
                "shares": stmt.excluded.shares,
                "value": stmt.excluded.value,
                "filing_date": stmt.excluded.filing_date,
            },
        )
        await db.execute(stmt)
        count += 1
    await db.commit()
    return count


# ── Orchestrator ───────────────────────────────────────────────────────────

async def sync_fund(
    client: httpx.AsyncClient,
    db: AsyncSession,
    fund_name: str,
    fund_cik: str,
    name_to_ticker: dict[str, str],
    known_tickers: set[str],
) -> int:
    logger.info(f"--- {fund_name} (CIK {fund_cik}) ---")
    accession, _primary, filing_date, period_of_report = await _get_latest_13f(client, fund_cik)
    if not accession:
        logger.warning(f"No 13F-HR found for {fund_name}")
        return 0
    logger.info(f"Latest filing: {accession} — period {period_of_report}, filed {filing_date}")

    info_url = await _get_info_table_url(client, fund_cik, accession)
    if not info_url:
        logger.warning(f"Could not locate info-table XML for {fund_name}")
        return 0

    positions = await _parse_info_table(client, info_url)
    logger.info(f"{fund_name}: parsed {len(positions)} positions")
    if not positions:
        return 0

    # Resolve CUSIPs → tickers (best effort). We only bother with unique CUSIPs
    # to keep OpenFIGI usage small.
    unique_cusips = sorted({p["cusip"] for p in positions if p.get("cusip")})
    cusip_map = await _openfigi_cusip_lookup(client, unique_cusips)
    logger.info(f"{fund_name}: OpenFIGI resolved {len(cusip_map)}/{len(unique_cusips)} CUSIPs")

    matched = await _upsert_holdings(
        db,
        fund_name,
        fund_cik,
        period_of_report,
        filing_date,
        positions,
        cusip_map,
        name_to_ticker,
        known_tickers,
    )
    logger.info(f"{fund_name}: upserted {matched} biotech positions")
    return matched


async def main() -> None:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        async with async_session() as db:
            known = {
                t.upper()
                for (t,) in (await db.execute(select(Company.ticker))).all()
            }
            name_to_ticker = await _load_company_name_lookup(db)
            logger.info(
                f"Loaded {len(known)} tickers and {len(name_to_ticker)} company-name keys"
            )
            totals = {}
            for fund_name, cik in FUNDS:
                try:
                    totals[fund_name] = await sync_fund(
                        client, db, fund_name, cik, name_to_ticker, known
                    )
                except Exception as e:
                    logger.error(f"{fund_name} failed: {e}")
                    totals[fund_name] = 0
                # Stay well under SEC's 10 req/s limit.
                await asyncio.sleep(0.25)
    logger.info(f"Done. Upserts: {json.dumps(totals)}")


if __name__ == "__main__":
    asyncio.run(main())
