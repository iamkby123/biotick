from datetime import datetime, date
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Trial(Base):
    __tablename__ = "trials"

    nct_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    drug_id: Mapped[str | None] = mapped_column(
        String(200), ForeignKey("drugs.drug_id")
    )
    company_ticker: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("companies.ticker")
    )
    sponsor_name: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    brief_summary: Mapped[str | None] = mapped_column(String(5000))
    phase: Mapped[str | None] = mapped_column(String(20))  # EARLY_PHASE1, PHASE1, PHASE1_PHASE2, PHASE2, PHASE3, PHASE4
    overall_status: Mapped[str | None] = mapped_column(String(50))
    therapeutic_area: Mapped[str | None] = mapped_column(String(200))
    indication: Mapped[str | None] = mapped_column(String(500))
    enrollment: Mapped[int | None] = mapped_column(Integer)
    start_date: Mapped[date | None] = mapped_column(Date)
    primary_completion_date: Mapped[date | None] = mapped_column(Date)
    completion_date: Mapped[date | None] = mapped_column(Date)
    study_type: Mapped[str | None] = mapped_column(String(30))
    results_first_posted: Mapped[date | None] = mapped_column(Date)
    last_update_posted: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    drug: Mapped["Drug | None"] = relationship(back_populates="trials")
    company: Mapped["Company | None"] = relationship()

    __table_args__ = (
        Index("ix_trials_company", "company_ticker"),
        Index("ix_trials_phase_status", "phase", "overall_status"),
        Index("ix_trials_completion", "primary_completion_date"),
        Index("ix_trials_drug", "drug_id"),
    )


from app.models.drug import Drug  # noqa: E402, F811
from app.models.company import Company  # noqa: E402, F811
