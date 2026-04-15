"""
Fetch stock prices from Finnhub.io API.

Much more reliable than yfinance — 60 req/min on free tier,
no aggressive rate limiting or blocking.
"""

import asyncio
import logging
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.sync_log import SyncLog
from app.config import BIOTECH_SIC_CODES

logger = logging.getLogger(__name__)

# Read from config
def _get_api_key():
    import os
    return os.environ.get("FINNHUB_API_KEY", "")


async def sync_prices_finnhub(db: AsyncSession) -> int:
    """Fetch prices for all biotech companies from Finnhub."""
    api_key = _get_api_key()
    if not api_key:
        logger.error("FINNHUB_API_KEY not set in environment/.env")
        return 0

    log = SyncLog(
        sync_type="PRICES_FINNHUB",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        result = await db.execute(
            select(Company).where(Company.sic_code.in_(BIOTECH_SIC_CODES))
        )
        companies = result.scalars().all()
        total = len(companies)
        count = 0

        async with httpx.AsyncClient(timeout=10) as client:
            for i, company in enumerate(companies):
                try:
                    resp = await client.get(
                        "https://finnhub.io/api/v1/quote",
                        params={"symbol": company.ticker, "token": api_key},
                    )

                    if resp.status_code == 429:
                        logger.warning("Finnhub rate limited, waiting 60s")
                        await asyncio.sleep(60)
                        resp = await client.get(
                            "https://finnhub.io/api/v1/quote",
                            params={"symbol": company.ticker, "token": api_key},
                        )

                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    current_price = data.get("c", 0)  # Current price
                    prev_close = data.get("pc", 0)     # Previous close
                    high = data.get("h", 0)             # Day high
                    low = data.get("l", 0)              # Day low

                    if current_price and current_price > 0:
                        company.price = round(current_price, 2)

                        if prev_close and prev_close > 0:
                            change_pct = ((current_price - prev_close) / prev_close) * 100
                            company.price_change_pct = round(change_pct, 2)

                        # Estimate market cap from price * shares outstanding
                        if company.shares_outstanding and company.shares_outstanding > 0:
                            company.market_cap = current_price * company.shares_outstanding

                        company.updated_at = datetime.utcnow()
                        count += 1

                    # Rate limit: 60 req/min = 1 per second
                    await asyncio.sleep(1.05)

                    if (i + 1) % 50 == 0:
                        await db.commit()
                        logger.info(f"Finnhub price sync: {i+1}/{total} ({count} updated)")

                except Exception as e:
                    logger.warning(f"Finnhub error for {company.ticker}: {e}")
                    continue

        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = count
        await db.commit()

        logger.info(f"Finnhub price sync complete: {count}/{total} updated")
        return count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Finnhub price sync failed: {e}")
        raise


async def sync_financials_finnhub(db: AsyncSession) -> int:
    """Fetch company financials (beta, PE, 52w high/low, etc.) from Finnhub."""
    api_key = _get_api_key()
    if not api_key:
        logger.error("FINNHUB_API_KEY not set")
        return 0

    log = SyncLog(
        sync_type="FINANCIALS_FINNHUB",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        result = await db.execute(
            select(Company).where(
                Company.sic_code.in_(BIOTECH_SIC_CODES),
                Company.beta.is_(None),  # Not yet enriched
            )
        )
        companies = result.scalars().all()
        total = len(companies)
        count = 0

        async with httpx.AsyncClient(timeout=10) as client:
            for i, company in enumerate(companies):
                try:
                    # Fetch basic financials
                    resp = await client.get(
                        "https://finnhub.io/api/v1/stock/metric",
                        params={
                            "symbol": company.ticker,
                            "metric": "all",
                            "token": api_key,
                        },
                    )

                    if resp.status_code == 429:
                        logger.warning("Finnhub rate limited, waiting 60s")
                        await asyncio.sleep(60)
                        continue

                    if resp.status_code == 200:
                        data = resp.json()
                        metric = data.get("metric", {})

                        if metric:
                            company.beta = metric.get("beta")
                            company.pe_ratio = metric.get("peBasicExclExtraTTM") or metric.get("peTTM")
                            company.fifty_two_week_high = metric.get("52WeekHigh")
                            company.fifty_two_week_low = metric.get("52WeekLow")
                            company.avg_volume = int(metric.get("10DayAverageTradingVolume", 0) * 1_000_000) if metric.get("10DayAverageTradingVolume") else None
                            company.dividend_yield = metric.get("dividendYieldIndicatedAnnual")
                            company.revenue = metric.get("revenuePerShareTTM", 0) * (company.shares_outstanding or 0) if metric.get("revenuePerShareTTM") else None
                            company.profit_margin = metric.get("netProfitMarginTTM")
                            if company.profit_margin:
                                company.profit_margin = company.profit_margin / 100  # Convert to decimal

                            # Shares outstanding from Finnhub
                            shares = metric.get("sharesOutstanding")
                            if shares:
                                company.shares_outstanding = shares * 1_000_000  # Finnhub returns in millions

                            # Recalculate market cap
                            if company.price and company.shares_outstanding:
                                company.market_cap = company.price * company.shares_outstanding

                            company.updated_at = datetime.utcnow()
                            count += 1

                    # Rate limit
                    await asyncio.sleep(1.05)

                    if (i + 1) % 50 == 0:
                        await db.commit()
                        logger.info(f"Finnhub financials: {i+1}/{total} ({count} updated)")

                except Exception as e:
                    logger.warning(f"Finnhub financials error for {company.ticker}: {e}")
                    continue

        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = count
        await db.commit()

        logger.info(f"Finnhub financials complete: {count}/{total} updated")
        return count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Finnhub financials failed: {e}")
        raise
