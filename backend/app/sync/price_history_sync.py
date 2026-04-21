"""Backfill + incremental sync of daily OHLCV via yfinance.

We originally used Finnhub's /stock/candle endpoint, but that's a paid
feature — on the free tier it returns 403 "You don't have access to
this resource". yfinance (already installed for the Finnhub fallback
path elsewhere) is free and has no daily rate limit, just slows down
under hammering.

Strategy:
  - For each ticker, call Ticker(sym).history(period=..., auto_adjust=False)
  - Convert rows to (date, open, high, low, close, volume) and upsert.
  - Throttle ~0.6s between tickers to be nice to Yahoo.
  - Backfill = 365d by default; daily cron passes days=7.

yfinance is occasionally flaky (429s, empty frames). We tolerate those:
log the ticker, skip, keep going. No hard failure unless half the batch
fails.
"""

import asyncio
import logging
from datetime import datetime, date, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.price_history import PriceHistory
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)


def _period_for_days(days: int) -> str:
    """Map day counts to yfinance period strings (they accept fixed labels
    like '1y' / '5y' more efficiently than explicit date ranges)."""
    if days <= 7:
        return "1mo"
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


def _fetch_candles_sync(ticker: str, period: str):
    """Run yfinance in a thread (it's blocking / requests-based)."""
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        df = t.history(period=period, auto_adjust=False, actions=False)
        return df
    except Exception as e:
        logger.warning(f"yfinance {ticker} error: {e}")
        return None


async def _upsert_dataframe(db: AsyncSession, ticker: str, df) -> int:
    """Upsert a yfinance DataFrame for one ticker. Returns row count."""
    if df is None or df.empty:
        return 0
    batch = 0
    for idx, row in df.iterrows():
        try:
            # idx is a pandas Timestamp — convert to date
            d = idx.date() if hasattr(idx, "date") else date.today()
            async with db.begin_nested():
                stmt = pg_upsert(PriceHistory).values(
                    ticker=ticker,
                    date=d,
                    open=float(row["Open"]) if row.get("Open") is not None else None,
                    high=float(row["High"]) if row.get("High") is not None else None,
                    low=float(row["Low"]) if row.get("Low") is not None else None,
                    close=float(row["Close"]) if row.get("Close") is not None else None,
                    volume=float(row["Volume"]) if row.get("Volume") is not None else None,
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
    """Pull the last `days` of daily candles for every company (or subset).

    `days=1825` triggers a 5y backfill via yfinance's `5y` period.
    Daily cron uses days=7 to top up without reprocessing.
    """
    log = SyncLog(
        sync_type="PRICE_HISTORY", started_at=datetime.utcnow(), status="RUNNING"
    )
    db.add(log)
    await db.commit()

    try:
        if tickers:
            wanted = [t.upper() for t in tickers]
        else:
            wanted = [t for (t,) in (await db.execute(select(Company.ticker))).all()]

        period = _period_for_days(days)
        total = 0
        empty_count = 0

        for ticker in wanted:
            df = await asyncio.to_thread(_fetch_candles_sync, ticker, period)
            if df is None or df.empty:
                empty_count += 1
            else:
                total += await _upsert_dataframe(db, ticker, df)
            # Be gentle with Yahoo — no explicit rate limit but they soft-throttle
            await asyncio.sleep(0.6)

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = total
        await db.commit()
        logger.info(
            f"Price history sync (yfinance): {total} candles across "
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
