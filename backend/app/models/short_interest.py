from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ShortInterest(Base):
    """Daily short-sale volume per ticker, from FINRA's public Reg SHO feeds.

    This is daily short volume (short sales as a fraction of total volume on
    the day), not the bi-monthly short-interest report. Freshness > frequency
    here — daily data updates every morning and tracks trends meaningfully.
    """

    __tablename__ = "short_interest"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    short_volume: Mapped[float | None] = mapped_column(Numeric)
    total_volume: Mapped[float | None] = mapped_column(Numeric)
    short_pct: Mapped[float | None] = mapped_column(Numeric)
    market: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("ticker", "report_date", "market", name="uq_short_interest_tdm"),
        Index("ix_short_interest_ticker_date", "ticker", "report_date"),
        Index("ix_short_interest_date", "report_date"),
    )
