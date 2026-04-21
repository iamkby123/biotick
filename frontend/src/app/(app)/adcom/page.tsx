"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Users, Loader2, Calendar as CalendarIcon, ExternalLink } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";

interface AdComMeeting {
  id: number;
  committee: string | null;
  meeting_date: string | null;
  topics: string | null;
  drug_name: string | null;
  company_ticker: string | null;
  url: string | null;
}

interface AdComResponse {
  items: AdComMeeting[];
  total: number;
}

const SHORT_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function formatDate(iso: string | null): string {
  if (!iso) return "TBD";
  const d = new Date(iso + "T12:00:00");
  return `${SHORT_MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

export default function AdComPage() {
  const [upcoming, setUpcoming] = useState(true);
  const { data, isLoading } = useQuery<AdComResponse>({
    queryKey: ["adcom", upcoming],
    queryFn: () =>
      fetchAPI(`/adcom?upcoming=${upcoming}&per_page=50`),
  });

  const items = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <Users className="w-4 h-4" />
          Catalysts
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">FDA Advisory Committees</h1>
        <p className="text-sm text-muted mt-1">
          Public FDA advisory-committee meetings where drug-approval decisions
          are debated. Often move stocks as much as PDUFA dates do.
        </p>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => setUpcoming(true)}
          className={cn(
            "px-4 py-2 rounded-md text-[12px] font-medium transition-colors",
            upcoming ? "bg-accent/15 text-accent" : "text-muted hover:text-foreground hover:bg-surface-hover"
          )}
        >
          Upcoming
        </button>
        <button
          onClick={() => setUpcoming(false)}
          className={cn(
            "px-4 py-2 rounded-md text-[12px] font-medium transition-colors",
            !upcoming ? "bg-accent/15 text-accent" : "text-muted hover:text-foreground hover:bg-surface-hover"
          )}
        >
          All
        </button>
        {data && (
          <span className="text-xs text-muted ml-auto">{data.total} meetings</span>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <CalendarIcon className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">No advisory-committee meetings scheduled yet</p>
          <p className="text-xs text-muted/70 mt-1">
            The weekly scrape runs Monday 7am UTC.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((m) => (
            <div
              key={m.id}
              className="rounded-lg border border-border p-4 hover:border-accent/40 transition-colors"
            >
              <div className="flex items-start gap-4">
                <div className="w-16 shrink-0 text-center">
                  <div className="text-[10px] uppercase font-semibold text-muted">
                    {m.meeting_date
                      ? SHORT_MONTHS[new Date(m.meeting_date + "T12:00:00").getMonth()]
                      : "TBD"}
                  </div>
                  <div className="text-2xl font-bold">
                    {m.meeting_date
                      ? new Date(m.meeting_date + "T12:00:00").getDate()
                      : "—"}
                  </div>
                  <div className="text-[10px] text-muted">
                    {m.meeting_date
                      ? new Date(m.meeting_date + "T12:00:00").getFullYear()
                      : ""}
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    {m.company_ticker && (
                      <Link
                        href={`/companies/${m.company_ticker}`}
                        className="font-mono font-bold text-accent hover:underline"
                      >
                        {m.company_ticker}
                      </Link>
                    )}
                    {m.drug_name && (
                      <span className="text-[11px] bg-accent/10 text-accent px-2 py-0.5 rounded font-semibold">
                        {m.drug_name}
                      </span>
                    )}
                  </div>
                  <h3 className="text-sm font-semibold mt-1">{m.committee}</h3>
                  {m.topics && (
                    <p className="text-xs text-muted mt-1.5 line-clamp-3">{m.topics}</p>
                  )}
                  {m.url && (
                    <a
                      href={m.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline mt-2"
                    >
                      <ExternalLink className="w-3 h-3" />
                      FDA meeting page
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
