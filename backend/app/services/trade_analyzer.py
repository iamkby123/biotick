"""
AI-powered trade analyzer using Claude API.

Gathers all available data for a company and sends it to Claude
to generate a structured trading plan.
"""

import asyncio
import json
import logging
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor

from anthropic import Anthropic
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.company import Company
from app.models.drug import Drug
from app.models.trial import Trial
from app.models.catalyst import Catalyst
from app.models.filing import SECFiling, InsiderTrade
from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, BIOTECH_SIC_CODES

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)

SYSTEM_PROMPT = """You are an expert biotech trading analyst. Your job is to analyze biotech companies and generate actionable trading plans based on clinical trial data, FDA catalysts, SEC filings, and insider activity.

You MUST respond with valid JSON in this exact format:
{
  "recommendation": "LONG" | "SHORT" | "NEUTRAL",
  "confidence": <1-10>,
  "thesis": "<2-4 sentence investment thesis>",
  "entry_price": <number or null>,
  "exit_price": <number or null>,
  "stop_loss": <number or null>,
  "risk_reward": "<ratio like 1:3>",
  "timeframe": "<short-term (weeks), medium-term (months), or long-term (6+ months)>",
  "options_strategy": {
    "name": "<strategy name like 'Long Straddle', 'Bull Call Spread', etc.>",
    "description": "<1-2 sentence description of the options play>",
    "rationale": "<why this strategy fits the setup>"
  },
  "key_catalysts": [
    {"date": "<YYYY-MM-DD>", "description": "<event>", "impact": "HIGH|MEDIUM|LOW"}
  ],
  "risks": ["<risk 1>", "<risk 2>", ...],
  "additional_notes": "<any other relevant trading considerations>"
}

Analysis guidelines:
- Consider the phase of lead drug candidates (Phase 3 readouts are the biggest movers)
- Factor in market cap — small-cap biotechs move more on catalysts
- Evaluate insider buying vs selling patterns as a sentiment indicator
- Consider implied volatility around catalyst dates for options strategies
- For binary events (FDA decisions), straddles/strangles are common plays
- Phase 3 success rates are ~50-60% for oncology, ~60-70% for other indications
- PDUFA dates are the most important single-day events
- Consider the competitive landscape and unmet medical need

Be specific with price targets and always provide a stop loss. If data is insufficient for a recommendation, set recommendation to "NEUTRAL" and explain why in the thesis."""


async def analyze_trade(db: AsyncSession, ticker: str) -> dict:
    """
    Analyze a company and generate a structured trade plan using Claude.
    """
    if not ANTHROPIC_API_KEY:
        return {"error": "Anthropic API key not configured. Set ANTHROPIC_API_KEY in backend/.env"}

    # Gather all data
    company_data = await _gather_company_data(db, ticker)
    if not company_data:
        return {"error": f"Company {ticker} not found"}

    # Build the analysis prompt
    prompt = _build_prompt(company_data)

    # Call Claude API in thread pool (blocking SDK call)
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, _call_claude, prompt)
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return {"error": f"Analysis failed: {str(e)}"}

    # Add metadata
    result["ticker"] = ticker
    result["company_name"] = company_data["company"]["name"]
    result["current_price"] = company_data["company"]["price"]
    result["market_cap"] = company_data["company"]["market_cap"]
    result["generated_at"] = datetime.utcnow().isoformat()

    return result


def _call_claude(prompt: str) -> dict:
    """Blocking call to Claude API."""
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": prompt}],
    )

    # Parse JSON from response
    response_text = message.content[0].text

    # Try to extract JSON from the response
    try:
        # Try direct parse first
        return json.loads(response_text)
    except json.JSONDecodeError:
        # Try to find JSON block in the response
        import re
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

    # If parsing fails, return raw text
    return {
        "recommendation": "NEUTRAL",
        "confidence": 1,
        "thesis": response_text[:500],
        "entry_price": None,
        "exit_price": None,
        "stop_loss": None,
        "risk_reward": "N/A",
        "timeframe": "unknown",
        "options_strategy": None,
        "key_catalysts": [],
        "risks": ["Could not parse structured response"],
        "additional_notes": response_text,
    }


