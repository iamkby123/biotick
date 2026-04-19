"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Star, Plus, Trash2, Loader2, Search, LogIn } from "lucide-react";
import { supabase } from "@/lib/supabase";
import { useAuth } from "@/lib/providers";
import { fetchAPI } from "@/lib/api";
import { cn, formatPrice, formatPercent, formatMarketCap } from "@/lib/utils";
import type { Company } from "@/lib/types";

interface WatchlistItem {
  id: string;
  ticker: string;
  notes: string | null;
  created_at: string;
}

export default function WatchlistPage() {
  const { user, loading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  const [searchInput, setSearchInput] = useState("");
  const [showSearch, setShowSearch] = useState(false);

  // Fetch watchlist from Supabase
  const { data: watchlist, isLoading } = useQuery<WatchlistItem[]>({
    queryKey: ["watchlist", user?.id],
    queryFn: async () => {
      if (!user) return [];
      const { data, error } = await supabase
        .from("watchlist")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", { ascending: false });
      if (error) throw error;
      return data || [];
    },
    enabled: !!user,
  });

  // Fetch company data for watchlist tickers
  const tickers = watchlist?.map((w) => w.ticker) || [];
  const { data: companiesData } = useQuery<{ companies: Company[] }>({
    queryKey: ["watchlist-companies", tickers],
    queryFn: async () => {
      if (tickers.length === 0) return { companies: [] };
      // Fetch each company
      const companies = await Promise.all(
        tickers.map((t) => fetchAPI<Company>(`/companies/${t}`).catch(() => null))
      );
      return { companies: companies.filter(Boolean) as Company[] };
    },
    enabled: tickers.length > 0,
  });

  // Search tickers
  const { data: searchResults } = useQuery<{ companies: Company[] }>({
    queryKey: ["watchlist-search", searchInput],
    queryFn: () => fetchAPI(`/companies?search=${encodeURIComponent(searchInput)}&per_page=5`),
    enabled: searchInput.length >= 1 && showSearch,
  });

  // Add to watchlist
  const addMutation = useMutation({
    mutationFn: async (ticker: string) => {
      if (!user) throw new Error("Not logged in");
      const { error } = await supabase
        .from("watchlist")
        .insert({ user_id: user.id, ticker });
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      setSearchInput("");
      setShowSearch(false);
    },
  });

  // Remove from watchlist
  const removeMutation = useMutation({
    mutationFn: async (ticker: string) => {
      if (!user) throw new Error("Not logged in");
      const { error } = await supabase
        .from("watchlist")
        .delete()
        .eq("user_id", user.id)
        .eq("ticker", ticker);
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  // Not logged in
  if (!authLoading && !user) {
    return (
      <div className="space-y-6">
        <div>
          <p className="text-sm font-medium text-accent">Watchlist</p>
          <h1 className="text-3xl font-bold tracking-tight mt-1">Your Stocks</h1>
        </div>
        <div className="rounded-xl border border-border border-dashed p-16 text-center">
          <Star className="w-10 h-10 text-muted/20 mx-auto mb-4" />
          <h3 className="text-lg font-semibold">Sign in to track stocks</h3>
          <p className="text-sm text-muted mt-1 max-w-sm mx-auto">
            Create an account to save your favorite biotech companies and get notified about catalysts.
          </p>
          <Link
            href="/login"
            className="inline-flex items-center gap-2 mt-4 px-5 py-2.5 rounded-lg bg-accent text-black font-semibold text-sm hover:bg-accent-hover transition-colors"
          >
            <LogIn className="w-4 h-4" />
            Sign In
          </Link>
        </div>
      </div>
    );
  }

  const companyMap = new Map(
    (companiesData?.companies || []).map((c) => [c.ticker, c])
  );

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <p className="text-sm font-medium text-accent">Watchlist</p>
          <h1 className="text-3xl font-bold tracking-tight mt-1">Your Stocks</h1>
          <p className="text-sm text-muted mt-1">
            {watchlist?.length || 0} companies tracked
          </p>
        </div>
        <button
          onClick={() => setShowSearch(!showSearch)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-black font-semibold text-sm hover:bg-accent-hover transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Stock
        </button>
      </div>

      {/* Add stock search */}
      {showSearch && (
        <div className="rounded-lg border border-accent/30 bg-surface p-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search ticker or company name..."
              autoFocus
              className="w-full pl-10 pr-4 py-2.5 bg-background border border-border rounded-lg text-sm placeholder:text-muted/50 focus:outline-none focus:ring-1 focus:ring-accent/40"
            />
          </div>
          {searchResults?.companies && searchResults.companies.length > 0 && (
            <div className="mt-2 space-y-1">
              {searchResults.companies
                .filter((c) => !tickers.includes(c.ticker))
                .map((c) => (
                  <button
                    key={c.ticker}
                    onClick={() => addMutation.mutate(c.ticker)}
                    disabled={addMutation.isPending}
                    className="flex items-center justify-between w-full px-3 py-2 rounded-md hover:bg-surface-hover transition-colors text-left"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-7 h-7 rounded bg-surface-hover flex items-center justify-center text-[10px] font-bold text-accent">
                        {c.ticker.slice(0, 2)}
                      </div>
                      <div>
                        <p className="text-sm font-medium">{c.ticker}</p>
                        <p className="text-[11px] text-muted truncate max-w-[200px]">{c.name}</p>
                      </div>
                    </div>
                    <Plus className="w-4 h-4 text-accent" />
                  </button>
                ))}
            </div>
          )}
        </div>
      )}

      {/* Watchlist table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : watchlist && watchlist.length > 0 ? (
        <div className="rounded-lg border border-border overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface/50 border-b border-border">
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Company</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Price</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Change</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Market Cap</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted w-10"></th>
              </tr>
            </thead>
            <tbody>
              {watchlist.map((item) => {
                const company = companyMap.get(item.ticker);
                return (
                  <tr key={item.id} className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors">
                    <td className="px-4 py-3">
                      <Link href={`/companies/${item.ticker}`} className="flex items-center gap-3 group">
                        <div className="w-8 h-8 rounded-md bg-surface-hover flex items-center justify-center text-[10px] font-bold text-accent">
                          {item.ticker.slice(0, 3)}
                        </div>
                        <div>
                          <p className="font-semibold text-[13px] group-hover:text-accent transition-colors">{item.ticker}</p>
                          <p className="text-[11px] text-muted truncate max-w-[180px]">{company?.name || "Loading..."}</p>
                        </div>
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-[13px]">{formatPrice(company?.price ?? null)}</td>
                    <td className="px-4 py-3 text-right">
                      <span className={cn(
                        "font-mono text-[11px] font-semibold px-1.5 py-0.5 rounded",
                        (company?.price_change_pct ?? 0) >= 0 ? "text-positive bg-positive/10" : "text-negative bg-negative/10"
                      )}>
                        {formatPercent(company?.price_change_pct ?? null)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-[13px] text-muted">
                      {formatMarketCap(company?.market_cap ?? null)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={(e) => { e.stopPropagation(); removeMutation.mutate(item.ticker); }}
                        className="p-1 rounded hover:bg-negative/10 text-muted hover:text-negative transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <Star className="w-8 h-8 text-muted/20 mx-auto mb-3" />
          <h3 className="text-sm font-semibold">No stocks tracked yet</h3>
          <p className="text-xs text-muted mt-1">Click "Add Stock" to start building your watchlist</p>
        </div>
      )}
    </div>
  );
}
