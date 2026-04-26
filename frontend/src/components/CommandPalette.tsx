"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import { useQuery } from "@tanstack/react-query";
import { create } from "zustand";
import {
  Search,
  LayoutDashboard,
  Calendar,
  Pill,
  Grid3x3,
  History,
  DollarSign,
  UserCheck,
  Users,
  Star,
  ArrowRight,
  Building2,
  Newspaper,
  Megaphone,
  Handshake,
  Landmark,
  TrendingDown,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatPrice, formatMarketCap } from "@/lib/utils";

// Quick-nav items visible even with empty query. Keep these short — they're
// for "I know where I want to go, just get me there."
const QUICK_LINKS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, keywords: "home overview" },
  { href: "/companies", label: "Screener", icon: Search, keywords: "companies filter" },
  { href: "/catalysts", label: "Catalyst Calendar", icon: Calendar, keywords: "events" },
  { href: "/pdufa", label: "PDUFA Dates", icon: Pill, keywords: "fda approval" },
  { href: "/competitors", label: "Competitor Matrix", icon: Grid3x3, keywords: "indications" },
  { href: "/historical", label: "Historical Catalysts", icon: History, keywords: "past readouts" },
  { href: "/news", label: "Biotech News", icon: Newspaper, keywords: "rss stat fierce endpoints articles" },
  { href: "/press-releases", label: "Press Releases", icon: Megaphone, keywords: "8k announcements pr" },
  { href: "/deals", label: "Deals", icon: Handshake, keywords: "m&a acquisitions partnerships material agreements officer changes" },
  { href: "/adcom", label: "FDA AdCom", icon: Users, keywords: "advisory committee meeting fda approval" },
  { href: "/congress-trades", label: "Congress Trades", icon: Landmark, keywords: "house senate ptr politician stock act" },
  { href: "/short-interest", label: "Short Interest", icon: TrendingDown, keywords: "shorts most shorted finra reg sho days to cover" },
  { href: "/earnings", label: "Earnings Calendar", icon: DollarSign, keywords: "reports" },
  { href: "/insider-trades", label: "Insider Trades", icon: UserCheck, keywords: "form 4 buying selling" },
  { href: "/conferences", label: "Conferences", icon: Users, keywords: "investor day asco" },
  { href: "/watchlist", label: "Watchlist", icon: Star, keywords: "saved tracking" },
];

interface CompanyHit {
  ticker: string;
  name: string;
  price: number | null;
  market_cap: number | null;
}

/** Global store so the sidebar (or anywhere else) can trigger the palette. */
interface PaletteStore {
  open: boolean;
  setOpen: (v: boolean) => void;
  toggle: () => void;
}
export const useCommandPalette = create<PaletteStore>((set) => ({
  open: false,
  setOpen: (v) => set({ open: v }),
  toggle: () => set((s) => ({ open: !s.open })),
}));

