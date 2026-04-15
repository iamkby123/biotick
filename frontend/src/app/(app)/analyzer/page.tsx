"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import Link from "next/link";
import {
  Sparkles,
  Loader2,
  TrendingUp,
  TrendingDown,
  Minus,
  Target,
  Shield,
  AlertTriangle,
  Calendar,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
  Search,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatPrice, formatMarketCap } from "@/lib/utils";
import type { TradeAnalysis } from "@/lib/types";

interface TickerOption {
  ticker: string;
  name: string;
}

export default function AnalyzerPage() {
  const [searchInput, setSearchInput] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Ticker autocomplete
  const { data: tickerResults } = useQuery<{ tickers: TickerOption[] }>({
    queryKey: ["analyzer-tickers", searchInput],
    queryFn: () => fetchAPI(`/analyzer/tickers?search=${encodeURIComponent(searchInput)}`),
    enabled: searchInput.length >= 1,
  });

  // Analysis mutation
  const analysisMutation = useMutation<TradeAnalysis>({
    mutationFn: () =>
      fetchAPI(`/analyzer/${selectedTicker}`, { method: "POST" }),
  });

  const handleSelectTicker = useCallback((ticker: string) => {
    setSelectedTicker(ticker);
    setSearchInput(ticker);
    setShowDropdown(false);
  }, []);

  const handleAnalyze = useCallback(() => {
    if (selectedTicker) {
      analysisMutation.mutate();
    }
  }, [selectedTicker, analysisMutation]);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const analysis = analysisMutation.data;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-accent" />
          </div>
          Trade Analyzer
        </h1>
        <p className="text-muted mt-2">
          AI-powered analysis using clinical trials, catalysts, SEC filings, and insider activity
        </p>
      </div>

      {/* Search + Analyze */}
      <div className="rounded-xl border border-border bg-surface p-6">
        <div className="flex items-end gap-4">
          <div className="flex-1 relative" ref={dropdownRef}>
            <label className="text-sm font-medium text-muted block mb-2">
              Company Ticker
            </label>
            <div className="relative">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => {
                  setSearchInput(e.target.value);
                  setShowDropdown(true);
                  setSelectedTicker(null);
                }}
                onFocus={() => setShowDropdown(true)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && selectedTicker) handleAnalyze();
                }}
                placeholder="Search ticker or company name..."
                className="w-full pl-10 pr-4 py-3 bg-background border border-border rounded-xl text-base font-mono placeholder:text-muted/50 focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/50 transition"
              />
            </div>

            {/* Autocomplete dropdown */}
            {showDropdown && tickerResults?.tickers && tickerResults.tickers.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 rounded-xl border border-border bg-surface-elevated shadow-lg overflow-hidden z-50">
                {tickerResults.tickers.map((t) => (
                  <button
                    key={t.ticker}
                    onClick={() => handleSelectTicker(t.ticker)}
                    className="flex items-center gap-3 w-full px-4 py-3 hover:bg-surface-hover transition-colors text-left"
                  >
                    <div className="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center text-accent font-bold text-xs">
                      {t.ticker.slice(0, 2)}
                    </div>
                    <div>
                      <p className="font-semibold text-sm">{t.ticker}</p>
                      <p className="text-xs text-muted truncate max-w-[300px]">{t.name}</p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={handleAnalyze}
            disabled={!selectedTicker || analysisMutation.isPending}
            className={cn(
              "px-8 py-3 rounded-xl font-semibold text-base transition-all flex items-center gap-2",
              selectedTicker && !analysisMutation.isPending
                ? "bg-accent text-black hover:bg-accent-hover"
                : "bg-surface-hover text-muted cursor-not-allowed"
            )}
          >
            {analysisMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Analyzing...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Analyze
              </>
            )}
          </button>
        </div>

        {analysisMutation.isPending && (
          <div className="mt-6 flex items-center gap-3 text-muted">
            <Loader2 className="w-5 h-5 animate-spin text-accent" />
            <span>Gathering pipeline data, catalysts, filings, and insider activity for {selectedTicker}...</span>
          </div>
        )}

        {analysisMutation.isError && (
          <div className="mt-4 rounded-lg border border-negative/30 bg-negative/5 p-4">
            <p className="text-negative text-sm">
              Analysis failed: {(analysisMutation.error as Error).message}
            </p>
          </div>
        )}
      </div>

      {/* Results */}
      {analysis && (
        <div className="space-y-6">
          {/* Recommendation hero */}
          <div className={cn(
            "rounded-xl border p-8",
            analysis.recommendation === "LONG"
              ? "border-positive/30 bg-positive/5"
              : analysis.recommendation === "SHORT"
                ? "border-negative/30 bg-negative/5"
                : "border-border bg-surface"
          )}>
            <div className="flex items-start justify-between gap-6">
              <div>
                <div className="flex items-center gap-3">
                  <Link
                    href={`/companies/${analysis.ticker}`}
                    className="text-2xl font-bold hover:text-accent transition"
                  >
                    {analysis.ticker}
                  </Link>
                  <span className={cn(
                    "px-4 py-1.5 rounded-full text-sm font-bold",
                    analysis.recommendation === "LONG"
                      ? "bg-positive/20 text-positive"
                      : analysis.recommendation === "SHORT"
                        ? "bg-negative/20 text-negative"
                        : "bg-surface-hover text-muted"
                  )}>
                    {analysis.recommendation === "LONG" && <TrendingUp className="w-4 h-4 inline mr-1" />}
                    {analysis.recommendation === "SHORT" && <TrendingDown className="w-4 h-4 inline mr-1" />}
                    {analysis.recommendation === "NEUTRAL" && <Minus className="w-4 h-4 inline mr-1" />}
                    {analysis.recommendation}
                  </span>
                  <span className="text-sm text-muted">
                    Confidence: {analysis.confidence}/10
                  </span>
                </div>
                <p className="text-muted mt-1">{analysis.company_name}</p>
                <div className="flex items-baseline gap-3 mt-3">
                  <span className="text-3xl font-bold font-mono">
                    {formatPrice(analysis.current_price)}
                  </span>
                  <span className="text-sm text-muted">
                    MCap: {formatMarketCap(analysis.market_cap)}
                  </span>
                </div>
              </div>

              {/* Confidence meter */}
              <div className="text-center shrink-0">
                <div className="w-20 h-20 rounded-full border-4 flex items-center justify-center text-2xl font-bold" style={{
                  borderColor: analysis.confidence >= 7 ? 'var(--positive)' : analysis.confidence >= 4 ? 'var(--warning)' : 'var(--negative)',
                }}>
                  {analysis.confidence}
                </div>
                <p className="text-xs text-muted mt-1">Confidence</p>
              </div>
            </div>

            {/* Thesis */}
            <div className="mt-6 pt-6 border-t border-border/50">
              <h3 className="text-sm font-semibold uppercase text-muted mb-2">Investment Thesis</h3>
              <p className="text-[15px] leading-relaxed">{analysis.thesis}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Trade Plan */}
            <div className="rounded-xl border border-border bg-surface p-6">
              <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
                <Target className="w-5 h-5 text-accent" />
                Trade Plan
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <PlanItem label="Entry Price" value={analysis.entry_price ? `$${analysis.entry_price}` : "N/A"} color="text-foreground" />
                <PlanItem label="Exit Price" value={analysis.exit_price ? `$${analysis.exit_price}` : "N/A"} color="text-positive" icon={<ArrowUpRight className="w-3.5 h-3.5" />} />
                <PlanItem label="Stop Loss" value={analysis.stop_loss ? `$${analysis.stop_loss}` : "N/A"} color="text-negative" icon={<ArrowDownRight className="w-3.5 h-3.5" />} />
                <PlanItem label="Risk/Reward" value={analysis.risk_reward} color="text-accent" />
              </div>
              <div className="mt-4 pt-4 border-t border-border">
                <p className="text-xs text-muted uppercase font-medium">Timeframe</p>
                <p className="text-sm font-medium mt-1">{analysis.timeframe}</p>
              </div>
            </div>

            {/* Options Strategy */}
            <div className="rounded-xl border border-border bg-surface p-6">
              <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
                <BarChart3 className="w-5 h-5 text-accent" />
                Options Strategy
              </h3>
              {analysis.options_strategy ? (
                <div>
                  <p className="text-xl font-bold text-accent">{analysis.options_strategy.name}</p>
                  <p className="text-sm text-muted mt-2">{analysis.options_strategy.description}</p>
                  <div className="mt-4 pt-4 border-t border-border">
                    <p className="text-xs text-muted uppercase font-medium">Rationale</p>
                    <p className="text-sm mt-1">{analysis.options_strategy.rationale}</p>
                  </div>
                </div>
              ) : (
                <p className="text-muted">No options strategy suggested</p>
              )}
            </div>
          </div>

          {/* Key Catalysts */}
          {analysis.key_catalysts && analysis.key_catalysts.length > 0 && (
            <div className="rounded-xl border border-border bg-surface p-6">
              <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
                <Calendar className="w-5 h-5 text-accent" />
                Key Catalysts
              </h3>
              <div className="space-y-3">
                {analysis.key_catalysts.map((cat, i) => (
                  <div key={i} className="flex items-center gap-4 py-2">
                    <span className="text-sm font-mono text-muted w-28 shrink-0">{cat.date}</span>
                    <span className="text-sm flex-1">{cat.description}</span>
                    <span className={cn(
                      "text-xs font-semibold px-2 py-0.5 rounded-full",
                      cat.impact === "HIGH"
                        ? "bg-negative/10 text-negative"
                        : cat.impact === "MEDIUM"
                          ? "bg-warning/10 text-warning"
                          : "bg-accent/10 text-accent"
                    )}>
                      {cat.impact}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Risks */}
          {analysis.risks && analysis.risks.length > 0 && (
            <div className="rounded-xl border border-border bg-surface p-6">
              <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
                <AlertTriangle className="w-5 h-5 text-warning" />
                Risks
              </h3>
              <ul className="space-y-2">
                {analysis.risks.map((risk, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <Shield className="w-4 h-4 text-muted shrink-0 mt-0.5" />
                    <span>{risk}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Disclaimer */}
          <p className="text-xs text-muted text-center px-8">
            This analysis is AI-generated for educational purposes only. It is not financial advice.
            Always do your own research before making investment decisions. Generated at {analysis.generated_at}.
          </p>
        </div>
      )}

      {/* Empty state */}
      {!analysis && !analysisMutation.isPending && (
        <div className="rounded-xl border border-border border-dashed bg-surface p-16 text-center">
          <Sparkles className="w-12 h-12 text-muted/30 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-muted">Select a company to analyze</h3>
          <p className="text-sm text-muted/70 mt-1 max-w-md mx-auto">
            Search for a biotech company above and click Analyze to get an AI-powered trade plan
            with stock and options recommendations.
          </p>
        </div>
      )}
    </div>
  );
}

function PlanItem({
  label,
  value,
  color,
  icon,
}: {
  label: string;
  value: string;
  color: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg bg-background/50 p-3">
      <p className="text-xs text-muted uppercase font-medium">{label}</p>
      <p className={cn("text-lg font-bold font-mono mt-1 flex items-center gap-1", color)}>
        {icon}
        {value}
      </p>
    </div>
  );
}
