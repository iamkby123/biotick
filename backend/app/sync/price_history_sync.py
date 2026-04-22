"""Backfill + incremental sync of daily OHLCV.

History of this file:
1. Originally Finnhub's /stock/candle — 403 on free tier.
2. Pivoted to yfinance — Yahoo rate-limits Fly.io's datacenter IP range
   with `YFRateLimitError: Too Many Requests` on the FIRST request from
   Fly. yfinance is a dead end in production.
3. Tried Stooq — now requires a captcha-gated API key as of 2025.
4. Now: Polygon.io (free tier — 5 req/min, 2y history). User must set
   POLYGON_API_KEY in Fly secrets. Without it, the sync no-ops cleanly
   so the daily cron doesn't spam errors.

Polygon free-tier endpoint:
  GET /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}?apiKey=...
Returns: {results: [{t: ms, o, h, l, c, v}, ...]}

Rate limit: 5 req/min. 500 tickers = 100 minutes. We pace ~13s between
calls to stay under it.
"""

import asyncio
import logging
import os
from datetime import datetime, date, timedelta

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.price_history import PriceHistory
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)


_POLYGON_BASE = "https://api.polygon.io"


def _polygon_key() -> str:
    return os.environ.get("POLYGON_API_KEY", "").strip()


async def _fetch_candles_polygon(
    client: httpx.AsyncClient, ticker: str, days: int
) -> list[dict] | None:
    """Download Polygon.io daily-aggregate OHLCV for one ticker.

    Returns a list of {date, open, high, low, close, volume} dicts or None
    on failure / empty / rate-limit.
    """
    key = _polygon_key()
    if not key:
        return None
    today = date.today()
    d1 = today - timedelta(days=days)
    url = (
        f"{_POLYGON_BASE}/v2/aggs/ticker/{ticker.upper()}"
        f"/range/1/day/{d1.isoformat()}/{today.isoformat()}"
    )
    try:
        resp = await client.get(
            url,
            params={"apiKey": key, "adjusted": "true", "sort": "asc", "limit": 5000},
            timeout=20,
        )
    except Exception as e:
        logger.warning(f"polygon {ticker}: {e}")
        return None
    if resp.status_code == 429:
        # Free tier is 5 req/min. If we hit a 429 our pacing is off —
        # back off hard and let the next iteration retry.
        logger.warning(f"polygon {ticker}: 429, sleeping 60s")
        await asyncio.sleep(60)
        return None
    if resp.status_code != 200:
        logger.warning(f"polygon {ticker}: HTTP {resp.status_code}")
        return None
    try:
        data = resp.json() or {}
    except Exception:
        return None
    results = data.get("results") or []
    rows: list[dict] = []
    for r in results:
        try:
            ts = r.get("t")  # ms timestamp
            if not ts:
                continue
            d = datetime.utcfromtimestamp(ts / 1000).date()
            rows.append({
                "date": d,
                "open": r.get("o"),
                "high": r.get("h"),
                "low": r.get("l"),
                "close": r.get("c"),
                "volume": r.get("v"),
            })
        except Exception:
            continue
    return rows


async def _upsert_candles(
    db: AsyncSession, ticker: str, rows: list[dict]
) -> int:
    """Upsert parsed rows for one ticker. Returns row count."""
    if not rows:
        return 0
    written = 0
    for r in rows:
        try:
            async with db.begin_nested():
                stmt = pg_upsert(PriceHistory).values(
                    ticker=ticker,
                    date=r["date"],
                    open=r["open"],
                    high=r["high"],
                    low=r["low"],
                    close=r["close"],
                    volume=r["volume"],
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
    """Pull the last `days` of daily candles for every company (or subset).

    `days=1825` = 5y backfill. Daily cron uses days=7 to top up without
    reprocessing old data.

    Requires POLYGON_API_KEY env var. Without it this is a no-op that
    exits cleanly (so the daily scheduler doesn't spam FAILED entries).
    """
    log = SyncLog(
        sync_type="PRICE_HISTORY", started_at=datetime.utcnow(), status="RUNNING"
    )
    db.add(log)
    await db.commit()

    try:
        if not _polygon_key():
            log.completed_at = datetime.utcnow()
            log.status = "COMPLETED"
            log.records_processed = 0
            log.error_message = "POLYGON_API_KEY not set — skipped"
            await db.commit()
            logger.warning(
                "Price history sync skipped — POLYGON_API_KEY not set. "
                "Sign up free at polygon.io/dashboard/api-keys (5 req/min tier)."
            )
            return 0

        if tickers:
            wanted = [t.upper() for t in tickers]
        else:
            # Scope to top 100 by market cap. Polygon free tier is 5 req/min
            # so 500 would take 100 minutes. Top 100 takes ~20 minutes, covers
            # every tradable biotech anyone charts.
            wanted = [
                t
                for (t,) in (
                    await db.execute(
                        select(Company.ticker)
                        .where(Company.market_cap.is_not(None))
                        .order_by(Company.market_cap.desc().nullslast())
                        .limit(100)
                    )
                ).all()
            ]

        total = 0
        empty_count = 0

        async with httpx.AsyncClient() as client:
            for ticker in wanted:
                rows = await _fetch_candles_polygon(client, ticker, days)
                if not rows:
                    empty_count += 1
                else:
                    total += await _upsert_candles(db, ticker, rows)
                # 13s / ticker keeps us under Polygon free-tier 5 req/min.
                await asyncio.sleep(13)

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = total
        await db.commit()
        logger.info(
            f"Price history sync (polygon): {total} candles across "
            f"{len(wanted)} tickers ({empty_count} had no data)"
        )
        return total

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Price history sync failed: {e}")
        raise
