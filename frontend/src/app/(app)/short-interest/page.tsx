"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { TrendingDown, Loader2, Search } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatMarketCap } from "@/lib/utils";

interface ShortStock {
  ticker: string;
  name: string;
  price: number | null;
  market_cap: number | null;
  // edge/top-shorted reuses days_to_cover to carry 30-day average short_pct (0..1).
  days_to_cover: number | null;
  // 30-day average daily short volume (shares).
  short_interest: number | null;
  // 30-day average total daily volume (shares).
  avg_volume: number | null;
  settlement_date: string | null;
}

interface TopShortedResponse {
  stocks: ShortStock[];
  total: number;
}

interface PerTickerResponse {
  ticker: string;
  days: number;
  items: Array<{
    date: string;
    short_volume: number | null;
    total_volume: number | null;
    short_pct: number | null;
  }>;
}

const LIMIT_OPTIONS = [25, 50, 100];

export default function ShortInterestPage() {
  const [limit, setLimit] = useState(50);
  const [search, setSearch] = useState("");
  const [activeTicker, setActiveTicker] = useState<string | null>(null);

  const { data: leaderboard, isLoading } = useQuery<TopShortedResponse>({
    queryKey: ["top-shorted", limit],
    queryFn: () => fetchAPI(`/edge/top-shorted?limit=${limit}`),
    staleTime: 5 * 60 * 1000,
  });

  const filtered = (leaderboard?.stocks ?? []).filter((s) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      s.ticker.toLowerCase().includes(q) ||
      (s.name ?? "").toLowerCase().includes(q)
    );
  });

  const { data: detail } = useQuery<PerTickerResponse>({
    queryKey: ["short-interest-detail", activeTicker],
    queryFn: () => fetchAPI(`/short-interest/${activeTicker}?days=60`),
    enabled: !!activeTicker,
  });

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <TrendingDown className="w-4 h-4" />
          Edge
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">Short Interest</h1>
        <p className="text-sm text-muted mt-1">
          Daily short volume from FINRA Reg SHO, ranked by 30-day average short
          volume %. The higher the bar, the more of each day&apos;s trading
          volume is short selling.
        </p>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search ticker or company…"
            className="pl-9 pr-3 py-1.5 rounded-md bg-surface border border-border text-sm focus:border-accent focus:outline-none w-64"
          />
        </div>
        <span className="text-xs text-muted">Show top:</span>
        {LIMIT_OPTIONS.map((n) => (
          <button
            key={n}
            onClick={() => setLimit(n)}
            className={cn(
              "px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors",
              limit === n
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-hover"
            )}
          >
            {n}
          </button>
        ))}
        {leaderboard && (
          <span className="text-xs text-muted ml-auto">
            {filtered.length} of {leaderboard.total} ranked
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <p className="text-sm text-foreground">No tickers match</p>
          <p className="text-xs text-muted mt-1">
            Try clearing the search box or expanding the leaderboard size.
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface/50 border-b border-border">
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted w-10">#</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Ticker</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Company</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted w-[35%]">30-Day Avg Short Vol %</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Price</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Market Cap</th>
                <th className="w-12" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((s, i) => {
                const pct = (s.days_to_cover ?? 0) * 100;
                const isActive = activeTicker === s.ticker;
                return (
                  <tr
                    key={s.ticker}
                    className={cn(
                      "border-b border-border last:border-b-0 transition-colors cursor-pointer",
                      isActive ? "bg-accent/5" : "hover:bg-surface/80"
                    )}
                    onClick={() => setActiveTicker(isActive ? null : s.ticker)}
                  >
                    <td className="px-4 py-2.5 text-[11px] font-mono text-muted">{i + 1}</td>
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/companies/${s.ticker}`}
                        onClick={(e) => e.stopPropagation()}
                        className="font-semibold text-[13px] text-accent hover:underline"
                      >
                        {s.ticker}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5 text-[12px] text-muted truncate max-w-[260px]">
                      {s.name}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-3">
                        <div className="flex-1 h-1.5 rounded-full bg-surface/80 overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-negative/50 to-negative rounded-full"
                            style={{ width: `${Math.min(100, pct)}%` }}
                          />
                        </div>
                        <span className="font-mono text-[12px] font-semibold text-negative w-12 text-right">
                          {pct.toFixed(1)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px]">
                      {s.price != null ? `$${s.price.toFixed(2)}` : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px] text-muted">
                      {formatMarketCap(s.market_cap)}
                    </td>
                    <td className="px-4 py-2.5 text-right text-[10px] text-muted">
                      {isActive ? "▾" : "▸"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Per-ticker drill-down */}
      {activeTicker && (
        <div className="rounded-lg border border-border p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-xs uppercase tracking-widest text-muted">
                Daily detail
              </p>
              <h2 className="text-lg font-bold tracking-tight">
                {activeTicker} short volume — last 60 days
              </h2>
            </div>
            <button
              onClick={() => setActiveTicker(null)}
              className="text-xs text-muted hover:text-foreground"
            >
              Close
            </button>
          </div>
          {!detail ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-accent" />
            </div>
          ) : detail.items.length === 0 ? (
            <p className="text-sm text-muted text-center py-12">
              No daily rows for {activeTicker} yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="bg-surface/50 border-b border-border">
                    <th className="text-left px-3 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">Date</th>
                    <th className="text-right px-3 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">Short Volume</th>
                    <th className="text-right px-3 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">Total Volume</th>
                    <th className="text-left px-3 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted w-[40%]">Short %</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.items
                    .slice()
                    .sort((a, b) => (b.date || "").localeCompare(a.date || ""))
                    .map((row, i) => {
                      const pct = (row.short_pct ?? 0) * 100;
                      return (
                        <tr key={i} className="border-b border-border/50 last:border-b-0">
                          <td className="px-3 py-1.5 font-mono text-muted">{row.date}</td>
                          <td className="px-3 py-1.5 text-right font-mono">
                            {row.short_volume?.toLocaleString(undefined, { maximumFractionDigits: 0 }) || "—"}
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono text-muted">
                            {row.total_volume?.toLocaleString(undefined, { maximumFractionDigits: 0 }) || "—"}
                          </td>
                          <td className="px-3 py-1.5">
                            <div className="flex items-center gap-2">
                              <div className="flex-1 h-1 rounded-full bg-surface overflow-hidden">
                                <div
                                  className="h-full bg-negative/70 rounded-full"
                                  style={{ width: `${Math.min(100, pct)}%` }}
                                />
                              </div>
                              <span className="font-mono text-[11px] text-negative w-10 text-right">
                                {pct.toFixed(1)}%
                              </span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
