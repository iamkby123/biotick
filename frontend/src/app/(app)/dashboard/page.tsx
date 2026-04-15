"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Search,
  Calendar,
  FlaskConical,
  Star,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Clock,
  Database,
  Activity,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatMarketCap, formatPrice, formatPercent } from "@/lib/utils";
import type { CompanyListResponse } from "@/lib/types";

interface Mover {
  ticker: string;
  name: string;
  price: number;
  change: number;
  market_cap: number | null;
}

interface CatalystItem {
  company_ticker: string;
  drug_name: string | null;
  event_description: string | null;
  expected_date: string | null;
  significance_score: number | null;
}

export default function DashboardPage() {
  const { data: topCompanies } = useQuery<CompanyListResponse>({
    queryKey: ["dashboard-top"],
    queryFn: () => fetchAPI("/companies?sort_by=market_cap&sort_dir=desc&per_page=6"),
  });

  const { data: catalysts } = useQuery<{ catalysts: CatalystItem[] }>({
    queryKey: ["dashboard-catalysts"],
    queryFn: () => fetchAPI("/catalysts/upcoming?days=30&min_significance=3"),
  });

  const { data: moversData } = useQuery<{ gainers: Mover[]; losers: Mover[] }>({
    queryKey: ["movers"],
    queryFn: () => fetchAPI("/edge/movers"),
  });

  return (
    <div className="space-y-8">
      {/* Hero */}
      <div className="flex items-end justify-between">
        <div>
          <p className="text-sm font-medium text-accent">Dashboard</p>
          <h1 className="text-3xl font-bold tracking-tight mt-1">Overview</h1>
        </div>
        <Link
          href="/companies"
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-black font-semibold text-sm hover:bg-accent-hover transition-colors"
        >
          <Search className="w-4 h-4" />
          Browse Companies
        </Link>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Companies"
          value={topCompanies?.total?.toString() || "—"}
          icon={Database}
          href="/companies"
        />
        <StatCard
          label="Catalysts"
          value={catalysts?.catalysts?.length?.toString() || "—"}
          sublabel="next 30 days"
          icon={Calendar}
          href="/catalysts"
        />
        <StatCard
          label="Pipelines"
          value="644"
          sublabel="drug programs"
          icon={FlaskConical}
          href="/companies"
        />
        <StatCard
          label="Watchlist"
          value="0"
          sublabel="tracked"
          icon={Star}
          href="/watchlist"
        />
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Top Biotech — takes 2 cols */}
        <div className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
              Top Biotech Companies
            </h2>
            <Link
              href="/companies"
              className="text-xs text-accent hover:underline flex items-center gap-1"
            >
              View all <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface/50">
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-muted uppercase">Company</th>
                  <th className="text-right px-4 py-2.5 text-xs font-medium text-muted uppercase">Price</th>
                  <th className="text-right px-4 py-2.5 text-xs font-medium text-muted uppercase">Change</th>
                  <th className="text-right px-4 py-2.5 text-xs font-medium text-muted uppercase">Market Cap</th>
                </tr>
              </thead>
              <tbody>
                {topCompanies?.companies?.map((c, i) => (
                  <tr
                    key={c.ticker}
                    className={cn(
                      "hover:bg-surface-hover transition-colors",
                      i < (topCompanies?.companies?.length ?? 0) - 1 && "border-b border-border"
                    )}
                  >
                    <td className="px-4 py-3">
                      <Link href={`/companies/${c.ticker}`} className="flex items-center gap-3 group">
                        <div className="w-8 h-8 rounded-md bg-surface-hover flex items-center justify-center text-[11px] font-bold text-accent">
                          {c.ticker.slice(0, 3)}
                        </div>
                        <div>
                          <p className="font-medium text-sm group-hover:text-accent transition-colors">{c.ticker}</p>
                          <p className="text-[11px] text-muted truncate max-w-[160px]">{c.name}</p>
                        </div>
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-sm">{formatPrice(c.price)}</td>
                    <td className="px-4 py-3 text-right">
                      <span className={cn(
                        "font-mono text-xs font-semibold px-1.5 py-0.5 rounded",
                        (c.price_change_pct ?? 0) >= 0 ? "text-positive bg-positive/10" : "text-negative bg-negative/10"
                      )}>
                        {formatPercent(c.price_change_pct)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-sm text-muted">{formatMarketCap(c.market_cap)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Upcoming Catalysts */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
              Upcoming Catalysts
            </h2>
            <Link href="/catalysts" className="text-xs text-accent hover:underline flex items-center gap-1">
              Calendar <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          <div className="space-y-2">
            {catalysts?.catalysts && catalysts.catalysts.length > 0 ? (
              catalysts.catalysts.slice(0, 7).map((c, i) => (
                <Link
                  key={i}
                  href={`/companies/${c.company_ticker}`}
                  className="flex items-start gap-3 p-3 rounded-lg border border-border hover:border-accent/30 hover:bg-surface-hover transition-all group"
                >
                  <div className={cn(
                    "w-2 h-2 rounded-full mt-1.5 shrink-0",
                    (c.significance_score ?? 0) >= 7 ? "bg-negative" : (c.significance_score ?? 0) >= 5 ? "bg-warning" : "bg-accent"
                  )} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-semibold group-hover:text-accent transition-colors">{c.company_ticker}</p>
                      <span className="text-[10px] text-muted font-mono">{c.expected_date}</span>
                    </div>
                    <p className="text-xs text-muted line-clamp-1 mt-0.5">{c.event_description}</p>
                  </div>
                </Link>
              ))
            ) : (
              <div className="rounded-lg border border-border border-dashed p-8 text-center">
                <Clock className="w-5 h-5 text-muted/40 mx-auto mb-2" />
                <p className="text-xs text-muted">No upcoming catalysts</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Top Movers */}
      {moversData && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Gainers */}
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-positive" />
              Top Gainers
            </h2>
            <div className="rounded-lg border border-border overflow-hidden">
              {moversData.gainers.slice(0, 5).map((m, i) => (
                <Link
                  key={m.ticker}
                  href={`/companies/${m.ticker}`}
                  className={cn(
                    "flex items-center justify-between px-4 py-2.5 hover:bg-surface-hover transition-colors",
                    i < 4 && "border-b border-border"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold w-12">{m.ticker}</span>
                    <span className="text-[11px] text-muted truncate max-w-[120px]">{m.name}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-sm">${m.price.toFixed(2)}</span>
                    <span className="text-xs font-semibold text-positive bg-positive/10 px-1.5 py-0.5 rounded">
                      +{m.change.toFixed(1)}%
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Losers */}
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted mb-3 flex items-center gap-2">
              <TrendingDown className="w-4 h-4 text-negative" />
              Top Losers
            </h2>
            <div className="rounded-lg border border-border overflow-hidden">
              {moversData.losers.slice(0, 5).map((m, i) => (
                <Link
                  key={m.ticker}
                  href={`/companies/${m.ticker}`}
                  className={cn(
                    "flex items-center justify-between px-4 py-2.5 hover:bg-surface-hover transition-colors",
                    i < 4 && "border-b border-border"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold w-12">{m.ticker}</span>
                    <span className="text-[11px] text-muted truncate max-w-[120px]">{m.name}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-sm">${m.price.toFixed(2)}</span>
                    <span className="text-xs font-semibold text-negative bg-negative/10 px-1.5 py-0.5 rounded">
                      {m.change.toFixed(1)}%
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  sublabel,
  icon: Icon,
  href,
  accent,
}: {
  label: string;
  value: string;
  sublabel?: string;
  icon: React.ComponentType<{ className?: string }>;
  href: string;
  accent?: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-lg border p-4 transition-all duration-150 group",
        accent
          ? "border-accent/30 bg-accent/5 hover:bg-accent/10"
          : "border-border bg-surface hover:border-accent/20 hover:bg-surface-hover"
      )}
    >
      <div className="flex items-center justify-between mb-3">
        <Icon className={cn("w-4 h-4", accent ? "text-accent" : "text-muted")} />
        <ArrowRight className="w-3 h-3 text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
      <p className="text-2xl font-bold tracking-tight">{value}</p>
      <p className="text-xs text-muted mt-0.5">{sublabel || label}</p>
    </Link>
  );
}
