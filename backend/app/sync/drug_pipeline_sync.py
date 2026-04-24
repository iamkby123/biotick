"""Fill gaps in the `drugs` table by Claude-extracting pipelines from 10-K / 20-F.

The primary `drugs` ingest comes from matching ClinicalTrials.gov sponsors
to our companies table. That misses:
- Vaccines that aren't listed by brand (Moderna's COVID/flu/RSV programs)
- Early-stage preclinical programs that never enter ClinicalTrials.gov
- Pipeline programs under code names that differ from trial sponsor names

Strategy:
- Find companies with <5 drugs (undercount suspects) that have a 10-K or 20-F filed recently.
- Grab the pipeline section of the filing (anchors: "Pipeline", "Development Programs", "Product Portfolio").
- Ask Claude to return a structured list of {name, indication, phase, mechanism}.
- Upsert into the drugs table, generating a deterministic drug_id from ticker+name.

Rate-limited (16s pacing) for the same reason as drug_sales_sync: ~30k tokens / min budget.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SEC_USER_AGENT
from app.models.drug import Drug
from app.models.sync_log import SyncLog
from app.sync.drug_sales_sync import _fetch_10k_body

logger = logging.getLogger(__name__)


_SYSTEM = """You extract a biotech/pharma company's drug pipeline from SEC annual-report text (10-K or 20-F).

Return ONLY a JSON object:
{
  "drugs": [
    {
      "name": "<brand or development code, e.g. 'Spikevax' or 'mRNA-1345'>",
      "generic_name": "<INN / generic name, or null>",
      "indication": "<disease / condition, ≤80 chars>",
      "phase": "<one of: PRECLINICAL | PHASE_1 | PHASE_2 | PHASE_3 | FILED | APPROVED | MARKETED | DISCONTINUED>",
      "mechanism": "<mechanism of action, ≤120 chars>"
    },
    ...
  ]
}

Rules:
- Include the company's OWN programs — internal pipeline + marketed products.
- Skip: licensed-in candidates only mentioned in passing, competitor drugs, discontinued programs older than 2 years, platform technologies without a specific candidate.
- If a drug is marketed (commercial sales), phase = MARKETED.
- Include vaccines, monoclonal antibodies, cell therapies, gene therapies, small molecules, RNA therapeutics — anything the company is developing.
- Prefer brand names; fall back to development codes (e.g. "INCB-xxxxx") when that's all the filing provides.
- If you find nothing, return {"drugs": []}.
"""


_PIPELINE_ANCHORS = [
    "Pipeline",
    "Product Pipeline",
    "Development Programs",
    "Product Portfolio",
    "Pipeline Summary",
    "Clinical Programs",
    "Our Programs",
    "Our Pipeline",
    "Clinical Candidates",
    "Pipeline Overview",
]


_PHASE_NORMALIZE = {
    "preclinical": "PRECLINICAL",
    "phase 1": "PHASE_1", "phase1": "PHASE_1", "phase_1": "PHASE_1", "ph1": "PHASE_1", "phase i": "PHASE_1",
    "phase 1/2": "PHASE_2", "phase 2": "PHASE_2", "phase2": "PHASE_2", "phase_2": "PHASE_2", "ph2": "PHASE_2", "phase ii": "PHASE_2",
    "phase 2/3": "PHASE_3", "phase 3": "PHASE_3", "phase3": "PHASE_3", "phase_3": "PHASE_3", "ph3": "PHASE_3", "phase iii": "PHASE_3",
    "filed": "FILED", "submitted": "FILED",
    "approved": "APPROVED",
    "marketed": "MARKETED", "commercial": "MARKETED",
    "discontinued": "DISCONTINUED", "terminated": "DISCONTINUED",
}


def _extract_pipeline_section(html: str) -> str:
    """Return a ~30k-char slice of 10-K/20-F text likely to contain the pipeline.

    Pipeline sections are almost always in Item 1 "Business" — the FRONT of
    the 10-K, not the financial-statements back half like the revenue note.
    So we search the first two-thirds.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "img", "svg"]):
        t.decompose()
    text_doc = soup.get_text(separator="\n", strip=True)
    if not text_doc:
        return ""

    lowered = text_doc.lower()
    # Find first anchor in the first 2/3 of the doc
    best_idx = -1
    front_ceiling = int(len(text_doc) * 0.66)
    for a in _PIPELINE_ANCHORS:
        idx = lowered.find(a.lower(), 0, front_ceiling)
        if idx >= 0 and (best_idx < 0 or idx < best_idx):
            best_idx = idx

    if best_idx < 0:
        # Fallback: start of the doc (most pipelines are near the top of Item 1)
        best_idx = 0

    # 30k chars ~ 7.5k tokens. Same budget as drug_sales.
    return text_doc[best_idx : best_idx + 30_000]


async def _extract_with_claude(body_text: str) -> dict | None:
    """Call Claude, return parsed dict or None on any failure.

    Raises _ClaudeCreditsExhausted if credits run out; caller should abort.
    """
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
            max_tokens=3000,  # pipelines can have 20+ programs
            system=[
                {"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}
            ],
            messages=[
                {
                    "role": "user",
                    "content": f"Extract the drug pipeline from this annual-report excerpt:\n\n{body_text}",
                }
            ],
        )
    except Exception as e:
        err = str(e)
        if "credit balance is too low" in err:
            raise RuntimeError("CREDITS_EXHAUSTED") from e
        logger.warning(f"Claude pipeline call failed: {e}")
        return None

    blocks = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    raw = "".join(blocks).strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL)
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception as e:
            logger.warning(f"Claude pipeline JSON parse failed: {e}: {raw[:300]}")
    return None


