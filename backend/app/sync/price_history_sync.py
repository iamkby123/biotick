"""Backfill + incremental sync of daily OHLCV via Yahoo's chart JSON API.

We call `https://query1.finance.yahoo.com/v7/finance/chart/{ticker}` directly
with a `curl_cffi` session that impersonates Chrome — this defeats Yahoo's
datacenter IP rate-limit (yfinance's own cookie+crumb flow breaks when
wrapped in curl_cffi's session, but the chart endpoint doesn't need a
crumb, so we bypass yfinance entirely).

We also include the 4 biotech ETFs (XBI, IBB, LABU, SBIO) so the ETF
flows page has a real NAV time series.
"""

import asyncio
import logging
from datetime import datetime, date

from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.price_history import PriceHistory
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)


_ETF_TICKERS = ["XBI", "IBB", "LABU", "SBIO"]
_CHART_URL = "https://query1.finance.yahoo.com/v7/finance/chart/{ticker}"


def _range_for_days(days: int) -> str:
    """Map day counts to Yahoo range labels. Yahoo accepts: 1d, 5d, 1mo,
    3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max."""
    if days <= 31:
        return "1mo"
    if days <= 93:
        return "3mo"
    if days <= 186:
        return "6mo"
    if days <= 365:
        return "1y"
    if days <= 730:
        return "2y"
    return "5y"


def _fetch_candles_sync(ticker: str, range_label: str) -> list[dict] | None:
    """Blocking HTTP call via curl_cffi. Returns list of candle dicts or None."""
    try:
        from curl_cffi import requests as cureq

        sess = cureq.Session(impersonate="chrome124")
        resp = sess.get(
            _CHART_URL.format(ticker=ticker),
            params={"interval": "1d", "range": range_label},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"yahoo chart {ticker}: HTTP {resp.status_code}")
            return None
        data = resp.json() or {}
        res_list = data.get("chart", {}).get("result") or []
        if not res_list:
            return None
        res = res_list[0]
        timestamps = res.get("timestamp") or []
        quote = (res.get("indicators", {}).get("quote") or [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        rows: list[dict] = []
        for i, ts in enumerate(timestamps):
            try:
                d = datetime.utcfromtimestamp(ts).date()
                rows.append({
                    "date": d,
                    "open": opens[i] if i < len(opens) else None,
                    "high": highs[i] if i < len(highs) else None,
                    "low": lows[i] if i < len(lows) else None,
                    "close": closes[i] if i < len(closes) else None,
                    "volume": volumes[i] if i < len(volumes) else None,
                })
            except Exception:
                continue
        return rows
    except Exception as e:
        logger.warning(f"yahoo chart {ticker} error: {e}")
        return None


async def _upsert_candles(
    db: AsyncSession, ticker: str, rows: list[dict]
) -> int:
    """Upsert parsed rows for one ticker."""
    if not rows:
        return 0
    written = 0
    for r in rows:
        try:
            # Skip rows with no close price (non-trading day at edges)
            if r["close"] is None:
                continue
            async with db.begin_nested():
                stmt = pg_upsert(PriceHistory).values(
                    ticker=ticker,
                    date=r["date"],
                    open=float(r["open"]) if r["open"] is not None else None,
                    high=float(r["high"]) if r["high"] is not None else None,
                    low=float(r["low"]) if r["low"] is not None else None,
                    close=float(r["close"]),
                    volume=float(r["volume"]) if r["volume"] is not None else None,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["ticker", "date"],
                    set_={
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "close": stmt.excluded.close,
                        "volume": stmt.excluded.volume,
                    },
                )
                await db.execute(stmt)
            written += 1
            if written % 200 == 0:
                await db.commit()
        except Exception as e:
            logger.warning(f"{ticker} candle row error: {e}")
            continue
    await db.commit()
    return written


async def sync_price_history(
    db: AsyncSession,
    days: int = 365,
    tickers: list[str] | None = None,
) -> int:
    """Pull the last `days` of daily candles for every company (or subset)."""
    log = SyncLog(
        sync_type="PRICE_HISTORY", started_at=datetime.utcnow(), status="RUNNING"
    )
    db.add(log)
    await db.commit()

    try:
        if tickers:
            wanted = [t.upper() for t in tickers]
        else:
            # Top 500 by market cap + the 4 biotech ETFs (pinned).
            company_rows = (
                await db.execute(
                    select(Company.ticker)
                    .where(Company.market_cap.is_not(None))
                    .order_by(Company.market_cap.desc().nullslast())
                    .limit(500)
                )
            ).all()
            wanted = [t for (t,) in company_rows]
            for etf in _ETF_TICKERS:
                if etf not in wanted:
                    wanted.append(etf)

        range_label = _range_for_days(days)
        total = 0
        empty_count = 0
        consec_empty = 0

        for ticker in wanted:
            rows = await asyncio.to_thread(_fetch_candles_sync, ticker, range_label)
            if not rows:
                empty_count += 1
                consec_empty += 1
                if consec_empty >= 10:
                    # Got rate-limited — back off hard before continuing
                    logger.warning("Yahoo chart: 10 consecutive empties, backing off 30s")
                    await asyncio.sleep(30)
                    consec_empty = 0
            else:
                total += await _upsert_candles(db, ticker, rows)
                consec_empty = 0
            # 1.0s pacing — chart endpoint is more permissive than the
            # cookie+crumb endpoints yfinance uses.
            await asyncio.sleep(1.0)

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = total
        await db.commit()
        logger.info(
            f"Price history sync (yahoo chart): {total} candles across "
            f"{len(wanted)} tickers ({empty_count} returned no data)"
        )
        return total

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Price history sync failed: {e}")
        raise
