"""Extract per-drug annual revenue from 10-K filings using Claude.

10-K "Net Product Sales" or "Revenue" tables are free-form HTML. Rather
than brittle regex-based parsing, we hand the relevant snippet to Claude
with a tight system prompt and ask for structured JSON.

Cost control:
- Only process companies with >= 2 drugs in the `drugs` table (filter out
  pre-revenue shell biotechs — nothing to extract).
- One 10-K per company per run; once extracted for a given (ticker,
  fiscal_year), we don't re-run until a newer 10-K appears.
- Prompt cached via cache_control on the system block; after the first
  hit each subsequent call is billed at 10% of input tokens.
- Max input trimmed to 12k chars (roughly 3k tokens, well under the
  $0.03/filing budget).

If ANTHROPIC_API_KEY is missing, the sync logs a warning and exits cleanly.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.config import SEC_USER_AGENT
from app.models.adcom import DrugSales
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

_SYSTEM = """You extract per-drug annual revenue from SEC 10-K filings.

Return ONLY a JSON object matching this schema — no prose, no markdown:
{
  "fiscal_year": <int>,
  "drugs": [
    {"name": "<drug brand name>", "revenue_usd": <float USD>},
    ...
  ]
}

Rules:
- Use USD millions if the filing does; convert to absolute USD (e.g. $1,234M -> 1234000000).
- Include only DRUG products with explicit revenue lines. Skip "royalties", "collaboration revenue", "grants", "licensing" unless tied to a specific drug.
- If you cannot find per-drug revenue, return {"fiscal_year": <int or null>, "drugs": []}.
- Use the most recent completed fiscal year in the filing.
"""


def _extract_revenue_section(html: str) -> str:
    """Return a ~12k-char slice of 10-K HTML that likely contains the
    revenue table. Heuristic: the first block after any of these anchors."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "img"]):
        t.decompose()
    text_doc = soup.get_text(separator="\n", strip=True)

    # Find the first occurrence of any of these anchors; take 12k chars
    # starting there. If none found, use the middle of the doc.
    anchors = [
        "Net Product Sales",
        "Net product revenues",
        "Product sales",
        "Disaggregation of Revenue",
        "Revenues by product",
    ]
    lowered = text_doc.lower()
    best_idx = -1
    for a in anchors:
        idx = lowered.find(a.lower())
        if idx >= 0 and (best_idx < 0 or idx < best_idx):
            best_idx = idx
    if best_idx < 0:
        best_idx = max(0, len(text_doc) // 3)
    return text_doc[best_idx : best_idx + 12_000]


async def _extract_with_claude(body_text: str) -> dict | None:
    """Call Claude, return parsed dict or None on any failure."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key or not body_text:
        return None
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return None

    client = AsyncAnthropic(api_key=key)
    try:
        msg = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1200,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": f"Extract per-drug revenue from this 10-K excerpt:\n\n{body_text}",
                }
            ],
        )
    except Exception as e:
        logger.warning(f"Claude drug-sales call failed: {e}")
        return None

    blocks = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    raw = "".join(blocks).strip()
    # Strip fenced code blocks if Claude ignored the "no markdown" rule
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL)
    try:
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Claude returned non-JSON: {e}: {raw[:200]}")
        return None


async def _candidate_companies(db: AsyncSession, limit: int) -> list[dict]:
    """10-Ks worth extracting revenue from.

    Prioritize larger companies (higher market cap) that are much more
    likely to have multiple revenue-generating products. Previous
    ORDER BY filed_date DESC picked recent 10-Ks, which skewed to
    small pre-revenue biotechs and wasted Claude calls on filings with
    no product revenue. Limit to companies with >= 2 drugs AND
    market_cap >= $500M so we only spend tokens where there's likely
    something to extract.
    """
    rows = await db.execute(
        text("""
            SELECT sf.ticker, sf.accession_number, sf.edgar_url, sf.filed_date,
                   c.market_cap
            FROM sec_filings sf
            JOIN companies c ON c.ticker = sf.ticker
            JOIN (
              SELECT company_ticker
              FROM drugs
              GROUP BY company_ticker
              HAVING COUNT(*) >= 2
            ) d ON d.company_ticker = sf.ticker
            WHERE sf.filing_type = '10-K'
              AND sf.edgar_url IS NOT NULL
              AND sf.filed_date > NOW() - INTERVAL '500 days'
              AND c.market_cap IS NOT NULL
              AND c.market_cap >= 500000000
              AND NOT EXISTS (
                SELECT 1 FROM drug_sales ds
                WHERE ds.ticker = sf.ticker
                  AND ds.source_accession = sf.accession_number
              )
            ORDER BY c.market_cap DESC NULLS LAST
            LIMIT :lim
        """),
        {"lim": limit},
    )
    return [
        {"ticker": r[0], "accession": r[1], "edgar_url": r[2], "filed_date": r[3]}
        for r in rows.fetchall()
    ]


async def _fetch_10k_body(client: httpx.AsyncClient, edgar_url: str) -> str | None:
    """Fetch index page, find the biggest .htm exhibit (likely the 10-K),
    then fetch + return its text."""
    try:
        idx = await client.get(
            edgar_url,
            headers={"User-Agent": SEC_USER_AGENT},
            timeout=20,
            follow_redirects=True,
        )
    except Exception as e:
        logger.warning(f"10-K idx {edgar_url}: {e}")
        return None
    if idx.status_code != 200:
        return None

    soup = BeautifulSoup(idx.text, "html.parser")
    best_href = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith((".htm", ".html")) and "index" not in href.lower():
            best_href = href
            break
    if not best_href:
        return None

    # Resolve relative links
    from urllib.parse import urljoin
    full = urljoin(edgar_url, best_href)
    try:
        doc = await client.get(
            full,
            headers={"User-Agent": SEC_USER_AGENT},
            timeout=40,
            follow_redirects=True,
        )
    except Exception as e:
        logger.warning(f"10-K doc {full}: {e}")
        return None
    if doc.status_code != 200:
        return None
    return doc.text


async def sync_drug_sales(db: AsyncSession, limit: int = 10) -> int:
    """Process up to `limit` 10-Ks and extract per-drug revenue via Claude."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY not set — skipping drug_sales sync")
        return 0

    log = SyncLog(sync_type="DRUG_SALES", started_at=datetime.utcnow(), status="RUNNING")
    db.add(log)
    await db.commit()

    try:
        batch = await _candidate_companies(db, limit)
        logger.info(f"drug_sales: {len(batch)} 10-Ks to process")
        written = 0

        async with httpx.AsyncClient() as client:
            for f in batch:
                try:
                    body_html = await _fetch_10k_body(client, f["edgar_url"])
                    await asyncio.sleep(0.2)
                    if not body_html:
                        continue
                    excerpt = _extract_revenue_section(body_html)
                    if not excerpt:
                        continue
                    parsed = await _extract_with_claude(excerpt)
                    if not parsed:
                        continue
                    fy = parsed.get("fiscal_year")
                    if not isinstance(fy, int):
                        continue
                    for d in (parsed.get("drugs") or []):
                        name = (d.get("name") or "").strip()
                        rev = d.get("revenue_usd")
                        if not name or not isinstance(rev, (int, float)) or rev <= 0:
                            continue
                        async with db.begin_nested():
                            stmt = pg_upsert(DrugSales).values(
                                ticker=f["ticker"],
                                drug_name=name[:200],
                                fiscal_year=fy,
                                revenue_usd=float(rev),
                                source_accession=f["accession"],
                            )
                            stmt = stmt.on_conflict_do_update(
                                index_elements=["ticker", "drug_name", "fiscal_year"],
                                set_={
                                    "revenue_usd": stmt.excluded.revenue_usd,
                                    "source_accession": stmt.excluded.source_accession,
                                    "extracted_at": datetime.utcnow(),
                                },
                            )
                            await db.execute(stmt)
                        written += 1
                    await db.commit()
                except Exception as e:
                    logger.warning(f"10-K {f.get('accession')}: {e}")
                    continue

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = written
        await db.commit()
        logger.info(f"drug_sales: {written} rows")
        return written

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"drug_sales sync failed: {e}")
        raise
