"""Extract press releases + deals from 8-K filings.

Pipeline:
  1. Query `sec_filings` for 8-K rows we haven't processed yet.
  2. For each, fetch the filing index at the `edgar_url` to enumerate
     attached documents.
  3. Classify the 8-K by Item code (1.01 / 2.01 / 2.02 / 5.02 / 7.01 / 8.01).
  4. Download any Ex-99 attachments (press releases) and strip HTML
     into plain-text body + headline.
  5. Items 7.01, 8.01, 2.02 -> press_releases table.
     Items 1.01, 2.01, 5.02 -> deals table (with counterparty regex).
  6. If ANTHROPIC_API_KEY is set, call Claude with cached system prompt
     to produce a 2-sentence summary. Otherwise skip summaries.

The pipeline is idempotent via UNIQUE(accession_number). Re-running is
safe — already-processed filings are skipped by a FROM-NOT-EXISTS check.
"""

import asyncio
import logging
import os
import re
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from app.config import SEC_USER_AGENT
from app.models.eight_k import Deal, PressRelease
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

# Item code -> (table, deal_type). Items we don't handle are ignored.
_PRESS_RELEASE_ITEMS = {"2.02", "7.01", "8.01"}
_DEAL_ITEMS = {
    "1.01": "material_agreement",
    "2.01": "acquisition",
    "5.02": "officer_change",
}

_ITEM_CODE_RE = re.compile(r"Item\s+(\d+\.\d+)", re.IGNORECASE)
_COUNTERPARTY_RE = re.compile(
    r"\b(?:with|from|to|between [\w\s\.,]+ and|by and (?:between|among))\s+"
    r"([A-Z][A-Za-z0-9 &.,\-]{2,60?}(?:Inc|Corp|Corporation|Ltd|LLC|LP|Pharmaceuticals|Therapeutics|Biosciences)\.?)",
    re.IGNORECASE,
)


# ─── Claude summary (optional) ──────────────────────────────────────────

_SUMMARY_SYSTEM_PROMPT = """You summarize biotech SEC 8-K press releases in exactly two sentences.

Rules:
- Sentence 1: what happened (be specific — drug name, trial phase, outcome, counterparty, dollar amount).
- Sentence 2: why it matters to investors (stock-relevant angle).
- No hype, no "the company announced that". Lead with the news.
- If the filing contains no substantive news (routine, ceremonial), reply with just "Administrative filing.".
- Keep each sentence <= 35 words.
"""

# Set to True once we observe a "credit balance too low" 400 from the
# Anthropic API. Once tripped, we stop calling Claude for the rest of
# the process lifetime — no point burning HTTP round-trips to get the
# same 400 back for every filing. Reset requires a process restart.
_claude_credits_exhausted = False


async def _maybe_summarize(body: str, headline: str) -> str | None:
    """Call Claude for a 2-sentence summary. Returns None if no key set or error."""
    global _claude_credits_exhausted
    if _claude_credits_exhausted:
        return None
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key or not body:
        return None
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        logger.warning("anthropic package not installed; skipping summaries")
        return None

    client = AsyncAnthropic(api_key=key)
    # Cap input to 6k chars (roughly 1.5k tokens) — most press releases
    # have the news in the first paragraph anyway.
    excerpt = body[:6000]
    try:
        msg = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=180,
            system=[
                {
                    "type": "text",
                    "text": _SUMMARY_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": f"Headline: {headline}\n\nBody:\n{excerpt}",
                }
            ],
        )
        blocks = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
        return ("".join(blocks).strip() or None)
    except Exception as e:
        err = str(e)
        if "credit balance is too low" in err or "insufficient_quota" in err.lower():
            _claude_credits_exhausted = True
            logger.warning(
                "Claude credit balance exhausted — disabling summaries for "
                "the rest of this process. Add credits at console.anthropic.com."
            )
        else:
            logger.warning(f"Claude summary failed: {e}")
        return None


# ─── EDGAR fetchers ──────────────────────────────────────────────────────


