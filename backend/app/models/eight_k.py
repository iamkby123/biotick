from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PressRelease(Base):
    """Press releases parsed from 8-K Ex-99 attachments.

    Sourced from 8-K filings with Items 7.01 (Reg FD), 8.01 (Other
    Events), or 2.02 (Results of Operations). Each row is one PR.
    """

    __tablename__ = "press_releases"

    id: Mapped[int] = mapped_column(primary_key=True)
    accession_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    ticker: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("companies.ticker", ondelete="CASCADE")
    )
    headline: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    filed_date: Mapped[date | None] = mapped_column(Date)
    item_code: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_press_releases_ticker_date", "ticker", "filed_date"),
        Index("ix_press_releases_filed_date", "filed_date"),
    )


class Deal(Base):
    """Material agreements / acquisitions parsed from 8-K attachments.

    Sourced from 8-K filings with Items 1.01 (Material Definitive
    Agreement), 2.01 (Acquisition), or 5.02 (Officer / director changes).
    """

    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    accession_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    ticker: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("companies.ticker", ondelete="CASCADE")
    )
    deal_type: Mapped[str | None] = mapped_column(String(40))  # "agreement" | "acquisition" | "officer_change"
    counterparty: Mapped[str | None] = mapped_column(Text)
    headline: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    filed_date: Mapped[date | None] = mapped_column(Date)
    item_code: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_deals_ticker_date", "ticker", "filed_date"),
        Index("ix_deals_filed_date", "filed_date"),
    )
