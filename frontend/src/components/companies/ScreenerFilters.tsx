"use client";

import { Search, X } from "lucide-react";

interface ScreenerFiltersProps {
  search: string;
  onSearchChange: (value: string) => void;
  exchange: string;
  onExchangeChange: (value: string) => void;
  marketCapRange: string;
  onMarketCapRangeChange: (value: string) => void;
  // Biotech filters
  runway?: string;
  onRunwayChange?: (value: string) => void;
  highestPhase?: string;
  onHighestPhaseChange?: (value: string) => void;
  catalyst?: string;
  onCatalystChange?: (value: string) => void;
  profitability?: string;
  onProfitabilityChange?: (value: string) => void;
}

const MARKET_CAP_RANGES = [
  { label: "All Cap", value: "" },
  { label: ">$100B", value: "mega" },
  { label: "$10-100B", value: "large" },
  { label: "$2-10B", value: "mid" },
  { label: "$300M-2B", value: "small" },
  { label: "<$300M", value: "micro" },
];

const EXCHANGES = [
  { label: "All", value: "" },
  { label: "NASDAQ", value: "NASDAQ" },
  { label: "NYSE", value: "NYSE" },
];

const RUNWAY_OPTIONS = [
  { label: "Any", value: "" },
  { label: "<6mo", value: "critical" },
  { label: "6-12mo", value: "low" },
  { label: "12-24mo", value: "moderate" },
  { label: ">24mo", value: "strong" },
];

const PHASE_OPTIONS = [
  { label: "Any Phase", value: "" },
  { label: "Has Phase 3", value: "PHASE3" },
  { label: "Has Phase 2", value: "PHASE2" },
  { label: "Has Phase 1", value: "PHASE1" },
  { label: "Has Approved", value: "PHASE4" },
];

const CATALYST_OPTIONS = [
  { label: "Any", value: "" },
  { label: "Next 30d", value: "30" },
  { label: "Next 60d", value: "60" },
  { label: "Next 90d", value: "90" },
];

const PROFITABILITY_OPTIONS = [
  { label: "All", value: "" },
  { label: "Profitable", value: "profitable" },
  { label: "Pre-revenue", value: "pre-revenue" },
];

export default function ScreenerFilters({
  search,
  onSearchChange,
  exchange,
  onExchangeChange,
  marketCapRange,
  onMarketCapRangeChange,
  runway = "",
  onRunwayChange,
  highestPhase = "",
  onHighestPhaseChange,
  catalyst = "",
  onCatalystChange,
  profitability = "",
  onProfitabilityChange,
}: ScreenerFiltersProps) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {/* Search */}
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted" />
          <input
            type="text"
            placeholder="Search ticker or company..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full pl-9 pr-8 py-2 bg-surface border border-border rounded-md text-[13px] text-foreground placeholder:text-muted/50 focus:outline-none focus:ring-1 focus:ring-accent/40 focus:border-accent/40 transition-all"
          />
          {search && (
            <button
              onClick={() => onSearchChange("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted hover:text-foreground transition"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Exchange pills */}
        <div className="flex items-center border border-border rounded-md overflow-hidden">
          {EXCHANGES.map((ex) => (
            <button
              key={ex.value}
              onClick={() => onExchangeChange(ex.value)}
              className={`px-3 py-2 text-[12px] font-medium transition-colors ${
                exchange === ex.value
                  ? "bg-accent/15 text-accent"
                  : "text-muted hover:text-foreground hover:bg-surface-hover"
              }`}
            >
              {ex.label}
            </button>
          ))}
        </div>

        {/* Market cap pills */}
        <div className="flex items-center border border-border rounded-md overflow-hidden">
          {MARKET_CAP_RANGES.map((r) => (
            <button
              key={r.value}
              onClick={() => onMarketCapRangeChange(r.value)}
              className={`px-2.5 py-2 text-[12px] font-medium transition-colors ${
                marketCapRange === r.value
                  ? "bg-accent/15 text-accent"
                  : "text-muted hover:text-foreground hover:bg-surface-hover"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Biotech-specific filters row */}
      <div className="flex flex-wrap items-center gap-2">
        <FilterPills label="Runway" options={RUNWAY_OPTIONS} value={runway} onChange={onRunwayChange} />
        <FilterPills label="Phase" options={PHASE_OPTIONS} value={highestPhase} onChange={onHighestPhaseChange} />
        <FilterPills label="Catalyst" options={CATALYST_OPTIONS} value={catalyst} onChange={onCatalystChange} />
        <FilterPills label="Revenue" options={PROFITABILITY_OPTIONS} value={profitability} onChange={onProfitabilityChange} />
      </div>
    </div>
  );
}

function FilterPills({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { label: string; value: string }[];
  value: string;
  onChange?: (v: string) => void;
}) {
  if (!onChange) return null;
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-wider text-muted/60 font-medium">{label}:</span>
      <div className="flex items-center border border-border rounded-md overflow-hidden">
        {options.map((o) => (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            className={`px-2.5 py-1.5 text-[11px] font-medium transition-colors ${
              value === o.value
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-hover"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function getMarketCapBounds(range: string): { min?: number; max?: number } {
  switch (range) {
    case "mega": return { min: 100e9 };
    case "large": return { min: 10e9, max: 100e9 };
    case "mid": return { min: 2e9, max: 10e9 };
    case "small": return { min: 300e6, max: 2e9 };
    case "micro": return { max: 300e6 };
    default: return {};
  }
}

export function getRunwayBounds(range: string): { min?: number; max?: number } {
  switch (range) {
    case "critical": return { max: 6 };
    case "low": return { min: 6, max: 12 };
    case "moderate": return { min: 12, max: 24 };
    case "strong": return { min: 24 };
    default: return {};
  }
}
