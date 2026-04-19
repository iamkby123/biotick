"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { DollarSign, Loader2, Calendar, Clock } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatMarketCap, formatPrice } from "@/lib/utils";
import { PaywallGate } from "@/components/PaywallGate";
import { usePlan } from "@/hooks/usePlan";

interface EarningsItem {
  ticker: string;
  name: string;
  date: string;
  hour: string;
  eps_estimate: number | null;
  eps_actual: number | null;
  revenue_estimate: number | null;
  revenue_actual: number | null;
  price: number | null;
  market_cap: number | null;
}

interface EarningsResponse {
  earnings: EarningsItem[];
  total: number;
  date_range: { start: string; end: string };
}

const RANGE_OPTIONS = [
  { label: "This Week", days: 7 },
  { label: "2 Weeks", days: 14 },
  { label: "This Month", days: 30 },
  { label: "3 Months", days: 90 },
];

function formatRevenue(val: number | null): string {
  if (!val) return "--";
  if (val >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (val >= 1e6) return `$${(val / 1e6).toFixed(0)}M`;
  return `$${val.toLocaleString()}`;
}

function formatEPS(val: number | null): string {
  if (val === null || val === undefined) return "--";
  return `$${val.toFixed(2)}`;
}

const SHORT_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00");
  return `${SHORT_MONTHS[d.getMonth()]} ${d.getDate()}`;
}

export default function EarningsPage() {
  const [rangeDays, setRangeDays] = useState(14);
  const { isPro } = usePlan();

  const today = new Date();
  const start = today.toISOString().split("T")[0];
  const end = new Date(today.getTime() + rangeDays * 86400000).toISOString().split("T")[0];

  const { data, isLoading } = useQuery<EarningsResponse>({
    queryKey: ["earnings", start, end],
    queryFn: () => fetchAPI(`/earnings?start=${start}&end=${end}`),
  });

  const earnings = data?.earnings || [];

  // Group by date
  const grouped: Record<string, EarningsItem[]> = {};
  for (const e of earnings) {
    if (!grouped[e.date]) grouped[e.date] = [];
    grouped[e.date].push(e);
  }

  const content = (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <DollarSign className="w-4 h-4" />
          Earnings
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">
          Earnings Calendar
        </h1>
        <p className="text-sm text-muted mt-1">
          Upcoming biotech earnings reports with EPS and revenue estimates.
        </p>
      </div>

      {/* Range filter */}
      <div className="flex items-center gap-2">
        {RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.days}
            onClick={() => setRangeDays(opt.days)}
            className={cn(
              "px-4 py-2 rounded-md text-[12px] font-medium transition-colors",
              rangeDays === opt.days
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-hover"
            )}
          >
            {opt.label}
          </button>
        ))}
        {data && (
          <span className="text-xs text-muted ml-auto">
            {data.total} biotech earnings
          </span>
        )}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : earnings.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <Calendar className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">No biotech earnings in this period</p>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([dateStr, items]) => {
            const d = new Date(dateStr + "T12:00:00");
            const dayName = d.toLocaleDateString("en-US", { weekday: "long" });
            const isToday = dateStr === today.toISOString().split("T")[0];

            return (
              <div key={dateStr}>
                <h2 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3 flex items-center gap-2">
                  <div className={cn("w-1.5 h-1.5 rounded-full", isToday ? "bg-accent animate-pulse" : "bg-muted/30")} />
                  {dayName}, {formatDate(dateStr)}
                  {isToday && <span className="text-accent font-bold">TODAY</span>}
                  <span className="font-normal">({items.length})</span>
                </h2>

                <div className="rounded-lg border border-border overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-surface/50 border-b border-border">
                        <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Company</th>
                        <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Time</th>
                        <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Price</th>
                        <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Mkt Cap</th>
                        <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">EPS Est</th>
                        <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">EPS Actual</th>
                        <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Rev Est</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((e) => {
                        const surprise = e.eps_actual !== null && e.eps_estimate !== null
                          ? e.eps_actual - e.eps_estimate
                          : null;
                        return (
                          <tr key={e.ticker} className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors">
                            <td className="px-4 py-3">
                              <Link href={`/companies/${e.ticker}`} className="group">
                                <span className="font-semibold text-[13px] text-accent group-hover:underline">{e.ticker}</span>
                                <span className="text-xs text-muted ml-2 hidden lg:inline">{e.name?.slice(0, 25)}</span>
                              </Link>
                            </td>
                            <td className="px-4 py-3">
                              <span className={cn(
                                "text-[10px] font-semibold px-2 py-0.5 rounded",
                                e.hour === "bmo" ? "bg-warning/10 text-warning" :
                                e.hour === "amc" ? "bg-accent/10 text-accent" :
                                "bg-surface-hover text-muted"
                              )}>
                                {e.hour === "bmo" ? "Pre-Market" : e.hour === "amc" ? "After Hours" : "TBD"}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-right font-mono text-sm">{formatPrice(e.price)}</td>
                            <td className="px-4 py-3 text-right font-mono text-xs text-muted">{formatMarketCap(e.market_cap)}</td>
                            <td className="px-4 py-3 text-right font-mono text-sm">{formatEPS(e.eps_estimate)}</td>
                            <td className="px-4 py-3 text-right">
                              {e.eps_actual !== null ? (
                                <div>
                                  <span className="font-mono text-sm">{formatEPS(e.eps_actual)}</span>
                                  {surprise !== null && (
                                    <span className={cn(
                                      "ml-1 text-[10px] font-semibold",
                                      surprise >= 0 ? "text-positive" : "text-negative"
                                    )}>
                                      {surprise >= 0 ? "+" : ""}{surprise.toFixed(2)}
                                    </span>
                                  )}
                                </div>
                              ) : (
                                <span className="text-xs text-muted">--</span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-right font-mono text-xs text-muted">{formatRevenue(e.revenue_estimate)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  if (!isPro) {
    return <PaywallGate feature="Earnings Calendar">{content}</PaywallGate>;
  }
  return content;
}
