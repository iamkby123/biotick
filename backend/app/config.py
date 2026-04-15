import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Database — Supabase PostgreSQL
# Accepts any of:
#   postgres://...  postgresql://...  postgresql+asyncpg://...
_raw_url = os.environ.get("DATABASE_URL", "")
# Normalize scheme to postgresql+asyncpg
if _raw_url.startswith("postgres://"):
    _raw_url = "postgresql+asyncpg://" + _raw_url[len("postgres://"):]
elif _raw_url.startswith("postgresql://") and "+asyncpg" not in _raw_url:
    _raw_url = "postgresql+asyncpg://" + _raw_url[len("postgresql://"):]
# Strip sslmode query param (asyncpg uses ssl= connect_arg instead)
if "?" in _raw_url:
    _raw_url = _raw_url.split("?")[0]
DATABASE_URL = _raw_url

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
