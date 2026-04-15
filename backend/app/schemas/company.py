from datetime import datetime
from pydantic import BaseModel


class CompanyBase(BaseModel):
    ticker: str
    name: str
    exchange: str | None = None
    market_cap: float | None = None
    price: float | None = None
    price_change_pct: float | None = None
    sector: str | None = None
    therapeutic_area: str | None = None


class CompanyListItem(CompanyBase):
    """Compact company for the screener table."""
    sic_code: str | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class CompanyDetail(CompanyBase):
    """Full company detail for the company page."""
    cik: str | None = None
    sic_code: str | None = None
    description: str | None = None
    website: str | None = None
    employees: int | None = None
    # Location
    city: str | None = None
    state: str | None = None
    country: str | None = None
    address: str | None = None
    zip_code: str | None = None
    phone: str | None = None
    # Financials
    revenue: float | None = None
    profit_margin: float | None = None
    beta: float | None = None
    pe_ratio: float | None = None
    dividend_yield: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    avg_volume: int | None = None
    shares_outstanding: float | None = None
    # Dates
    founded_year: str | None = None
    ipo_date: str | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class CompanyListResponse(BaseModel):
    companies: list[CompanyListItem]
    total: int
    page: int
    per_page: int
    total_pages: int
