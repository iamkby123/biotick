"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Megaphone, Loader2, ExternalLink } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";

interface PressRelease {
  id: number;
  ticker: string | null;
  headline: string | null;
  summary: string | null;
  url: string | null;
  item_code: string | null;
  filed_date: string | null;
  accession_number: string;
}

interface PRResponse {
  items: PressRelease[];
  total: number;
  page: number;
  total_pages: number;
}

const WINDOWS: { id: number; label: string }[] = [
  { id: 7, label: "7d" },
  { id: 14, label: "14d" },
  { id: 30, label: "30d" },
  { id: 90, label: "90d" },
];

const SHORT_MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function dateBucket(iso: string | null): string {
  if (!iso) return "Unknown";
  const d = new Date(iso + "T12:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((today.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
  if (diff <= 0) return "Today";
  if (diff === 1) return "Yesterday";
  return `${SHORT_MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

export default function PressReleasesPage() {
  const [days, setDays] = useState(14);
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<PRResponse>({
    queryKey: ["press-releases", days, page],
    queryFn: () =>
      fetchAPI(`/press-releases?days=${days}&page=${page}&per_page=25`),
  });

  const items = data?.items ?? [];
  const grouped: Record<string, PressRelease[]> = {};
  for (const it of items) {
    (grouped[dateBucket(it.filed_date)] ??= []).push(it);
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <Megaphone className="w-4 h-4" />
          Edge
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">Press Releases</h1>
        <p className="text-sm text-muted mt-1">
          Extracted from SEC 8-K Items 7.01, 8.01 and 2.02. Summaries are
          AI-generated (2 sentences) — click through for the full release.
        </p>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {WINDOWS.map((w) => (
          <button
            key={w.id}
            onClick={() => {
              setDays(w.id);
              setPage(1);
            }}
            className={cn(
              "px-4 py-2 rounded-md text-[12px] font-medium transition-colors",
              days === w.id
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-hover"
            )}
          >
            {w.label}
          </button>
        ))}
        {data && (
          <span className="text-xs text-muted ml-auto">{data.total} releases</span>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <Megaphone className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">No press releases in this window yet</p>
          <p className="text-xs text-muted/70 mt-1">
            The 8-K pipeline runs overnight; check back tomorrow.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([key, rows]) => (
            <div key={key}>
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3 flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-accent/70" />
                {key}
                <span className="font-normal">({rows.length})</span>
              </h2>
              <div className="space-y-2">
                {rows.map((it) => (
                  <div
                    key={it.id}
                    className="rounded-lg border border-border p-4 hover:border-accent/40 transition-colors"
                  >
                    <div className="flex items-center gap-2 flex-wrap text-[11px]">
                      {it.ticker && (
                        <Link
                          href={`/companies/${it.ticker}`}
                          className="font-mono font-bold text-accent hover:underline"
                        >
                          {it.ticker}
                        </Link>
                      )}
                      {it.item_code && (
                        <span className="bg-surface-hover text-muted px-1.5 py-0.5 rounded">
                          Item {it.item_code}
                        </span>
                      )}
                    </div>
                    {it.headline && (
                      <h3 className="text-sm font-semibold mt-1.5">{it.headline}</h3>
                    )}
                    {it.summary && (
                      <p className="text-[13px] text-muted mt-2 leading-relaxed">
                        {it.summary}
                      </p>
                    )}
                    {it.url && (
                      <a
                        href={it.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline mt-2"
                      >
                        <ExternalLink className="w-3 h-3" />
                        Full release
                      </a>
                    )}
                  </div>
                ))}
              </div>
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
