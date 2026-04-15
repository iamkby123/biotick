from datetime import datetime, date
from sqlalchemy import String, Integer, Date, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Conference(Base):
    __tablename__ = "conferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(50))
    organizer: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    location: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(2000))
    website: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(50))
    significance: Mapped[int] = mapped_column(Integer, default=5)
    is_virtual: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
