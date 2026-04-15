from datetime import datetime, date
from sqlalchemy import String, Float, Integer, Date, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SECFiling(Base):
    __tablename__ = "sec_filings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker"), nullable=False
    )
    cik: Mapped[str | None] = mapped_column(String(20))
    accession_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    filing_type: Mapped[str] = mapped_column(String(20), nullable=False)
    filed_date: Mapped[date] = mapped_column(Date, nullable=False)
    accepted_date: Mapped[datetime | None] = mapped_column(DateTime)
    reporting_date: Mapped[date | None] = mapped_column(Date)
    edgar_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company"] = relationship(back_populates="filings")

    __table_args__ = (
        Index("ix_filings_ticker_date", "ticker", filed_date.desc()),
        Index("ix_filings_type", "filing_type"),
    )


class InsiderTrade(Base):
    __tablename__ = "insider_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker"), nullable=False
    )
    accession_number: Mapped[str | None] = mapped_column(String(30))
    insider_name: Mapped[str] = mapped_column(String(200), nullable=False)
    insider_title: Mapped[str | None] = mapped_column(String(200))
    trade_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # PURCHASE, SALE, OPTION_EXERCISE, GIFT
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    price_per_share: Mapped[float | None] = mapped_column(Float)
    total_value: Mapped[float | None] = mapped_column(Float)
    shares_owned_after: Mapped[float | None] = mapped_column(Float)
    filing_date: Mapped[date | None] = mapped_column(Date)
    is_direct: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company"] = relationship(back_populates="insider_trades")

    __table_args__ = (
        Index("ix_insider_ticker_date", "ticker", transaction_date.desc()),
        Index("ix_insider_type", "trade_type"),
    )


from app.models.company import Company  # noqa: E402, F811