async def _gather_company_data(db: AsyncSession, ticker: str) -> dict | None:
    """Gather all available data for a company."""
    ticker = ticker.upper()

    # Company
    result = await db.execute(select(Company).where(Company.ticker == ticker))
    company = result.scalar_one_or_none()
    if not company:
        return None

    # Pipeline
    result = await db.execute(
        select(Drug).where(Drug.company_ticker == ticker).order_by(Drug.highest_phase.desc())
    )
    drugs = result.scalars().all()

    # Upcoming catalysts
    today = date.today()
    result = await db.execute(
        select(Catalyst).where(
            and_(
                Catalyst.company_ticker == ticker,
                Catalyst.expected_date >= today,
                Catalyst.is_past == False,
            )
        ).order_by(Catalyst.expected_date.asc()).limit(20)
    )
    catalysts = result.scalars().all()

    # Active trials
    result = await db.execute(
        select(Trial).where(
            and_(
                Trial.company_ticker == ticker,
                Trial.overall_status.in_(["RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION", "NOT_YET_RECRUITING"]),
            )
        ).order_by(Trial.primary_completion_date.asc()).limit(20)
    )
    active_trials = result.scalars().all()

    # Recent SEC filings
    result = await db.execute(
        select(SECFiling).where(SECFiling.ticker == ticker)
        .order_by(SECFiling.filed_date.desc()).limit(10)
    )
    filings = result.scalars().all()

    # Insider trades (90 days)
    cutoff = today - timedelta(days=90)
    result = await db.execute(
        select(InsiderTrade).where(
            InsiderTrade.ticker == ticker,
            InsiderTrade.transaction_date >= cutoff,
        ).order_by(InsiderTrade.transaction_date.desc())
    )
    insider_trades = result.scalars().all()

    # Insider summary
    buys = sum(t.total_value or 0 for t in insider_trades if t.trade_type == "PURCHASE")
    sells = sum(t.total_value or 0 for t in insider_trades if t.trade_type == "SALE")

    return {
        "company": {
            "ticker": company.ticker,
            "name": company.name,
            "price": company.price,
            "price_change_pct": company.price_change_pct,
            "market_cap": company.market_cap,
            "sector": company.sector,
            "description": company.description,
        },
        "drugs": [
            {
                "name": d.drug_name,
                "phase": d.highest_phase,
                "therapeutic_area": d.therapeutic_area,
                "indication": d.indication,
                "status": d.status,
            }
            for d in drugs[:30]  # Limit to top 30 drugs
        ],
        "catalysts": [
            {
                "date": c.expected_date.isoformat() if c.expected_date else None,
                "description": c.event_description,
                "significance": c.significance_score,
                "confidence": c.confidence,
            }
            for c in catalysts
        ],
        "active_trials": [
            {
                "nct_id": t.nct_id,
                "title": t.title[:100],
                "phase": t.phase,
                "status": t.overall_status,
                "indication": t.indication,
                "enrollment": t.enrollment,
                "primary_completion": t.primary_completion_date.isoformat() if t.primary_completion_date else None,
            }
            for t in active_trials
        ],
        "filings": [
            {
                "type": f.filing_type,
                "date": f.filed_date.isoformat() if f.filed_date else None,
                "description": f.description,
            }
            for f in filings
        ],
        "insider_activity": {
            "total_buy_value": buys,
            "total_sell_value": sells,
            "net_value": buys - sells,
            "signal": "BULLISH" if buys > sells else "BEARISH" if sells > buys else "NEUTRAL",
            "recent_trades": [
                {
                    "name": t.insider_name,
                    "title": t.insider_title,
                    "type": t.trade_type,
                    "shares": t.shares,
                    "value": t.total_value,
                    "date": t.transaction_date.isoformat() if t.transaction_date else None,
                }
                for t in insider_trades[:10]
            ],
        },
    }


def _build_prompt(data: dict) -> str:
    """Build the analysis prompt from gathered data."""
    c = data["company"]

    sections = [
        f"Analyze {c['ticker']} ({c['name']}) for biotech trading opportunities.",
        "",
        f"## Company Overview",
        f"- Ticker: {c['ticker']}",
        f"- Price: ${c['price']}" if c['price'] else "- Price: N/A",
        f"- Daily Change: {c['price_change_pct']}%" if c['price_change_pct'] else "",
        f"- Market Cap: ${c['market_cap']:,.0f}" if c['market_cap'] else "- Market Cap: N/A",
        f"- Sector: {c['sector']}" if c['sector'] else "",
    ]

    # Pipeline
    if data["drugs"]:
        sections.append("")
        sections.append("## Drug Pipeline")
        for d in data["drugs"]:
            phase = d['phase'] or 'Unknown'
            sections.append(f"- {d['name']}: {phase} | {d['therapeutic_area'] or 'N/A'} | {d['indication'] or 'N/A'} | {d['status'] or 'Active'}")

    # Catalysts
    if data["catalysts"]:
        sections.append("")
        sections.append("## Upcoming Catalysts")
        for cat in data["catalysts"]:
            sections.append(f"- {cat['date']}: {cat['description']} (Significance: {cat['significance']}/10, Confidence: {cat['confidence']})")

    # Active trials
    if data["active_trials"]:
        sections.append("")
        sections.append("## Active Clinical Trials")
        for t in data["active_trials"]:
            sections.append(f"- {t['nct_id']}: {t['title']} | {t['phase'] or '?'} | {t['status']} | Completion: {t['primary_completion'] or 'TBD'}")

    # Filings
    if data["filings"]:
        sections.append("")
        sections.append("## Recent SEC Filings")
        for f in data["filings"]:
            sections.append(f"- {f['date']}: {f['type']} — {f['description']}")

    # Insider activity
    insider = data["insider_activity"]
    sections.append("")
    sections.append("## Insider Activity (90 Days)")
    sections.append(f"- Net insider activity: ${insider['net_value']:,.0f} ({insider['signal']})")
    sections.append(f"- Total buys: ${insider['total_buy_value']:,.0f}")
    sections.append(f"- Total sells: ${insider['total_sell_value']:,.0f}")
    if insider["recent_trades"]:
        for t in insider["recent_trades"][:5]:
            sections.append(f"  - {t['date']}: {t['name']} ({t['title']}) — {t['type']} {t['shares']:,.0f} shares (${t['value']:,.0f})" if t['value'] else f"  - {t['date']}: {t['name']} — {t['type']} {t['shares']:,.0f} shares")

    sections.append("")
    sections.append("Based on all the above data, generate a comprehensive trading analysis with specific entry/exit prices, options strategy recommendation, and risk assessment. Respond in the JSON format specified.")

    return "\n".join(sections)
