from datetime import datetime, date
from sqlalchemy import String, Date, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Drug(Base):
    __tablename__ = "drugs"

    drug_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    drug_name: Mapped[str] = mapped_column(String(300), nullable=False)
    company_ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker"), nullable=False
    )
    generic_name: Mapped[str | None] = mapped_column(String(300))
    mechanism: Mapped[str | None] = mapped_column(String(500))
    therapeutic_area: Mapped[str | None] = mapped_column(String(200))
    indication: Mapped[str | None] = mapped_column(String(500))
    highest_phase: Mapped[str | None] = mapped_column(String(20))  # PRECLINICAL, PHASE1, PHASE2, PHASE3, APPROVED
    status: Mapped[str | None] = mapped_column(String(20))  # ACTIVE, DISCONTINUED, APPROVED
    first_approval_date: Mapped[date | None] = mapped_column(Date)
    # Therapeutic-modality class (peptide / monoclonal_antibody / mrna / etc.)
    # Populated by app.sync.drug_class_tagger.
    drug_class: Mapped[str | None] = mapped_column(String(40))
    drug_class_source: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    company: Mapped["Company"] = relationship(back_populates="drugs")
    trials: Mapped[list["Trial"]] = relationship(back_populates="drug", cascade="all, delete-orphan")
    catalysts: Mapped[list["Catalyst"]] = relationship(back_populates="drug", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_drugs_company", "company_ticker"),
        Index("ix_drugs_therapeutic_area", "therapeutic_area"),
        Index("ix_drugs_phase", "highest_phase"),
    )


from app.models.company import Company  # noqa: E402, F811
from app.models.trial import Trial  # noqa: E402, F811
from app.models.catalyst import Catalyst  # noqa: E402, F811
