"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Newspaper,
  Loader2,
  ExternalLink,
  Search as SearchIcon,
  Megaphone,
  Handshake,
  UserCog,
  UserCheck,
  TrendingUp,
  TrendingDown,
  Pill,
  Sparkles,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────────────

type FeedKind =
  | "news"
  | "press_release"
  | "deal"
  | "leadership"
  | "insider"
  | "mover"
  | "catalyst";

interface FeedItem {
  kind: FeedKind;
  id: string;
  ticker: string | null;
  tickers: string[];
  headline: string;
  summary: string | null;
  url: string | null;
  source: string;
  timestamp: string | null;

  // Kind-specific extras (all optional)
  trade_type?: string;
  shares?: number | null;
  price?: number | null;
  total_value?: number | null;
  price_change_pct?: number | null;
  market_cap?: number | null;
  deal_type?: string;
  counterparty?: string | null;
  person?: string | null;
  event_type?: string;
  outcome?: string | null;
  item_code?: string | null;
}

interface FeedResponse {
  items: FeedItem[];
  total: number;
  page: number;
  total_pages: number;
  kinds: FeedKind[];
}

interface KindCounts {
  days: number;
  counts: Record<FeedKind, number>;
}

// ─── Kind metadata ──────────────────────────────────────────────────────

const KIND_META: Record<
  FeedKind,
  { label: string; icon: typeof Newspaper; tone: string; pill: string }
> = {
  news:          { label: "News",         icon: Newspaper,    tone: "text-accent",   pill: "bg-accent/10 text-accent" },
  press_release: { label: "Press release",icon: Megaphone,    tone: "text-accent",   pill: "bg-accent/15 text-accent" },
  deal:          { label: "Deal",         icon: Handshake,    tone: "text-warning",  pill: "bg-warning/15 text-warning" },
  leadership:    { label: "Leadership",   icon: UserCog,      tone: "text-warning",  pill: "bg-warning/10 text-warning" },
  insider:       { label: "Insider",      icon: UserCheck,    tone: "text-accent",   pill: "bg-accent/10 text-accent" },
  mover:         { label: "Stock move",   icon: TrendingUp,   tone: "text-positive", pill: "bg-positive/15 text-positive" },
  catalyst:      { label: "Catalyst",     icon: Pill,         tone: "text-negative", pill: "bg-negative/15 text-negative" },
};

const SHORT_MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

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

// ─── Page ───────────────────────────────────────────────────────────────

// Dramatic-news window. Hardcoded at 7 days because the feed is now
// filtered to "big moves only" — events older than a week are stale and
// should be looked up via the dedicated tabs (insider-trades, deals, etc.).
const DRAMATIC_WINDOW_DAYS = 7;

