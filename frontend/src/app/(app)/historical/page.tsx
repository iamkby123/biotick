"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  History,
  Loader2,
  ExternalLink,
  TrendingUp,
  TrendingDown,
  Filter,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatMarketCap, formatPrice } from "@/lib/utils";
import { PaywallGate } from "@/components/PaywallGate";
import { usePlan } from "@/hooks/usePlan";

interface HistoricalCatalyst {
  id: number;
  ticker: string;
  company_name: string | null;
  current_price: number | null;
  market_cap: number | null;
  drug_name: string | null;
  drug_id: string | null;
  event_type: string;
  event_description: string | null;
  catalyst_date: string | null;
  date_precision: string | null;
  significance_score: number | null;
  confidence: string | null;
  outcome: string | null;
  source: string | null;
  source_url: string | null;
}

interface HistResponse {
  catalysts: HistoricalCatalyst[];
  total: number;
  page: number;
  total_pages: number;
}

const EVENT_LABELS: Record<string, string> = {
  DATA_READOUT: "Data Readout",
  FDA_APPROVAL: "FDA Approval",
  PDUFA: "PDUFA Date",
  ADVISORY_COMMITTEE: "AdCom",
  PHASE_TRANSITION: "Phase Advance",
};

const OUTCOME_STYLES: Record<string, { color: string; bg: string; label: string }> = {
  POSITIVE: { color: "text-positive", bg: "bg-positive/10", label: "Positive" },
  NEGATIVE: { color: "text-negative", bg: "bg-negative/10", label: "Negative" },
  MIXED: { color: "text-warning", bg: "bg-warning/10", label: "Mixed" },
  PENDING: { color: "text-muted", bg: "bg-surface-hover", label: "Pending" },
};

const SHORT_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "TBD";
  const d = new Date(dateStr + "T12:00:00");
  return `${SHORT_MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

export default function HistoricalCatalystsPage() {
  const [page, setPage] = useState(1);
  const [minSig, setMinSig] = useState(5);
  const [eventType, setEventType] = useState<string | null>(null);
  const { isPro } = usePlan();

  const { data, isLoading } = useQuery<HistResponse>({
    queryKey: ["historical-catalysts", page, minSig, eventType],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("per_page", "30");
      params.set("min_significance", String(minSig));
      if (eventType) params.set("event_type", eventType);
      return fetchAPI(`/historical/catalysts?${params}`);
    },
  });

  const catalysts = data?.catalysts || [];

  const content = (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <History className="w-4 h-4" />
          Historical
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">
          Historical Catalysts
        </h1>
        <p className="text-sm text-muted mt-1">
          Past FDA decisions, data readouts, and clinical trial milestones across biotech.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted">Significance:</span>
        {[
          { label: "All", value: 1 },
          { label: "Medium+", value: 3 },
          { label: "High+", value: 5 },
          { label: "Critical", value: 7 },
        ].map((f) => (
          <button
            key={f.value}
            onClick={() => { setMinSig(f.value); setPage(1); }}
            className={cn(
              "px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors",
              minSig === f.value ? "bg-accent/15 text-accent" : "text-muted hover:text-foreground hover:bg-surface-hover"
            )}
          >
            {f.label}
          </button>
        ))}

        <div className="w-px h-5 bg-border mx-1" />

        <button
          onClick={() => { setEventType(null); setPage(1); }}
          className={cn("px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors", !eventType ? "bg-accent/15 text-accent" : "text-muted hover:bg-surface-hover")}
        >
          All Types
        </button>
        {["DATA_READOUT", "FDA_APPROVAL"].map((t) => (
          <button
            key={t}
            onClick={() => { setEventType(eventType === t ? null : t); setPage(1); }}
            className={cn("px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors", eventType === t ? "bg-accent/15 text-accent" : "text-muted hover:bg-surface-hover")}
          >
            {EVENT_LABELS[t] || t}
          </button>
        ))}

        {data && <span className="text-xs text-muted ml-auto">{data.total} events</span>}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : catalysts.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <History className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">No historical catalysts found</p>
        </div>
      ) : (
        <div className="space-y-3">
          {catalysts.map((c) => {
            const outcome = OUTCOME_STYLES[c.outcome || "PENDING"] || OUTCOME_STYLES.PENDING;

            return (
              <div
                key={c.id}
                className={cn(
                  "rounded-lg border border-border p-4 transition-all hover:border-accent/20",
                  c.outcome === "POSITIVE" && "border-l-2 border-l-positive",
                  c.outcome === "NEGATIVE" && "border-l-2 border-l-negative",
                  c.outcome === "MIXED" && "border-l-2 border-l-warning"
                )}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    {/* Top row: ticker, drug, event type */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link href={`/companies/${c.ticker}`} className="font-bold text-accent hover:underline text-[15px]">
                        {c.ticker}
                      </Link>
                      <span className="text-xs text-muted">{c.company_name?.slice(0, 30)}</span>
                      <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded", outcome.bg, outcome.color)}>
                        {outcome.label}
                      </span>
                      <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-surface-hover text-muted">
                        {EVENT_LABELS[c.event_type] || c.event_type}
                      </span>
                    </div>

                    {/* Drug + description */}
                    {c.drug_name && (
                      <p className="text-sm font-medium mt-1">{c.drug_name}</p>
                    )}
                    <p className="text-xs text-muted mt-1 line-clamp-2">{c.event_description}</p>

                    {/* Bottom row: date, significance, source */}
                    <div className="flex items-center gap-4 mt-2 flex-wrap">
                      <span className="text-[11px] font-mono text-muted">
                        {formatDate(c.catalyst_date)}
                      </span>
                      <span className={cn(
                        "text-[10px] font-semibold px-1.5 py-0.5 rounded",
                        (c.significance_score || 0) >= 7 ? "bg-negative/10 text-negative" :
                        (c.significance_score || 0) >= 5 ? "bg-warning/10 text-warning" :
                        "bg-accent/10 text-accent"
                      )}>
                        Impact: {(c.significance_score || 0) >= 7 ? "HIGH" : (c.significance_score || 0) >= 5 ? "MEDIUM" : "LOW"}
                      </span>
                      {c.source_url && (
                        <a href={c.source_url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-accent hover:underline flex items-center gap-1">
                          <ExternalLink className="w-3 h-3" />
                          {c.source || "Source"}
                        </a>
                      )}
                    </div>
                  </div>

                  {/* Right side: price + market cap */}
                  <div className="text-right shrink-0">
                    <p className="font-mono text-sm font-semibold">{formatPrice(c.current_price)}</p>
                    <p className="text-[10px] text-muted">{formatMarketCap(c.market_cap)}</p>
                  </div>
                </div>
              </div>
            );
          })}
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
    return <PaywallGate feature="Historical Catalysts">{content}</PaywallGate>;
  }
  return content;
}
