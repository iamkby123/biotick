from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PriceHistory(Base):
    """Daily OHLCV candles per ticker, back-filled 5y via Finnhub."""

    __tablename__ = "price_history"

    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Numeric)
    high: Mapped[float | None] = mapped_column(Numeric)
    low: Mapped[float | None] = mapped_column(Numeric)
    close: Mapped[float | None] = mapped_column(Numeric)
    volume: Mapped[float | None] = mapped_column(Numeric)

    __table_args__ = (
        Index("ix_price_history_ticker_date", "ticker", "date"),
    )
