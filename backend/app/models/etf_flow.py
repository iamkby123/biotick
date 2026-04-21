from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ETFFlowDaily(Base):
    """Daily snapshot of shares-outstanding + AUM for each biotech ETF.

    We compute delta_shares / delta_aum against the previous row at write
    time so the frontend doesn't have to re-derive it. Shares-outstanding
    swings for a big ETF like XBI are the cleanest money-flow signal
    available on the biotech tape.
    """

    __tablename__ = "etf_flow_daily"

    etf_ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    shares_outstanding: Mapped[float | None] = mapped_column(Numeric)
    aum: Mapped[float | None] = mapped_column(Numeric)
    nav: Mapped[float | None] = mapped_column(Numeric)
    delta_shares: Mapped[float | None] = mapped_column(Numeric)
    delta_aum: Mapped[float | None] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_etf_flow_daily_etf_date", "etf_ticker", "date"),
    )
