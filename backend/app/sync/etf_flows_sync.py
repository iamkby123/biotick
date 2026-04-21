"""Daily ETF flow snapshot.

We track four biotech ETFs: XBI, IBB, LABU, SBIO. For each, we snapshot
shares-outstanding + AUM once per day and compute the delta vs. the
previous snapshot — creations (positive delta) imply net money in,
redemptions (negative) imply money out.

Data source: Finnhub's /etf/profile?symbol=... endpoint (free tier has
ETF profile data, though not intraday).
"""

import asyncio
import logging
import os
from datetime import date, datetime

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.etf_flow import ETFFlowDaily
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

_BASE = "https://finnhub.io/api/v1"
_ETFS = ["XBI", "IBB", "LABU", "SBIO"]


def _key() -> str:
    return os.environ.get("FINNHUB_API_KEY", "").strip()


async def _fetch_profile(client: httpx.AsyncClient, ticker: str) -> dict | None:
    try:
        resp = await client.get(
            f"{_BASE}/etf/profile",
            params={"symbol": ticker, "token": _key()},
            timeout=15,
        )
    except Exception as e:
        logger.warning(f"ETF profile fetch failed {ticker}: {e}")
        return None
    if resp.status_code == 429:
        logger.warning("Finnhub 429, sleeping 60s")
        await asyncio.sleep(60)
        return None
    if resp.status_code != 200:
        logger.warning(f"ETF profile {ticker}: {resp.status_code} {resp.text[:200]}")
        return None
    try:
        return resp.json() or {}
    except Exception:
        return None


async def _fetch_quote(client: httpx.AsyncClient, ticker: str) -> dict | None:
    """NAV proxy — use last-close quote."""
    try:
        resp = await client.get(
            f"{_BASE}/quote",
            params={"symbol": ticker, "token": _key()},
            timeout=15,
        )
    except Exception as e:
        logger.warning(f"quote {ticker}: {e}")
        return None
    if resp.status_code != 200:
        return None
    try:
        return resp.json() or {}
    except Exception:
        return None


async def sync_etf_flows(db: AsyncSession) -> int:
    """Snapshot all four biotech ETFs and compute deltas."""
    if not _key():
        logger.warning("FINNHUB_API_KEY not set — skipping etf_flows sync")
        return 0

    log = SyncLog(sync_type="ETF_FLOWS", started_at=datetime.utcnow(), status="RUNNING")
    db.add(log)
    await db.commit()

    try:
        today = date.today()
        rows_written = 0

        async with httpx.AsyncClient() as client:
            for t in _ETFS:
                profile = await _fetch_profile(client, t)
                await asyncio.sleep(1.05)
                quote = await _fetch_quote(client, t)
                await asyncio.sleep(1.05)

                # Finnhub ETF profile field names (vary by tier — free tier
                # often has profile endpoint returning empty {}). Fall back
                # to /quote for NAV which definitely works on free tier.
                profile = profile or {}
                nested = profile.get("profile") if isinstance(profile.get("profile"), dict) else profile

                shares = (
                    nested.get("sharesOutstanding")
                    or nested.get("shareOutstanding")
                    or nested.get("shares_outstanding")
                )
                aum = (
                    nested.get("totalAssets")
                    or nested.get("aum")
                    or nested.get("totalAum")
                )
                nav = (
                    nested.get("nav")
                    or (quote.get("c") if quote else None)
                )

                # Even if profile is empty we still want a daily NAV row so
                # the chart has SOMETHING to show. Only skip if NAV is also
                # missing (true zero-data case).
                if nav is None and aum is None and shares is None:
                    logger.warning(f"ETF {t}: no profile data at all")
                    continue

                # Find the previous row to compute delta
                prev = (
                    await db.execute(
                        select(ETFFlowDaily)
                        .where(ETFFlowDaily.etf_ticker == t, ETFFlowDaily.date < today)
                        .order_by(ETFFlowDaily.date.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

                delta_shares = (
                    float(shares) - float(prev.shares_outstanding)
                    if shares is not None and prev and prev.shares_outstanding is not None
                    else None
                )
                delta_aum = (
                    float(aum) - float(prev.aum)
                    if aum is not None and prev and prev.aum is not None
                    else None
                )

                async with db.begin_nested():
                    stmt = pg_upsert(ETFFlowDaily).values(
                        etf_ticker=t,
                        date=today,
                        shares_outstanding=shares,
                        aum=aum,
                        nav=nav,
                        delta_shares=delta_shares,
                        delta_aum=delta_aum,
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["etf_ticker", "date"],
                        set_={
                            "shares_outstanding": stmt.excluded.shares_outstanding,
                            "aum": stmt.excluded.aum,
                            "nav": stmt.excluded.nav,
                            "delta_shares": stmt.excluded.delta_shares,
                            "delta_aum": stmt.excluded.delta_aum,
                        },
                    )
                    await db.execute(stmt)
                await db.commit()
                rows_written += 1

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = rows_written
        await db.commit()
        logger.info(f"ETF flows sync: {rows_written} rows")
        return rows_written

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"ETF flows sync failed: {e}")
        raise
