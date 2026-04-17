from datetime import datetime, date
from sqlalchemy import String, Float, Integer, Date, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InstitutionalHolding(Base):
    """13F institutional holdings — which biotech-focused funds own which tickers."""

    __tablename__ = "institutional_holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker"), nullable=False
    )
    fund_name: Mapped[str] = mapped_column(String(200), nullable=False)
    fund_cik: Mapped[str] = mapped_column(String(20), nullable=False)
    shares: Mapped[float | None] = mapped_column(Float)
    value: Mapped[float | None] = mapped_column(Float)  # Reported dollar value
    quarter_end: Mapped[date | None] = mapped_column(Date)
    filing_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ticker", "fund_cik", "quarter_end", name="uq_institutional_holding"),
        Index("ix_institutional_ticker", "ticker"),
        Index("ix_institutional_fund", "fund_cik"),
        Index("ix_institutional_quarter", quarter_end.desc()),
    )
