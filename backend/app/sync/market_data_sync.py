"""
Sync market data (prices, market cap) from yfinance.
"""

import asyncio
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.sync_log import SyncLog

_executor = ThreadPoolExecutor(max_workers=2)


def _download_batch(ticker_str: str):
    """Run yfinance download in a thread (it's blocking I/O)."""
    return yf.download(
        ticker_str,
        period="2d",
        group_by="ticker",
        progress=False,
        threads=True,
    )

logger = logging.getLogger(__name__)


async def sync_market_data(db: AsyncSession, batch_size: int = 100) -> int:
    """
    Update stock prices and market caps for all companies using yfinance.
    Uses batch download for efficiency.
    Returns the number of companies updated.
    """
    log = SyncLog(
        sync_type="MARKET_DATA",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        # Get all tickers
        result = await db.execute(select(Company.ticker))
        tickers = [r[0] for r in result.all()]

        if not tickers:
            log.completed_at = datetime.utcnow()
            log.status = "COMPLETED"
            log.records_processed = 0
            await db.commit()
            return 0

        count = 0

        # Process in batches
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i : i + batch_size]
            ticker_str = " ".join(batch)

            try:
                # yfinance batch download in thread pool (blocking I/O)
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(_executor, _download_batch, ticker_str)

                if data.empty:
                    continue

                for ticker in batch:
                    try:
                        if len(batch) == 1:
                            ticker_data = data
                        else:
                            if ticker not in data.columns.get_level_values(0):
                                continue
                            ticker_data = data[ticker]

                        if ticker_data.empty:
                            continue

                        # Get the latest row
                        latest = ticker_data.iloc[-1]
                        close_price = float(latest.get("Close", 0))

                        # Calculate daily change
                        if len(ticker_data) >= 2:
                            prev_close = float(ticker_data.iloc[-2].get("Close", 0))
                            if prev_close > 0:
                                change_pct = ((close_price - prev_close) / prev_close) * 100
                            else:
                                change_pct = 0.0
                        else:
                            change_pct = 0.0

                        # Update the company
                        company_result = await db.execute(
                            select(Company).where(Company.ticker == ticker)
                        )
                        company = company_result.scalar_one_or_none()
                        if company and close_price > 0:
                            company.price = round(close_price, 2)
                            company.price_change_pct = round(change_pct, 2)
                            company.updated_at = datetime.utcnow()
                            count += 1

                    except Exception as e:
                        logger.warning(f"Error updating {ticker}: {e}")
                        continue

            except Exception as e:
                logger.warning(f"Error downloading batch: {e}")
                continue

            # Commit after each batch so data appears progressively
            await db.commit()
            logger.info(f"Market data batch {i//batch_size + 1}: {count} total updated so far")

        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = count
        await db.commit()

        logger.info(f"Market data sync complete: {count} companies updated")
        return count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Market data sync failed: {e}")
        raise


async def sync_company_info(db: AsyncSession, limit: int = 50) -> int:
    """
    Enrich companies with detailed info from yfinance (market cap, description, etc).
    Processes a limited batch since each ticker requires a separate API call.
    """
    log = SyncLog(
        sync_type="COMPANY_INFO",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        # Get companies that need enrichment (no market_cap yet)
        result = await db.execute(
            select(Company)
            .where(Company.market_cap.is_(None))
            .limit(limit)
        )
        companies = result.scalars().all()

        def _get_ticker_info(ticker_symbol: str):
            """Blocking call to get ticker info."""
            return yf.Ticker(ticker_symbol).info

        count = 0
        loop = asyncio.get_event_loop()
        for company in companies:
            try:
                info = await loop.run_in_executor(_executor, _get_ticker_info, company.ticker)

                if info:
                    company.market_cap = info.get("marketCap")
                    company.description = (info.get("longBusinessSummary") or "")[:2000]
                    company.website = info.get("website")
                    company.employees = info.get("fullTimeEmployees")
                    company.sector = info.get("industry") or company.sector

                    # Location
                    company.city = info.get("city")
                    company.state = info.get("state")
                    company.country = info.get("country")
                    company.address = info.get("address1")
                    company.zip_code = info.get("zip")
                    company.phone = info.get("phone")

                    # Financials
                    company.revenue = info.get("totalRevenue")
                    company.profit_margin = info.get("profitMargins")
                    company.beta = info.get("beta")
                    company.pe_ratio = info.get("trailingPE")
                    company.dividend_yield = info.get("dividendYield")
                    company.fifty_two_week_high = info.get("fiftyTwoWeekHigh")
                    company.fifty_two_week_low = info.get("fiftyTwoWeekLow")
                    company.avg_volume = info.get("averageVolume")
                    company.shares_outstanding = info.get("sharesOutstanding")

                    # Get current price if not set
                    if not company.price:
                        company.price = info.get("currentPrice") or info.get("previousClose")

                    company.updated_at = datetime.utcnow()
                    count += 1

                # Rate limiting for yfinance
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.warning(f"Error enriching {company.ticker}: {e}")
                continue

        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = count
        await db.commit()

        logger.info(f"Company info sync complete: {count} companies enriched")
        return count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Company info sync failed: {e}")
        raise
