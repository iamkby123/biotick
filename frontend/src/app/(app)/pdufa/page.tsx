"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Calendar,
  Loader2,
  ExternalLink,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Info,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatCatalystDate } from "@/lib/utils";

interface PDUFAEvent {
  id: number;
  company_ticker: string;
  drug_name: string | null;
  event_type: string;
  event_description: string | null;
  expected_date: string | null;
  date_precision: string | null;
  significance_score: number | null;
  confidence: string | null;
  source: string | null;
  source_url: string | null;
  is_past: boolean;
  outcome: string | null;
}

interface PDUFAResponse {
  events: PDUFAEvent[];
  total: number;
  page: number;
  total_pages: number;
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  PDUFA: "PDUFA Date",
  FDA_APPROVAL: "FDA Decision",
  ADVISORY_COMMITTEE: "AdCom Meeting",
  DATA_READOUT: "Data Readout",
};

const EVENT_TYPE_COLORS: Record<string, string> = {
  PDUFA: "bg-accent/15 text-accent",
  FDA_APPROVAL: "bg-positive/15 text-positive",
  ADVISORY_COMMITTEE: "bg-warning/15 text-warning",
  DATA_READOUT: "bg-accent/10 text-accent",
};

const OUTCOME_ICONS: Record<string, typeof CheckCircle2> = {
  POSITIVE: CheckCircle2,
  NEGATIVE: XCircle,
  MIXED: AlertTriangle,
};

const OUTCOME_COLORS: Record<string, string> = {
  POSITIVE: "text-positive",
  NEGATIVE: "text-negative",
  MIXED: "text-warning",
  PENDING: "text-muted",
};

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export default function PDUFAPage() {
  const [showPast, setShowPast] = useState(false);
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<PDUFAResponse>({
    queryKey: ["pdufa", showPast, page],
    queryFn: () =>
      fetchAPI(
        `/pdufa?upcoming_only=${!showPast}&months_ahead=24&page=${page}&per_page=100`
      ),
  });

  const events = data?.events || [];

  // Group events by YYYY-MM (more useful than quarter for biotech catalysts)
  const grouped = useMemo(() => {
    const map: Record<string, PDUFAEvent[]> = {};
    for (const e of events) {
      if (!e.expected_date) continue;
      const key = e.expected_date.slice(0, 7); // YYYY-MM
      if (!map[key]) map[key] = [];
      map[key].push(e);
    }
    // Sort events within each month: EXACT-precision first, then by date
    for (const k of Object.keys(map)) {
      map[k].sort((a, b) => {
        const aExact = (a.date_precision || "").toUpperCase() === "EXACT" ? 0 : 1;
        const bExact = (b.date_precision || "").toUpperCase() === "EXACT" ? 0 : 1;
        if (aExact !== bExact) return aExact - bExact;
        return (a.expected_date ?? "").localeCompare(b.expected_date ?? "");
      });
    }
    return map;
  }, [events]);

  const monthKeys = useMemo(() => Object.keys(grouped).sort(), [grouped]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <Calendar className="w-4 h-4" />
          PDUFA Calendar
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">
          FDA Action Dates
        </h1>
        <p className="text-sm text-muted mt-1">
          Upcoming PDUFA target dates, FDA approval decisions, and advisory
          committee meetings.
        </p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => { setShowPast(false); setPage(1); }}
          className={cn(
            "px-4 py-2 rounded-md text-[12px] font-medium transition-colors",
            !showPast
              ? "bg-accent/15 text-accent"
              : "text-muted hover:text-foreground hover:bg-surface-hover"
          )}
        >
          Upcoming
        </button>
        <button
          onClick={() => { setShowPast(true); setPage(1); }}
          className={cn(
            "px-4 py-2 rounded-md text-[12px] font-medium transition-colors",
            showPast
              ? "bg-accent/15 text-accent"
              : "text-muted hover:text-foreground hover:bg-surface-hover"
          )}
        >
          All (incl. past)
        </button>
        {data && (
          <span className="text-xs text-muted ml-auto">
            {data.total} events
          </span>
        )}
      </div>

      {/* Date-precision notice */}
      <div className="flex items-start gap-2 rounded-md border border-border/50 bg-surface/30 px-3 py-2 text-[11px] text-muted">
        <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-accent/70" />
        <div>
          <span className="text-foreground/80">Most dates are month-precision.</span>{" "}
          Data readouts come from ClinicalTrials.gov&apos;s Primary Completion Date
          field, which sponsors typically submit as YYYY-MM. Events with
          EXACT-day precision (from 8-K PDUFA announcements) are listed first
          within each month.
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : events.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <Clock className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">No PDUFA events found</p>
          <p className="text-xs text-muted/60 mt-1">
            Run a data sync to populate FDA calendar events.
          </p>
        </div>
      ) : (
        <div className="space-y-8">
          {monthKeys.map((key) => {
            const items = grouped[key];
            const [year, monthIdx] = key.split("-").map(Number);
            const monthLabel = `${MONTH_NAMES[monthIdx - 1]} ${year}`;
            return (
              <div key={key}>
                <h2 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3 flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-accent" />
                  {monthLabel}
                  <span className="font-normal">({items.length})</span>
                </h2>

                <div className="rounded-lg border border-border overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-surface/50 border-b border-border">
                        <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Date</th>
                        <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Company</th>
                        <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Drug</th>
                        <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Event</th>
                        <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Status</th>
                        <th className="w-8" />
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((e) => {
                        const OutcomeIcon = e.outcome ? OUTCOME_ICONS[e.outcome] : null;
                        const isExact = (e.date_precision || "").toUpperCase() === "EXACT";
                        return (
                          <tr
                            key={e.id}
                            className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors"
                          >
                            <td className="px-4 py-3 text-xs font-mono text-muted whitespace-nowrap">
                              <span className={cn(isExact && "text-accent font-semibold")}>
                                {formatCatalystDate(e.expected_date, e.date_precision)}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <Link
                                href={`/companies/${e.company_ticker}`}
                                className="font-semibold text-[13px] text-accent hover:underline"
                              >
                                {e.company_ticker}
                              </Link>
                            </td>
                            <td className="px-4 py-3 text-[13px] max-w-[200px] truncate">
                              {e.drug_name || "--"}
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={cn(
                                  "text-[11px] font-medium px-2 py-0.5 rounded",
                                  EVENT_TYPE_COLORS[e.event_type] || "bg-surface-hover text-muted"
                                )}
                              >
                                {EVENT_TYPE_LABELS[e.event_type] || e.event_type}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-1.5">
                                {OutcomeIcon && (
                                  <OutcomeIcon
                                    className={cn(
                                      "w-3.5 h-3.5",
                                      OUTCOME_COLORS[e.outcome || "PENDING"]
                                    )}
                                  />
                                )}
                                <span
                                  className={cn(
                                    "text-[11px]",
                                    OUTCOME_COLORS[e.outcome || "PENDING"]
                                  )}
                                >
                                  {e.outcome || "PENDING"}
                                </span>
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              {e.source_url && (
                                <a
                                  href={e.source_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-muted hover:text-accent"
                                >
                                  <ExternalLink className="w-3.5 h-3.5" />
                                </a>
                              )}
                            </td>
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

      {/* Pagination */}
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
