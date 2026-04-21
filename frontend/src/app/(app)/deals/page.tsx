"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Handshake, Loader2, ExternalLink } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Deal {
  id: number;
  ticker: string | null;
  deal_type: string | null;
  counterparty: string | null;
  headline: string | null;
  summary: string | null;
  url: string | null;
  item_code: string | null;
  filed_date: string | null;
  accession_number: string;
}

interface DealsResponse {
  items: Deal[];
  total: number;
  page: number;
  total_pages: number;
}

const TYPES: { id: string | null; label: string }[] = [
  { id: null, label: "All" },
  { id: "material_agreement", label: "Agreements" },
  { id: "acquisition", label: "Acquisitions" },
  { id: "officer_change", label: "Officer Changes" },
];

const TYPE_COLORS: Record<string, string> = {
  material_agreement: "bg-accent/10 text-accent",
  acquisition: "bg-positive/10 text-positive",
  officer_change: "bg-warning/10 text-warning",
};

const SHORT_MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + "T12:00:00");
  return `${SHORT_MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

export default function DealsPage() {
  const [dealType, setDealType] = useState<string | null>(null);
  const [days, setDays] = useState(90);
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<DealsResponse>({
    queryKey: ["deals", dealType, days, page],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("days", String(days));
      params.set("page", String(page));
      params.set("per_page", "25");
      if (dealType) params.set("deal_type", dealType);
      return fetchAPI(`/deals?${params}`);
    },
  });

  const items = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <Handshake className="w-4 h-4" />
          Edge
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">Deals & Agreements</h1>
        <p className="text-sm text-muted mt-1">
          Material agreements (Item 1.01), acquisitions (2.01), and officer
          changes (5.02) parsed from 8-K filings. Counterparties auto-extracted.
        </p>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {TYPES.map((t) => (
          <button
            key={t.label}
            onClick={() => {
              setDealType(t.id);
              setPage(1);
            }}
            className={cn(
              "px-4 py-2 rounded-md text-[12px] font-medium transition-colors",
              dealType === t.id
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-hover"
            )}
          >
            {t.label}
          </button>
        ))}
        <span className="text-xs text-muted ml-4">Window:</span>
        {[30, 90, 180].map((d) => (
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
        {data && (
          <span className="text-xs text-muted ml-auto">{data.total} deals</span>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <Handshake className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">No deals in this window yet</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((d) => (
            <div
              key={d.id}
              className="rounded-lg border border-border p-4 hover:border-accent/40 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2 flex-wrap text-[11px]">
                  {d.ticker && (
                    <Link
                      href={`/companies/${d.ticker}`}
                      className="font-mono font-bold text-accent hover:underline"
                    >
                      {d.ticker}
                    </Link>
                  )}
                  {d.deal_type && (
                    <span
                      className={cn(
                        "px-2 py-0.5 rounded font-semibold uppercase tracking-wider",
                        TYPE_COLORS[d.deal_type] || "bg-surface-hover text-muted"
                      )}
                    >
                      {d.deal_type.replace(/_/g, " ")}
                    </span>
                  )}
                  {d.item_code && (
                    <span className="bg-surface-hover text-muted px-1.5 py-0.5 rounded">
                      Item {d.item_code}
                    </span>
                  )}
                </div>
                <span className="text-[11px] text-muted shrink-0">
                  {formatDate(d.filed_date)}
                </span>
              </div>
              {d.headline && (
                <h3 className="text-sm font-semibold mt-1.5">{d.headline}</h3>
              )}
              {d.counterparty && (
                <p className="text-xs text-muted mt-1">
                  Counterparty: <span className="text-foreground">{d.counterparty}</span>
                </p>
              )}
              {d.summary && (
                <p className="text-[13px] text-muted mt-2 leading-relaxed">
                  {d.summary}
                </p>
              )}
              {d.url && (
                <a
                  href={d.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline mt-2"
                >
                  <ExternalLink className="w-3 h-3" />
                  Full 8-K
                </a>
              )}
            </div>
          ))}
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
