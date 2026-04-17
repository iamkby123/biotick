from datetime import datetime, date
from pydantic import BaseModel


class DrugResponse(BaseModel):
    drug_id: str
    drug_name: str
    company_ticker: str
    generic_name: str | None = None
    mechanism: str | None = None
    therapeutic_area: str | None = None
    indication: str | None = None
    highest_phase: str | None = None
    status: str | None = None
    first_approval_date: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class TrialResponse(BaseModel):
    nct_id: str
    drug_id: str | None = None
    company_ticker: str | None = None
    sponsor_name: str
    title: str
    brief_summary: str | None = None
    phase: str | None = None
    overall_status: str | None = None
    therapeutic_area: str | None = None
    indication: str | None = None
    enrollment: int | None = None
    start_date: date | None = None
    primary_completion_date: date | None = None
    completion_date: date | None = None
    study_type: str | None = None
    results_first_posted: date | None = None
    last_update_posted: date | None = None
    why_stopped: str | None = None
    has_results: bool = False

    class Config:
        from_attributes = True


class DrugWithTrials(DrugResponse):
    trials: list[TrialResponse] = []