export function CommandPalette() {
  const open = useCommandPalette((s) => s.open);
  const setOpen = useCommandPalette((s) => s.setOpen);
  const [query, setQuery] = useState("");
  const router = useRouter();

  // Keyboard shortcut: ⌘K / Ctrl+K
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        useCommandPalette.getState().toggle();
      }
      if (e.key === "Escape") useCommandPalette.getState().setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  // Reset query when palette closes so next open is fresh.
  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  // Debounced search — only hit the API once the user has typed 2+ chars.
  const debounced = useDebouncedValue(query, 180);

  const { data: companies = [], isFetching } = useQuery<CompanyHit[]>({
    queryKey: ["cmdk-companies", debounced],
    queryFn: async () => {
      if (debounced.trim().length < 1) return [];
      const res = await fetchAPI<{ companies: CompanyHit[] }>(
        `/companies?search=${encodeURIComponent(debounced)}&per_page=8&sort_by=market_cap&sort_dir=desc`
      );
      return res.companies || [];
    },
    enabled: open && debounced.trim().length >= 1,
    staleTime: 60 * 1000,
  });

  const filteredLinks = useMemo(() => {
    if (!query.trim()) return QUICK_LINKS;
    const q = query.toLowerCase();
    return QUICK_LINKS.filter(
      (l) =>
        l.label.toLowerCase().includes(q) ||
        l.keywords.toLowerCase().includes(q)
    );
  }, [query]);

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  if (!open) {
    // Still rendered so the floating "⌘K" hint can live somewhere; we use
    // a portal-free layout so the hint lives in the navbar instead.
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[10vh] px-4"
      onClick={() => setOpen(false)}
    >
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" aria-hidden />

      {/* Palette */}
      <Command
        className="relative w-full max-w-xl rounded-xl border border-border bg-surface shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        shouldFilter={false}
        loop
      >
        <div className="flex items-center gap-3 border-b border-border px-4">
          <Search className="w-4 h-4 text-muted shrink-0" />
          <Command.Input
            autoFocus
            value={query}
            onValueChange={setQuery}
            placeholder="Jump to ticker, company, or page…"
            className="flex-1 bg-transparent py-4 text-[14px] focus:outline-none placeholder:text-muted/60"
          />
          <kbd className="text-[10px] font-mono text-muted border border-border rounded px-1.5 py-0.5 shrink-0">
            ESC
          </kbd>
        </div>

        <Command.List className="max-h-[420px] overflow-y-auto py-2">
          {isFetching && debounced && (
            <div className="px-4 py-2 text-[11px] text-muted">Searching…</div>
          )}

          <Command.Empty className="px-4 py-8 text-center text-sm text-muted">
            No results.
          </Command.Empty>

          {/* Companies — only when query is non-empty and we have hits */}
          {companies.length > 0 && (
            <Command.Group
              heading="Companies"
              className="px-2 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-muted [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-2"
            >
              {companies.map((c) => (
                <Command.Item
                  key={c.ticker}
                  value={`${c.ticker} ${c.name}`}
                  onSelect={() => go(`/companies/${c.ticker}`)}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer",
                    "data-[selected=true]:bg-accent/10 data-[selected=true]:text-foreground",
                    "text-muted hover:text-foreground"
                  )}
                >
                  <Building2 className="w-4 h-4 text-accent shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-[13px] text-foreground">
                        {c.ticker}
                      </span>
                      <span className="text-[12px] truncate">{c.name}</span>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-[12px] font-mono">{formatPrice(c.price)}</div>
                    <div className="text-[10px] text-muted">
                      {formatMarketCap(c.market_cap)}
                    </div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-muted/60 shrink-0" />
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {/* Pages */}
          {filteredLinks.length > 0 && (
            <Command.Group
              heading={query ? "Pages" : "Jump to"}
              className="px-2 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-muted [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-2"
            >
              {filteredLinks.map((l) => {
                const Icon = l.icon;
                return (
                  <Command.Item
                    key={l.href}
                    value={`${l.label} ${l.keywords}`}
                    onSelect={() => go(l.href)}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer",
                      "data-[selected=true]:bg-accent/10 data-[selected=true]:text-foreground",
                      "text-muted hover:text-foreground"
                    )}
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    <span className="text-[13px] flex-1">{l.label}</span>
                    <ArrowRight className="w-3.5 h-3.5 text-muted/60 shrink-0" />
                  </Command.Item>
                );
              })}
            </Command.Group>
          )}
        </Command.List>

        <div className="border-t border-border px-3 py-2 flex items-center gap-4 text-[10px] text-muted">
          <span className="flex items-center gap-1">
            <kbd className="font-mono border border-border rounded px-1">↑↓</kbd>
            navigate
          </span>
          <span className="flex items-center gap-1">
            <kbd className="font-mono border border-border rounded px-1">↵</kbd>
            select
          </span>
          <span className="ml-auto flex items-center gap-1">
            <kbd className="font-mono border border-border rounded px-1">⌘K</kbd>
            toggle
          </span>
        </div>
      </Command>
    </div>
  );
}

/** Simple debounce hook — avoids a useEffect-heavy custom implementation. */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}
