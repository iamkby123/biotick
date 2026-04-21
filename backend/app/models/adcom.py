from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdComMeeting(Base):
    """An FDA Advisory Committee meeting, scraped from the FDA calendar."""

    __tablename__ = "adcom_meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    committee: Mapped[str | None] = mapped_column(Text)
    meeting_date: Mapped[date | None] = mapped_column(Date)
    topics: Mapped[str | None] = mapped_column(Text)
    drug_name: Mapped[str | None] = mapped_column(Text)
    company_ticker: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("companies.ticker", ondelete="SET NULL")
    )
    url: Mapped[str | None] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_adcom_meeting_date", "meeting_date"),
    )


class CongressTrade(Base):
    """Trade disclosure from US Congress periodic transaction reports."""

    __tablename__ = "congress_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    chamber: Mapped[str] = mapped_column(String(10), nullable=False)  # "house" | "senate"
    member_name: Mapped[str] = mapped_column(Text, nullable=False)
    party: Mapped[str | None] = mapped_column(String(2))
    state: Mapped[str | None] = mapped_column(String(2))
    trade_date: Mapped[date | None] = mapped_column(Date)
    ticker: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("companies.ticker", ondelete="SET NULL")
    )
    trade_type: Mapped[str | None] = mapped_column(String(20))  # purchase | sale | exchange
    amount_min: Mapped[float | None] = mapped_column(Numeric)
    amount_max: Mapped[float | None] = mapped_column(Numeric)
    disclosure_url: Mapped[str | None] = mapped_column(Text)
    filing_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_congress_trades_ticker_date", "ticker", "trade_date"),
        Index("ix_congress_trades_date", "trade_date"),
    )


class DrugSales(Base):
    """Per-drug annual revenue, extracted from 10-K filings."""

    __tablename__ = "drug_sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False
    )
    drug_name: Mapped[str] = mapped_column(Text, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue_usd: Mapped[float | None] = mapped_column(Numeric)
    source_accession: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_drug_sales_ticker_year", "ticker", "fiscal_year"),
    )
