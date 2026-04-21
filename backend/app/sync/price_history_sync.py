"""Backfill + incremental sync of daily OHLCV from Finnhub.

Finnhub endpoint:
    GET https://finnhub.io/api/v1/stock/candle?symbol=SYM&resolution=D&from=X&to=Y

Returns
    {"c": [close...], "o": [open...], "h": [high...], "l": [low...],
     "v": [volume...], "t": [unix_seconds...], "s": "ok"|"no_data"}

Free tier = 60 req/min. We honor 1.05s between calls.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, date, timedelta

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.company import Company
from app.models.price_history import PriceHistory
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

_BASE = "https://finnhub.io/api/v1/stock/candle"


def _api_key() -> str:
    return os.environ.get("FINNHUB_API_KEY", "").strip()


async def _fetch_candle(
    client: httpx.AsyncClient, ticker: str, start: date, end: date
) -> dict | None:
    params = {
        "symbol": ticker,
        "resolution": "D",
        "from": int(time.mktime(start.timetuple())),
        "to": int(time.mktime(end.timetuple())),
        "token": _api_key(),
    }
    try:
        resp = await client.get(_BASE, params=params, timeout=20)
    except Exception as e:
        logger.warning(f"candle fetch failed {ticker}: {e}")
        return None
    if resp.status_code == 429:
        logger.warning("Finnhub 429 — sleeping 60s")
        await asyncio.sleep(60)
        return None
    if resp.status_code != 200:
        logger.warning(f"{ticker} candle {resp.status_code}: {resp.text[:200]}")
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    if data.get("s") != "ok":
        return None
    return data


async def _upsert_candles(db: AsyncSession, ticker: str, data: dict) -> int:
    """Upsert one Finnhub candle block and return rows written."""
    closes = data.get("c") or []
    opens = data.get("o") or []
    highs = data.get("h") or []
    lows = data.get("l") or []
    vols = data.get("v") or []
    times = data.get("t") or []
    n = min(len(closes), len(opens), len(highs), len(lows), len(vols), len(times))
    if not n:
        return 0

    batch = 0
    for i in range(n):
        try:
            d = datetime.utcfromtimestamp(times[i]).date()
            async with db.begin_nested():
                stmt = pg_upsert(PriceHistory).values(
                    ticker=ticker,
                    date=d,
                    open=opens[i],
                    high=highs[i],
                    low=lows[i],
                    close=closes[i],
                    volume=vols[i],
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
            batch += 1
            if batch % 200 == 0:
                await db.commit()
        except Exception as e:
            logger.warning(f"{ticker} candle row error: {e}")
            continue
    await db.commit()
    return batch


async def sync_price_history(
    db: AsyncSession,
    days: int = 365,
    tickers: list[str] | None = None,
) -> int:
    """Pull the last `days` of daily candles for every company (or a subset).

    `days=1825` (5y) is the one-time backfill; daily cron uses `days=7`
    to top up without reprocessing the full history.
    """
    if not _api_key():
        logger.warning("FINNHUB_API_KEY not set — skipping price_history sync")
        return 0

    log = SyncLog(
        sync_type="PRICE_HISTORY", started_at=datetime.utcnow(), status="RUNNING"
    )
    db.add(log)
    await db.commit()

    try:
        # Pick tickers: either explicit list or every company in the universe.
        if tickers:
            wanted = [t.upper() for t in tickers]
        else:
            wanted = [t for (t,) in (await db.execute(select(Company.ticker))).all()]

        end = date.today()
        start = end - timedelta(days=days)
        total = 0

        async with httpx.AsyncClient() as client:
            for ticker in wanted:
                data = await _fetch_candle(client, ticker, start, end)
                # Finnhub rate limit is 60 req/min on free tier.
                await asyncio.sleep(1.05)
                if not data:
                    continue
                count = await _upsert_candles(db, ticker, data)
                total += count

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = total
        await db.commit()
        logger.info(f"Price history sync: {total} candle rows over {len(wanted)} tickers")
        return total

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Price history sync failed: {e}")
        raise
