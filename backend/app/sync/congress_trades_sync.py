"""US House Financial Disclosure (Periodic Transaction Reports) ingest.

Source: https://disclosures-clerk.house.gov/FinancialDisclosure

The House clerk publishes a yearly ZIP containing an XML file with all
Periodic Transaction Reports (PTRs). URL pattern:
    https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{YEAR}FD.zip

Inside the zip is `{YEAR}FD.xml`. Each `<Member>` has their own entries
and a link to the per-member PDF. The XML only lists filings, not
transactions line-by-line — for the actual trades we'd need to OCR PDFs.

For a reliable MVP we use the unofficial-but-faithful mirror at
https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json
which is updated nightly by a community scraper (public S3, no auth).
Fields map cleanly to our schema. Senate data is deferred (Cloudflare /
captcha gating per the plan).
"""

import asyncio
import logging
import re
from datetime import datetime, date

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.adcom import CongressTrade
from app.models.company import Company
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

_DATA_URL = (
    "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/"
    "data/all_transactions.json"
)

# Amounts in house filings come as ranges like "$1,001 - $15,000".
_AMOUNT_RANGE_RE = re.compile(r"\$([\d,]+)\s*-\s*\$([\d,]+)")
_AMOUNT_SINGLE_RE = re.compile(r"\$([\d,]+)")


def _parse_amount(raw: str) -> tuple[float | None, float | None]:
    if not raw:
        return None, None
    m = _AMOUNT_RANGE_RE.search(raw)
    if m:
        try:
            return float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
        except ValueError:
            return None, None
    m = _AMOUNT_SINGLE_RE.search(raw)
    if m:
        try:
            v = float(m.group(1).replace(",", ""))
            return v, v
        except ValueError:
            return None, None
    return None, None


def _parse_date(raw: str) -> date | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


async def sync_congress_trades(db: AsyncSession) -> int:
    """Pull House PTR transactions, filter to our universe, upsert."""
    log = SyncLog(
        sync_type="CONGRESS_TRADES", started_at=datetime.utcnow(), status="RUNNING"
    )
    db.add(log)
    await db.commit()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _DATA_URL,
                headers={"User-Agent": "BiotickCongressBot/1.0 (+https://biotick.io)"},
                timeout=60,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"House PTR fetch returned {resp.status_code}")
            try:
                transactions = resp.json()
            except Exception as e:
                raise RuntimeError(f"Invalid JSON: {e}") from e

        if not isinstance(transactions, list):
            raise RuntimeError("Unexpected payload shape (expected list)")

        known = {t for (t,) in (await db.execute(select(Company.ticker))).all()}
        logger.info(f"Fetched {len(transactions)} House transactions")

        written = 0
        for tx in transactions:
            try:
                ticker = str(tx.get("ticker") or "").strip().upper()
                # Skip "--" / blank tickers used for private assets / bonds
                if not ticker or ticker in {"--", "N/A"}:
                    continue
                if ticker not in known:
                    continue

                trade_type = str(tx.get("type") or "").lower()
                if trade_type.startswith("p"):
                    trade_type = "purchase"
                elif trade_type.startswith("s"):
                    trade_type = "sale"
                elif trade_type.startswith("e"):
                    trade_type = "exchange"
                else:
                    trade_type = trade_type or "other"

                amount_min, amount_max = _parse_amount(str(tx.get("amount") or ""))
                trade_date = _parse_date(str(tx.get("transaction_date") or ""))
                filing_date = _parse_date(str(tx.get("disclosure_date") or ""))

                async with db.begin_nested():
                    stmt = pg_upsert(CongressTrade).values(
                        chamber="house",
                        member_name=(tx.get("representative") or "").strip(),
                        party=(tx.get("party") or "")[:2] or None,
                        state=(tx.get("state") or "")[:2] or None,
                        trade_date=trade_date,
                        ticker=ticker,
                        trade_type=trade_type,
                        amount_min=amount_min,
                        amount_max=amount_max,
                        disclosure_url=tx.get("ptr_link") or None,
                        filing_date=filing_date,
                    )
                    # DB unique is (member_name, trade_date, ticker, trade_type, amount_min)
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=[
                            "member_name",
                            "trade_date",
                            "ticker",
                            "trade_type",
                            "amount_min",
                        ],
                    )
                    await db.execute(stmt)
                written += 1
                if written % 200 == 0:
                    await db.commit()
            except Exception as e:
                logger.warning(f"PTR row error: {e}")
                continue
        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = written
        await db.commit()
        logger.info(f"Congress trades sync: {written} rows")
        return written

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Congress trades sync failed: {e}")
        raise
