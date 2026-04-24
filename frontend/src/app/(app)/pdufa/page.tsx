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
  List as ListIcon,
  LayoutGrid,
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

// Compact per-event dot color for calendar squares
const EVENT_DOT_COLOR: Record<string, string> = {
  PDUFA: "bg-accent",
  FDA_APPROVAL: "bg-positive",
  ADVISORY_COMMITTEE: "bg-warning",
  DATA_READOUT: "bg-accent/60",
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

type ViewMode = "list" | "calendar";

export default function PDUFAPage() {
  const [view, setView] = useState<ViewMode>("calendar");
  const [showPast, setShowPast] = useState(false);
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<PDUFAResponse>({
    queryKey: ["pdufa", showPast, page, view],
    queryFn: () =>
      fetchAPI(
        // In calendar mode pull a larger window per call — a 6-month view
        // needs enough events to fill the months, and the current server
        // side page size caps at 200.
        `/pdufa?upcoming_only=${!showPast}&months_ahead=24&page=${page}&per_page=${view === "calendar" ? 200 : 50}`
      ),
  });

  const events = data?.events || [];

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

      {/* View toggle + filters */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* View toggle */}
        <div className="inline-flex rounded-md border border-border p-0.5">
          <button
            onClick={() => setView("calendar")}
            className={cn(
              "px-3 py-1.5 rounded text-[12px] font-medium inline-flex items-center gap-1.5 transition-colors",
              view === "calendar"
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground"
            )}
          >
            <LayoutGrid className="w-3.5 h-3.5" />
            Calendar
          </button>
          <button
            onClick={() => setView("list")}
            className={cn(
              "px-3 py-1.5 rounded text-[12px] font-medium inline-flex items-center gap-1.5 transition-colors",
              view === "list"
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground"
            )}
          >
            <ListIcon className="w-3.5 h-3.5" />
            List
          </button>
        </div>

        {/* Past / upcoming */}
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
          EXACT-day precision (from 8-K PDUFA announcements) are pinned to
          their specific day; month-precision events are grouped at the top
          of their month.
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
      ) : view === "calendar" ? (
        <CalendarView events={events} />
      ) : (
        <ListView events={events} />
      )}

      {/* Pagination (list view only — calendar pulls a big batch) */}
      {view === "list" && data && data.total_pages > 1 && (
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


// ─── Calendar view ─────────────────────────────────────────────────────
//
// We render a series of month cards. Each card is a traditional 7-column
// day grid with event chips inside day cells. Month-precision events get
// a dedicated "Somewhere this month" strip at the top of the card —
// pinning them to a specific day would be misleading, and clustering
// them at the top keeps the accurate-day cells clean for EXACT events.

function CalendarView({ events }: { events: PDUFAEvent[] }) {
  // Group by YYYY-MM
  const byMonth = useMemo(() => {
    const map: Record<string, PDUFAEvent[]> = {};
    for (const e of events) {
      if (!e.expected_date) continue;
      const key = e.expected_date.slice(0, 7); // YYYY-MM
      if (!map[key]) map[key] = [];
      map[key].push(e);
    }
    return map;
  }, [events]);

  // Sorted month keys (chronological)
  const monthKeys = useMemo(
    () => Object.keys(byMonth).sort(),
    [byMonth]
  );

  if (monthKeys.length === 0) {
    return (
      <div className="rounded-lg border border-border border-dashed p-16 text-center">
        <p className="text-sm text-muted">No events to plot</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
      {monthKeys.map((key) => (
        <MonthCard key={key} monthKey={key} events={byMonth[key]} />
      ))}
    </div>
  );
}


function MonthCard({
  monthKey,
  events,
}: {
  monthKey: string;
  events: PDUFAEvent[];
}) {
  const [year, monthIdx] = monthKey.split("-").map(Number);
  // monthIdx is 1-12, JS Date wants 0-11
  const firstDay = new Date(year, monthIdx - 1, 1);
  const lastDay = new Date(year, monthIdx, 0).getDate();
  const firstWeekday = firstDay.getDay(); // 0 (Sun) .. 6

  // Split EXACT-day events (pin to cell) from MONTH / QUARTER (float at top)
  const exactByDay: Record<number, PDUFAEvent[]> = {};
  const fuzzyEvents: PDUFAEvent[] = [];
  for (const e of events) {
    if (!e.expected_date) continue;
    const precision = (e.date_precision || "").toUpperCase();
    if (precision === "EXACT") {
      const day = Number(e.expected_date.slice(8, 10));
      if (!exactByDay[day]) exactByDay[day] = [];
      exactByDay[day].push(e);
    } else {
      fuzzyEvents.push(e);
    }
  }

  // Build 7 × (5 or 6) grid
  const cells: (number | null)[] = [];
  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let d = 1; d <= lastDay; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  const today = new Date();
  const isCurrentMonth =
    today.getFullYear() === year && today.getMonth() + 1 === monthIdx;

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      {/* Month header */}
      <div className="px-4 py-3 border-b border-border bg-surface/50 flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          {MONTH_NAMES[monthIdx - 1]} {year}
        </h3>
        <span className="text-[11px] font-mono text-muted">
          {events.length} event{events.length === 1 ? "" : "s"}
        </span>
      </div>

      {/* Fuzzy (month-precision) strip */}
      {fuzzyEvents.length > 0 && (
        <div className="px-3 py-2 border-b border-border/50 bg-accent/5">
          <div className="text-[9px] uppercase tracking-widest text-muted/70 mb-1.5">
            Somewhere this month
          </div>
          <div className="flex flex-wrap gap-1">
            {fuzzyEvents.slice(0, 14).map((e) => (
              <EventChip key={e.id} event={e} compact />
            ))}
            {fuzzyEvents.length > 14 && (
              <span className="text-[10px] text-muted self-center ml-1">
                +{fuzzyEvents.length - 14}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Day grid */}
      <div className="grid grid-cols-7 text-[10px] uppercase tracking-widest text-muted border-b border-border/50">
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
          <div key={d} className="px-2 py-1.5 text-center">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 auto-rows-[68px]">
        {cells.map((day, i) => {
          const isToday =
            isCurrentMonth && today.getDate() === day;
          const dayEvents = day ? exactByDay[day] || [] : [];
          return (
            <div
              key={i}
              className={cn(
                "border-b border-r border-border/40 p-1 text-[10px] overflow-hidden",
                !day && "bg-surface/20",
                isToday && "bg-accent/10"
              )}
            >
              {day && (
                <>
                  <div
                    className={cn(
                      "font-mono mb-0.5",
                      isToday ? "text-accent font-semibold" : "text-muted"
                    )}
                  >
                    {day}
                  </div>
                  <div className="flex flex-col gap-0.5">
                    {dayEvents.slice(0, 2).map((e) => (
                      <EventChip key={e.id} event={e} compact />
                    ))}
                    {dayEvents.length > 2 && (
                      <span className="text-[9px] text-muted">
                        +{dayEvents.length - 2}
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}


function EventChip({
  event,
  compact = false,
}: {
  event: PDUFAEvent;
  compact?: boolean;
}) {
  const dotColor = EVENT_DOT_COLOR[event.event_type] || "bg-muted";
  return (
    <Link
      href={`/companies/${event.company_ticker}`}
      title={`${event.company_ticker} — ${event.drug_name ?? "?"} (${event.event_type})`}
      className={cn(
        "inline-flex items-center gap-1 rounded text-accent/90 hover:text-accent",
        compact
          ? "px-1.5 py-0.5 bg-accent/10 text-[10px] max-w-full"
          : "px-2 py-1 bg-accent/10 text-[11px]"
      )}
    >
      <span className={cn("w-1 h-1 rounded-full shrink-0", dotColor)} />
      <span className="font-mono font-semibold">{event.company_ticker}</span>
      {event.drug_name && (
        <span className="text-muted truncate max-w-[90px]">
          {event.drug_name}
        </span>
      )}
    </Link>
  );
}


// ─── List view (existing table, by quarter) ─────────────────────────────

function ListView({ events }: { events: PDUFAEvent[] }) {
  const grouped: Record<string, PDUFAEvent[]> = {};
  for (const e of events) {
    if (!e.expected_date) continue;
    const d = new Date(e.expected_date + "T12:00:00");
    const q = Math.ceil((d.getMonth() + 1) / 3);
    const key = `Q${q} ${d.getFullYear()}`;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(e);
  }

  return (
    <div className="space-y-8">
      {Object.entries(grouped).map(([quarter, items]) => (
        <div key={quarter}>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3 flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-accent" />
            {quarter}
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
                  return (
                    <tr
                      key={e.id}
                      className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors"
                    >
                      <td className="px-4 py-3 text-xs font-mono text-muted whitespace-nowrap">
                        {formatCatalystDate(e.expected_date, e.date_precision)}
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          href={`/companies/${e.company_ticker}`}
                          className="font-semibold text-[13px] text-accent hover:underline"
                        >
                          {e.company_ticker}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-[13px] max-w-[150px] truncate">
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
      ))}
    </div>
  );
}
