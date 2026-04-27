"""EDGAR firmwide fast-path: poll the latest filings every 10 min.

The slow `filing_sync` walks all 1054 companies and pulls their last 50
filings via SEC's per-company submissions JSON. That takes ~25 min, so
we can only run it every 3h. Between sweeps a freshly-filed Form 4 / 8-K
sits invisible to our DB.

This fast-path uses EDGAR's firmwide latest-filings ATOM feed:

    https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4
    https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K

ATOM returns the most recent ~40 filings firmwide (across all 13,000+
public companies, not just biotech). We filter to filings whose CIK is
in our `companies` table (~1,054 biotechs), then route each filing
through the same _parse_form4 / sec_filings upsert pipeline.

Volume: SEC publishes ~50 Form 4s and ~30 8-Ks every 10 minutes
firmwide during market hours. Of those, maybe 1-3 are biotech. So each
run does roughly 2-5 EDGAR HTTP fetches. Cheap.

Schedule: every 10 minutes during market hours (9:00-21:00 UTC) since
that's when 95% of filings hit EDGAR.
"""

import asyncio
import logging
import re
from datetime import datetime, date

import httpx
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SEC_USER_AGENT
from app.models.company import Company
from app.models.filing import SECFiling
from app.models.sync_log import SyncLog
from app.sync.filing_sync import _parse_form4

logger = logging.getLogger(__name__)


# Form types we care about + which trigger downstream parsers.
FAST_PATH_FORMS = {"4", "8-K", "6-K", "20-F", "10-K", "10-Q"}

# EDGAR firmwide latest-filings RSS URL pattern. `count=40` returns the
# most-recent ~40 filings of that type. `output=atom` requests structured
# XML rather than HTML.
LATEST_URL_TPL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?"
    "action=getcurrent&type={form}&company=&dateb=&owner=include&count=40&output=atom"
)

# Regex to pull (CIK, accession) out of EDGAR's atom <id> field. Example:
#  urn:tag:sec.gov,2008:accession-number=0001127602-26-013824
_ACCESSION_RE = re.compile(r"accession-number=([0-9-]+)")
_CIK_RE = re.compile(r"/Archives/edgar/data/(\d+)/")


async def _fetch_latest_filings(
    client: httpx.AsyncClient, form_type: str
) -> list[dict]:
    """Hit EDGAR's firmwide latest-filings ATOM feed and parse out
    (cik, accession, form, filed_at, primary_doc) for each entry."""
    url = LATEST_URL_TPL.format(form=form_type)
    try:
        resp = await client.get(
            url,
            headers={"User-Agent": SEC_USER_AGENT, "Accept": "application/atom+xml"},
            timeout=15,
        )
    except Exception as e:
        logger.warning(f"EDGAR latest {form_type}: {e}")
        return []
    if resp.status_code != 200:
        return []

    entries: list[dict] = []
    text_body = resp.text

    # Cheap regex parser — we don't need the full XML tree, just a few fields.
    # Each <entry> block has:
    #   <id>urn:tag:sec.gov,2008:accession-number=NNNNNNN-NN-NNNNNN</id>
    #   <link href="https://www.sec.gov/Archives/edgar/data/CIK/ACCNN/PRIMARYDOC"/>
    #   <updated>2026-04-27T12:34:56-04:00</updated>
    #   <category term="4"/>
    for entry_match in re.finditer(
        r"<entry>(.*?)</entry>", text_body, re.DOTALL
    ):
        block = entry_match.group(1)

        acc_m = _ACCESSION_RE.search(block)
        if not acc_m:
            continue
        accession = acc_m.group(1)

        link_m = re.search(r'<link[^>]+href="([^"]+)"', block)
        link = link_m.group(1) if link_m else ""
        cik_m = _CIK_RE.search(link)
        if not cik_m:
            continue
        cik = int(cik_m.group(1))

        # primary doc filename (after the last /)
        primary_doc = link.split("/")[-1] if "/Archives/" in link else None

        updated_m = re.search(r"<updated>([^<]+)</updated>", block)
        try:
            filed_at = (
                datetime.fromisoformat(updated_m.group(1).replace("Z", "+00:00")).date()
                if updated_m
                else date.today()
            )
        except Exception:
            filed_at = date.today()

        entries.append({
            "cik": cik,
            "accession": accession,
            "form": form_type,
            "filed_date": filed_at,
            "primary_doc": primary_doc,
            "edgar_url": link,
        })

    return entries


async def sync_edgar_fast_path(db: AsyncSession) -> int:
    """Poll EDGAR's firmwide latest filings, filter to biotech tickers in
    our universe, and upsert them. Returns # of new filings written."""
    log = SyncLog(
        sync_type="EDGAR_FAST_PATH",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        # Build CIK -> Company lookup once (1,054 entries, fits in memory)
        comp_rows = (await db.execute(select(Company))).scalars().all()
        cik_to_company = {int(c.cik): c for c in comp_rows if c.cik}
        logger.info(f"edgar_fast_path: scanning {len(cik_to_company)} biotechs")

        new_filings = 0
        new_form4_rows = 0

        async with httpx.AsyncClient() as client:
            for form_type in ["4", "8-K", "6-K"]:
                entries = await _fetch_latest_filings(client, form_type)
                # Tiny pace between calls to be nice to EDGAR
                await asyncio.sleep(1)

                for e in entries:
                    company = cik_to_company.get(e["cik"])
                    if not company:
                        continue
                    # Already in DB? Cheap check via accession_number unique index.
                    exists = (await db.execute(
                        text("SELECT 1 FROM sec_filings WHERE accession_number = :a"),
                        {"a": e["accession"]},
                    )).scalar()
                    if exists:
                        continue

                    # Insert sec_filings row
                    try:
                        async with db.begin_nested():
                            stmt = pg_upsert(SECFiling).values(
                                ticker=company.ticker,
                                cik=company.cik,
                                accession_number=e["accession"],
                                filing_type=e["form"],
                                filed_date=e["filed_date"],
                                edgar_url=e["edgar_url"],
                                description=e["form"],
                            )
                            stmt = stmt.on_conflict_do_nothing(
                                index_elements=["accession_number"]
                            )
                            await db.execute(stmt)
                        new_filings += 1
                    except Exception as ex:
                        logger.warning(
                            f"  fast-path {company.ticker} {e['accession']}: {ex}"
                        )
                        continue

                    # Form 4 → also parse insider trades
                    if e["form"] == "4" and e["primary_doc"]:
                        acc_formatted = e["accession"].replace("-", "")
                        try:
                            n = await _parse_form4(
                                db,
                                client,
                                company,
                                e["accession"],
                                acc_formatted,
                                e["primary_doc"],
                                e["filed_date"],
                            )
                            new_form4_rows += n
                        except Exception as ex:
                            logger.warning(
                                f"  fast-path Form 4 parse {company.ticker}: {ex}"
                            )

                await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = new_filings
        log.error_message = f"new_filings={new_filings} insider_rows={new_form4_rows}"
        await db.commit()
        logger.info(
            f"edgar_fast_path: {new_filings} new filings, {new_form4_rows} insider rows"
        )
        return new_filings

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"edgar_fast_path failed: {e}")
        raise