def _derive_directory(edgar_url: str) -> str:
    """sec_filings.edgar_url points to the primary 8-K HTML doc, not the
    filing index. Strip the filename to get the directory URL which
    EDGAR serves as an auto-index page listing every file in the filing."""
    if edgar_url.endswith("/"):
        return edgar_url
    # https://.../000119312526164330/d120122d8k.htm  -> ...000119312526164330/
    return edgar_url.rsplit("/", 1)[0] + "/"


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        resp = await client.get(
            url,
            headers={"User-Agent": SEC_USER_AGENT},
            timeout=20,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception as e:
        logger.warning(f"fetch {url}: {e}")
        return None


async def _fetch_index(client: httpx.AsyncClient, edgar_url: str) -> str | None:
    """Fetch the directory-listing HTML for a filing. Takes the primary-doc
    URL and derives the directory URL which EDGAR auto-indexes."""
    directory = _derive_directory(edgar_url)
    return await _fetch_text(client, directory)


def _find_exhibits(html: str, base_url: str) -> list[dict]:
    """Given the filing directory HTML (EDGAR auto-index), return
    [{name, href}] for the main 8-K doc + Ex-99 attachments. The directory
    index lists every filename with a link; we match by filename."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith((".htm", ".html", ".txt")):
            continue
        name = a.get_text(strip=True) or href.rsplit("/", 1)[-1]
        fname = href.rsplit("/", 1)[-1].lower()
        # Match: 8-k bodies (d*-8k.htm, form8-k.htm, *8k*.htm, *aldx-*.htm
        # where 8-K tickers appear), OR exhibit 99.1/99.2 attachments.
        if (
            "8k" in fname
            or "8-k" in fname
            or "ex99" in fname
            or "ex-99" in fname
            or "exhibit" in fname
            or "exhibit99" in fname
        ):
            out.append({"name": name or fname, "href": urljoin(base_url, href)})
    return out


async def _fetch_and_clean(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    """Return (headline, body_text) from a document URL. Both can be empty strings."""
    try:
        resp = await client.get(
            url,
            headers={"User-Agent": SEC_USER_AGENT},
            timeout=25,
            follow_redirects=True,
        )
    except Exception as e:
        logger.warning(f"fetch exhibit {url}: {e}")
        return "", ""
    if resp.status_code != 200:
        return "", ""
    soup = BeautifulSoup(resp.text, "html.parser")
    # Strip script/style/images
    for t in soup(["script", "style", "img"]):
        t.decompose()
    headline = ""
    if soup.title and soup.title.get_text(strip=True):
        headline = soup.title.get_text(strip=True)
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        headline = h1.get_text(strip=True)
    body_text = soup.get_text(separator="\n", strip=True)
    # Collapse huge whitespace runs
    body_text = re.sub(r"\n{3,}", "\n\n", body_text)
    return headline[:500], body_text[:20000]


# ─── Core sync ───────────────────────────────────────────────────────────


async def _unprocessed_8ks(db: AsyncSession, limit: int) -> list[dict]:
    """8-K rows that aren't yet in press_releases OR deals."""
    rows = await db.execute(
        text("""
            SELECT sf.accession_number, sf.ticker, sf.edgar_url, sf.filed_date
            FROM sec_filings sf
            WHERE sf.filing_type = '8-K'
              AND sf.edgar_url IS NOT NULL
              AND sf.filed_date > NOW() - INTERVAL '60 days'
              AND NOT EXISTS (
                SELECT 1 FROM press_releases pr WHERE pr.accession_number = sf.accession_number
              )
              AND NOT EXISTS (
                SELECT 1 FROM deals d WHERE d.accession_number = sf.accession_number
              )
            ORDER BY sf.filed_date DESC
            LIMIT :lim
        """),
        {"lim": limit},
    )
    return [
        {"accession": r[0], "ticker": r[1], "edgar_url": r[2], "filed_date": r[3]}
        for r in rows.fetchall()
    ]


def _extract_item_codes(body: str) -> set[str]:
    return {m.group(1) for m in _ITEM_CODE_RE.finditer(body or "")}


def _extract_counterparty(body: str) -> str | None:
    if not body:
        return None
    m = _COUNTERPARTY_RE.search(body)
    return m.group(1).strip() if m else None


async def sync_eight_k_pipeline(db: AsyncSession, limit: int = 100) -> int:
    """Process up to `limit` unprocessed 8-Ks and emit press_releases / deals."""
    log = SyncLog(sync_type="EIGHT_K_PIPELINE", started_at=datetime.utcnow(), status="RUNNING")
    db.add(log)
    await db.commit()

    try:
        batch = await _unprocessed_8ks(db, limit)
        logger.info(f"8-K pipeline: {len(batch)} filings to process")
        written = 0

        async with httpx.AsyncClient() as client:
            for f in batch:
                try:
                    # Step 1: fetch the filing's directory index
                    html = await _fetch_index(client, f["edgar_url"])
                    await asyncio.sleep(0.15)

                    # Step 2: always treat the primary edgar_url as the main
                    # 8-K doc (it IS one by construction — sec_filings stores
                    # the primary-doc link). Additionally scan the directory
                    # listing for Ex-99 press-release attachments.
                    main_doc = {
                        "name": f["edgar_url"].rsplit("/", 1)[-1],
                        "href": f["edgar_url"],
                    }
                    pr_docs: list[dict] = []
                    if html:
                        for e in _find_exhibits(html, _derive_directory(f["edgar_url"])):
                            fname = e["href"].rsplit("/", 1)[-1].lower()
                            if "ex99" in fname or "ex-99" in fname or "exhibit99" in fname:
                                pr_docs.append(e)

                    item_codes: set[str] = set()
                    if main_doc:
                        _, main_body = await _fetch_and_clean(client, main_doc["href"])
                        await asyncio.sleep(0.15)
                        item_codes = _extract_item_codes(main_body)
                    press_release_wanted = bool(item_codes & _PRESS_RELEASE_ITEMS)
                    deal_item = next(
                        (c for c in item_codes if c in _DEAL_ITEMS), None
                    )

                    if not (press_release_wanted or deal_item):
                        # Filing has nothing we care about. Skip.
                        continue

                    # Step 4: take the first Ex-99 as the PR body (most filings
                    # have one main press release; merging multiples adds noise).
                    pr_headline = ""
                    pr_body = ""
                    pr_url = ""
                    if pr_docs:
                        pr_headline, pr_body = await _fetch_and_clean(
                            client, pr_docs[0]["href"]
                        )
                        pr_url = pr_docs[0]["href"]
                        await asyncio.sleep(0.15)
                    elif main_doc:
                        pr_headline, pr_body = await _fetch_and_clean(
                            client, main_doc["href"]
                        )
                        pr_url = main_doc["href"]
                        await asyncio.sleep(0.15)

                    if not pr_body:
                        continue

                    # Step 5: optional Claude summary
                    summary = await _maybe_summarize(pr_body, pr_headline)

                    # Step 6: dispatch to press_releases / deals
                    if press_release_wanted:
                        async with db.begin_nested():
                            stmt = pg_upsert(PressRelease).values(
                                accession_number=f["accession"],
                                ticker=f["ticker"],
                                headline=pr_headline or None,
                                body_text=pr_body,
                                summary=summary,
                                url=pr_url or None,
                                filed_date=f["filed_date"],
                                item_code=next(iter(item_codes & _PRESS_RELEASE_ITEMS), None),
                            )
                            stmt = stmt.on_conflict_do_update(
                                index_elements=["accession_number"],
                                set_={
                                    "headline": stmt.excluded.headline,
                                    "body_text": stmt.excluded.body_text,
                                    "summary": stmt.excluded.summary,
                                    "url": stmt.excluded.url,
                                    "item_code": stmt.excluded.item_code,
                                },
                            )
                            await db.execute(stmt)
                        written += 1

                    if deal_item:
                        counterparty = _extract_counterparty(pr_body)
                        async with db.begin_nested():
                            stmt = pg_upsert(Deal).values(
                                accession_number=f["accession"],
                                ticker=f["ticker"],
                                deal_type=_DEAL_ITEMS[deal_item],
                                counterparty=counterparty,
                                headline=pr_headline or None,
                                body_text=pr_body,
                                summary=summary,
                                url=pr_url or None,
                                filed_date=f["filed_date"],
                                item_code=deal_item,
                            )
                            stmt = stmt.on_conflict_do_update(
                                index_elements=["accession_number"],
                                set_={
                                    "deal_type": stmt.excluded.deal_type,
                                    "counterparty": stmt.excluded.counterparty,
                                    "headline": stmt.excluded.headline,
                                    "body_text": stmt.excluded.body_text,
                                    "summary": stmt.excluded.summary,
                                    "url": stmt.excluded.url,
                                    "item_code": stmt.excluded.item_code,
                                },
                            )
                            await db.execute(stmt)
                        written += 1

                    await db.commit()
                except Exception as e:
                    logger.warning(f"8-K {f.get('accession')}: {e}")
                    continue

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = written
        await db.commit()
        logger.info(f"8-K pipeline: {written} rows written across press_releases + deals")
        return written

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"8-K pipeline failed: {e}")
        raise