export default function NewsPage() {
  const [activeKind, setActiveKind] = useState<FeedKind | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<FeedResponse>({
    queryKey: ["feed", activeKind, page],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("per_page", "60");
      params.set("days", String(DRAMATIC_WINDOW_DAYS));
      if (activeKind) params.set("kind", activeKind);
      return fetchAPI(`/feed?${params}`);
    },
  });

  const { data: countData } = useQuery<KindCounts>({
    queryKey: ["feed-kinds"],
    queryFn: () => fetchAPI(`/feed/kinds?days=${DRAMATIC_WINDOW_DAYS}`),
    staleTime: 5 * 60 * 1000,
  });

  // Client-side keyword filter (cheap; the server doesn't index headlines)
  const filtered = useMemo(() => {
    const items = data?.items ?? [];
    if (!search) return items;
    const q = search.toLowerCase();
    return items.filter((it) =>
      it.headline.toLowerCase().includes(q) ||
      (it.summary || "").toLowerCase().includes(q) ||
      (it.tickers || []).some((t) => t.toLowerCase().includes(q))
    );
  }, [data, search]);

  // Group by date bucket
  const grouped = useMemo(() => {
    const out: Record<string, FeedItem[]> = {};
    for (const it of filtered) {
      const k = dateKey(it.timestamp);
      (out[k] ??= []).push(it);
    }
    return out;
  }, [filtered]);

  const kindKeys: FeedKind[] = ["news", "press_release", "deal", "leadership", "insider", "mover", "catalyst"];
  const counts = countData?.counts;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <Sparkles className="w-4 h-4" />
          Edge
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">
          Biotech Feed
        </h1>
        <p className="text-sm text-muted mt-1">
          Only the dramatic stuff from the last 7 days — FDA decisions,
          Phase 3 readouts, M&amp;A, leadership shake-ups, ≥$1M insider trades,
          and ±15% stock moves. Click a chip to focus on one kind.
        </p>
      </div>

      {/* Kind filter chips */}
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          onClick={() => { setActiveKind(null); setPage(1); }}
          className={cn(
            "px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors",
            !activeKind ? "bg-accent/15 text-accent" : "text-muted hover:text-foreground hover:bg-surface-hover"
          )}
        >
          All
          {data && <span className="ml-1 text-[10px] opacity-70">({data.total})</span>}
        </button>
        {kindKeys.map((k) => {
          const meta = KIND_META[k];
          const Icon = meta.icon;
          const active = activeKind === k;
          const c = counts?.[k];
          return (
            <button
              key={k}
              onClick={() => { setActiveKind(active ? null : k); setPage(1); }}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors",
                active
                  ? meta.pill
                  : "text-muted hover:text-foreground hover:bg-surface-hover"
              )}
            >
              <Icon className="w-3 h-3" />
              {meta.label}
              {c != null && <span className="text-[10px] opacity-70">({c})</span>}
            </button>
          );
        })}
      </div>

      {/* Search */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] uppercase tracking-widest text-muted/60">
          Last {DRAMATIC_WINDOW_DAYS} days · dramatic events only
        </span>

        <div className="ml-auto relative w-full sm:w-64">
          <SearchIcon className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search this feed…"
            className="w-full pl-9 pr-3 py-2 rounded-md bg-surface border border-border text-sm placeholder:text-muted focus:outline-none focus:border-accent/50 transition"
          />
        </div>
      </div>

      {/* Feed */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <Newspaper className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">Nothing matching</p>
          <p className="text-xs text-muted/60 mt-1">
            Try clearing the search box or expanding the time window.
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
                  <FeedCard key={it.id} item={it} />
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

// ─── One feed card ──────────────────────────────────────────────────────

function FeedCard({ item }: { item: FeedItem }) {
  const meta = KIND_META[item.kind];
  const Icon = meta.icon;

  // Special-cased "kind" tone — movers go green or red based on direction
  const kindPill =
    item.kind === "mover" && item.price_change_pct != null
      ? (item.price_change_pct >= 0
          ? "bg-positive/15 text-positive"
          : "bg-negative/15 text-negative")
      : meta.pill;

  // Render the card as a link if there's a URL, else a div
  const hasUrl = !!item.url;
  const Wrapper = (hasUrl ? "a" : "div") as "a" | "div";
  const wrapperProps = hasUrl
    ? { href: item.url!, target: "_blank", rel: "noopener noreferrer" }
    : {};

  return (
    <Wrapper
      {...wrapperProps}
      className={cn(
        "block rounded-lg border border-border p-4 transition-all group",
        hasUrl && "hover:border-accent/40 hover:bg-surface/60"
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* Top row: kind badge + source + relative time + tickers */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className={cn(
              "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-widest",
              kindPill
            )}>
              <Icon className="w-2.5 h-2.5" />
              {meta.label}
            </span>
            <span className="text-[10px] text-muted">{item.source}</span>
            <span className="text-[10px] text-muted">·</span>
            <span className="text-[11px] text-muted">{formatRelative(item.timestamp)}</span>
            {(item.tickers || []).slice(0, 5).map((t) => (
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

          {/* Headline */}
          <h3 className={cn(
            "text-sm font-semibold mt-1.5 leading-snug",
            hasUrl && "group-hover:text-accent transition-colors"
          )}>
            {item.headline}
          </h3>

          {/* Body / summary — kind-specific */}
          {item.summary && (
            <p className="text-xs text-muted mt-1.5 line-clamp-2 leading-relaxed">
              {item.summary}
            </p>
          )}

          {/* Mover-specific tail row */}
          {item.kind === "mover" && item.price_change_pct != null && (
            <div className="flex items-center gap-3 mt-2 text-[11px]">
              <span className={cn(
                "inline-flex items-center gap-1 font-mono font-semibold",
                item.price_change_pct >= 0 ? "text-positive" : "text-negative"
              )}>
                {item.price_change_pct >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                {item.price_change_pct >= 0 ? "+" : ""}{item.price_change_pct.toFixed(1)}%
              </span>
              {item.market_cap != null && (
                <span className="text-muted">
                  market cap: ${(item.market_cap / 1e9).toFixed(2)}B
                </span>
              )}
            </div>
          )}

          {/* Insider-specific tail row */}
          {item.kind === "insider" && item.total_value != null && (
            <div className="flex items-center gap-3 mt-2 text-[11px] text-muted">
              <span className={cn(
                "font-mono font-semibold",
                (item.trade_type || "").toUpperCase() === "PURCHASE" ? "text-positive" :
                (item.trade_type || "").toUpperCase() === "SALE" ? "text-negative" : "text-muted"
              )}>
                ${(item.total_value / 1e6).toFixed(2)}M total
              </span>
              {item.price && <span>@ ${item.price.toFixed(2)}/sh</span>}
            </div>
          )}

          {/* Catalyst-specific tail row */}
          {item.kind === "catalyst" && item.outcome && (
            <div className="mt-2">
              <span className={cn(
                "inline-block text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-widest",
                item.outcome === "POSITIVE" ? "bg-positive/15 text-positive" :
                item.outcome === "NEGATIVE" ? "bg-negative/15 text-negative" :
                "bg-warning/15 text-warning"
              )}>
                {item.outcome}
              </span>
            </div>
          )}
        </div>

        {hasUrl && (
          <ExternalLink className="w-3.5 h-3.5 text-muted/60 shrink-0 mt-1 group-hover:text-accent transition-colors" />
        )}
      </div>
    </Wrapper>
  );
}
