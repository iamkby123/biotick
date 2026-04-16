"use client";

import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useCompanies } from "@/hooks/useCompanies";
import CompanyTable from "@/components/companies/CompanyTable";
import ScreenerFilters, { getMarketCapBounds } from "@/components/companies/ScreenerFilters";
import { ChevronLeft, ChevronRight, Loader2, LayoutGrid, List, TrendingUp, TrendingDown } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatPrice, formatPercent, formatMarketCap } from "@/lib/utils";

interface Mover {
  ticker: string;
  name: string;
  price: number;
  change: number;
  market_cap: number | null;
}

export default function CompaniesPage() {
  const [view, setView] = useState<"heatmap" | "table">("heatmap");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [exchange, setExchange] = useState("");
  const [marketCapRange, setMarketCapRange] = useState("");
  const [sortBy, setSortBy] = useState("market_cap");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(1);

  const [searchTimeout, setSearchTimeout] = useState<NodeJS.Timeout | null>(null);
  const handleSearchChange = useCallback(
    (value: string) => {
      setSearch(value);
      if (searchTimeout) clearTimeout(searchTimeout);
      const timeout = setTimeout(() => {
        setDebouncedSearch(value);
        setPage(1);
      }, 300);
      setSearchTimeout(timeout);
    },
    [searchTimeout]
  );

  const { min: minMarketCap, max: maxMarketCap } = getMarketCapBounds(marketCapRange);

  const { data, isLoading, error } = useCompanies({
    search: debouncedSearch || undefined,
    exchange: exchange || undefined,
    minMarketCap,
    maxMarketCap,
    sortBy,
    sortDir,
    page,
    perPage: view === "heatmap" ? 200 : 50,
  });

  // Movers data for the sidebar columns
  const { data: moversData } = useQuery<{ gainers: Mover[]; losers: Mover[] }>({
    queryKey: ["movers"],
    queryFn: () => fetchAPI("/edge/movers"),
    enabled: view === "heatmap",
  });

  const handleSort = (field: string) => {
    if (sortBy === field) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortBy(field); setSortDir("desc"); }
    setPage(1);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <p className="text-sm font-medium text-accent">Screener</p>
          <h1 className="text-3xl font-bold tracking-tight mt-1">Biotech Companies</h1>
          <p className="text-sm text-muted mt-1">
            {data ? `${data.total.toLocaleString()} companies` : "Loading..."}
          </p>
        </div>
        <div className="flex items-center gap-1 bg-surface rounded-lg border border-border p-0.5">
          <button onClick={() => setView("heatmap")} className={cn("p-2 rounded-md transition", view === "heatmap" ? "bg-accent/15 text-accent" : "text-muted hover:text-foreground")}>
            <LayoutGrid className="w-4 h-4" />
          </button>
          <button onClick={() => setView("table")} className={cn("p-2 rounded-md transition", view === "table" ? "bg-accent/15 text-accent" : "text-muted hover:text-foreground")}>
            <List className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Filters */}
      <ScreenerFilters
        search={search}
        onSearchChange={handleSearchChange}
        exchange={exchange}
        onExchangeChange={(v) => { setExchange(v); setPage(1); }}
        marketCapRange={marketCapRange}
        onMarketCapRangeChange={(v) => { setMarketCapRange(v); setPage(1); }}
      />

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
          <span className="ml-2 text-sm text-muted">Loading companies...</span>
        </div>
      ) : error ? (
        <div className="rounded-lg border border-negative/20 bg-negative/5 p-6 text-center">
          <p className="text-negative text-sm font-medium">Failed to load companies</p>
        </div>
      ) : view === "heatmap" ? (
        <div className="space-y-6">
          {/* Heatmap */}
          <Heatmap companies={data?.companies || []} />

          {/* Gainers / Losers columns */}
          {moversData && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <MoversColumn title="Top Gainers" icon={TrendingUp} items={moversData.gainers} colorClass="text-positive" bgClass="bg-positive/[0.04]" />
              <MoversColumn title="Top Losers" icon={TrendingDown} items={moversData.losers} colorClass="text-negative" bgClass="bg-negative/[0.04]" />
            </div>
          )}
        </div>
      ) : (
        <>
          <CompanyTable companies={data?.companies || []} onSort={handleSort} sortBy={sortBy} sortDir={sortDir} />
          {data && data.total_pages > 1 && (
            <div className="flex items-center justify-between pt-2">
              <p className="text-xs text-muted">Page {data.page} of {data.total_pages}</p>
              <div className="flex items-center gap-1">
                <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1} className="p-1.5 rounded-md border border-border hover:bg-surface-hover disabled:opacity-30 transition text-sm">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                {Array.from({ length: Math.min(5, data.total_pages) }, (_, i) => {
                  const p = Math.max(1, Math.min(page - 2, data.total_pages - 4)) + i;
                  if (p > data.total_pages) return null;
                  return (
                    <button key={p} onClick={() => setPage(p)} className={`w-8 h-8 rounded-md text-xs font-medium transition ${p === page ? "bg-accent text-black" : "hover:bg-surface-hover text-muted"}`}>
                      {p}
                    </button>
                  );
                })}
                <button onClick={() => setPage(Math.min(data.total_pages, page + 1))} disabled={page >= data.total_pages} className="p-1.5 rounded-md border border-border hover:bg-surface-hover disabled:opacity-30 transition text-sm">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ── Heatmap ── */
function Heatmap({ companies }: { companies: Array<{ ticker: string; name: string; price: number | null; price_change_pct: number | null; market_cap: number | null }> }) {
  // Filter to companies with price data, sort by market cap
  const items = companies
    .filter((c) => c.price && c.market_cap && c.market_cap > 0)
    .sort((a, b) => (b.market_cap || 0) - (a.market_cap || 0))
    .slice(0, 100);

  if (items.length === 0) return null;

  // Calculate relative sizes using sqrt of market cap for visual balance
  const maxMcap = Math.max(...items.map((c) => c.market_cap || 0));

  function getColor(change: number | null): string {
    if (!change) return "bg-surface-hover";
    if (change >= 5) return "bg-[#15803d]";
    if (change >= 3) return "bg-[#16a34a]";
    if (change >= 1) return "bg-[#22c55e]/80";
    if (change >= 0) return "bg-[#22c55e]/40";
    if (change >= -1) return "bg-[#ef4444]/40";
    if (change >= -3) return "bg-[#ef4444]/80";
    if (change >= -5) return "bg-[#dc2626]";
    return "bg-[#b91c1c]";
  }

  function getTextColor(change: number | null): string {
    if (!change) return "text-muted";
    if (Math.abs(change) >= 1) return "text-white";
    return "text-foreground";
  }

  return (
    <div>
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">
        Market Heatmap — sized by market cap, colored by daily change
      </h2>
      <div className="flex flex-wrap gap-[2px] rounded-lg overflow-hidden">
        {items.map((c) => {
          const relSize = Math.sqrt((c.market_cap || 0) / maxMcap);
          const minPx = 50;
          const maxPx = 140;
          const size = Math.max(minPx, Math.round(relSize * maxPx));
          const change = c.price_change_pct || 0;

          return (
            <Link
              key={c.ticker}
              href={`/companies/${c.ticker}`}
              className={cn(
                "flex flex-col items-center justify-center rounded-sm transition-all hover:ring-2 hover:ring-white/20 hover:z-10",
                getColor(c.price_change_pct),
                getTextColor(c.price_change_pct)
              )}
              style={{ width: `${size}px`, height: `${size}px` }}
              title={`${c.name}\n${formatPrice(c.price)} (${formatPercent(c.price_change_pct)})\nMkt Cap: ${formatMarketCap(c.market_cap)}`}
            >
              <span className="font-bold text-[11px] leading-tight">{c.ticker}</span>
              <span className="text-[9px] font-mono leading-tight mt-0.5">
                {change >= 0 ? "+" : ""}{change.toFixed(1)}%
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

/* ── Movers Column ── */
function MoversColumn({
  title,
  icon: Icon,
  items,
  colorClass,
  bgClass,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  items: Mover[];
  colorClass: string;
  bgClass: string;
}) {
  return (
    <div>
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3 flex items-center gap-2">
        <Icon className={cn("w-4 h-4", colorClass)} />
        {title}
      </h2>
      <div className="rounded-lg border border-border overflow-hidden">
        {items.slice(0, 10).map((m, i) => (
          <Link
            key={m.ticker}
            href={`/companies/${m.ticker}`}
            className={cn(
              "flex items-center justify-between px-4 py-2.5 hover:bg-surface-hover transition-colors",
              bgClass,
              i < items.length - 1 && "border-b border-border"
            )}
          >
            <div className="flex items-center gap-3">
              <span className="text-sm font-bold w-12">{m.ticker}</span>
              <span className="text-[11px] text-muted truncate max-w-[120px]">{m.name}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm">${m.price.toFixed(2)}</span>
              <span className={cn("text-xs font-semibold px-1.5 py-0.5 rounded", colorClass, bgClass)}>
                {m.change >= 0 ? "+" : ""}{m.change.toFixed(1)}%
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
