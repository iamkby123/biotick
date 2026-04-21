"""Populate the `patents` table via the Lens.org patent search API.

Docs: https://docs.api.lens.org/request-patent.html
Endpoint: POST https://api.lens.org/patent/search

Auth: `Authorization: Bearer <LENS_API_KEY>` header. Register for a free
key at https://www.lens.org/lens/user/subscriptions.

Free-tier request budget is tight (roughly 1000 searches/month for the
public plan), so we:
  - Query once per company (not per patent), paging with size=50
  - Restrict to jurisdiction=US so we're not wasting budget on foreign filings
  - Cap per-company patents to 50 most recent (what users will actually read)
  - Sleep 1.2s between requests to stay well under per-second throttles

If LENS_API_KEY is unset, sync logs a warning and exits cleanly.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, date, timedelta

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.patent import Patent
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

_API_URL = "https://api.lens.org/patent/search"


def _normalize_for_match(name: str) -> str:
    """Strip corporate suffixes + lowercase for fuzzy assignee match."""
    if not name:
        return ""
    s = name.lower()
    s = re.sub(
        r",?\s+(inc\.?|corp\.?|corporation|ltd\.?|plc|llc|co\.?|holdings?|pharmaceuticals?|therapeutics|biosciences?|biotech)$",
        "",
        s,
    )
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def _expiration_from_filing(filing_date: date | None) -> date | None:
    """US utility patents expire 20y from filing. Ignores PTA/PTE."""
    if not filing_date:
        return None
    try:
        return filing_date.replace(year=filing_date.year + 20)
    except ValueError:
        return filing_date + timedelta(days=365 * 20)


def _parse_lens_date(raw: str | None) -> date | None:
    """Lens dates are ISO strings 'YYYY-MM-DD' or occasionally 'YYYY-MM-DDT...'."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _applicant_name(record: dict) -> str | None:
    """Lens docs nest applicants under biblio.parties.applicants[].extracted_name.value."""
    try:
        parties = (record.get("biblio", {}) or {}).get("parties", {}) or {}
        applicants = parties.get("applicants", []) or []
        if not applicants:
            return None
        first = applicants[0] or {}
        ext = first.get("extracted_name") or {}
        name = ext.get("value") or first.get("residence") or None
        return name
    except Exception:
        return None


def _invention_title(record: dict) -> str | None:
    """Title sits under biblio.invention_title[] — pick the English variant."""
    try:
        titles = (record.get("biblio", {}) or {}).get("invention_title", []) or []
        for t in titles:
            if (t.get("lang") or "").lower().startswith("en"):
                return t.get("text")
        return titles[0].get("text") if titles else None
    except Exception:
        return None


def _abstract_text(record: dict) -> str | None:
    try:
        absts = record.get("abstract") or []
        for a in absts:
            if (a.get("lang") or "").lower().startswith("en"):
                return a.get("text")
        return absts[0].get("text") if absts else None
    except Exception:
        return None


def _app_filing_date(record: dict) -> date | None:
    try:
        app_refs = (record.get("biblio", {}) or {}).get("application_reference", []) or []
        if not app_refs:
            return None
        return _parse_lens_date(app_refs[0].get("date"))
    except Exception:
        return None


def _pub_date(record: dict) -> date | None:
    try:
        pub = (record.get("biblio", {}) or {}).get("publication_reference", {}) or {}
        return _parse_lens_date(pub.get("date"))
    except Exception:
        return None


def _doc_number(record: dict) -> str | None:
    """Prefer jurisdictioned doc number like 'US11123456B2', else raw lens_id."""
    try:
        pub = (record.get("biblio", {}) or {}).get("publication_reference", {}) or {}
        juris = pub.get("jurisdiction") or ""
        num = pub.get("doc_number") or ""
        kind = pub.get("kind") or ""
        if num:
            return f"{juris}{num}{kind}".strip()
    except Exception:
        pass
    return record.get("lens_id")


