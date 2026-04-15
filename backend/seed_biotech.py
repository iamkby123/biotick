"""
Quick seed script: populate the database with curated biotech companies.
Uses rate limiting to avoid yfinance throttling.
"""

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

import yfinance as yf
from sqlalchemy import select
from app.database import init_db, async_session
from app.models.company import Company, SponsorAlias

# Curated list of major publicly traded biotech companies
BIOTECH_TICKERS = [
    # Large cap biotech
    "LLY", "ABBV", "AMGN", "GILD", "REGN", "VRTX", "MRNA", "BIIB",
    "ILMN", "ALNY", "BMRN", "IONS", "NBIX", "EXEL",
    # Mid cap biotech
    "INCY", "HALO", "PCVX", "SRPT", "RARE", "BPMC", "CORT",
    "TGTX", "KRYS", "RXRX", "APLS", "ARVN",
    # Small cap biotech
    "IMVT", "KRTX", "RVMD", "PRTA", "FOLD", "TVTX",
    "IDYA", "RCKT", "TARS", "AKRO", "CYTK",
    # Gene therapy / Cell therapy
    "CRSP", "NTLA", "BEAM", "EDIT", "BLUE",
    # Pharma (with biotech pipelines)
    "PFE", "JNJ", "MRK", "BMY", "AZN", "NVS",
]


async def seed():
    await init_db()

    print(f"Seeding {len(BIOTECH_TICKERS)} biotech companies with rate limiting...")
    print("This will take a few minutes to respect Yahoo Finance rate limits.\n")

    async with async_session() as db:
        for i, ticker in enumerate(BIOTECH_TICKERS):
            try:
                # Rate limit: 1 request every 2 seconds
                if i > 0:
                    time.sleep(2)

                info = yf.Ticker(ticker).info

                if not info or "shortName" not in info:
                    print(f"  [{i+1}/{len(BIOTECH_TICKERS)}] {ticker}: SKIPPED (no data)")
                    continue

                price = info.get("currentPrice") or info.get("previousClose")
                prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
                change_pct = None
                if price and prev_close and prev_close > 0:
                    change_pct = round(((price - prev_close) / prev_close) * 100, 2)

                # Upsert company
                result = await db.execute(select(Company).where(Company.ticker == ticker))
                company = result.scalar_one_or_none()

                name = info.get("shortName") or info.get("longName") or ticker
                market_cap = info.get("marketCap")
                sector = info.get("industry")
                desc = (info.get("longBusinessSummary") or "")[:2000]
                website = info.get("website")
                employees = info.get("fullTimeEmployees")
                exchange = "NASDAQ" if info.get("exchange") in ("NMS", "NGM", "NCM") else "NYSE"

                if company:
                    company.name = name
                    company.price = round(price, 2) if price else None
                    company.price_change_pct = change_pct
                    company.market_cap = market_cap
                    company.sector = sector
                    company.description = desc
                    company.website = website
                    company.employees = employees
                    company.sic_code = "2836"
                    company.exchange = exchange
                else:
                    company = Company(
                        ticker=ticker,
                        name=name,
                        sic_code="2836",
                        exchange=exchange,
                        market_cap=market_cap,
                        price=round(price, 2) if price else None,
                        price_change_pct=change_pct,
                        sector=sector,
                        description=desc,
                        website=website,
                        employees=employees,
                    )
                    db.add(company)

                # Add sponsor alias
                alias_result = await db.execute(
                    select(SponsorAlias).where(
                        SponsorAlias.ticker == ticker,
                        SponsorAlias.alias_name == name,
                    )
                )
                if not alias_result.scalar_one_or_none():
                    db.add(SponsorAlias(ticker=ticker, alias_name=name, is_primary=True))

                await db.commit()

                mcap_str = f"${market_cap/1e9:.1f}B" if market_cap else "N/A"
                price_str = f"${price:.2f}" if price else "N/A"
                print(f"  [{i+1}/{len(BIOTECH_TICKERS)}] {ticker}: {price_str} | {name} | MCap: {mcap_str}")

            except Exception as e:
                err = str(e)
                if "Rate" in err or "429" in err or "Too Many" in err:
                    print(f"  [{i+1}/{len(BIOTECH_TICKERS)}] {ticker}: Rate limited, waiting 30s...")
                    time.sleep(30)
                    # Retry once
                    try:
                        info = yf.Ticker(ticker).info
                        price = info.get("currentPrice") or info.get("previousClose")
                        result = await db.execute(select(Company).where(Company.ticker == ticker))
                        company = result.scalar_one_or_none()
                        if not company:
                            company = Company(
                                ticker=ticker,
                                name=info.get("shortName", ticker),
                                sic_code="2836",
                                exchange="NASDAQ",
                                price=round(price, 2) if price else None,
                                market_cap=info.get("marketCap"),
                                sector=info.get("industry"),
                            )
                            db.add(company)
                        await db.commit()
                        print(f"  [{i+1}/{len(BIOTECH_TICKERS)}] {ticker}: RETRY OK")
                    except Exception as e2:
                        print(f"  [{i+1}/{len(BIOTECH_TICKERS)}] {ticker}: FAILED - {e2}")
                        await db.rollback()
                else:
                    print(f"  [{i+1}/{len(BIOTECH_TICKERS)}] {ticker}: ERROR - {e}")
                    await db.rollback()
                continue

    print(f"\nDone! Restart the backend and check localhost:3000/companies")


if __name__ == "__main__":
    asyncio.run(seed())
