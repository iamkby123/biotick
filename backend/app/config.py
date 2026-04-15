import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Database — Supabase PostgreSQL (direct connection, requires IPv6)
from sqlalchemy import URL as _SAURL
_db_password = os.environ.get("SUPABASE_DB_PASSWORD", "")
DATABASE_URL = _SAURL.create(
    drivername="postgresql+psycopg",
    username="postgres",
    password=_db_password,
    host="db.bfhmaswnkzoowfxrsfce.supabase.co",
    port=5432,
    database="postgres",
)

# SEC EDGAR
SEC_USER_AGENT = "BiotechPlatform kbysnkr6@gmail.com"
SEC_BASE_URL = "https://data.sec.gov"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"

# ClinicalTrials.gov
CT_GOV_BASE_URL = "https://clinicaltrials.gov/api/v2"

# Healthcare & Biotech SIC codes
BIOTECH_SIC_CODES = {
    # Pharma & Biotech
    "2833",  # Pharmaceutical preparations
    "2834",  # Pharmaceutical preparations
    "2835",  # In vitro diagnostics
    "2836",  # Biological products
    # Medical Devices & Instruments
    "3841",  # Surgical & medical instruments
    "3842",  # Orthopedic, prosthetic & surgical supplies
    "3845",  # Electromedical & electrotherapeutic equipment
    "3826",  # Laboratory analytical instruments
    "3823",  # Industrial instruments for measurement
    # Health Services
    "8000",  # Health services
    "8071",  # Health services / medical labs
    "8090",  # Health services (misc)
    # Chemicals & Materials
    "2800",  # Chemicals & allied products
    "2844",  # Cosmetics & personal care
    "2860",  # Industrial chemicals
    # Research
    "8731",  # R&D in physical/engineering/life sciences
}

# CORS
FRONTEND_URL = "http://localhost:3000"

# Claude API (for Trade Analyzer)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Finnhub (for stock prices)
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"

# Cache TTLs (seconds)
CACHE_TTL_QUOTES = 60
CACHE_TTL_COMPANY_DETAIL = 300
CACHE_TTL_OPTIONS = 120
CACHE_TTL_SCREENER = 120
CACHE_TTL_TRIALS = 1800
CACHE_TTL_CATALYSTS = 600
CACHE_TTL_ANALYSIS = 300
