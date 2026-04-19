"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { UserCheck, Loader2, ArrowUpRight, ArrowDownRight, Filter } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatPrice } from "@/lib/utils";
import { PaywallGate } from "@/components/PaywallGate";
import { usePlan } from "@/hooks/usePlan";

interface Trade {
  id: number;
  ticker: string;
  insider_name: string;
  insider_title: string | null;
  trade_type: string;
  transaction_date: string;
  shares: number;
  price_per_share: number | null;
  total_value: number | null;
  filing_date: string | null;
}

interface TradesResponse {
  trades: Trade[];
  total: number;
  page: number;
  total_pages: number;
}

const TRADE_COLORS: Record<string, string> = {
  PURCHASE: "text-positive bg-positive/10",
  SALE: "text-negative bg-negative/10",
  OPTION_EXERCISE: "text-warning bg-warning/10",
  GRANT: "text-accent bg-accent/10",
  GIFT: "text-muted bg-surface-hover",
  TAX_WITHHOLDING: "text-muted bg-surface-hover",
  OTHER: "text-muted bg-surface-hover",
};

const TRADE_LABELS: Record<string, string> = {
  PURCHASE: "Buy",
  SALE: "Sell",
  OPTION_EXERCISE: "Exercise",
  GRANT: "Grant",
  GIFT: "Gift",
  TAX_WITHHOLDING: "Tax",
  OTHER: "Other",
};

function formatValue(val: number | null): string {
  if (!val) return "--";
  if (val >= 1e6) return `$${(val / 1e6).toFixed(1)}M`;
  if (val >= 1e3) return `$${(val / 1e3).toFixed(0)}K`;
  return `$${val.toFixed(0)}`;
}

function formatShares(val: number): string {
  if (val >= 1e6) return `${(val / 1e6).toFixed(1)}M`;
  if (val >= 1e3) return `${(val / 1e3).toFixed(0)}K`;
  return val.toLocaleString();
}

const SHORT_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

export default function InsiderTradesPage() {
  const [filter, setFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useQuery<TradesResponse>({
    queryKey: ["all-insider-trades", filter, page],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("per_page", "50");
      params.set("sort_by", "transaction_date");
      params.set("sort_dir", "desc");
      if (filter) params.set("trade_type", filter);
      // Using /filings/form4 instead of /filings/insider-trades because
      // many ad-blockers (EasyList, AdGuard, uBlock) block URLs containing
      // "insider-trades" as "financial scraping" — even from our own API.
      return await fetchAPI(`/filings/form4?${params}`);
    },
  });

  const { isPro } = usePlan();
  const trades = data?.trades || [];

  const content = (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <UserCheck className="w-4 h-4" />
          Insider Activity
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">
          Insider Trades
        </h1>
        <p className="text-sm text-muted mt-1">
          Recent insider buying and selling across all biotech companies. Purchases highlighted in green.
        </p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        {[
          { label: "All Trades", value: null },
          { label: "Purchases", value: "PURCHASE" },
          { label: "Sales", value: "SALE" },
          { label: "Exercises", value: "OPTION_EXERCISE" },
        ].map((f) => (
          <button
            key={f.label}
            onClick={() => { setFilter(f.value); setPage(1); }}
            className={cn(
              "px-4 py-2 rounded-md text-[12px] font-medium transition-colors",
              filter === f.value
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-hover"
            )}
          >
            {f.label}
          </button>
        ))}
        {data && (
          <span className="text-xs text-muted ml-auto">{data.total} trades</span>
        )}
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : error ? (
        <div className="rounded-lg border border-negative/30 bg-negative/5 p-6 text-center">
          <p className="text-sm font-semibold text-negative">
            Couldn&apos;t load insider trades
          </p>
          <p className="text-xs text-muted mt-2 font-mono break-all">
            {error instanceof Error ? error.message : String(error)}
          </p>
          <p className="text-[11px] text-muted/70 mt-3">
            Endpoint: /proxy/filings/form4 (same-origin through Vercel)
          </p>
        </div>
      ) : trades.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <UserCheck className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">No insider trades found</p>
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface/50 border-b border-border">
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Ticker</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Insider</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Title</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Type</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Date</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Shares</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Price</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Value</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr
                  key={t.id}
                  className={cn(
                    "border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors",
                    t.trade_type === "PURCHASE" && "bg-positive/[0.03]",
                    t.trade_type === "SALE" && "bg-negative/[0.03]"
                  )}
                >
                  <td className="px-4 py-3">
                    <Link href={`/companies/${t.ticker}`} className="font-semibold text-[13px] text-accent hover:underline">
                      {t.ticker}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-[13px] max-w-[150px] truncate">{t.insider_name}</td>
                  <td className="px-4 py-3 text-xs text-muted max-w-[100px] truncate">{t.insider_title || "--"}</td>
                  <td className="px-4 py-3">
                    <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded", TRADE_COLORS[t.trade_type] || TRADE_COLORS.OTHER)}>
                      {TRADE_LABELS[t.trade_type] || t.trade_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs font-mono text-muted">{t.transaction_date}</td>
                  <td className="px-4 py-3 text-right font-mono text-sm">{formatShares(t.shares)}</td>
                  <td className="px-4 py-3 text-right font-mono text-sm">{t.price_per_share ? formatPrice(t.price_per_share) : "--"}</td>
                  <td className="px-4 py-3 text-right">
                    <span className={cn("font-mono text-sm font-medium", t.trade_type === "PURCHASE" ? "text-positive" : t.trade_type === "SALE" ? "text-negative" : "")}>
                      {formatValue(t.total_value)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1} className="px-3 py-1.5 rounded text-xs text-muted hover:text-foreground disabled:opacity-30">Previous</button>
          <span className="text-xs text-muted">Page {page} of {data.total_pages}</span>
          <button onClick={() => setPage(Math.min(data.total_pages, page + 1))} disabled={page === data.total_pages} className="px-3 py-1.5 rounded text-xs text-muted hover:text-foreground disabled:opacity-30">Next</button>
        </div>
      )}
    </div>
  );

  if (!isPro) {
    return <PaywallGate feature="Insider Trades">{content}</PaywallGate>;
  }
  return content;
}
