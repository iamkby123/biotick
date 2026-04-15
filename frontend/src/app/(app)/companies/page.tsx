"use client";

import { useState, useCallback } from "react";
import { useCompanies } from "@/hooks/useCompanies";
import CompanyTable from "@/components/companies/CompanyTable";
import ScreenerFilters, {
  getMarketCapBounds,
} from "@/components/companies/ScreenerFilters";
import { ChevronLeft, ChevronRight, Loader2, Search } from "lucide-react";

export default function CompaniesPage() {
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
    perPage: 50,
  });

  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortDir("desc");
    }
    setPage(1);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <p className="text-sm font-medium text-accent">Screener</p>
        <h1 className="text-3xl font-bold tracking-tight mt-1">
          Biotech Companies
        </h1>
        <p className="text-sm text-muted mt-1">
          {data ? `${data.total.toLocaleString()} companies` : "Loading..."}
        </p>
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

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
          <span className="ml-2 text-sm text-muted">Loading companies...</span>
        </div>
      ) : error ? (
        <div className="rounded-lg border border-negative/20 bg-negative/5 p-6 text-center">
          <p className="text-negative text-sm font-medium">Failed to load companies</p>
          <p className="text-xs text-muted mt-1">Make sure the backend is running at localhost:8000</p>
        </div>
      ) : (
        <>
          <CompanyTable
            companies={data?.companies || []}
            onSort={handleSort}
            sortBy={sortBy}
            sortDir={sortDir}
          />

          {/* Pagination */}
          {data && data.total_pages > 1 && (
            <div className="flex items-center justify-between pt-2">
              <p className="text-xs text-muted">
                Page {data.page} of {data.total_pages}
              </p>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage(Math.max(1, page - 1))}
                  disabled={page <= 1}
                  className="p-1.5 rounded-md border border-border hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed transition text-sm"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                {/* Page numbers */}
                {Array.from({ length: Math.min(5, data.total_pages) }, (_, i) => {
                  const p = Math.max(1, Math.min(page - 2, data.total_pages - 4)) + i;
                  if (p > data.total_pages) return null;
                  return (
                    <button
                      key={p}
                      onClick={() => setPage(p)}
                      className={`w-8 h-8 rounded-md text-xs font-medium transition ${
                        p === page
                          ? "bg-accent text-black"
                          : "hover:bg-surface-hover text-muted"
                      }`}
                    >
                      {p}
                    </button>
                  );
                })}
                <button
                  onClick={() => setPage(Math.min(data.total_pages, page + 1))}
                  disabled={page >= data.total_pages}
                  className="p-1.5 rounded-md border border-border hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed transition text-sm"
                >
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
