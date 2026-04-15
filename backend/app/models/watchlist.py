from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker"), nullable=False, unique=True
    )
    added_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[str | None] = mapped_column(String(1000))
    alert_price_above: Mapped[float | None] = mapped_column(Float)
    alert_price_below: Mapped[float | None] = mapped_column(Float)
    notify_catalysts: Mapped[bool] = mapped_column(Boolean, default=True)

    company: Mapped["Company"] = relationship()


from app.models.company import Company  # noqa: E402, F811
