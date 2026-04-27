"""
Sync SEC filings and insider trades from EDGAR.

Fetches recent filings for each biotech company and parses
Form 4 XML for insider trading data.
"""

import asyncio
import logging
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor

import httpx
from lxml import etree
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_upsert

from app.models.company import Company
from app.models.filing import SECFiling, InsiderTrade
from app.models.sync_log import SyncLog
from app.config import SEC_USER_AGENT, BIOTECH_SIC_CODES

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)


async def sync_filings(db: AsyncSession) -> int:
    """Sync SEC filings for all biotech companies."""
    log = SyncLog(
        sync_type="FILINGS",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        result = await db.execute(
            select(Company).where(
                Company.sic_code.in_(BIOTECH_SIC_CODES),
                Company.cik.isnot(None),
            )
        )
        companies = result.scalars().all()

        total_filings = 0
        total_insider = 0
        headers = {"User-Agent": SEC_USER_AGENT}

        async with httpx.AsyncClient(headers=headers, timeout=15) as client:
            for i, company in enumerate(companies):
                try:
                    url = f"https://data.sec.gov/submissions/CIK{company.cik}.json"
                    resp = await client.get(url)

                    if resp.status_code != 200:
                        logger.warning(f"EDGAR returned {resp.status_code} for {company.ticker}")
                        await asyncio.sleep(0.15)
                        continue

                    data = resp.json()
                    recent = data.get("filings", {}).get("recent", {})

                    forms = recent.get("form", [])
                    filing_dates = recent.get("filingDate", [])
                    accession_numbers = recent.get("accessionNumber", [])
                    primary_docs = recent.get("primaryDocument", [])
                    descriptions = recent.get("primaryDocDescription", [])

                    # Only process last 50 filings
                    for j in range(min(len(forms), 50)):
                        form_type = forms[j]
                        filed_date_str = filing_dates[j] if j < len(filing_dates) else None
                        accession = accession_numbers[j] if j < len(accession_numbers) else None
                        primary_doc = primary_docs[j] if j < len(primary_docs) else None
                        desc = descriptions[j] if j < len(descriptions) else None

                        if not accession:
                            continue

                        # Filter to relevant filing types.
                        #
                        # Foreign private issuers (FPIs) like ARGX, BNTX,
                        # GMAB, VLDX file different forms — 20-F instead
                        # of 10-K (annual report), 6-K instead of 8-K
                        # (current report). Without these we have zero
                        # filings coverage for non-US-domiciled biotechs
                        # even when they're NASDAQ-listed and biotech.
                        relevant_types = {
                            "10-K", "10-Q", "8-K",            # US domestic
                            "20-F", "6-K", "40-F",            # Foreign private issuers
                            "S-1", "S-3", "F-1", "F-3",       # Registration statements (FPI variants for F-*)
                            "DEF 14A",
                            "424B4", "424B5",
                            "4",                               # Insider transactions
                            "SC 13D", "SC 13G",
                        }
                        if form_type not in relevant_types:
                            continue

                        # Parse date
                        try:
                            filed_date = datetime.strptime(filed_date_str, "%Y-%m-%d").date() if filed_date_str else None
                        except ValueError:
                            filed_date = None

                        # Build EDGAR URL
                        acc_formatted = accession.replace("-", "")
                        edgar_url = f"https://www.sec.gov/Archives/edgar/data/{int(company.cik)}/{acc_formatted}/{primary_doc}" if primary_doc else None

                        # Upsert filing
                        async with db.begin_nested():
                            stmt = pg_upsert(SECFiling).values(
                                ticker=company.ticker,
                                cik=company.cik,
                                accession_number=accession,
                                filing_type=form_type,
                                filed_date=filed_date,
                                edgar_url=edgar_url,
                                description=desc or form_type,
                            )
                            stmt = stmt.on_conflict_do_nothing(index_elements=["accession_number"])
                            await db.execute(stmt)
                        total_filings += 1

                        # Parse Form 4 for insider trades
                        if form_type == "4" and primary_doc and filed_date:
                            try:
                                insider_count = await _parse_form4(
                                    db, client, company, accession, acc_formatted, primary_doc, filed_date
                                )
                                total_insider += insider_count
                            except Exception as e:
                                logger.debug(f"Error parsing Form 4 for {company.ticker}: {e}")

                    await db.commit()
                    logger.info(f"[{i+1}/{len(companies)}] {company.ticker}: filings synced")

                    # SEC rate limit: 10 req/sec
                    await asyncio.sleep(0.15)

                except Exception as e:
                    logger.warning(f"Error syncing filings for {company.ticker}: {e}")
                    await asyncio.sleep(0.15)
                    continue

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = total_filings
        await db.commit()

        logger.info(f"Filing sync complete: {total_filings} filings, {total_insider} insider trades")
        return total_filings

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Filing sync failed: {e}")
        raise


async def _parse_form4(
    db: AsyncSession,
    client: httpx.AsyncClient,
    company: Company,
    accession: str,
    acc_formatted: str,
    primary_doc: str,
    filing_date: date,
) -> int:
    """Parse a Form 4 XML filing for insider trade data."""
    # Try to fetch the XML.
    # Form 4 primary doc URLs come prefixed with an XSLT-transform path
    # like `xslF345X05/foo.xml` or `xslF345X06/foo.xml`. We need the raw
    # XML, not the transformed view, so strip ANY `xslF345Xnn/` prefix.
    # Previously this only stripped X05 — when SEC rolled to X06, every
    # new Form 4 silently failed to parse and we lost ~12 days of insider
    # trades before catching it.
    import re as _re
    clean_doc = _re.sub(r"^xslF345X\d+/", "", primary_doc)

    xml_url = f"https://www.sec.gov/Archives/edgar/data/{int(company.cik)}/{acc_formatted}/{clean_doc}"

    resp = await client.get(xml_url)
    if resp.status_code != 200:
        # Try without stripping
        xml_url2 = f"https://www.sec.gov/Archives/edgar/data/{int(company.cik)}/{acc_formatted}/{primary_doc}"
        resp = await client.get(xml_url2)
        if resp.status_code != 200:
            return 0

    content = resp.text
    if not content.strip().startswith("<?xml") and "<ownershipDocument" not in content:
        return 0

    try:
        root = etree.fromstring(content.encode())
    except Exception:
        return 0

    count = 0

    # Get reporter info
    reporter = root.find(".//reportingOwner/reportingOwnerId")
    if reporter is None:
        return 0

    insider_name = reporter.findtext("rptOwnerName", "Unknown")
    relationship = root.find(".//reportingOwner/reportingOwnerRelationship")
    insider_title = ""
    if relationship is not None:
        if relationship.findtext("isOfficer") == "1" or relationship.findtext("isOfficer") == "true":
            insider_title = relationship.findtext("officerTitle", "Officer")
        elif relationship.findtext("isDirector") == "1" or relationship.findtext("isDirector") == "true":
            insider_title = "Director"
        elif relationship.findtext("isTenPercentOwner") == "1":
            insider_title = "10% Owner"

    # Parse non-derivative transactions
    for txn in root.findall(".//nonDerivativeTransaction"):
        try:
            txn_date_str = txn.findtext(".//transactionDate/value")
            txn_code = txn.findtext(".//transactionCoding/transactionCode", "")
            shares_str = txn.findtext(".//transactionAmounts/transactionShares/value", "0")
            price_str = txn.findtext(".//transactionAmounts/transactionPricePerShare/value", "0")
            shares_after_str = txn.findtext(".//postTransactionAmounts/sharesOwnedFollowingTransaction/value", "0")
            ownership_nature = txn.findtext(".//ownershipNature/directOrIndirectOwnership/value", "D")

            # Parse values
            txn_date = datetime.strptime(txn_date_str, "%Y-%m-%d").date() if txn_date_str else filing_date
            shares = float(shares_str) if shares_str else 0
            price = float(price_str) if price_str and price_str != "0" else None
            shares_after = float(shares_after_str) if shares_after_str else None

            # Map transaction codes
            trade_type_map = {
                "P": "PURCHASE",
                "S": "SALE",
                "M": "OPTION_EXERCISE",
                "A": "GRANT",
                "G": "GIFT",
                "J": "OTHER",
                "F": "TAX_WITHHOLDING",
            }
            trade_type = trade_type_map.get(txn_code, "OTHER")

            # Skip if no meaningful shares
            if shares <= 0:
                continue

            total_value = shares * price if price else None

            async with db.begin_nested():
                stmt = pg_upsert(InsiderTrade).values(
                    ticker=company.ticker,
                    accession_number=accession,
                    insider_name=insider_name,
                    insider_title=insider_title,
                    trade_type=trade_type,
                    transaction_date=txn_date,
                    shares=shares,
                    price_per_share=price,
                    total_value=total_value,
                    shares_owned_after=shares_after,
                    filing_date=filing_date,
                    is_direct=(ownership_nature == "D"),
                )
                # Use on_conflict_do_nothing since unique constraint covers dedup
                stmt = stmt.on_conflict_do_nothing(
                    constraint="uq_insider_trade"
                )
                await db.execute(stmt)
            count += 1

        except Exception as e:
            logger.debug(f"Error parsing transaction in Form 4: {e}")
            continue

    return count
