from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ETFHolding(Base):
    """ETF constituent holdings — which biotech ETFs hold which tickers and at what weight."""

    __tablename__ = "etf_holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    etf_ticker: Mapped[str] = mapped_column(String(10), nullable=False)  # XBI, IBB, LABU, SBIO
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker"), nullable=False
    )
    weight: Mapped[float | None] = mapped_column(Float)  # Weight % (0-100)
    shares: Mapped[float | None] = mapped_column(Float)
    market_value: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("etf_ticker", "ticker", name="uq_etf_ticker_holding"),
        Index("ix_etf_ticker", "ticker"),
        Index("ix_etf_etf_ticker", "etf_ticker"),
    )
