from datetime import datetime, date
from sqlalchemy import String, Integer, Date, DateTime, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Catalyst(Base):
    __tablename__ = "catalysts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker"), nullable=False
    )
    drug_id: Mapped[str | None] = mapped_column(
        String(200), ForeignKey("drugs.drug_id")
    )
    drug_name: Mapped[str | None] = mapped_column(String(300))
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # PDUFA, DATA_READOUT, PHASE_TRANSITION, ADVISORY_COMMITTEE, EARNINGS, CONFERENCE
    event_description: Mapped[str | None] = mapped_column(String(500))
    expected_date: Mapped[date | None] = mapped_column(Date)
    date_precision: Mapped[str | None] = mapped_column(String(20))  # EXACT, MONTH, QUARTER, HALF, YEAR
    significance_score: Mapped[int | None] = mapped_column(Integer)  # 1-10
    confidence: Mapped[str | None] = mapped_column(String(10))  # HIGH, MEDIUM, LOW
    source: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    is_past: Mapped[bool] = mapped_column(Boolean, default=False)
    actual_date: Mapped[date | None] = mapped_column(Date)
    outcome: Mapped[str | None] = mapped_column(String(20))  # POSITIVE, NEGATIVE, MIXED, PENDING
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    company: Mapped["Company"] = relationship(back_populates="catalysts")
    drug: Mapped["Drug | None"] = relationship(back_populates="catalysts")

    __table_args__ = (
        UniqueConstraint(
            "company_ticker", "drug_name", "event_type", "expected_date",
            name="uq_catalyst_event"
        ),
        Index("ix_catalysts_date", "expected_date"),
        Index("ix_catalysts_company", "company_ticker"),
        Index("ix_catalysts_significance", significance_score.desc()),
    )


from app.models.company import Company  # noqa: E402, F811
from app.models.drug import Drug  # noqa: E402, F811
