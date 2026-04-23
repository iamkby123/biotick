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
    """Return a ~30k-char slice of 10-K text likely to contain the
    per-product revenue table.

    Anthropic's Tier-1 rate limit is 30k input tokens per minute, and
    full 10-Ks clock in at ~100k-150k tokens. We can't feed the whole
    doc per call — we'd burn the limit on one LLY filing. So we pick a
    focused window using two heuristics:

      1. Find the LAST occurrence of a strong revenue-table anchor —
         the revenue note is always in the financial-statements section
         which comes late in the doc. First occurrences of "Product
         sales" / "Revenue" get matched by boilerplate / risk factors /
         geographic disclosures.
      2. Fall back to chars 60%-90% of the doc (financial statements
         are always there) if no anchor matched.

    30k chars ≈ 7,500 tokens — fits 4 calls/min under the limit.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "img", "svg"]):
        t.decompose()
    text_doc = soup.get_text(separator="\n", strip=True)
    if not text_doc:
        return ""

    # Strong anchors for the actual product-revenue disclosure note
    strong_anchors = [
        "Disaggregation of Revenue",
        "Disaggregated revenue",
        "Revenues by product",
        "Revenue by Product",
        "Net Product Sales",
        "Net product revenues",
        "Major Products",
        "Principal Products",
    ]

    lowered = text_doc.lower()

    # Find the LAST occurrence — the revenue note lives in the back half.
    best_idx = -1
    for a in strong_anchors:
        idx = lowered.rfind(a.lower())
        if idx > best_idx:
            best_idx = idx

    if best_idx < 0:
        # Fallback: chars 60%-90% of the doc — financial statements.
        best_idx = int(len(text_doc) * 0.60)

    # Back up 1k chars to catch the table header that precedes the anchor
    start = max(0, best_idx - 1_000)
    return text_doc[start : start + 30_000]


# Set to True once we see a "credit balance too low" 400. Aborts the
# rest of the run — no point fetching 10-Ks we can't extract.
_claude_credits_exhausted = False


class _ClaudeCreditsExhausted(Exception):
    """Raised to abort the drug_sales loop cleanly when Claude credit is gone."""


async def _extract_with_claude(body_text: str) -> dict | None:
    """Call Claude, return parsed dict or None on any failure.

    Raises _ClaudeCreditsExhausted if the API reports the account is out
    of credits — caller should short-circuit the entire run.
    """
    global _claude_credits_exhausted
    if _claude_credits_exhausted:
        raise _ClaudeCreditsExhausted()
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
            model="claude-sonnet-4-5",
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
        err = str(e)
        if "credit balance is too low" in err or "insufficient_quota" in err.lower():
            _claude_credits_exhausted = True
            logger.warning(
                "Claude credit balance exhausted — aborting drug_sales run."
            )
            raise _ClaudeCreditsExhausted() from e
        logger.warning(f"Claude drug-sales call failed: {e}")
        return None

    blocks = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    raw = "".join(blocks).strip()
    # Strip fenced code blocks if Claude ignored the "no markdown" rule
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL)
    # Also try to find a JSON object inside any prose wrapper Claude adds
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception as e:
            logger.warning(f"Claude JSON extraction failed: {e}: {raw[:300]}")
            return None
    logger.warning(f"Claude returned no JSON-looking text: {raw[:300]}")
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
    """Fetch the LARGEST .htm exhibit from a 10-K filing — that's almost
    always the 10-K body. Previously we picked the FIRST .htm which was
    typically the cover page or a small exhibit, and the revenue tables
    were never in our 25k-char window downstream.

    Strategy:
      1. Derive the filing directory from `edgar_url` (strip filename).
      2. Fetch the EDGAR auto-index page listing all files + sizes.
      3. Pick the .htm file with the biggest Content-Length (or the one
         whose name contains '10-k' / '10k' / 'annual').
    """
    from urllib.parse import urljoin

    # Derive directory from primary doc URL
    directory = edgar_url if edgar_url.endswith("/") else edgar_url.rsplit("/", 1)[0] + "/"

    try:
        idx = await client.get(
            directory,
            headers={"User-Agent": SEC_USER_AGENT},
            timeout=20,
            follow_redirects=True,
        )
    except Exception as e:
        logger.warning(f"10-K dir {directory}: {e}")
        return None
    if idx.status_code != 200:
        return None

    # EDGAR auto-index rows are 3 cells:
    #   [0] <a href="...">filename.htm</a>
    #   [1] "175785"   (size in bytes)
    #   [2] "2026-02-12 13:58:32"
    # Parse accordingly.
    soup = BeautifulSoup(idx.text, "html.parser")
    candidates: list[tuple[str, int]] = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        a = cells[0].find("a")
        if not a:
            continue
        name = a.get_text(strip=True) or a.get("href") or ""
        if not name.lower().endswith((".htm", ".html")):
            continue
        lname = name.lower()
        # Skip exhibits — we want the primary 10-K body, not an appendix.
        if (
            "index" in lname
            or "financial_report" in lname
            or "exhibit" in lname
            or "_ex" in lname
        ):
            continue
        # Size column (bytes).
        size_txt = cells[1].get_text(strip=True).replace(",", "")
        try:
            size = int(size_txt)
        except ValueError:
            size = 0
        candidates.append((name, size))

    if not candidates:
        # Fall back to old behavior
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith((".htm", ".html")) and "index" not in href.lower():
                candidates.append((href, 0))
                break
    if not candidates:
        return None

    # Prefer files with "10-k" or "10k" in the name; fall back to biggest.
    named = [(n, s) for n, s in candidates if "10-k" in n.lower() or "10k" in n.lower()]
    picked = max(named or candidates, key=lambda c: c[1])
    full = urljoin(directory, picked[0])

    try:
        doc = await client.get(
            full,
            headers={"User-Agent": SEC_USER_AGENT},
            timeout=60,
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
                        logger.info(f"drug_sales {f['ticker']}: empty 10-K body")
                        continue
                    excerpt = _extract_revenue_section(body_html)
                    if not excerpt:
                        logger.info(f"drug_sales {f['ticker']}: empty revenue section")
                        continue
                    try:
                        parsed = await _extract_with_claude(excerpt)
                    except _ClaudeCreditsExhausted:
                        # No point iterating the rest of the batch — every call
                        # will return the same 400. Break out and let the
                        # sync_log reflect whatever we got before the wall.
                        logger.warning(
                            "drug_sales aborting: Claude credits exhausted"
                        )
                        break
                    if not parsed:
                        logger.info(f"drug_sales {f['ticker']}: Claude returned no JSON")
                        continue
                    fy = parsed.get("fiscal_year")
                    drugs_list = parsed.get("drugs") or []
                    logger.info(
                        f"drug_sales {f['ticker']}: Claude parsed fy={fy}, "
                        f"drugs={len(drugs_list)}"
                    )
                    if not isinstance(fy, int):
                        continue
                    for d in drugs_list:
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
                    # Pace to stay under Anthropic Tier-1 rate limit
                    # (30k input tokens/min). Each ~7.5k-token call at
                    # 16s interval = 4 calls/min = 30k tokens/min exactly.
                    await asyncio.sleep(16)
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
