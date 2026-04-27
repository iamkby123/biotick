"""Unified biotech-news feed.

The dedicated /news router serves only RSS articles. This /feed endpoint
merges everything that's "news-shaped" across the database into one
chronological stream:

  - **news**            — RSS articles (Endpoints, FierceBio, STAT)
  - **press_release**   — 8-K Items 7.01 / 8.01 / 2.02 (with AI summary)
  - **deal**            — 8-K Items 1.01 / 2.01 (M&A, material agreements)
  - **leadership**      — 8-K Item 5.02 (officer / director changes)
  - **insider**         — Form 4 trades > $500k OR by C-level officers
  - **mover**           — daily price moves of |%| ≥ 10% on biotechs
                          with market cap > $50M (filters out penny names)
  - **catalyst**        — FDA approvals, AdComs, PDUFA dates within ±7 days

Each item shares a common shape so the frontend can render them in one
list with kind-specific badges/colors.

This endpoint is server-cached at 120s (see response_cache.py rule below).
"""

from datetime import date, datetime, timedelta, timezone
from math import ceil
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(prefix="/api/feed", tags=["feed"])


VALID_KINDS = {
    "news",
    "press_release",
    "deal",
    "leadership",
    "insider",
    "mover",
    "catalyst",
}


def _epoch(s: datetime | date | None) -> int | None:
    """Convert a date/datetime to a UTC epoch integer for stable sorting.
    None values bubble to the bottom of the feed."""
    if s is None:
        return None
    if isinstance(s, datetime):
        if s.tzinfo is None:
            s = s.replace(tzinfo=timezone.utc)
        return int(s.timestamp())
    return int(datetime.combine(s, datetime.min.time(), tzinfo=timezone.utc).timestamp())


