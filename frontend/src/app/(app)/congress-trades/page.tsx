"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Landmark, Loader2, ExternalLink } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CTrade {
  id: number;
  chamber: string;
  member_name: string;
  party: string | null;
  state: string | null;
  ticker: string | null;
  trade_type: string | null;
  trade_date: string | null;
  filing_date: string | null;
  amount_min: number | null;
  amount_max: number | null;
  disclosure_url: string | null;
}

interface CTResponse {
  items: CTrade[];
  total: number;
  total_pages: number;
}

const FILTERS: { id: string | null; label: string }[] = [
  { id: null, label: "All" },
  { id: "purchase", label: "Purchases" },
  { id: "sale", label: "Sales" },
  { id: "exchange", label: "Exchanges" },
];

function formatAmount(min: number | null, max: number | null): string {
  if (min == null || max == null) return "—";
  const fmt = (n: number) => {
    if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
    return `$${n.toFixed(0)}`;
  };
  if (min === max) return fmt(min);
  return `${fmt(min)}–${fmt(max)}`;
}

const SHORT_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function shortDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + "T12:00:00");
  return `${SHORT_MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

export default function CongressTradesPage() {
  const [tradeType, setTradeType] = useState<string | null>(null);
  const [days, setDays] = useState(180);
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<CTResponse>({
    queryKey: ["congress-trades", tradeType, days, page],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("days", String(days));
      params.set("page", String(page));
      params.set("per_page", "50");
      if (tradeType) params.set("trade_type", tradeType);
      return fetchAPI(`/congress-trades?${params}`);
    },
  });

  const items = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <Landmark className="w-4 h-4" />
          Edge
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">Congressional Trades</h1>
        <p className="text-sm text-muted mt-1">
          Biotech-only trades disclosed by US House members under the STOCK
          Act. House only for now — Senate coming later.
        </p>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {FILTERS.map((f) => (
          <button
            key={f.label}
            onClick={() => {
              setTradeType(f.id);
              setPage(1);
            }}
            className={cn(
              "px-4 py-2 rounded-md text-[12px] font-medium transition-colors",
              tradeType === f.id
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-hover"
            )}
          >
            {f.label}
          </button>
        ))}
        <span className="text-xs text-muted ml-4">Window:</span>
        {[90, 180, 365].map((d) => (
          <button
            key={d}
            onClick={() => {
              setDays(d);
              setPage(1);
            }}
            className={cn(
              "px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors",
              days === d
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-hover"
            )}
          >
            {d}d
          </button>
        ))}
        {data && <span className="text-xs text-muted ml-auto">{data.total} trades</span>}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <Landmark className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">No trades in this window yet</p>
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface/50 border-b border-border">
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Trade Date</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Member</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Ticker</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Type</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Amount</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Filed</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Disclosure</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id} className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors">
                  <td className="px-4 py-3 text-[12px] font-mono text-muted">{shortDate(t.trade_date)}</td>
                  <td className="px-4 py-3 text-[13px]">
                    {t.member_name}
                    {t.party && t.state && (
                      <span className="text-[10px] text-muted ml-1.5">
                        ({t.party}-{t.state})
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {t.ticker ? (
                      <Link
                        href={`/companies/${t.ticker}`}
                        className="font-mono font-semibold text-accent hover:underline text-[13px]"
                      >
                        {t.ticker}
                      </Link>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "text-[10px] font-semibold px-2 py-0.5 rounded uppercase tracking-wider",
                        t.trade_type === "purchase" && "bg-positive/10 text-positive",
                        t.trade_type === "sale" && "bg-negative/10 text-negative",
                        t.trade_type === "exchange" && "bg-warning/10 text-warning",
                      )}
                    >
                      {t.trade_type || "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-[12px]">
                    {formatAmount(t.amount_min, t.amount_max)}
                  </td>
                  <td className="px-4 py-3 text-[11px] font-mono text-muted">{shortDate(t.filing_date)}</td>
                  <td className="px-4 py-3">
                    {t.disclosure_url && (
                      <a
                        href={t.disclosure_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-accent hover:underline text-[11px] inline-flex items-center gap-1"
                      >
                        <ExternalLink className="w-3 h-3" />
                        PTR
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 rounded text-xs text-muted hover:text-foreground disabled:opacity-30"
          >
            Previous
          </button>
          <span className="text-xs text-muted">
            Page {page} of {data.total_pages}
          </span>
          <button
            onClick={() => setPage(Math.min(data.total_pages, page + 1))}
            disabled={page === data.total_pages}
            className="px-3 py-1.5 rounded text-xs text-muted hover:text-foreground disabled:opacity-30"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
