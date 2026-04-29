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
    # Use `created_at` (when WE ingested the row) rather than the
    # source document's date — that's what "freshness" actually means
    # for a user. A patent filed in 2018 but ingested today shouldn't
    # show as 8 years stale.
    # All queries fall back to `created_at` (when our pipeline inserted
    # the row) when the source-document date is a DATE-only column with
    # no time component. Otherwise "freshness" sticks at midnight UTC of
    # the filing day rather than reflecting when we ingested.
    queries: dict[str, str] = {
        "news":          "SELECT MAX(GREATEST(published_at, created_at)) FROM news_items",
        "press":         "SELECT MAX(created_at) FROM press_releases",
        "deals":         "SELECT MAX(created_at) FROM deals",
        "insider":       "SELECT MAX(created_at) FROM insider_trades",
        "filings":       "SELECT MAX(created_at) FROM sec_filings",
        "prices":        "SELECT MAX(updated_at) FROM companies WHERE updated_at IS NOT NULL",
        "short_interest":"SELECT MAX(created_at) FROM short_interest",
        "congress":      "SELECT MAX(created_at) FROM congress_trades",
        "patents":       "SELECT MAX(created_at) FROM patents",
        "adcom":         "SELECT MAX(created_at) FROM adcom_meetings",
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
