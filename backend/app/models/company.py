from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    cik: Mapped[str | None] = mapped_column(String(20), unique=True)
    sic_code: Mapped[str | None] = mapped_column(String(10))
    exchange: Mapped[str | None] = mapped_column(String(20))
    market_cap: Mapped[float | None] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float)
    price_change_pct: Mapped[float | None] = mapped_column(Float)
    sector: Mapped[str | None] = mapped_column(String(100))
    therapeutic_area: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(2000))
    website: Mapped[str | None] = mapped_column(String(500))
    employees: Mapped[int | None] = mapped_column(Integer)
    # Location
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(300))
    zip_code: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(30))
    # Financials
    revenue: Mapped[float | None] = mapped_column(Float)
    profit_margin: Mapped[float | None] = mapped_column(Float)
    beta: Mapped[float | None] = mapped_column(Float)
    pe_ratio: Mapped[float | None] = mapped_column(Float)
    dividend_yield: Mapped[float | None] = mapped_column(Float)
    fifty_two_week_high: Mapped[float | None] = mapped_column(Float)
    fifty_two_week_low: Mapped[float | None] = mapped_column(Float)
    avg_volume: Mapped[int | None] = mapped_column(Integer)
    shares_outstanding: Mapped[float | None] = mapped_column(Float)
    # Cash runway
    cash_and_equivalents: Mapped[float | None] = mapped_column(Float)
    annual_burn_rate: Mapped[float | None] = mapped_column(Float)
    runway_months: Mapped[int | None] = mapped_column(Integer)
    # Dates
    founded_year: Mapped[str | None] = mapped_column(String(10))
    ipo_date: Mapped[str | None] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    aliases: Mapped[list["SponsorAlias"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    drugs: Mapped[list["Drug"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    catalysts: Mapped[list["Catalyst"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    filings: Mapped[list["SECFiling"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    insider_trades: Mapped[list["InsiderTrade"]] = relationship(back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_companies_sic_code", "sic_code"),
        Index("ix_companies_market_cap", market_cap.desc()),
        Index("ix_companies_exchange", "exchange"),
    )


class SponsorAlias(Base):
    __tablename__ = "sponsor_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(10), ForeignKey("companies.ticker"), nullable=False)
    alias_name: Mapped[str] = mapped_column(String(300), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    company: Mapped["Company"] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("ticker", "alias_name", name="uq_sponsor_alias"),
    )


# Import here to avoid circular imports at module level
from app.models.drug import Drug  # noqa: E402, F811
from app.models.catalyst import Catalyst  # noqa: E402, F811
from app.models.filing import SECFiling, InsiderTrade  # noqa: E402, F811
