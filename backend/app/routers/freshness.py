"""How fresh is each data source?

Returns the most-recent row timestamp per major data category so the
frontend can show "Updated 4 min ago" badges. This is what tells the
user the site is alive.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(prefix="/api/freshness", tags=["freshness"])


@router.get("")
async def freshness(db: AsyncSession = Depends(get_db)):
    """Return ISO-formatted "last updated" timestamps for each data
    source we surface in the UI.

    These come from each source's most-recent row — they reflect when
    the latest *event* occurred (not when the sync ran). For news that
    means "the most recent article we've ingested"; for prices it
    means "the latest market quote refresh"; etc.
    """
    queries: dict[str, str] = {
        "news":          "SELECT MAX(published_at) FROM news_items",
        "press":         "SELECT MAX(filed_date::timestamp) FROM press_releases",
        "deals":         "SELECT MAX(filed_date::timestamp) FROM deals",
        "insider":       "SELECT MAX(transaction_date::timestamp) FROM insider_trades",
        "filings":       "SELECT MAX(filed_date::timestamp) FROM sec_filings",
        "prices":        "SELECT MAX(updated_at) FROM companies WHERE updated_at IS NOT NULL",
        "short_interest":"SELECT MAX(report_date::timestamp) FROM short_interest",
        "congress":      "SELECT MAX(filing_date::timestamp) FROM congress_trades",
        "patents":       "SELECT MAX(filing_date::timestamp) FROM patents",
        "adcom":         "SELECT MAX(meeting_date::timestamp) FROM adcom_meetings",
    }
    out: dict[str, str | None] = {}
    for key, sql in queries.items():
        try:
            ts = (await db.execute(text(sql))).scalar()
            out[key] = ts.isoformat() if ts else None
        except Exception:
            out[key] = None

    # Latest sync_log run per sync_type for the "last refreshed" badge
    sync_rows = (await db.execute(
        text("""
            SELECT sync_type, MAX(completed_at) AS last
            FROM sync_log
            WHERE status='COMPLETED'
              AND completed_at > NOW() - INTERVAL '7 days'
            GROUP BY sync_type
        """)
    )).fetchall()
    out["last_sync"] = {r[0]: r[1].isoformat() for r in sync_rows if r[1]}

    return out
