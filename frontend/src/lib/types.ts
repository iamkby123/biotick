export interface Company {
  ticker: string;
  name: string;
  exchange: string | null;
  market_cap: number | null;
  price: number | null;
  price_change_pct: number | null;
  sector: string | null;
  therapeutic_area: string | null;
  sic_code: string | null;
  description: string | null;
  website: string | null;
  employees: number | null;
  cik: string | null;
  // Location
  city: string | null;
  state: string | null;
  country: string | null;
  address: string | null;
  zip_code: string | null;
  phone: string | null;
  // Financials
  revenue: number | null;
  profit_margin: number | null;
  beta: number | null;
  pe_ratio: number | null;
  dividend_yield: number | null;
  fifty_two_week_high: number | null;
  fifty_two_week_low: number | null;
  avg_volume: number | null;
  shares_outstanding: number | null;
  // Dates
  founded_year: string | null;
  ipo_date: string | null;
  updated_at: string | null;
}

export interface CompanyListResponse {
  companies: Company[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface Drug {
  drug_id: string;
  drug_name: string;
  company_ticker: string;
  generic_name: string | null;
  mechanism: string | null;
  therapeutic_area: string | null;
  indication: string | null;
  highest_phase: string | null;
  status: string | null;
  first_approval_date: string | null;
}

export interface Trial {
  nct_id: string;
  drug_id: string | null;
  company_ticker: string | null;
  sponsor_name: string;
  title: string;
  brief_summary: string | null;
  phase: string | null;
  overall_status: string | null;
  therapeutic_area: string | null;
  indication: string | null;
  enrollment: number | null;
  start_date: string | null;
  primary_completion_date: string | null;
  completion_date: string | null;
  study_type: string | null;
  results_first_posted: string | null;
  last_update_posted: string | null;
  why_stopped?: string | null;
  has_results?: boolean;
}

export interface DrugWithTrials extends Drug {
  trials: Trial[];
}

export interface SyncStatus {
  sync_type: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  records_processed: number;
  error_message: string | null;
}

export interface TradeAnalysis {
  ticker: string;
  company_name: string;
  current_price: number | null;
  market_cap: number | null;
  recommendation: "LONG" | "SHORT" | "NEUTRAL";
  confidence: number;
  thesis: string;
  entry_price: number | null;
  exit_price: number | null;
  stop_loss: number | null;
  risk_reward: string;
  timeframe: string;
  options_strategy: {
    name: string;
    description: string;
    rationale: string;
  } | null;
  key_catalysts: Array<{
    date: string;
    description: string;
    impact: string;
  }>;
  risks: string[];
  additional_notes: string | null;
  generated_at: string;
}