def _normalize_phase(raw: str | None) -> str | None:
    if not raw:
        return None
    r = raw.strip().lower()
    for k, v in _PHASE_NORMALIZE.items():
        if k in r:
            return v
    if r in {"preclinical", "phase_1", "phase_2", "phase_3", "filed", "approved", "marketed", "discontinued"}:
        return r.upper()
    return None


def _make_drug_id(ticker: str, drug_name: str) -> str:
    """Deterministic drug_id per (ticker, drug_name). Prefixed with 'claude_'
    so it's obvious in the DB where the row came from."""
    h = hashlib.sha1(f"{ticker}|{drug_name.lower().strip()}".encode()).hexdigest()[:12]
    return f"claude_{ticker.lower()}_{h}"


async def _candidate_companies(db: AsyncSession, limit: int, min_market_cap: int) -> list[dict]:
    """Tickers with <5 drugs + a recent annual report (10-K or 20-F) + market cap."""
    rows = await db.execute(
        text(
            """
            SELECT DISTINCT ON (c.ticker)
                   c.ticker, c.market_cap, sf.edgar_url, sf.accession_number,
                   sf.filed_date, sf.filing_type
            FROM companies c
            JOIN sec_filings sf ON sf.ticker = c.ticker
            LEFT JOIN (
                SELECT company_ticker, COUNT(*) AS n
                FROM drugs
                GROUP BY company_ticker
            ) d ON d.company_ticker = c.ticker
            WHERE sf.filing_type IN ('10-K', '20-F')
              AND sf.edgar_url IS NOT NULL
              AND sf.filed_date > NOW() - INTERVAL '700 days'
              AND c.market_cap >= :min_cap
              AND COALESCE(d.n, 0) < 5
            ORDER BY c.ticker, sf.filed_date DESC
            LIMIT :lim
            """
        ),
        {"lim": limit, "min_cap": min_market_cap},
    )
    return [
        {
            "ticker": r[0],
            "edgar_url": r[2],
            "accession": r[3],
            "filed_date": r[4],
            "filing_type": r[5],
        }
        for r in rows.fetchall()
    ]


async def sync_drug_pipelines(
    db: AsyncSession,
    limit: int = 30,
    min_market_cap: int = 500_000_000,
) -> int:
    """Extract drug pipelines from 10-K / 20-F for companies with thin coverage."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY not set — skipping drug_pipelines sync")
        return 0

    log = SyncLog(sync_type="DRUG_PIPELINE", started_at=datetime.utcnow(), status="RUNNING")
    db.add(log)
    await db.commit()

    try:
        batch = await _candidate_companies(db, limit, min_market_cap)
        logger.info(f"drug_pipelines: {len(batch)} tickers to enrich")
        written = 0

        async with httpx.AsyncClient() as client:
            for f in batch:
                try:
                    body_html = await _fetch_10k_body(client, f["edgar_url"])
                    await asyncio.sleep(0.2)
                    if not body_html:
                        continue
                    excerpt = _extract_pipeline_section(body_html)
                    if not excerpt:
                        continue
                    try:
                        parsed = await _extract_with_claude(excerpt)
                    except RuntimeError:
                        logger.warning("drug_pipelines aborting: Claude credits exhausted")
                        break
                    if not parsed:
                        continue
                    drugs_list = parsed.get("drugs") or []
                    logger.info(
                        f"drug_pipelines {f['ticker']} ({f['filing_type']}): {len(drugs_list)} pipeline programs"
                    )
                    for d in drugs_list:
                        name = (d.get("name") or "").strip()
                        if not name or len(name) > 200:
                            continue
                        phase = _normalize_phase(d.get("phase"))
                        async with db.begin_nested():
                            stmt = pg_upsert(Drug).values(
                                drug_id=_make_drug_id(f["ticker"], name),
                                drug_name=name[:200],
                                company_ticker=f["ticker"],
                                generic_name=(d.get("generic_name") or None),
                                indication=(d.get("indication") or None),
                                mechanism=(d.get("mechanism") or None),
                                highest_phase=phase,
                                status="ACTIVE" if phase != "DISCONTINUED" else "DISCONTINUED",
                                updated_at=datetime.utcnow(),
                            )
                            stmt = stmt.on_conflict_do_update(
                                index_elements=["drug_id"],
                                set_={
                                    "indication": stmt.excluded.indication,
                                    "mechanism": stmt.excluded.mechanism,
                                    "highest_phase": stmt.excluded.highest_phase,
                                    "generic_name": stmt.excluded.generic_name,
                                    "status": stmt.excluded.status,
                                    "updated_at": datetime.utcnow(),
                                },
                            )
                            await db.execute(stmt)
                        written += 1
                    await db.commit()
                    # Anthropic Tier-1 pacing
                    await asyncio.sleep(16)
                except Exception as e:
                    logger.warning(
                        f"drug_pipelines {f.get('ticker')} {f.get('accession')}: {e}"
                    )
                    continue

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = written
        await db.commit()
        logger.info(f"drug_pipelines: {written} drugs written")
        return written

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"drug_pipelines sync failed: {e}")
        raise
