"""Daily ETF NAV snapshot + 1y history backfill.

We track XBI, IBB, LABU, SBIO. Finnhub's /etf/profile and /etf/holdings
are both 403 on free tier, so we call Yahoo's chart JSON directly via
curl_cffi (which defeats datacenter-IP fingerprint blocks by spoofing
Chrome's TLS ClientHello).

We populate:
- `nav` from daily close price
- `delta_shares` column reused as the daily NAV % return (avoids a
  schema migration; the router + frontend now interpret it as pct)
- `shares_outstanding` / `aum` / `delta_aum` stay NULL — Yahoo's
  quoteSummary endpoint needs a crumb cookie we can't obtain
  reliably, and these fields aren't essential for the chart.

1y backfill on first run gives the flows chart 250 bars out of the gate,
so users see a real trend instead of a 2-day stub.
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.etf_flow import ETFFlowDaily
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

_ETFS = ["XBI", "IBB", "LABU", "SBIO"]
_CHART_URL = "https://query1.finance.yahoo.com/v7/finance/chart/{ticker}"


def _fetch_history_sync(ticker: str) -> list[dict] | None:
    """Blocking HTTP call to Yahoo chart. Returns list of (date, close, volume)."""
    try:
        from curl_cffi import requests as cureq

        sess = cureq.Session(impersonate="chrome124")
        resp = sess.get(
            _CHART_URL.format(ticker=ticker),
            params={"interval": "1d", "range": "1y"},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"yahoo ETF {ticker}: HTTP {resp.status_code}")
            return None
        data = resp.json() or {}
        res_list = data.get("chart", {}).get("result") or []
        if not res_list:
            return None
        res = res_list[0]
        timestamps = res.get("timestamp") or []
        quote = (res.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        rows: list[dict] = []
        for i, ts in enumerate(timestamps):
            try:
                d = datetime.utcfromtimestamp(ts).date()
                close = closes[i] if i < len(closes) else None
                if close is None:
                    continue
                rows.append({
                    "date": d,
                    "nav": float(close),
                    "volume": float(volumes[i]) if i < len(volumes) and volumes[i] is not None else None,
                })
            except Exception:
                continue
        return rows
    except Exception as e:
        logger.warning(f"yahoo ETF {ticker} error: {e}")
        return None


async def _upsert_etf_history(db: AsyncSession, ticker: str, rows: list[dict]) -> int:
    """Write NAV history for one ETF. Reuse delta_shares column to store
    daily NAV % return (no schema migration needed)."""
    if not rows:
        return 0
    rows.sort(key=lambda r: r["date"])

    written = 0
    prev_nav = None
    for r in rows:
        delta_nav_pct = None
        if prev_nav and prev_nav > 0:
            delta_nav_pct = (r["nav"] - prev_nav) / prev_nav
        try:
            async with db.begin_nested():
                stmt = pg_upsert(ETFFlowDaily).values(
                    etf_ticker=ticker,
                    date=r["date"],
                    nav=r["nav"],
                    shares_outstanding=None,
                    aum=None,
                    delta_shares=delta_nav_pct,  # stores NAV % return
                    delta_aum=None,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["etf_ticker", "date"],
                    set_={
                        "nav": stmt.excluded.nav,
                        "delta_shares": stmt.excluded.delta_shares,
                    },
                )
                await db.execute(stmt)
            written += 1
        except Exception as e:
            logger.warning(f"{ticker} ETF row error: {e}")
            continue
        prev_nav = r["nav"]
    await db.commit()
    return written


async def sync_etf_flows(db: AsyncSession) -> int:
    """Backfill 1y of NAV for each of the 4 biotech ETFs."""
    log = SyncLog(sync_type="ETF_FLOWS", started_at=datetime.utcnow(), status="RUNNING")
    db.add(log)
    await db.commit()

    try:
        total = 0
        for etf in _ETFS:
            rows = await asyncio.to_thread(_fetch_history_sync, etf)
            if rows:
                total += await _upsert_etf_history(db, etf, rows)
            await asyncio.sleep(1.0)

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = total
        await db.commit()
        logger.info(f"ETF flows sync: {total} rows across {len(_ETFS)} ETFs")
        return total

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"ETF flows sync failed: {e}")
        raise
