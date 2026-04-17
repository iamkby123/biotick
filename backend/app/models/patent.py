from datetime import datetime, date
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Patent(Base):
    """USPTO patents assigned to biotech companies."""

    __tablename__ = "patents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patent_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(1000))
    assignee_name: Mapped[str | None] = mapped_column(String(300))
    company_ticker: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("companies.ticker")
    )
    filing_date: Mapped[date | None] = mapped_column(Date)
    grant_date: Mapped[date | None] = mapped_column(Date)
    expiration_date: Mapped[date | None] = mapped_column(Date)
    abstract: Mapped[str | None] = mapped_column(String(4000))
    patent_type: Mapped[str | None] = mapped_column(String(40))  # utility, design, plant
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_patents_ticker", "company_ticker"),
        Index("ix_patents_grant_date", grant_date.desc()),
    )
