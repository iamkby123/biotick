"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Newspaper,
  Loader2,
  ExternalLink,
  Search as SearchIcon,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";

interface NewsRow {
  id: number;
  source: string;
  title: string;
  url: string;
  summary: string | null;
  published_at: string | null;
  tickers: string[];
}

interface NewsResponse {
  items: NewsRow[];
  total: number;
  page: number;
  total_pages: number;
}

interface SourceInfo {
  source: string;
  last_published: string | null;
  count: number;
}

const SHORT_MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** Render a short human-readable "2h ago" / "Apr 19" string from ISO ts. */
function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const mins = (Date.now() - d.getTime()) / 60000;
  if (mins < 1) return "just now";
  if (mins < 60) return `${Math.round(mins)}m ago`;
  const hrs = mins / 60;
  if (hrs < 24) return `${Math.round(hrs)}h ago`;
  return `${SHORT_MONTHS[d.getMonth()]} ${d.getDate()}`;
}

function dateKey(iso: string | null): string {
  if (!iso) return "Unknown date";
  const d = new Date(iso);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const dDay = new Date(d);
  dDay.setHours(0, 0, 0, 0);
  const diff = (today.getTime() - dDay.getTime()) / (1000 * 60 * 60 * 24);
  if (diff < 1) return "Today";
  if (diff < 2) return "Yesterday";
  return `${SHORT_MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

export default function NewsPage() {
  const [source, setSource] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  // Debounce-free — keep it simple; the cache middleware absorbs repeats.
  const { data, isLoading } = useQuery<NewsResponse>({
    queryKey: ["news", source, search, page],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("per_page", "30");
      if (source) params.set("source", source);
      if (search) params.set("search", search);
      return fetchAPI(`/news?${params}`);
    },
  });

  const { data: sources } = useQuery<{ sources: SourceInfo[] }>({
    queryKey: ["news-sources"],
    queryFn: () => fetchAPI("/news/sources"),
    staleTime: 10 * 60 * 1000,
  });

  const items = data?.items ?? [];

  // Group by date bucket for the date-grouped feed pattern.
  const grouped: Record<string, NewsRow[]> = {};
  for (const it of items) {
    const key = dateKey(it.published_at);
    (grouped[key] ??= []).push(it);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <Newspaper className="w-4 h-4" />
          Edge
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">
          Biotech News
        </h1>
        <p className="text-sm text-muted mt-1">
          Live feed from Endpoints, Fierce Biotech, and STAT. Tickers are
          auto-tagged against our 1,000+ company universe so you can filter
          per name.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => {
            setSource(null);
            setPage(1);
          }}
          className={cn(
            "px-4 py-2 rounded-md text-[12px] font-medium transition-colors",
            !source
              ? "bg-accent/15 text-accent"
              : "text-muted hover:text-foreground hover:bg-surface-hover"
          )}
        >
          All sources
        </button>
        {sources?.sources.map((s) => (
          <button
            key={s.source}
            onClick={() => {
              setSource(source === s.source ? null : s.source);
              setPage(1);
            }}
            className={cn(
              "px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors",
              source === s.source
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-hover"
            )}
            title={`${s.count} stories`}
          >
            {s.source}
          </button>
        ))}

        <div className="ml-auto relative w-full sm:w-64">
          <SearchIcon className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search news…"
            className="w-full pl-9 pr-3 py-2 rounded-md bg-surface border border-border text-sm placeholder:text-muted focus:outline-none focus:border-accent/50 transition"
          />
        </div>
      </div>

      {/* Feed */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <Newspaper className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">No stories found</p>
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
                  <a
                    key={it.id}
                    href={it.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block rounded-lg border border-border p-4 hover:border-accent/40 hover:bg-surface/60 transition-all group"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-[10px] font-semibold uppercase tracking-widest text-accent">
                            {it.source}
                          </span>
                          <span className="text-[11px] text-muted">
                            {formatRelative(it.published_at)}
                          </span>
                          {it.tickers.slice(0, 5).map((t) => (
                            <Link
                              key={t}
                              href={`/companies/${t}`}
                              onClick={(e) => e.stopPropagation()}
                              className="text-[10px] font-mono font-semibold text-accent/80 bg-accent/10 px-1.5 py-0.5 rounded hover:bg-accent/20 transition-colors"
                            >
                              {t}
                            </Link>
                          ))}
                        </div>
                        <h3 className="text-sm font-semibold mt-1.5 group-hover:text-accent transition-colors">
                          {it.title}
                        </h3>
                        {it.summary && (
                          <p className="text-xs text-muted mt-1.5 line-clamp-2">
                            {it.summary}
                          </p>
                        )}
                      </div>
                      <ExternalLink className="w-3.5 h-3.5 text-muted/60 shrink-0 mt-1 group-hover:text-accent transition-colors" />
                    </div>
                  </a>
                ))}
              </div>
            </div>
          ))}
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
