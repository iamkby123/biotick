"""US House Financial Disclosure (Periodic Transaction Reports) ingest.

Previous source (house-stock-watcher S3) was closed to public access in
late 2025 — every request returns 403. We now parse the official feed
directly from the House Clerk.

Pipeline:
  1. Download `{YEAR}FD.ZIP` from disclosures-clerk.house.gov. It
     contains `{YEAR}FD.xml` indexing every filing with member name,
     state/district, filing type, and DocID.
  2. Filter to FilingType in {'P', 'A'} — PTR and PTR amendment.
  3. For each DocID not already in our `congress_trades` table (keyed
     on member_name + trade_date + ticker + trade_type), download the
     PDF at `/public_disc/ptr-pdfs/{year}/{docID}.pdf`.
  4. Extract text via pypdf, then regex out transactions:
         `<asset name> (<TICKER>) [<type>] <P|S|E> <MM/DD/YYYY> ...`
  5. Cross-reference the ticker against our `companies` table; skip
     non-biotech trades (Congress mostly trades megacap tech — we only
     care about biotech signal).
  6. Upsert. Idempotent via unique(member_name, trade_date, ticker, trade_type, amount_min).

Senate is still deferred — efdsearch.senate.gov has a captcha that
requires a real browser.
"""

import asyncio
import io
import logging
import re
import zipfile
from datetime import datetime, date
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.adcom import CongressTrade
from app.models.company import Company
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)


_ZIP_URL_TPL = (
    "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.ZIP"
)
_PDF_URL_TPL = (
    "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"
)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 BiotickResearch/1.0"
)

# PTR transaction row regex. The PDF text (after pypdf extraction) looks
# roughly like:
#   Moderna, Inc. - Common Stock (MRNA) [ST]
#   P        03/16/202603/16/2026$1,001 - $15,000
# or collapsed onto one line. We tolerate both shapes.
# Captures: ticker, txn type, txn date, notification date, amount range.
_TXN_RE = re.compile(
    r"\(([A-Z][A-Z0-9./\-]{0,6})\)\s*(?:\[(?:ST|OT|OP|DO|MF|CO|HE)\])?\s*"
    r"(S\s*\(partial\)|P|S|E)\s*"
    r"(\d{1,2}/\d{1,2}/\d{4})\s*(\d{1,2}/\d{1,2}/\d{4})\s*"
    r"\$([\d,]+)\s*-\s*\$([\d,]+)",
    re.IGNORECASE,
)


def _parse_txn_type(raw: str) -> str:
    r = raw.strip().lower()
    if r.startswith("p"):
        return "purchase"
    if r.startswith("s"):
        return "sale"
    if r.startswith("e"):
        return "exchange"
    return "other"


def _parse_date(raw: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


async def _fetch_year_index(
    client: httpx.AsyncClient, year: int
) -> list[dict]:
    """Download + unzip + parse the yearly XML. Returns list of PTR filings."""
    url = _ZIP_URL_TPL.format(year=year)
    try:
        resp = await client.get(url, timeout=60, headers={"User-Agent": _UA})
    except Exception as e:
        logger.warning(f"House zip {year}: {e}")
        return []
    if resp.status_code != 200:
        logger.warning(f"House zip {year}: HTTP {resp.status_code}")
        return []
    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
    except Exception as e:
        logger.warning(f"House zip {year} unzip failed: {e}")
        return []
    # Find the XML inside the zip
    xml_name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
    if not xml_name:
        return []
    with zf.open(xml_name) as f:
        try:
            root = ET.parse(f).getroot()
        except Exception as e:
            logger.warning(f"House zip {year} XML parse failed: {e}")
            return []

    filings = []
    for m in root.findall("Member"):
        filing_type = (m.findtext("FilingType") or "").strip()
        # P = PTR, A = PTR Amendment. Those are the ones with transactions.
        if filing_type not in {"P", "A"}:
            continue
        doc_id = (m.findtext("DocID") or "").strip()
        if not doc_id:
            continue
        first = (m.findtext("First") or "").strip()
        last = (m.findtext("Last") or "").strip()
        prefix = (m.findtext("Prefix") or "").strip()
        state_dst = (m.findtext("StateDst") or "").strip()
        filing_date_raw = (m.findtext("FilingDate") or "").strip()
        member_name = " ".join(x for x in [prefix, first, last] if x)
        filings.append(
            {
                "year": year,
                "doc_id": doc_id,
                "member_name": member_name,
                "state": state_dst[:2] if state_dst else None,
                "district": state_dst,
                "filing_date": _parse_date(filing_date_raw),
            }
        )
    return filings


async def _fetch_pdf_text(
    client: httpx.AsyncClient, year: int, doc_id: str
) -> str | None:
    """Download one PTR PDF and extract its plain text."""
    url = _PDF_URL_TPL.format(year=year, doc_id=doc_id)
    try:
        resp = await client.get(url, timeout=30, headers={"User-Agent": _UA})
    except Exception as e:
        logger.warning(f"PTR pdf {doc_id}: {e}")
        return None
    if resp.status_code != 200:
        return None
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(resp.content))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:
        logger.warning(f"PTR pdf {doc_id} parse: {e}")
        return None


