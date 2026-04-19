"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  ChevronLeft,
  ChevronRight,
  Calendar,
  Loader2,
  ExternalLink,
  FlaskConical,
  Clock,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatCatalystDate } from "@/lib/utils";

interface CatalystItem {
  id: number;
  company_ticker: string;
  drug_id: string | null;
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

interface CalendarData {
  year: number;
  month: number;
  days: Record<string, CatalystItem[]>;
  total_catalysts: number;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function CatalystsPage() {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [minSignificance, setMinSignificance] = useState(1);

  const { data: calendarData, isLoading } = useQuery<CalendarData>({
    queryKey: ["calendar", year, month],
    queryFn: () => fetchAPI(`/catalysts/calendar?year=${year}&month=${month}`),
  });

  const prevMonth = () => {
    if (month === 1) { setMonth(12); setYear(year - 1); }
    else setMonth(month - 1);
    setSelectedDate(null);
  };

  const nextMonth = () => {
    if (month === 12) { setMonth(1); setYear(year + 1); }
    else setMonth(month + 1);
    setSelectedDate(null);
  };

  // Build calendar grid
  const firstDay = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();
  const weeks: (number | null)[][] = [];
  let currentWeek: (number | null)[] = Array(firstDay).fill(null);

  for (let d = 1; d <= daysInMonth; d++) {
    currentWeek.push(d);
    if (currentWeek.length === 7) {
      weeks.push(currentWeek);
      currentWeek = [];
    }
  }
  if (currentWeek.length > 0) {
    while (currentWeek.length < 7) currentWeek.push(null);
    weeks.push(currentWeek);
  }

  const filterCatalysts = (list: CatalystItem[]) =>
    list.filter((c) => (c.significance_score ?? 0) >= minSignificance);

  const selectedCatalysts = selectedDate && calendarData
    ? filterCatalysts(calendarData.days[selectedDate] || [])
    : [];

  const allMonthCatalysts = calendarData
    ? filterCatalysts(Object.values(calendarData.days).flat())
        .sort((a, b) => (a.expected_date || "").localeCompare(b.expected_date || ""))
    : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <p className="text-sm font-medium text-accent">Catalysts</p>
        <h1 className="text-3xl font-bold tracking-tight mt-1">
          Event Calendar
        </h1>
        <p className="text-sm text-muted mt-1">
          {calendarData
            ? `${calendarData.total_catalysts} events in ${MONTH_NAMES[month - 1]} ${year}`
            : "Loading..."}
        </p>
      </div>

      {/* Filter pills */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted mr-1">Filter:</span>
        {[
          { label: "All", value: 1 },
          { label: "Medium+", value: 3 },
          { label: "High+", value: 5 },
          { label: "Critical", value: 7 },
        ].map((f) => (
          <button
            key={f.value}
            onClick={() => setMinSignificance(f.value)}
            className={cn(
              "px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors",
              minSignificance === f.value
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-hover"
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Calendar */}
      <div className="rounded-lg border border-border overflow-x-auto">
        {/* Month navigation */}
        <div className="flex items-center justify-between px-5 py-3 bg-surface/50 border-b border-border">
          <button onClick={prevMonth} className="p-1.5 rounded-md hover:bg-surface-hover transition">
            <ChevronLeft className="w-4 h-4" />
          </button>
          <h2 className="text-sm font-semibold uppercase tracking-wider">
            {MONTH_NAMES[month - 1]} {year}
          </h2>
          <button onClick={nextMonth} className="p-1.5 rounded-md hover:bg-surface-hover transition">
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-5 h-5 animate-spin text-accent" />
          </div>
        ) : (
          <>
            {/* Day headers */}
            <div className="grid grid-cols-7 border-b border-border bg-surface/30">
              {DAY_NAMES.map((day) => (
                <div key={day} className="px-2 py-2 text-center text-[10px] font-semibold text-muted uppercase tracking-widest">
                  {day}
                </div>
              ))}
            </div>

            {/* Calendar grid */}
            {weeks.map((week, wi) => (
              <div key={wi} className="grid grid-cols-7 border-b border-border last:border-b-0">
                {week.map((day, di) => {
                  if (day === null) {
                    return <div key={di} className="min-h-[85px] bg-background/20" />;
                  }

                  const dateStr = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
                  const dayCatalysts = filterCatalysts(calendarData?.days[dateStr] || []);
                  const isToday = day === today.getDate() && month === today.getMonth() + 1 && year === today.getFullYear();
                  const isSelected = selectedDate === dateStr;
                  const hasCatalysts = dayCatalysts.length > 0;

                  return (
                    <div
                      key={di}
                      onClick={() => setSelectedDate(isSelected ? null : dateStr)}
                      className={cn(
                        "min-h-[85px] p-2 cursor-pointer transition-all border-r border-border last:border-r-0",
                        isSelected
                          ? "bg-accent/10 ring-1 ring-inset ring-accent/30"
                          : hasCatalysts
                            ? "hover:bg-surface-hover"
                            : "hover:bg-surface-hover/30"
                      )}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span
                          className={cn(
                            "text-xs w-6 h-6 flex items-center justify-center rounded-full",
                            isToday && "bg-accent text-black font-bold",
                            !isToday && !hasCatalysts && "text-muted",
                            !isToday && hasCatalysts && "font-semibold"
                          )}
                        >
                          {day}
                        </span>
                      </div>
                      {/* Catalyst previews */}
                      <div className="space-y-0.5">
                        {dayCatalysts.slice(0, 2).map((c, ci) => (
                          <div
                            key={ci}
                            className={cn(
                              "text-[10px] px-1.5 py-0.5 rounded truncate",
                              (c.significance_score ?? 0) >= 7
                                ? "bg-negative/15 text-negative"
                                : (c.significance_score ?? 0) >= 5
                                  ? "bg-warning/15 text-warning"
                                  : "bg-accent/10 text-accent"
                            )}
                          >
                            {c.company_ticker}
                          </div>
                        ))}
                        {dayCatalysts.length > 2 && (
                          <p className="text-[10px] text-muted px-1.5">
                            +{dayCatalysts.length - 2} more
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ))}
          </>
        )}
      </div>

      {/* Selected date detail */}
      {selectedDate && selectedCatalysts.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted mb-3">
            {new Date(selectedDate + "T12:00:00").toLocaleDateString("en-US", {
              weekday: "long",
              month: "long",
              day: "numeric",
            })}
          </h3>
          <div className="space-y-2">
            {selectedCatalysts.map((c) => (
              <CatalystRow key={c.id} catalyst={c} />
            ))}
          </div>
        </div>
      )}

      {/* Full month list */}
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted mb-3">
          All Events &mdash; {MONTH_NAMES[month - 1]} {year}
          <span className="font-normal ml-2">({allMonthCatalysts.length})</span>
        </h3>
        {allMonthCatalysts.length > 0 ? (
          <div className="rounded-lg border border-border overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface/50 border-b border-border">
                  <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Date</th>
                  <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Company</th>
                  <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Event</th>
                  <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Impact</th>
                  <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Confidence</th>
                  <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted w-8"></th>
                </tr>
              </thead>
              <tbody>
                {allMonthCatalysts.map((c) => (
                  <tr key={c.id} className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors">
                    <td className="px-4 py-3 text-xs font-mono text-muted whitespace-nowrap">{formatCatalystDate(c.expected_date, c.date_precision)}</td>
                    <td className="px-4 py-3">
                      <Link href={`/companies/${c.company_ticker}`} className="font-semibold text-[13px] text-accent hover:underline">
                        {c.company_ticker}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-[13px] max-w-[300px] truncate">{c.event_description}</td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        "text-[11px] font-semibold px-2 py-0.5 rounded",
                        (c.significance_score ?? 0) >= 7
                          ? "bg-negative/10 text-negative"
                          : (c.significance_score ?? 0) >= 5
                            ? "bg-warning/10 text-warning"
                            : "bg-accent/10 text-accent"
                      )}>
                        {(c.significance_score ?? 0) >= 7 ? "HIGH" : (c.significance_score ?? 0) >= 5 ? "MEDIUM" : "LOW"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        "text-[11px] px-2 py-0.5 rounded",
                        c.confidence === "HIGH"
                          ? "bg-positive/10 text-positive"
                          : c.confidence === "MEDIUM"
                            ? "bg-warning/10 text-warning"
                            : "bg-surface-hover text-muted"
                      )}>
                        {c.confidence}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {c.source_url && (
                        <a href={c.source_url} target="_blank" rel="noopener noreferrer" className="text-muted hover:text-accent">
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="rounded-lg border border-border border-dashed p-12 text-center">
            <Clock className="w-6 h-6 text-muted/30 mx-auto mb-2" />
            <p className="text-sm text-muted">No catalysts found for this month</p>
            <p className="text-xs text-muted/60 mt-1">Try changing months or lowering the filter</p>
          </div>
        )}
      </div>
    </div>
  );
}

function CatalystRow({ catalyst: c }: { catalyst: CatalystItem }) {
  return (
    <Link
      href={`/companies/${c.company_ticker}`}
      className="flex items-center gap-4 p-3 rounded-lg border border-border hover:border-accent/30 hover:bg-surface-hover transition-all group"
    >
      <div className={cn(
        "w-2 h-8 rounded-full shrink-0",
        (c.significance_score ?? 0) >= 7
          ? "bg-negative"
          : (c.significance_score ?? 0) >= 5
            ? "bg-warning"
            : "bg-accent"
      )} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm group-hover:text-accent transition-colors">
            {c.company_ticker}
          </span>
          {c.drug_name && (
            <span className="text-xs text-muted">&middot; {c.drug_name}</span>
          )}
        </div>
        <p className="text-xs text-muted mt-0.5 truncate">{c.event_description}</p>
      </div>
      <div className="text-right shrink-0">
        <span className={cn(
          "text-[11px] font-semibold px-2 py-0.5 rounded",
          (c.significance_score ?? 0) >= 7
            ? "bg-negative/10 text-negative"
            : (c.significance_score ?? 0) >= 5
              ? "bg-warning/10 text-warning"
              : "bg-accent/10 text-accent"
        )}>
          {(c.significance_score ?? 0) >= 7 ? "HIGH" : (c.significance_score ?? 0) >= 5 ? "MEDIUM" : "LOW"}
        </span>
      </div>
    </Link>
  );
}