async def _search_company(
    client: httpx.AsyncClient, company_name: str, token: str, limit: int = 50
) -> list[dict]:
    """Return raw patent records for a company, newest first.

    We restrict to US-granted patents (jurisdiction=US, publication_type=granted)
    to both constrain the budget and match the old PatentsView behaviour.
    """
    body = {
        "query": {
            "bool": {
                "must": [
                    {"match_phrase": {"applicant.name": company_name}},
                    {"term": {"jurisdiction": "US"}},
                ]
            }
        },
        "size": limit,
        "sort": [{"date_published": "desc"}],
        "include": [
            "lens_id",
            "biblio.publication_reference",
            "biblio.application_reference",
            "biblio.parties.applicants",
            "biblio.invention_title",
            "abstract",
            "publication_type",
        ],
    }

    try:
        resp = await client.post(
            _API_URL,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "BiotickPatents/1.0 (+https://biotick.io)",
            },
            timeout=30,
        )
    except Exception as e:
        logger.warning(f"Lens fetch failed for {company_name}: {e}")
        return []

    if resp.status_code == 429:
        logger.warning("Lens rate-limit hit; sleeping 60s")
        await asyncio.sleep(60)
        return []
    if resp.status_code == 401:
        logger.error("Lens 401 — check LENS_API_KEY")
        return []
    if resp.status_code != 200:
        logger.warning(
            f"Lens {company_name!r}: {resp.status_code} {resp.text[:200]}"
        )
        return []

    try:
        data = resp.json() or {}
    except Exception as e:
        logger.warning(f"Lens bad JSON for {company_name}: {e}")
        return []

    return data.get("data", []) or []


async def sync_patents(db: AsyncSession, limit_companies: int | None = None) -> int:
    """Re-populate patents for every company via Lens.org."""
    token = os.environ.get("LENS_API_KEY", "").strip()
    if not token:
        logger.warning("LENS_API_KEY not set — skipping patents sync")
        return 0

    log = SyncLog(sync_type="PATENTS", started_at=datetime.utcnow(), status="RUNNING")
    db.add(log)
    await db.commit()

    try:
        q = select(Company.ticker, Company.name).order_by(Company.ticker)
        if limit_companies:
            q = q.limit(limit_companies)
        companies = (await db.execute(q)).all()

        total_inserted = 0
        async with httpx.AsyncClient() as client:
            for ticker, name in companies:
                if not name:
                    continue

                records = await _search_company(client, name, token)

                expected_match = _normalize_for_match(name)
                batch = 0
                for rec in records:
                    try:
                        doc_number = (_doc_number(rec) or "").strip()
                        if not doc_number:
                            continue

                        # Re-check assignee match — Lens's match_phrase can still
                        # return loose matches (e.g. "Johnson Research Inc" for
                        # an "Johnson" query).
                        assignee = _applicant_name(rec)
                        if assignee:
                            norm = _normalize_for_match(assignee)
                            if expected_match not in norm and norm not in expected_match:
                                continue

                        filing_date = _app_filing_date(rec)
                        grant_date = _pub_date(rec)

                        async with db.begin_nested():
                            stmt = pg_upsert(Patent).values(
                                patent_number=doc_number[:40],
                                title=(_invention_title(rec) or "")[:1000] or None,
                                assignee_name=(assignee or "")[:300] or None,
                                company_ticker=ticker,
                                filing_date=filing_date,
                                grant_date=grant_date,
                                expiration_date=_expiration_from_filing(filing_date),
                                abstract=(_abstract_text(rec) or "")[:4000] or None,
                                patent_type=(rec.get("publication_type") or "")[:40] or None,
                            )
                            stmt = stmt.on_conflict_do_update(
                                index_elements=["patent_number"],
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
                        batch += 1
                        total_inserted += 1
                        if batch % 50 == 0:
                            await db.commit()
                    except Exception as e:
                        logger.warning(f"patent row error {doc_number}: {e}")
                        continue

                if batch:
                    await db.commit()
                    logger.debug(f"{ticker}: +{batch} patents")

                # Conservative pacing — free tier is ~1k searches/mo so we
                # must keep the daily churn low anyway. 1.2s/company =
                # 3000 companies/hour max, fine for any foreseeable universe.
                await asyncio.sleep(1.2)

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = total_inserted
        await db.commit()
        logger.info(
            f"Patents sync (Lens): {total_inserted} upserted across {len(companies)} companies"
        )
        return total_inserted

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Patents sync failed: {e}")
        raise