def _extract_transactions(pdf_text: str) -> list[dict]:
    """Find every (ticker, type, date, amount) tuple in the PDF text."""
    if not pdf_text:
        return []
    out = []
    for m in _TXN_RE.finditer(pdf_text):
        ticker = m.group(1).upper()
        # House PTRs sometimes list options with ticker$STRIKE — skip those;
        # unlikely to land in our biotech universe anyway.
        if "$" in ticker or "/" in ticker:
            continue
        try:
            amt_min = float(m.group(5).replace(",", ""))
            amt_max = float(m.group(6).replace(",", ""))
        except Exception:
            continue
        out.append(
            {
                "ticker": ticker,
                "trade_type": _parse_txn_type(m.group(2)),
                "trade_date": _parse_date(m.group(3)),
                "notif_date": _parse_date(m.group(4)),
                "amount_min": amt_min,
                "amount_max": amt_max,
            }
        )
    return out


async def sync_congress_trades(db: AsyncSession) -> int:
    """Pull House PTR transactions from the current + previous calendar
    year, filter to biotech universe, upsert."""
    log = SyncLog(
        sync_type="CONGRESS_TRADES", started_at=datetime.utcnow(), status="RUNNING"
    )
    db.add(log)
    await db.commit()

    try:
        known = {t for (t,) in (await db.execute(select(Company.ticker))).all()}
        logger.info(f"Known biotech tickers: {len(known)}")

        written = 0
        current_year = date.today().year
        years = [current_year, current_year - 1]

        async with httpx.AsyncClient() as client:
            filings: list[dict] = []
            for y in years:
                ys = await _fetch_year_index(client, y)
                logger.info(f"House {y}: {len(ys)} PTR filings")
                filings.extend(ys)

            # Dedupe already-processed accession ids via disclosure_url lookup.
            # disclosure_url embeds the docID so we can check existence cheaply.
            seen_urls = {
                u
                for (u,) in (
                    await db.execute(
                        select(CongressTrade.disclosure_url).where(
                            CongressTrade.disclosure_url.is_not(None)
                        )
                    )
                ).all()
            }

            processed_pdfs = 0
            for f in filings:
                pdf_url = _PDF_URL_TPL.format(year=f["year"], doc_id=f["doc_id"])
                if pdf_url in seen_urls:
                    continue
                pdf_text = await _fetch_pdf_text(client, f["year"], f["doc_id"])
                # Be polite to the House server
                await asyncio.sleep(0.3)
                if not pdf_text:
                    continue
                processed_pdfs += 1
                txns = _extract_transactions(pdf_text)
                if not txns:
                    continue
                biotech_rows = [t for t in txns if t["ticker"] in known]
                if not biotech_rows:
                    continue

                for t in biotech_rows:
                    try:
                        async with db.begin_nested():
                            stmt = pg_upsert(CongressTrade).values(
                                chamber="house",
                                member_name=f["member_name"],
                                party=None,  # not in the XML
                                state=f["state"],
                                trade_date=t["trade_date"],
                                ticker=t["ticker"],
                                trade_type=t["trade_type"],
                                amount_min=t["amount_min"],
                                amount_max=t["amount_max"],
                                disclosure_url=pdf_url,
                                filing_date=f["filing_date"],
                            )
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
                        if written % 50 == 0:
                            await db.commit()
                    except Exception as e:
                        logger.warning(f"PTR row error {f['doc_id']}: {e}")
                        continue

            await db.commit()
            logger.info(
                f"Congress trades: processed {processed_pdfs} PDFs, "
                f"wrote {written} biotech trades"
            )

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = written
        await db.commit()
        return written

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Congress trades sync failed: {e}")
        raise
