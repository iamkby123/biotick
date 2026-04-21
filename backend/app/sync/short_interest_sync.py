"""FINRA daily short-sale volume ingest.

FINRA publishes daily pipe-separated CSVs at:

    https://cdn.finra.org/equity/regsho/daily/CNMSshvol<YYYYMMDD>.txt
    https://cdn.finra.org/equity/regsho/daily/FNQCshvol<YYYYMMDD>.txt
    https://cdn.finra.org/equity/regsho/daily/FNRAshvol<YYYYMMDD>.txt
    https://cdn.finra.org/equity/regsho/daily/FNYXshvol<YYYYMMDD>.txt

Columns (pipe separated, header row + rows):
    Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market

We pull the last 14 trading days for each of the four Reg SHO tapes
(covers NASDAQ, NYSE ARCA, FINRA ADF, and OTC), filter to the tickers
we track in `companies`, and upsert.

Rate: one request per tape per day — trivial load.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.short_interest import ShortInterest
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

# The four Reg SHO tapes FINRA publishes. Names match their URL prefixes.
_TAPES = ["CNMS", "FNQC", "FNRA", "FNYX"]

_BASE = "https://cdn.finra.org/equity/regsho/daily"


def _business_days_back(n: int) -> list[date]:
    """Return last `n` weekdays (FINRA only publishes Mon-Fri)."""
    out: list[date] = []
    d = date.today() - timedelta(days=1)  # yesterday; today's file posts overnight
    while len(out) < n:
        if d.weekday() < 5:  # 0=Mon, 4=Fri
            out.append(d)
        d -= timedelta(days=1)
    return out


async def _fetch_tape(
    client: httpx.AsyncClient, tape: str, day: date
) -> list[dict] | None:
    url = f"{_BASE}/{tape}shvol{day:%Y%m%d}.txt"
    try:
        resp = await client.get(url, timeout=15)
    except Exception as e:
        logger.warning(f"fetch {url} failed: {e}")
        return None
    if resp.status_code == 404:
        # Holiday / no data for this date. Normal.
        return None
    if resp.status_code != 200:
        logger.warning(f"{url} returned {resp.status_code}")
        return None

    text = resp.text
    rows: list[dict] = []
    for i, line in enumerate(text.splitlines()):
        if i == 0 or not line.strip() or line.startswith("Date"):
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue
        try:
            rows.append(
                {
                    "report_date": datetime.strptime(parts[0], "%Y%m%d").date(),
                    "ticker": parts[1].strip().upper(),
                    "short_volume": float(parts[2]) if parts[2] else None,
                    "total_volume": float(parts[4]) if parts[4] else None,
                    "market": tape,
                }
            )
        except (ValueError, IndexError):
            continue
    return rows


async def sync_short_interest(db: AsyncSession, days: int = 14) -> int:
    """Sync the last `days` business-day short-sale volumes from FINRA."""
    log = SyncLog(sync_type="SHORT_INTEREST", started_at=datetime.utcnow(), status="RUNNING")
    db.add(log)
    await db.commit()

    try:
        # Known tickers — filter FINRA rows down so we don't insert junk.
        known = {
            t for (t,) in (
                await db.execute(select(Company.ticker))
            ).all()
        }

        total_rows = 0
        async with httpx.AsyncClient() as client:
            for day in _business_days_back(days):
                for tape in _TAPES:
                    rows = await _fetch_tape(client, tape, day)
                    if not rows:
                        continue
                    # Filter to our universe before burning DB work
                    rows = [r for r in rows if r["ticker"] in known]
                    if not rows:
                        continue

                    batch = 0
                    for r in rows:
                        try:
                            short_pct = None
                            if r["total_volume"] and r["total_volume"] > 0:
                                short_pct = float(r["short_volume"] or 0) / float(
                                    r["total_volume"]
                                )
                            async with db.begin_nested():
                                stmt = pg_upsert(ShortInterest).values(
                                    ticker=r["ticker"],
                                    report_date=r["report_date"],
                                    short_volume=r["short_volume"],
                                    total_volume=r["total_volume"],
                                    short_pct=short_pct,
                                    market=tape,
                                )
                                stmt = stmt.on_conflict_do_update(
                                    index_elements=["ticker", "report_date", "market"],
                                    set_={
                                        "short_volume": stmt.excluded.short_volume,
                                        "total_volume": stmt.excluded.total_volume,
                                        "short_pct": stmt.excluded.short_pct,
                                    },
                                )
                                await db.execute(stmt)
                            batch += 1
                            total_rows += 1
                            if batch % 100 == 0:
                                await db.commit()
                        except Exception as e:
                            logger.warning(f"short_interest row error {r}: {e}")
                            continue
                    await db.commit()
                    # Don't hammer — small pause between tape files
                    await asyncio.sleep(0.3)

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = total_rows
        await db.commit()
        logger.info(f"Short interest sync: {total_rows} rows")
        return total_rows

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Short interest sync failed: {e}")
        raise
