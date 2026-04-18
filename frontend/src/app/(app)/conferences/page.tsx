"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  MapPin,
  Calendar,
  ExternalLink,
  Loader2,
  Globe,
  Users,
  Filter,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PaywallGate } from "@/components/PaywallGate";
import { usePlan } from "@/hooks/usePlan";

interface Conference {
  id: number;
  name: string;
  short_name: string | null;
  organizer: string | null;
  start_date: string;
  end_date: string;
  location: string | null;
  city: string | null;
  country: string | null;
  description: string | null;
  website: string | null;
  category: string | null;
  significance: number;
  is_virtual: boolean;
}

interface ConferenceResponse {
  conferences: Conference[];
  total: number;
  page: number;
  total_pages: number;
}

const CATEGORY_COLORS: Record<string, string> = {
  Oncology: "bg-negative/10 text-negative",
  Hematology: "bg-[#c084fc]/10 text-[#c084fc]",
  Neurology: "bg-accent/10 text-accent",
  Immunology: "bg-positive/10 text-positive",
  Metabolic: "bg-warning/10 text-warning",
  Investor: "bg-[#60a5fa]/10 text-[#60a5fa]",
  Industry: "bg-[#34d399]/10 text-[#34d399]",
  "Rare Disease": "bg-[#f472b6]/10 text-[#f472b6]",
  Hepatology: "bg-[#fb923c]/10 text-[#fb923c]",
};

const SHORT_MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function formatDateRange(start: string, end: string): string {
  const s = new Date(start + "T12:00:00");
  const e = new Date(end + "T12:00:00");

  const sMonth = SHORT_MONTHS[s.getMonth()];
  const eMonth = SHORT_MONTHS[e.getMonth()];

  if (sMonth === eMonth) {
    return `${sMonth} ${s.getDate()}\u2013${e.getDate()}, ${s.getFullYear()}`;
  }
  return `${sMonth} ${s.getDate()} \u2013 ${eMonth} ${e.getDate()}, ${s.getFullYear()}`;
}

