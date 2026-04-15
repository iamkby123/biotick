"use client";

import { Search, X } from "lucide-react";

interface ScreenerFiltersProps {
  search: string;
  onSearchChange: (value: string) => void;
  exchange: string;
  onExchangeChange: (value: string) => void;
  marketCapRange: string;
  onMarketCapRangeChange: (value: string) => void;
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

export default function ScreenerFilters({
  search,
  onSearchChange,
  exchange,
  onExchangeChange,
  marketCapRange,
  onMarketCapRangeChange,
}: ScreenerFiltersProps) {
  return (
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
