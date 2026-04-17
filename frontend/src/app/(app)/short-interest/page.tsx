"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { TrendingDown, Loader2, AlertTriangle } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatMarketCap, formatPrice, formatNumber } from "@/lib/utils";
import { PaywallGate } from "@/components/PaywallGate";
import { usePlan } from "@/hooks/usePlan";

interface ShortStock {
  ticker: string;
  name: string;
  price: number | null;
  market_cap: number | null;
  short_interest: number | null;
  avg_volume: number | null;
  days_to_cover: number | null;
  settlement_date: string | null;
}

interface TopShortedResponse {
  stocks: ShortStock[];
  total: number;
  error?: string;
}

type SortKey = "days_to_cover" | "short_interest" | "market_cap" | "ticker";

export default function ShortInterestPage() {
  const [sortKey, setSortKey] = useState<SortKey>("days_to_cover");
  const [limit, setLimit] = useState(50);

  const { data, isLoading, error } = useQuery<TopShortedResponse>({
    queryKey: ["top-shorted", limit],
    queryFn: () => fetchAPI(`/edge/top-shorted?limit=${limit}`),
  });

  const { isPro } = usePlan();
  const stocks = [...(data?.stocks || [])].sort((a, b) => {
    if (sortKey === "ticker") return a.ticker.localeCompare(b.ticker);
    const aVal = (a[sortKey] as number | null) || 0;
    const bVal = (b[sortKey] as number | null) || 0;
    return bVal - aVal;
  });

  const content = (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <TrendingDown className="w-4 h-4" />
          Market Data
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">
          Short Interest
        </h1>
        <p className="text-sm text-muted mt-1">
          Most heavily shorted biotech stocks. High days-to-cover may indicate squeeze potential or strong bearish sentiment.
        </p>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted">Sort by:</span>
          {[
            { label: "Days to Cover", value: "days_to_cover" as const },
            { label: "Short Interest", value: "short_interest" as const },
            { label: "Market Cap", value: "market_cap" as const },
            { label: "Ticker", value: "ticker" as const },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => setSortKey(opt.value)}
              className={cn(
                "px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors",
                sortKey === opt.value
                  ? "bg-accent/15 text-accent"
                  : "text-muted hover:text-foreground hover:bg-surface-hover"
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <span className="text-xs text-muted">Top</span>
          {[25, 50, 100].map((n) => (
            <button
              key={n}
              onClick={() => setLimit(n)}
              className={cn(
                "px-2.5 py-1 rounded text-[11px] font-medium transition-colors",
                limit === n
                  ? "bg-accent/15 text-accent"
                  : "text-muted hover:text-foreground hover:bg-surface-hover"
              )}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {/* Data quality notice */}
      <div className="flex items-start gap-2 rounded-lg border border-border p-3 text-xs text-muted">
        <AlertTriangle className="w-3.5 h-3.5 text-muted shrink-0 mt-0.5" />
        <span>
          Data sourced from Finnhub based on the latest FINRA short interest settlement.
          Finnhub&apos;s free tier only returns data for a subset of tickers — only stocks with available data are shown.
        </span>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
          <span className="ml-2 text-sm text-muted">Fetching short interest data for {limit} biotechs…</span>
        </div>
      ) : error ? (
        <div className="rounded-lg border border-negative/30 bg-negative/5 p-6 text-center">
          <p className="text-sm text-negative">Error loading short interest data.</p>
        </div>
      ) : stocks.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <TrendingDown className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">No short interest data available</p>
          {data?.error && <p className="text-xs text-muted mt-1">{data.error}</p>}
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface/50 border-b border-border">
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Ticker</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Company</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Price</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Market Cap</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Short Interest</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Avg Volume</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Days to Cover</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Settled</th>
              </tr>
            </thead>
            <tbody>
              {stocks.map((s) => {
                const dtc = s.days_to_cover || 0;
                const dtcColor = dtc >= 7 ? "text-negative" : dtc >= 3 ? "text-warning" : "text-muted";
                return (
                  <tr
                    key={s.ticker}
                    className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors"
                  >
                    <td className="px-4 py-3">
                      <Link href={`/companies/${s.ticker}`} className="font-semibold text-[13px] text-accent hover:underline">
                        {s.ticker}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-[13px] max-w-[240px] truncate text-muted">{s.name}</td>
                    <td className="px-4 py-3 text-right font-mono text-sm">{s.price !== null ? formatPrice(s.price) : "--"}</td>
                    <td className="px-4 py-3 text-right font-mono text-sm text-muted">{formatMarketCap(s.market_cap)}</td>
                    <td className="px-4 py-3 text-right font-mono text-sm">{s.short_interest ? formatNumber(s.short_interest) : "--"}</td>
                    <td className="px-4 py-3 text-right font-mono text-sm text-muted">{s.avg_volume ? formatNumber(s.avg_volume) : "--"}</td>
                    <td className={cn("px-4 py-3 text-right font-mono text-sm font-medium", dtcColor)}>
                      {s.days_to_cover !== null ? s.days_to_cover.toFixed(2) : "--"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-[11px] text-muted">{s.settlement_date || "--"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {data && stocks.length > 0 && (
        <p className="text-xs text-muted text-right">{stocks.length} tickers with short interest data (out of {limit} queried)</p>
      )}
    </div>
  );

  if (!isPro) {
    return <PaywallGate feature="Short Interest Data">{content}</PaywallGate>;
  }
  return content;
}