function daysUntil(dateStr: string): number {
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const target = new Date(dateStr + "T12:00:00");
  return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

export default function ConferencesPage() {
  const [showPast, setShowPast] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const { isPro } = usePlan();

  const { data, isLoading } = useQuery<ConferenceResponse>({
    queryKey: ["conferences", showPast, categoryFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("upcoming_only", String(!showPast));
      params.set("per_page", "100");
      if (categoryFilter) params.set("category", categoryFilter);
      return fetchAPI(`/conferences?${params}`);
    },
  });

  const conferences = data?.conferences || [];

  // Group by quarter
  const grouped: Record<string, Conference[]> = {};
  for (const c of conferences) {
    const d = new Date(c.start_date + "T12:00:00");
    const q = Math.ceil((d.getMonth() + 1) / 3);
    const key = `Q${q} ${d.getFullYear()}`;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(c);
  }

  // Unique categories
  const categories = [...new Set(conferences.map((c) => c.category).filter(Boolean))] as string[];

  const content = (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <Users className="w-4 h-4" />
          Conferences
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">
          Conference Schedule
        </h1>
        <p className="text-sm text-muted mt-1">
          Major biotech and pharma conferences, investor days, and medical
          meetings.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => { setShowPast(false); }}
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
          onClick={() => { setShowPast(true); }}
          className={cn(
            "px-4 py-2 rounded-md text-[12px] font-medium transition-colors",
            showPast
              ? "bg-accent/15 text-accent"
              : "text-muted hover:text-foreground hover:bg-surface-hover"
          )}
        >
          All
        </button>

        <div className="w-px h-5 bg-border mx-1" />

        <button
          onClick={() => setCategoryFilter(null)}
          className={cn(
            "px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors",
            !categoryFilter
              ? "bg-accent/15 text-accent"
              : "text-muted hover:text-foreground hover:bg-surface-hover"
          )}
        >
          All Categories
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() =>
              setCategoryFilter(categoryFilter === cat ? null : cat)
            }
            className={cn(
              "px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors",
              categoryFilter === cat
                ? CATEGORY_COLORS[cat] || "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-hover"
            )}
          >
            {cat}
          </button>
        ))}

        {data && (
          <span className="text-xs text-muted ml-auto">
            {data.total} conferences
          </span>
        )}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : conferences.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <Calendar className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">No conferences found</p>
        </div>
      ) : (
        <div className="space-y-8">
          {Object.entries(grouped).map(([quarter, items]) => (
            <div key={quarter}>
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3 flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-accent" />
                {quarter}
                <span className="font-normal">({items.length})</span>
              </h2>

              <div className="grid gap-3">
                {items.map((c) => {
                  const days = daysUntil(c.start_date);
                  const isOngoing = days <= 0 && daysUntil(c.end_date) >= 0;
                  const isPast = daysUntil(c.end_date) < 0;

                  return (
                    <div
                      key={c.id}
                      className={cn(
                        "rounded-lg border border-border p-4 transition-all hover:border-accent/30",
                        isOngoing && "border-accent/40 bg-accent/5",
                        isPast && "opacity-60"
                      )}
                    >
                      <div className="flex items-start gap-4">
                        {/* Date badge */}
                        <div className="w-14 h-14 rounded-lg bg-surface/80 border border-border flex flex-col items-center justify-center shrink-0">
                          <span className="text-[10px] uppercase font-semibold text-muted">
                            {SHORT_MONTHS[new Date(c.start_date + "T12:00:00").getMonth()]}
                          </span>
                          <span className="text-lg font-bold leading-tight">
                            {new Date(c.start_date + "T12:00:00").getDate()}
                          </span>
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <h3 className="font-semibold text-[15px] leading-tight">
                                {c.short_name ? (
                                  <>
                                    <span className="text-accent">
                                      {c.short_name}
                                    </span>{" "}
                                    <span className="text-muted font-normal">
                                      &mdash;{" "}
                                    </span>
                                    <span className="font-normal text-[13px]">
                                      {c.name}
                                    </span>
                                  </>
                                ) : (
                                  c.name
                                )}
                              </h3>
                              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5">
                                <span className="text-xs text-muted flex items-center gap-1">
                                  <Calendar className="w-3 h-3" />
                                  {formatDateRange(c.start_date, c.end_date)}
                                </span>
                                {c.city && (
                                  <span className="text-xs text-muted flex items-center gap-1">
                                    <MapPin className="w-3 h-3" />
                                    {c.city}
                                    {c.country && c.country !== "USA"
                                      ? `, ${c.country}`
                                      : ""}
                                  </span>
                                )}
                                {c.is_virtual && (
                                  <span className="text-xs text-muted flex items-center gap-1">
                                    <Globe className="w-3 h-3" />
                                    Virtual
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Status badge */}
                            <div className="flex items-center gap-2 shrink-0">
                              {c.category && (
                                <span
                                  className={cn(
                                    "text-[10px] font-semibold px-2 py-0.5 rounded",
                                    CATEGORY_COLORS[c.category] ||
                                      "bg-surface-hover text-muted"
                                  )}
                                >
                                  {c.category}
                                </span>
                              )}
                              {isOngoing ? (
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-accent/15 text-accent animate-pulse">
                                  LIVE
                                </span>
                              ) : !isPast && days <= 14 ? (
                                <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-warning/10 text-warning">
                                  {days}d
                                </span>
                              ) : null}
                            </div>
                          </div>

                          {c.description && (
                            <p className="text-xs text-muted mt-2 line-clamp-2">
                              {c.description}
                            </p>
                          )}

                          {c.website && (
                            <a
                              href={c.website}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline mt-2"
                            >
                              <ExternalLink className="w-3 h-3" />
                              Conference website
                            </a>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  if (!isPro) {
    return <PaywallGate feature="Conference Schedule">{content}</PaywallGate>;
  }
  return content;
}
