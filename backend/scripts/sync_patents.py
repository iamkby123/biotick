"""
Sync USPTO patents for biotech companies using the PatentsView API.

For each company in the ``companies`` table, we:

    1. Build a list of cleaned-name variations to search on.
    2. POST to https://api.patentsview.org/patents/query with
       ``assignee_organization`` filters.
    3. Take the top 50 most-recent patents.
    4. Compute a naive expiration date (grant + 20 years for utility patents
       when a value is not returned directly — a sensible default used by USPTO
       term calculators).
    5. Upsert into the ``patents`` table.

Run standalone::

    cd backend
    python -m scripts.sync_patents
    # or limit to specific tickers
    python scripts/sync_patents.py MRNA VRTX

Requires SUPABASE_DB_PASSWORD. PatentsView keys are optional (free public API).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.database import async_session  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.patent import Patent  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


PATENTSVIEW_URL = "https://api.patentsview.org/patents/query"
API_KEY = os.environ.get("PATENTSVIEW_API_KEY", "")

PER_COMPANY_LIMIT = 50
REQUEST_TIMEOUT = 60


# ── Name normalization ─────────────────────────────────────────────────────

_CORP_SUFFIXES = [
    "incorporated", "inc", "corporation", "corp", "co",
    "company", "ltd", "plc", "holdings", "holding",
    "group", "nv", "sa", "ag",
]


def _name_variations(name: str) -> list[str]:
    """Return a small set of assignee-name variations to query for."""
    if not name:
        return []
    base = name.strip()
    lower = base.lower()
    stripped = lower
    for suffix in _CORP_SUFFIXES:
        stripped = re.sub(rf"\b{suffix}\.?\b", "", stripped)
    stripped = re.sub(r"[,.]", "", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    variants = {base, base.lower(), stripped}
    # Keep only sufficiently-specific names; 1–2 generic words like
    # "bio" will explode the result set.
    return [v for v in variants if v and len(v) >= 4]


# ── API ────────────────────────────────────────────────────────────────────

_PATENTSVIEW_FIELDS = [
    "patent_number",
    "patent_title",
    "patent_abstract",
    "patent_type",
    "patent_date",                   # grant date
    "app_date",                      # filing (application) date
    "assignee_organization",
    "assignee_id",
]


async def _query_patents(
    client: httpx.AsyncClient, name_variants: list[str]
) -> list[dict]:
    if not name_variants:
        return []
    query = {"_or": [{"assignee_organization": v} for v in name_variants]}
    body = {
        "q": query,
        "f": _PATENTSVIEW_FIELDS,
        "s": [{"patent_date": "desc"}],
        "o": {"per_page": PER_COMPANY_LIMIT, "page": 1},
    }
    headers = {"Accept": "application/json"}
    if API_KEY:
        headers["X-Api-Key"] = API_KEY
    try:
        resp = await client.post(
            PATENTSVIEW_URL, json=body, headers=headers, timeout=REQUEST_TIMEOUT
        )
    except Exception as e:
        logger.warning(f"PatentsView request failed: {e}")
        return []
    if resp.status_code != 200:
        logger.warning(
            f"PatentsView returned {resp.status_code} for "
            f"{name_variants[:2]} — {resp.text[:180]}"
        )
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    return data.get("patents") or []


# ── Parsing ────────────────────────────────────────────────────────────────

def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _pick_assignee(patent: dict) -> str | None:
    # PatentsView can return multiple assignees per patent.
    assignees = patent.get("assignees") or []
    if assignees and isinstance(assignees, list):
        return (assignees[0] or {}).get("assignee_organization") or None
    return patent.get("assignee_organization") or None


def _expiration_date(grant_date: date | None, filing_date: date | None,
                     patent_type: str | None) -> date | None:
    """Naive USPTO expiration: filing + 20 years for utility patents."""
    ref = filing_date or grant_date
    if not ref:
        return None
    ptype = (patent_type or "").lower()
    years = 14 if "design" in ptype else 20
    try:
        return ref.replace(year=ref.year + years)
    except ValueError:
        # Handle leap-day filings by backing off one day.
        return ref.replace(year=ref.year + years, day=28) + timedelta(days=2)


# ── Upsert ─────────────────────────────────────────────────────────────────

async def _upsert_patents(
    db: AsyncSession, ticker: str, patents: list[dict]
) -> int:
    count = 0
    for p in patents:
        number = (p.get("patent_number") or "").strip()
        if not number:
            continue
        grant = _parse_date(p.get("patent_date"))
        app_date = _parse_date(p.get("app_date") or (p.get("applications", [{}])[0].get("app_date") if p.get("applications") else None))
        ptype = p.get("patent_type")

        values = {
            "patent_number": number,
            "title": (p.get("patent_title") or "").strip() or None,
            "assignee_name": _pick_assignee(p),
            "company_ticker": ticker,
            "filing_date": app_date,
            "grant_date": grant,
            "expiration_date": _expiration_date(grant, app_date, ptype),
            "abstract": (p.get("patent_abstract") or "").strip() or None,
            "patent_type": ptype,
        }
        stmt = pg_upsert(Patent).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Patent.patent_number],
            set_={
                "title": stmt.excluded.title,
                "assignee_name": stmt.excluded.assignee_name,
                "company_ticker": stmt.excluded.company_ticker,
                "filing_date": stmt.excluded.filing_date,
                "grant_date": stmt.excluded.grant_date,
                "expiration_date": stmt.excluded.expiration_date,
                "abstract": stmt.excluded.abstract,
                "patent_type": stmt.excluded.patent_type,
            },
        )
        await db.execute(stmt)
        count += 1
    await db.commit()
    return count


# ── Orchestrator ───────────────────────────────────────────────────────────

async def sync_company_patents(
    client: httpx.AsyncClient, db: AsyncSession, company: Company
) -> int:
    variants = _name_variations(company.name)
    if not variants:
        return 0
    logger.info(f"{company.ticker}: searching patents by {variants}")
    patents = await _query_patents(client, variants)
    if not patents:
        logger.info(f"{company.ticker}: no patents returned")
        return 0
    count = await _upsert_patents(db, company.ticker, patents)
    logger.info(f"{company.ticker}: upserted {count} patents")
    return count


async def main(ticker_filter: list[str] | None = None) -> None:
    async with httpx.AsyncClient() as client:
        async with async_session() as db:
            query = select(Company)
            if ticker_filter:
                query = query.where(
                    Company.ticker.in_([t.upper() for t in ticker_filter])
                )
            result = await db.execute(query)
            companies = result.scalars().all()
            logger.info(f"Syncing patents for {len(companies)} companies")

            totals: dict[str, int] = {}
            for i, company in enumerate(companies):
                try:
                    totals[company.ticker] = await sync_company_patents(
                        client, db, company
                    )
                except Exception as e:
                    logger.error(f"{company.ticker} failed: {e}")
                    totals[company.ticker] = 0
                # PatentsView free tier: be polite.
                await asyncio.sleep(0.3 if API_KEY else 1.0)

            logger.info(
                f"Done. Total patents upserted: {sum(totals.values())} "
                f"across {len(companies)} companies"
            )


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(main(args or None))