@router.get("")
async def feed(
    ticker: str | None = Query(None, description="Filter to one ticker"),
    kind: str | None = Query(None, description=f"Filter to one kind: {sorted(VALID_KINDS)}"),
    days: int = Query(14, ge=1, le=120, description="Lookback window"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Return a unified, chronologically-sorted biotech feed."""
    cutoff = date.today() - timedelta(days=days)
    cutoff_dt = datetime.utcnow() - timedelta(days=days)
    ticker_up = ticker.upper() if ticker else None
    kinds = {kind} if kind in VALID_KINDS else VALID_KINDS

    items: list[dict[str, Any]] = []

    # ── 1. RSS news ─────────────────────────────────────────────────────
    if "news" in kinds:
        sql = """
            SELECT id, source, title, url, summary, published_at, tickers
            FROM news_items
            WHERE published_at >= :cutoff_dt
              AND (CAST(:ticker AS text) IS NULL OR :ticker = ANY(tickers))
            ORDER BY published_at DESC NULLS LAST
            LIMIT 200
        """
        rows = (await db.execute(
            text(sql), {"cutoff_dt": cutoff_dt, "ticker": ticker_up}
        )).fetchall()
        for r in rows:
            items.append({
                "kind": "news",
                "id": f"news:{r[0]}",
                "ticker": (r[6] or [None])[0] if r[6] else None,
                "tickers": r[6] or [],
                "headline": r[2],
                "summary": r[4],
                "url": r[3],
                "source": r[1],
                "timestamp": r[5].isoformat() if r[5] else None,
                "_sort_ts": _epoch(r[5]),
            })

    # ── 2. Press releases (8-K Items 7.01 / 8.01 / 2.02) ────────────────
    if "press_release" in kinds:
        sql = """
            SELECT id, ticker, headline, summary, url, item_code, filed_date
            FROM press_releases
            WHERE filed_date >= :cutoff
              AND (CAST(:ticker AS text) IS NULL OR ticker = :ticker)
              AND headline IS NOT NULL
              AND LENGTH(headline) >= 15
              AND headline NOT ILIKE 'EX-%'
              AND headline NOT ILIKE '8-K%'
              AND headline NOT ILIKE 'Document%'
              AND headline NOT ILIKE '%.htm%'
              AND headline NOT ILIKE '%_8k%'
              -- skip filename-like headlines (e.g. "bio-20260421", "mbrx20260422", "wk-form4_...")
              AND headline !~* '^[a-z0-9]+-?[0-9]{6,}'
              AND headline !~* '^wk-'
              -- skip just a company name + "8-K" (no actual press-release content)
              AND headline !~* '8-K\\s*$'
            ORDER BY filed_date DESC
            LIMIT 200
        """
        rows = (await db.execute(
            text(sql), {"cutoff": cutoff, "ticker": ticker_up}
        )).fetchall()
        for r in rows:
            items.append({
                "kind": "press_release",
                "id": f"pr:{r[0]}",
                "ticker": r[1],
                "tickers": [r[1]] if r[1] else [],
                "headline": r[2],
                "summary": r[3],
                "url": r[4],
                "source": "SEC 8-K",
                "item_code": r[5],
                "timestamp": r[6].isoformat() if r[6] else None,
                "_sort_ts": _epoch(r[6]),
            })

    # ── 3. Deals (8-K Items 1.01 / 2.01) ───────────────────────────────
    if "deal" in kinds:
        sql = """
            SELECT id, ticker, deal_type, counterparty, headline, summary,
                   filed_date, item_code
            FROM deals
            WHERE filed_date >= :cutoff
              AND (CAST(:ticker AS text) IS NULL OR ticker = :ticker)
              AND deal_type IN ('material_agreement', 'acquisition')
              -- skip filename-like / placeholder headlines that the
              -- 8-K parser sometimes leaves behind.
              AND (headline IS NULL OR (
                LENGTH(headline) >= 15
                AND headline NOT ILIKE 'EX-%'
                AND headline NOT ILIKE '8-K%'
                AND headline NOT ILIKE 'Document%'
                AND headline NOT ILIKE '%.htm%'
                AND headline NOT ILIKE '%_8k%'
                AND headline !~* '^[a-z0-9]+-?[0-9]{6,}'
                AND headline !~* '8-K\\s*$'
              ))
            ORDER BY filed_date DESC
            LIMIT 200
        """
        rows = (await db.execute(
            text(sql), {"cutoff": cutoff, "ticker": ticker_up}
        )).fetchall()
        for r in rows:
            label = {"material_agreement": "Material Agreement", "acquisition": "Acquisition"}.get(r[2], r[2])
            items.append({
                "kind": "deal",
                "id": f"deal:{r[0]}",
                "ticker": r[1],
                "tickers": [r[1]] if r[1] else [],
                "headline": r[4] or f"{label}: {r[3] or 'undisclosed counterparty'}",
                "summary": r[5],
                "url": None,
                "source": "SEC 8-K",
                "item_code": r[7],
                "deal_type": r[2],
                "counterparty": r[3],
                "timestamp": r[6].isoformat() if r[6] else None,
                "_sort_ts": _epoch(r[6]),
            })

    # ── 4. Leadership changes (8-K Item 5.02) ──────────────────────────
    if "leadership" in kinds:
        sql = """
            SELECT id, ticker, counterparty, headline, summary, filed_date
            FROM deals
            WHERE filed_date >= :cutoff
              AND (CAST(:ticker AS text) IS NULL OR ticker = :ticker)
              AND deal_type = 'officer_change'
              -- same headline-quality filter as press_releases / deals.
              AND (headline IS NULL OR (
                LENGTH(headline) >= 15
                AND headline NOT ILIKE 'EX-%'
                AND headline NOT ILIKE '8-K%'
                AND headline NOT ILIKE 'Document%'
                AND headline NOT ILIKE '%.htm%'
                AND headline NOT ILIKE '%_8k%'
                AND headline !~* '^[a-z0-9]+-?[0-9]{6,}'
                AND headline !~* '8-K\\s*$'
              ))
            ORDER BY filed_date DESC
            LIMIT 100
        """
        rows = (await db.execute(
            text(sql), {"cutoff": cutoff, "ticker": ticker_up}
        )).fetchall()
        for r in rows:
            items.append({
                "kind": "leadership",
                "id": f"lead:{r[0]}",
                "ticker": r[1],
                "tickers": [r[1]] if r[1] else [],
                "headline": r[3] or f"Officer / director change: {r[2] or '(undisclosed)'}",
                "summary": r[4],
                "url": None,
                "source": "SEC 8-K Item 5.02",
                "person": r[2],
                "timestamp": r[5].isoformat() if r[5] else None,
                "_sort_ts": _epoch(r[5]),
            })

    # ── 5. Insider trades — high-value or by C-level ───────────────────
    if "insider" in kinds:
        sql = """
            SELECT it.id, it.ticker, it.insider_name, it.insider_title,
                   it.trade_type, it.transaction_date, it.shares,
                   it.price_per_share, it.total_value
            FROM insider_trades it
            WHERE it.filing_date >= :cutoff
              AND (CAST(:ticker AS text) IS NULL OR it.ticker = :ticker)
              AND (
                it.total_value >= 500000
                OR it.insider_title ILIKE '%CEO%'
                OR it.insider_title ILIKE '%CFO%'
                OR it.insider_title ILIKE '%President%'
                OR it.insider_title ILIKE '%Chief%'
              )
            ORDER BY it.transaction_date DESC, it.id DESC
            LIMIT 200
        """
        rows = (await db.execute(
            text(sql), {"cutoff": cutoff, "ticker": ticker_up}
        )).fetchall()
        for r in rows:
            (id_, tk, name, title, ttype, txn_date, shares, ppx, tot) = r
            tval = float(tot) if tot is not None else None
            tk_dollar = f"${(tval / 1_000_000):.1f}M" if tval and tval >= 1_000_000 else (f"${(tval / 1000):.0f}K" if tval else "")
            verb = {
                "PURCHASE": "bought",
                "SALE": "sold",
                "GRANT": "received grant of",
                "OPTION_EXERCISE": "exercised options for",
                "TAX_WITHHOLDING": "had withheld",
                "OTHER": "transacted",
            }.get((ttype or "").upper(), (ttype or "").lower() or "transacted")
            sh_str = f"{int(shares):,}" if shares else "?"
            headline = (
                f"{name} ({title or 'insider'}) {verb} "
                f"{sh_str} {tk} shares" + (f" ({tk_dollar})" if tk_dollar else "")
            )
            items.append({
                "kind": "insider",
                "id": f"insider:{id_}",
                "ticker": tk,
                "tickers": [tk] if tk else [],
                "headline": headline,
                "summary": None,
                "url": None,
                "source": "SEC Form 4",
                "trade_type": ttype,
                "shares": float(shares) if shares is not None else None,
                "price": float(ppx) if ppx is not None else None,
                "total_value": tval,
                "timestamp": txn_date.isoformat() if txn_date else None,
                "_sort_ts": _epoch(txn_date),
            })

    # ── 6. Big stock movers (today's |change_pct| >= 10%, market_cap > $50M) ──
    if "mover" in kinds:
        sql = """
            SELECT ticker, name, price, price_change_pct, market_cap
            FROM companies
            WHERE price_change_pct IS NOT NULL
              AND ABS(price_change_pct) >= 10
              AND market_cap >= 50000000
              AND (CAST(:ticker AS text) IS NULL OR ticker = :ticker)
            ORDER BY ABS(price_change_pct) DESC
            LIMIT 30
        """
        rows = (await db.execute(
            text(sql), {"ticker": ticker_up}
        )).fetchall()
        for r in rows:
            (tk, name, price, pct, mcap) = r
            direction = "surges" if pct > 0 else "drops"
            items.append({
                "kind": "mover",
                "id": f"mover:{tk}",
                "ticker": tk,
                "tickers": [tk],
                "headline": f"{tk} {direction} {abs(pct):.1f}% to ${float(price):.2f}",
                "summary": name,
                "url": None,
                "source": "Market data",
                "price": float(price) if price is not None else None,
                "price_change_pct": float(pct),
                "market_cap": float(mcap) if mcap is not None else None,
                # Use today's date as the timestamp — these are "today's"
                # events so they bubble to the top of the feed.
                "timestamp": date.today().isoformat(),
                "_sort_ts": _epoch(date.today()),
            })

    # ── 7. Catalysts — FDA approvals + AdComs in the window ────────────
    if "catalyst" in kinds:
        sql = """
            SELECT id, company_ticker, drug_name, event_type,
                   event_description, expected_date, actual_date, outcome,
                   source_url
            FROM catalysts
            WHERE (
                  (actual_date IS NOT NULL AND actual_date >= :cutoff)
               OR (expected_date BETWEEN CURRENT_DATE - INTERVAL '3 days'
                                     AND CURRENT_DATE + INTERVAL '7 days')
            )
              AND event_type IN ('FDA_APPROVAL', 'PDUFA', 'ADVISORY_COMMITTEE')
              AND (CAST(:ticker AS text) IS NULL OR company_ticker = :ticker)
            ORDER BY COALESCE(actual_date, expected_date) DESC NULLS LAST
            LIMIT 50
        """
        rows = (await db.execute(
            text(sql), {"cutoff": cutoff, "ticker": ticker_up}
        )).fetchall()
        for r in rows:
            (id_, tk, drug, etype, desc, exp_d, act_d, outcome, surl) = r
            d = act_d or exp_d
            label = {
                "FDA_APPROVAL": "FDA decision",
                "PDUFA": "PDUFA target",
                "ADVISORY_COMMITTEE": "AdCom meeting",
            }.get(etype, etype)
            outcome_tag = ""
            if outcome == "POSITIVE":
                outcome_tag = " — APPROVED"
            elif outcome == "NEGATIVE":
                outcome_tag = " — REJECTED"
            headline = f"{tk} {drug or 'asset'}: {label} {d.isoformat() if d else ''}{outcome_tag}".strip()
            items.append({
                "kind": "catalyst",
                "id": f"cat:{id_}",
                "ticker": tk,
                "tickers": [tk] if tk else [],
                "headline": headline,
                "summary": desc,
                "url": surl,
                "source": "FDA",
                "event_type": etype,
                "outcome": outcome,
                "timestamp": d.isoformat() if d else None,
                "_sort_ts": _epoch(d),
            })

    # ── Merge + sort + paginate ────────────────────────────────────────
    items.sort(key=lambda i: (i.get("_sort_ts") or 0), reverse=True)
    total = len(items)
    start = (page - 1) * per_page
    page_items = items[start : start + per_page]

    # Drop the internal sort key from the response
    for it in page_items:
        it.pop("_sort_ts", None)

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total else 0,
        "kinds": sorted(VALID_KINDS),
    }


@router.get("/kinds")
async def feed_kinds(
    db: AsyncSession = Depends(get_db),
    days: int = Query(14, ge=1, le=120),
):
    """Per-kind item counts for the feed in the given window. Used by the
    frontend to render filter chip counts without making N requests."""
    cutoff = date.today() - timedelta(days=days)
    cutoff_dt = datetime.utcnow() - timedelta(days=days)
    counts: dict[str, int] = {}

    counts["news"] = (await db.execute(
        text("SELECT COUNT(*) FROM news_items WHERE published_at >= :cutoff_dt"),
        {"cutoff_dt": cutoff_dt},
    )).scalar() or 0
    counts["press_release"] = (await db.execute(
        text("SELECT COUNT(*) FROM press_releases WHERE filed_date >= :c AND headline IS NOT NULL AND headline NOT ILIKE 'EX-%'"),
        {"c": cutoff},
    )).scalar() or 0
    counts["deal"] = (await db.execute(
        text("SELECT COUNT(*) FROM deals WHERE filed_date >= :c AND deal_type IN ('material_agreement','acquisition')"),
        {"c": cutoff},
    )).scalar() or 0
    counts["leadership"] = (await db.execute(
        text("SELECT COUNT(*) FROM deals WHERE filed_date >= :c AND deal_type='officer_change'"),
        {"c": cutoff},
    )).scalar() or 0
    counts["insider"] = (await db.execute(
        text("""
            SELECT COUNT(*) FROM insider_trades
            WHERE filing_date >= :c
              AND (total_value >= 500000
                   OR insider_title ILIKE '%CEO%'
                   OR insider_title ILIKE '%CFO%'
                   OR insider_title ILIKE '%President%'
                   OR insider_title ILIKE '%Chief%')
        """),
        {"c": cutoff},
    )).scalar() or 0
    counts["mover"] = (await db.execute(
        text("""
            SELECT COUNT(*) FROM companies
            WHERE price_change_pct IS NOT NULL
              AND ABS(price_change_pct) >= 10
              AND market_cap >= 50000000
        """)
    )).scalar() or 0
    counts["catalyst"] = (await db.execute(
        text("""
            SELECT COUNT(*) FROM catalysts
            WHERE event_type IN ('FDA_APPROVAL','PDUFA','ADVISORY_COMMITTEE')
              AND (
                (actual_date IS NOT NULL AND actual_date >= :c)
                OR (expected_date BETWEEN CURRENT_DATE - INTERVAL '3 days'
                                    AND CURRENT_DATE + INTERVAL '7 days')
              )
        """),
        {"c": cutoff},
    )).scalar() or 0

    return {"days": days, "counts": counts}
