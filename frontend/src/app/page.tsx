"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Search,
  Calendar,
  FlaskConical,
  FileText,
  TrendingDown,
  ArrowRight,
  Check,
  X,
  ChevronDown,
  ChevronUp,
  Zap,
  Pill,
  Megaphone,
  Landmark,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/providers";
import { fetchAPI } from "@/lib/api";

import { useUpgrade } from "@/lib/stripe";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <Hero />
      <TickerTape />
      <Stats />
      <Features />
      <FeatureShowcase />
      <HowItWorks />
      <Pricing />
      <FAQ />
      <Footer />
    </div>
  );
}

/* ── Navbar ── */
function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const { user, loading, signOut } = useAuth();

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handler);
    return () => window.removeEventListener("scroll", handler);
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const close = () => setMenuOpen(false);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [menuOpen]);

  const displayName =
    (user?.user_metadata as { full_name?: string } | undefined)?.full_name ||
    user?.email?.split("@")[0] ||
    "Account";

  return (
    <nav className={cn(
      "sticky top-0 z-50 transition-all duration-300",
      scrolled
        ? "border-b border-border bg-background/90 backdrop-blur-xl"
        : "bg-transparent"
    )}>
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-accent flex items-center justify-center">
            <Activity className="w-4 h-4 text-black" />
          </div>
          <span className="font-bold text-[15px] tracking-tight">Biotick</span>
        </Link>

        <div className="hidden md:flex items-center gap-8 text-sm text-muted">
          <a href="#features" className="hover:text-foreground transition">Features</a>
          <a href="#pricing" className="hover:text-foreground transition">Pricing</a>
          <a href="#faq" className="hover:text-foreground transition">FAQ</a>
        </div>

        <div className="flex items-center gap-3">
          {loading ? null : user ? (
            <>
              <Link
                href="/dashboard"
                className="px-4 py-2 rounded-md bg-accent text-black text-sm font-semibold hover:bg-accent-hover transition"
              >
                Go to Dashboard
              </Link>
              <div className="relative" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => setMenuOpen((v) => !v)}
                  className="w-9 h-9 rounded-full bg-surface border border-border hover:border-accent/50 text-sm font-semibold flex items-center justify-center transition-colors"
                  title={user.email || undefined}
                >
                  {displayName.slice(0, 2).toUpperCase()}
                </button>
                {menuOpen && (
                  <div className="absolute right-0 mt-2 w-64 rounded-lg border border-border bg-surface shadow-xl overflow-hidden">
                    <div className="px-4 py-3 border-b border-border">
                      <p className="text-xs text-muted">Signed in as</p>
                      <p className="text-sm font-medium truncate">{user.email}</p>
                    </div>
                    <Link
                      href="/dashboard"
                      className="block px-4 py-2 text-sm hover:bg-surface-hover transition"
                      onClick={() => setMenuOpen(false)}
                    >
                      Dashboard
                    </Link>
                    <Link
                      href="/watchlist"
                      className="block px-4 py-2 text-sm hover:bg-surface-hover transition"
                      onClick={() => setMenuOpen(false)}
                    >
                      Watchlist
                    </Link>
                    <button
                      onClick={async () => {
                        setMenuOpen(false);
                        await signOut();
                      }}
                      className="block w-full text-left px-4 py-2 text-sm text-negative hover:bg-negative/5 transition border-t border-border"
                    >
                      Sign out
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <Link href="/login" className="text-sm text-muted hover:text-foreground transition hidden sm:block">
                Log In
              </Link>
              <Link href="/signup" className="px-4 py-2 rounded-md bg-accent text-black text-sm font-semibold hover:bg-accent-hover transition">
                Get Started
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}

/* ── Stock chart SVG paths (biotech-style volatile moves) ── */
const CHART_PATHS = [
  // Spike and crash pattern (like Blue Water Vaccines -94%)
  "M0,180 L20,175 L40,170 L60,160 L80,140 L100,80 L120,40 L140,20 L150,15 L160,25 L180,120 L200,160 L220,175 L240,180 L260,182 L280,184 L320,185 L360,186 L400,186",
  // Gradual decline with a bounce (like Inflarx)
  "M0,40 L30,45 L60,55 L80,70 L90,30 L100,25 L110,35 L130,80 L160,120 L200,155 L240,170 L280,178 L320,182 L360,184 L400,185",
  // Pump and dump pattern (like Eargo)
  "M0,100 L20,95 L40,85 L60,60 L70,40 L80,30 L90,25 L100,35 L110,50 L120,90 L140,140 L160,165 L180,175 L200,180 L240,183 L280,185 L320,186 L360,186 L400,187",
  // Rally pattern (bullish biotech)
  "M0,185 L40,183 L80,180 L120,170 L140,155 L160,130 L180,100 L200,70 L220,50 L240,35 L260,25 L280,20 L300,22 L320,18 L340,15 L360,20 L380,18 L400,15",
];

/* ── Hero with biotech background ── */
function Hero() {
  const { user } = useAuth();
  return (
    <section className="relative overflow-hidden min-h-[85vh] flex items-center">
      {/* Animated background */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-b from-accent/8 via-accent/2 to-transparent" />

        {/* Stock chart backgrounds — dramatic biotech moves */}
        <svg className="absolute top-[10%] left-0 w-full h-[200px] opacity-[0.06]" viewBox="0 0 400 200" preserveAspectRatio="none">
          <path d={CHART_PATHS[0]} fill="none" stroke="var(--color-negative)" strokeWidth="2" />
          <path d={CHART_PATHS[0]} fill="url(#redFade)" />
          <defs><linearGradient id="redFade" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--color-negative)" stopOpacity="0.15" /><stop offset="100%" stopColor="var(--color-negative)" stopOpacity="0" /></linearGradient></defs>
        </svg>
        <svg className="absolute top-[35%] left-0 w-full h-[200px] opacity-[0.05]" viewBox="0 0 400 200" preserveAspectRatio="none">
          <path d={CHART_PATHS[3]} fill="none" stroke="var(--color-positive)" strokeWidth="2" />
          <path d={CHART_PATHS[3]} fill="url(#greenFade)" />
          <defs><linearGradient id="greenFade" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--color-positive)" stopOpacity="0.12" /><stop offset="100%" stopColor="var(--color-positive)" stopOpacity="0" /></linearGradient></defs>
        </svg>
        <svg className="absolute bottom-[5%] left-0 w-full h-[200px] opacity-[0.04]" viewBox="0 0 400 200" preserveAspectRatio="none">
          <path d={CHART_PATHS[2]} fill="none" stroke="var(--color-negative)" strokeWidth="1.5" />
        </svg>

        {/* Grid overlay */}
        <div className="absolute inset-0 opacity-[0.025]" style={{
          backgroundImage: "linear-gradient(var(--color-accent) 1px, transparent 1px), linear-gradient(90deg, var(--color-accent) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }} />

        {/* Glow orbs */}
        <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-accent/5 rounded-full blur-[120px]" />
        <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] bg-negative/3 rounded-full blur-[100px]" />
      </div>

      <div className="relative max-w-6xl mx-auto px-6 py-24 text-center">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-accent/20 bg-accent/5 text-accent text-xs font-medium mb-8 animate-fade-in">
          <Zap className="w-3 h-3" />
          Real-time biotech intelligence for serious traders
        </div>

        <h1 className="text-5xl md:text-6xl lg:text-[80px] font-bold tracking-tight leading-[1.05] max-w-5xl mx-auto animate-fade-in" style={{ animationDelay: "0.1s" }}>
          Modern{" "}
          <span className="relative inline-block">
            <span className="text-accent">biotech</span>
            <span className="absolute -bottom-2 left-0 right-0 h-1 bg-accent/30 rounded-full" />
          </span>
          {" "}data
        </h1>

        <p className="text-lg md:text-xl text-muted mt-8 max-w-2xl mx-auto leading-relaxed animate-fade-in" style={{ animationDelay: "0.2s" }}>
          1,000+ companies. 5,000+ clinical trials. FDA catalysts scored by significance.
          All the data Wall Street uses — at a fraction of the cost.
        </p>

        <div className="flex items-center justify-center gap-4 mt-12 animate-fade-in" style={{ animationDelay: "0.3s" }}>
          <Link
            href="/dashboard"
            className="group px-8 py-4 rounded-xl bg-accent text-black font-bold text-[15px] hover:bg-accent-hover transition-all hover:shadow-lg hover:shadow-accent/20 flex items-center gap-2"
          >
            {user ? "Go to Dashboard" : "Start Free"}
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
          </Link>
          <a
            href="#pricing"
            className="px-8 py-4 rounded-xl border border-border text-[15px] font-medium hover:bg-surface-hover transition-all hover:border-accent/30"
          >
            View Pricing
          </a>
        </div>

        <p className="text-xs text-muted/60 mt-4 animate-fade-in" style={{ animationDelay: "0.4s" }}>
          No credit card required. Free tier available forever.
        </p>
      </div>
    </section>
  );
}

/* ── Live Ticker Tape ── */
// Tickers shown on the landing-page marquee, in the order they should appear.
// Keep this list limited to tickers we actually track in `companies` — any
// symbol missing from the DB silently drops out of the marquee.
const TICKER_TAPE_SYMBOLS = [
  "LLY", "NVO", "MRNA", "PFE", "AMGN",
  "GILD", "VRTX", "REGN", "BIIB", "ALNY", "INCY",
];

interface TickerRow {
  ticker: string;
  price: number | null;
  price_change_pct: number | null;
}

function TickerTape() {
  // Pull live prices from the backend. The response cache on the server
  // keeps this at ~10-40ms per request; the price sync job refreshes the
  // DB every 30 min during market hours.
  const { data } = useQuery<{ companies: TickerRow[] }>({
    queryKey: ["ticker-tape", TICKER_TAPE_SYMBOLS.join(",")],
    queryFn: () => fetchAPI(
      `/companies?tickers=${TICKER_TAPE_SYMBOLS.join(",")}&per_page=${TICKER_TAPE_SYMBOLS.length}`
    ),
    staleTime: 60 * 1000,            // trust the server cache for 1 min
    refetchInterval: 5 * 60 * 1000,  // refresh every 5 min while page is open
  });

  // Preserve the order above, not whatever order the API returned.
  const byTicker = new Map<string, TickerRow>();
  for (const c of data?.companies || []) byTicker.set(c.ticker, c);
  const items = TICKER_TAPE_SYMBOLS
    .map((sym) => byTicker.get(sym))
    .filter((c): c is TickerRow => !!c && c.price != null);

  // On first paint (pre-fetch), avoid layout shift with a thin skeleton bar.
  if (items.length === 0) {
    return (
      <div className="border-y border-border bg-surface/50 overflow-hidden">
        <div className="h-[46px]" aria-hidden />
      </div>
    );
  }

  // Double for seamless scroll
  const doubled = [...items, ...items];

  return (
    <div className="border-y border-border bg-surface/50 overflow-hidden">
      <div className="flex animate-ticker-scroll">
        {doubled.map((t, i) => {
          const change = t.price_change_pct ?? 0;
          return (
            <div key={i} className="flex items-center gap-3 px-6 py-3 shrink-0 border-r border-border/50">
              <span className="font-bold text-sm">{t.ticker}</span>
              <span className="font-mono text-sm">${(t.price ?? 0).toFixed(2)}</span>
              <span className={cn(
                "font-mono text-xs font-semibold px-1.5 py-0.5 rounded",
                change >= 0 ? "text-positive bg-positive/10" : "text-negative bg-negative/10"
              )}>
                {change >= 0 ? "+" : ""}{change.toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Stats ── */
function Stats() {
  return (
    <section className="max-w-6xl mx-auto px-6 py-16">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
        {[
          { value: "1,054",   label: "Biotech Companies",  icon: Search },
          { value: "16,917",  label: "Clinical Trials",    icon: FlaskConical },
          { value: "5,549",   label: "Drug Programs",      icon: Pill },
          { value: "30,000+", label: "SEC Filings",        icon: FileText },
        ].map((s) => (
          <div key={s.label} className="rounded-xl border border-border bg-surface/50 p-5 text-center hover:border-accent/30 transition-colors">
            <s.icon className="w-5 h-5 text-accent mx-auto mb-3" />
            <p className="text-2xl font-bold text-accent">{s.value}</p>
            <p className="text-xs text-muted mt-1">{s.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ── Features ── */
function Features() {
  const features = [
    { icon: Search,       title: "Company Screener",     description: "Filter 1,000+ US-listed biotech companies by market cap, therapeutic area, pipeline stage, or upcoming catalyst." },
    { icon: FlaskConical, title: "Drug Pipelines",       description: "Every program Phase 1 through Marketed for 5,500+ drugs. Annual revenue auto-extracted from 10-K filings via Claude." },
    { icon: Calendar,     title: "PDUFA Calendar",       description: "Every FDA decision date, advisory committee, and trial readout in one calendar. Exact-day events pinned, outcomes auto-cross-referenced." },
    { icon: Megaphone,    title: "Press Releases (AI)",  description: "Every biotech 8-K press release with a 2-sentence Claude summary explaining the news angle and the investor takeaway." },
    { icon: Landmark,     title: "Congress Trades",      description: "Biotech trades by US House members, sourced directly from PTR filings on disclosures-clerk.house.gov." },
    { icon: TrendingDown, title: "Short Interest",       description: "53,000+ FINRA Reg SHO rows. Days-to-cover, most-shorted leaderboard, sparklines on every company page." },
  ];

  return (
    <section id="features" className="max-w-6xl mx-auto px-6 py-24">
      <div className="text-center mb-16">
        <p className="text-sm font-semibold text-accent uppercase tracking-wider">Features</p>
        <h2 className="text-3xl md:text-4xl font-bold mt-3">Everything you need to trade biotech</h2>
        <p className="text-muted mt-4 max-w-lg mx-auto">
          Data from ClinicalTrials.gov, SEC EDGAR, and market feeds — normalized and ready for trading decisions.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {features.map((f) => (
          <div key={f.title} className="rounded-xl border border-border bg-surface p-6 hover:border-accent/30 hover:-translate-y-1 transition-all duration-200 group">
            <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center mb-4 group-hover:bg-accent/20 transition-colors">
              <f.icon className="w-5 h-5 text-accent" />
            </div>
            <h3 className="font-semibold text-[15px]">{f.title}</h3>
            <p className="text-sm text-muted mt-2 leading-relaxed">{f.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ── Feature Showcase (alternating screenshot mocks) ──
   Each "screenshot" is a real React component styled as a UI mock —
   that way it always matches the live product, doesn't need a CDN, and
   never blocks page render waiting for image loads.
*/

function MockFrame({ children }: { children: React.ReactNode }) {
  // Browser-chrome wrapper. Subtle gradient ring + shadow to read as a
  // screenshot rather than an inline component.
  return (
    <div className="relative">
      <div className="absolute -inset-4 bg-gradient-to-br from-accent/15 via-accent/5 to-transparent blur-3xl opacity-60" />
      <div className="relative rounded-xl border border-border bg-background shadow-2xl shadow-accent/5 overflow-hidden">
        {/* Window chrome */}
        <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-border bg-surface/50">
          <span className="w-2.5 h-2.5 rounded-full bg-negative/40" />
          <span className="w-2.5 h-2.5 rounded-full bg-warning/40" />
          <span className="w-2.5 h-2.5 rounded-full bg-positive/40" />
          <span className="ml-3 text-[10px] font-mono text-muted/70">biotick.io</span>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

function ShowcaseRow({
  eyebrow,
  title,
  description,
  bullets,
  mock,
  reverse = false,
}: {
  eyebrow: string;
  title: string;
  description: string;
  bullets: string[];
  mock: React.ReactNode;
  reverse?: boolean;
}) {
  return (
    <div className={cn(
      "grid grid-cols-1 lg:grid-cols-2 gap-12 items-center",
      reverse ? "lg:[&>*:first-child]:order-2" : ""
    )}>
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-accent">
          {eyebrow}
        </p>
        <h3 className="text-3xl md:text-4xl font-bold tracking-tight mt-3">
          {title}
        </h3>
        <p className="text-muted mt-4 text-[15px] leading-relaxed">
          {description}
        </p>
        <ul className="mt-6 space-y-2.5">
          {bullets.map((b) => (
            <li key={b} className="flex items-start gap-2.5 text-sm">
              <Check className="w-4 h-4 text-accent shrink-0 mt-0.5" />
              <span>{b}</span>
            </li>
          ))}
        </ul>
      </div>
      <MockFrame>{mock}</MockFrame>
    </div>
  );
}

// ── Mock 1: Catalyst Calendar ────────────────────────────────────────────
function CalendarMock() {
  // Pretend May 2026: 7-col day grid, three pinned EXACT events + a
  // "Somewhere this month" strip mirroring the real PDUFA page.
  const days = Array.from({ length: 35 }, (_, i) => i - 4);
  const exact: Record<number, { ticker: string; type: "PDUFA" | "AdCom" | "Data"; color: string }> = {
    8: { ticker: "VRDN", type: "PDUFA", color: "bg-accent" },
    15: { ticker: "MRNA", type: "Data", color: "bg-accent/60" },
    22: { ticker: "IONS", type: "AdCom", color: "bg-warning" },
  };

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-surface/40 flex items-center justify-between">
        <span className="text-xs font-semibold">May 2026</span>
        <span className="text-[10px] font-mono text-muted">12 events</span>
      </div>

      {/* "Somewhere this month" strip */}
      <div className="px-3 py-2 border-b border-border/50 bg-accent/5">
        <p className="text-[8px] uppercase tracking-widest text-muted/70 mb-1.5">
          Somewhere this month
        </p>
        <div className="flex flex-wrap gap-1">
          {[
            { t: "BIIB", d: "BIIB-122" },
            { t: "SRPT", d: "ELEVIDYS" },
            { t: "ALNY", d: "Vutrisiran" },
            { t: "AXSM", d: "AXS-05" },
          ].map((c) => (
            <span key={c.t} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] bg-accent/10 text-accent">
              <span className="w-0.5 h-0.5 rounded-full bg-accent" />
              <span className="font-mono font-semibold">{c.t}</span>
              <span className="text-muted">{c.d}</span>
            </span>
          ))}
        </div>
      </div>

      {/* Day-of-week header */}
      <div className="grid grid-cols-7 text-[8px] uppercase tracking-widest text-muted/70 border-b border-border/50">
        {["S","M","T","W","T","F","S"].map((d, i) => (
          <div key={i} className="px-1 py-1 text-center">{d}</div>
        ))}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7 auto-rows-[44px]">
        {days.map((d, i) => {
          const valid = d >= 1 && d <= 31;
          const ev = valid ? exact[d] : undefined;
          return (
            <div
              key={i}
              className={cn(
                "border-b border-r border-border/40 p-1 text-[9px] overflow-hidden",
                !valid && "bg-surface/20"
              )}
            >
              {valid && (
                <>
                  <div className="font-mono text-muted">{d}</div>
                  {ev && (
                    <span className={cn(
                      "mt-0.5 inline-flex items-center gap-1 px-1 py-0 rounded text-[8px] bg-accent/10 text-accent"
                    )}>
                      <span className={cn("w-0.5 h-0.5 rounded-full", ev.color)} />
                      <span className="font-mono font-semibold">{ev.ticker}</span>
                    </span>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Mock 2: Drug Pipeline ────────────────────────────────────────────────
function PipelineMock() {
  const drugs = [
    { name: "Mounjaro",    indication: "Diabetes / Obesity",     phase: "MARKETED",  rev: "$23.0B" },
    { name: "Zepbound",    indication: "Obesity",                phase: "MARKETED",  rev: "$13.7B" },
    { name: "mRNA-3705",   indication: "Methylmalonic acidemia", phase: "PHASE 3",   rev: null },
    { name: "Veligrotug",  indication: "Thyroid eye disease",    phase: "FILED",     rev: null },
    { name: "Spikevax",    indication: "COVID-19",               phase: "MARKETED",  rev: "$1.6B" },
    { name: "BIIB-122",    indication: "Parkinson's",            phase: "PHASE 3",   rev: null },
  ];
  const phaseColor: Record<string, string> = {
    MARKETED:  "bg-positive/15 text-positive",
    "FILED":   "bg-accent/15 text-accent",
    "PHASE 3": "bg-accent/10 text-accent/90",
    "PHASE 2": "bg-muted/15 text-muted",
    "PHASE 1": "bg-muted/10 text-muted/80",
  };
  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-surface/40 flex items-center justify-between">
        <span className="text-xs font-semibold">Drug Pipeline</span>
        <span className="text-[10px] font-mono text-muted">5,549 drugs</span>
      </div>
      <table className="w-full text-[12px]">
        <tbody>
          {drugs.map((d, i) => (
            <tr key={i} className="border-b border-border/50 last:border-b-0">
              <td className="px-3 py-2 font-semibold">{d.name}</td>
              <td className="px-3 py-2 text-muted">{d.indication}</td>
              <td className="px-3 py-2">
                <span className={cn(
                  "text-[9px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider",
                  phaseColor[d.phase] || "bg-muted/10 text-muted"
                )}>
                  {d.phase}
                </span>
              </td>
              <td className="px-3 py-2 text-right font-mono text-positive">
                {d.rev ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Mock 3: Press Releases with AI Summaries ─────────────────────────────
function PressReleasesMock() {
  const items = [
    {
      ticker: "KYTX",
      headline: "Kyverna presents positive Phase 2/3 data for miv-cel CAR-T",
      summary: "Stiff person syndrome cohort showed 100% immunotherapy-free response and statistically significant disability reversal. CAR-T extends Kyverna's autoimmune franchise — first major data validation for non-oncology CAR-T.",
      time: "2h ago",
    },
    {
      ticker: "VRDN",
      headline: "Veligrotug receives PDUFA target action date of June 30, 2026",
      summary: "FDA accepted BLA for thyroid eye disease; priority review granted. Approval would compete directly with Tepezza ($5.2B AMGN drug) and likely command pricing parity.",
      time: "5h ago",
    },
  ];
  return (
    <div className="space-y-2">
      {items.map((it, i) => (
        <div key={i} className="rounded-lg border border-border p-3 hover:border-accent/30">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-[11px] font-bold text-accent">{it.ticker}</span>
            <span className="text-[10px] text-muted">·</span>
            <span className="text-[10px] text-muted">{it.time}</span>
            <span className="ml-auto inline-flex items-center gap-1 text-[9px] text-accent bg-accent/10 px-1.5 py-0.5 rounded font-semibold uppercase tracking-widest">
              <Sparkles className="w-2.5 h-2.5" /> AI Summary
            </span>
          </div>
          <p className="text-[12px] font-semibold leading-snug">{it.headline}</p>
          <p className="text-[11px] text-muted mt-1.5 leading-relaxed">{it.summary}</p>
        </div>
      ))}
    </div>
  );
}

// ── Mock 4: Congressional Trades ─────────────────────────────────────────
function CongressTradesMock() {
  const trades = [
    { date: "Mar 19", member: "Cisneros (D-CA)", ticker: "BBIO", type: "BUY",  amount: "$1K-$15K" },
    { date: "Mar 20", member: "Hern (R-OK)",     ticker: "MDT",  type: "SELL", amount: "$15K-$50K" },
    { date: "Mar 26", member: "Kean (R-NJ)",     ticker: "JNJ",  type: "SELL", amount: "$1K-$15K" },
    { date: "Apr 02", member: "Pelosi (D-CA)",   ticker: "VRTX", type: "BUY",  amount: "$50K-$100K" },
    { date: "Apr 14", member: "Crenshaw (R-TX)", ticker: "LLY",  type: "BUY",  amount: "$15K-$50K" },
  ];
  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-surface/40 flex items-center justify-between">
        <span className="text-xs font-semibold">House PTR Filings</span>
        <span className="text-[10px] font-mono text-muted">645 trades</span>
      </div>
      <table className="w-full text-[12px]">
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} className="border-b border-border/50 last:border-b-0">
              <td className="px-3 py-1.5 font-mono text-muted text-[11px]">{t.date}</td>
              <td className="px-3 py-1.5">{t.member}</td>
              <td className="px-3 py-1.5">
                <span className="font-mono font-semibold text-accent">{t.ticker}</span>
              </td>
              <td className="px-3 py-1.5">
                <span className={cn(
                  "text-[9px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider",
                  t.type === "BUY"
                    ? "bg-positive/15 text-positive"
                    : "bg-negative/15 text-negative"
                )}>
                  {t.type}
                </span>
              </td>
              <td className="px-3 py-1.5 text-right font-mono text-[11px] text-muted">{t.amount}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Mock 5: Price Chart with Insider Overlay ─────────────────────────────
function PriceChartMock() {
  // Stylized SVG line chart with green/red dots for insider buys/sells
  const w = 460, h = 200;
  const path = "M0,140 L40,135 L80,150 L120,120 L160,100 L200,90 L240,70 L260,55 L280,40 L320,50 L360,35 L400,25 L440,30 L460,28";
  const insiders = [
    { x: 80,  y: 150, type: "sell" },
    { x: 200, y: 90,  type: "buy"  },
    { x: 280, y: 40,  type: "buy"  },
    { x: 360, y: 35,  type: "sell" },
  ];
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-sm">MRNA</span>
          <span className="font-mono text-sm">$28.34</span>
          <span className="text-[10px] font-mono text-positive bg-positive/10 px-1 py-0.5 rounded">+18.4%</span>
        </div>
        <div className="flex items-center gap-2 text-[9px] text-muted">
          <span className="inline-flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-positive" /> Insider Buy
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-negative" /> Insider Sell
          </span>
        </div>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-[170px]">
        <defs>
          <linearGradient id="priceArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.3" />
            <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
          </linearGradient>
          <pattern id="grid" width="46" height="40" patternUnits="userSpaceOnUse">
            <path d="M 46 0 L 0 0 0 40" fill="none" stroke="var(--color-border)" strokeWidth="0.5" opacity="0.4" />
          </pattern>
        </defs>
        <rect width={w} height={h} fill="url(#grid)" />
        <path d={`${path} L${w},${h} L0,${h} Z`} fill="url(#priceArea)" />
        <path d={path} fill="none" stroke="var(--color-accent)" strokeWidth="2" />
        {insiders.map((p, i) => (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r="6" fill={p.type === "buy" ? "var(--color-positive)" : "var(--color-negative)"} opacity="0.2" />
            <circle cx={p.x} cy={p.y} r="3.5" fill={p.type === "buy" ? "var(--color-positive)" : "var(--color-negative)"} stroke="var(--color-background)" strokeWidth="1.5" />
          </g>
        ))}
      </svg>
    </div>
  );
}

// ── Mock 6: Most Shorted Biotechs ────────────────────────────────────────
function ShortInterestMock() {
  const tickers = [
    { ticker: "KMTS", name: "Kestra Medical",        pct: 80.8 },
    { ticker: "PROF", name: "Profound Medical",      pct: 79.9 },
    { ticker: "LBRX", name: "LB Pharma",             pct: 78.7 },
    { ticker: "NERV", name: "Minerva Neurosciences", pct: 75.4 },
    { ticker: "ELTX", name: "Elicio Therapeutics",   pct: 74.8 },
  ];
  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-surface/40 flex items-center justify-between">
        <span className="text-xs font-semibold">Most-Shorted Biotechs</span>
        <span className="text-[10px] font-mono text-muted">FINRA · 30d avg</span>
      </div>
      <div className="p-3 space-y-2.5">
        {tickers.map((t) => (
          <div key={t.ticker} className="grid grid-cols-[80px_1fr_60px] items-center gap-3">
            <div className="flex flex-col">
              <span className="font-mono font-bold text-[12px] text-accent">{t.ticker}</span>
              <span className="text-[9px] text-muted truncate">{t.name}</span>
            </div>
            <div className="h-2 rounded-full bg-surface overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-negative/60 to-negative rounded-full"
                style={{ width: `${t.pct}%` }}
              />
            </div>
            <span className="text-right font-mono text-[11px] font-semibold text-negative">
              {t.pct.toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function FeatureShowcase() {
  return (
    <section className="bg-gradient-to-b from-background via-surface/20 to-background border-y border-border/50">
      <div className="max-w-6xl mx-auto px-6 py-24 space-y-32">
        <div className="text-center">
          <p className="text-sm font-semibold text-accent uppercase tracking-wider">A closer look</p>
          <h2 className="text-3xl md:text-4xl font-bold mt-3">Built for biotech, not generic stocks</h2>
          <p className="text-muted mt-4 max-w-xl mx-auto text-[15px] leading-relaxed">
            Every feature is purpose-built for biotech's binary events — FDA decisions, trial readouts,
            insider activity around catalysts. Here&apos;s what you actually see when you log in.
          </p>
        </div>

        <ShowcaseRow
          eyebrow="PDUFA & Catalyst Calendar"
          title="Never miss an FDA decision"
          description="Every PDUFA date, advisory committee meeting, and trial readout in one calendar. Exact-day events get pinned to the day; month-precision events float at the top of the month so the layout stays honest."
          bullets={[
            "1,485+ upcoming biotech catalysts indexed",
            "Exact PDUFA dates auto-extracted from 8-K press releases",
            "FDA decision outcomes auto-cross-referenced with OpenFDA",
          ]}
          mock={<CalendarMock />}
        />

        <ShowcaseRow
          eyebrow="Drug Pipelines & Revenue"
          title="See every program from Phase 1 to $20B+ marketed"
          description="5,500+ drug programs across 1,000+ companies, with annual revenue extracted from 10-K disaggregated revenue tables via Claude. Mounjaro, Zepbound, Spikevax, Trulicity — all at exact dollar figures."
          bullets={[
            "Per-drug annual revenue from 10-K filings (LLY, AMGN, BIIB, etc.)",
            "Pipeline programs auto-extracted for thin-coverage tickers",
            "Phase tracking from Preclinical through Marketed",
          ]}
          mock={<PipelineMock />}
          reverse
        />

        <ShowcaseRow
          eyebrow="Press Releases · AI Summaries"
          title="The only signal in the 8-K firehose"
          description="Every biotech 8-K Item 7.01 / 8.01 press release, with a Claude-generated 2-sentence summary that tells you what happened AND why it matters to investors. Skip the boilerplate."
          bullets={[
            "645+ press releases indexed across the biotech universe",
            "AI summaries identify the news angle in 2 sentences",
            "Routine filings auto-tagged so you can ignore them",
          ]}
          mock={<PressReleasesMock />}
        />

        <ShowcaseRow
          eyebrow="Congressional Trades"
          title="See what Congress is buying"
          description="Pulled directly from disclosures-clerk.house.gov PTRs (Periodic Transaction Reports) and filtered to the biotech universe. Pelosi's VRTX position, Cisneros's BBIO buys — they're all here, days after they hit the public record."
          bullets={[
            "645 biotech trades from US House members (last 12 months)",
            "Sourced from official PTR PDFs — not a third-party mirror",
            "Filterable by ticker, member, party, trade type",
          ]}
          mock={<CongressTradesMock />}
          reverse
        />

        <ShowcaseRow
          eyebrow="Price Charts + Insider Overlay"
          title="Insider activity, plotted on the price chart"
          description="Form 4 buys (green) and sells (red) plotted on a 1-year price chart for every ticker we track. See exactly when management was loading up — usually right before a catalyst they knew was coming."
          bullets={[
            "1 year of OHLCV history for 500+ biotech tickers + 4 ETFs",
            "21,612 Form 4 insider transactions indexed",
            "Sparklines + days-to-cover from FINRA Reg SHO",
          ]}
          mock={<PriceChartMock />}
        />

        <ShowcaseRow
          eyebrow="Short Interest & Edge"
          title="Most-shorted biotechs, ranked"
          description="Daily short-volume from FINRA Reg SHO covering 53,000+ rows of biotech short interest. Filter out warrants and units — see only the legitimately shorted small-caps where short squeezes actually happen."
          bullets={[
            "53,053 short-interest rows from FINRA's free public feed",
            "30-day avg short_pct ranking by ticker",
            "Top 10 movers + catalyst impact stats",
          ]}
          mock={<ShortInterestMock />}
          reverse
        />

        <div className="text-center pt-4">
          <Link
            href="/dashboard"
            className="group inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-accent text-black font-bold text-[14px] hover:bg-accent-hover transition-all hover:shadow-lg hover:shadow-accent/20"
          >
            Tour the dashboard
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
          </Link>
        </div>
      </div>
    </section>
  );
}


/* ── How It Works ── */
function HowItWorks() {
  return (
    <section className="bg-surface/30 border-y border-border">
      <div className="max-w-6xl mx-auto px-6 py-24">
        <div className="text-center mb-16">
          <p className="text-sm font-semibold text-accent uppercase tracking-wider">How It Works</p>
          <h2 className="text-3xl md:text-4xl font-bold mt-3">Three steps to smarter trades</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            { num: "01", title: "Search", description: "Find biotech companies by name, ticker, therapeutic area, or pipeline stage." },
            { num: "02", title: "Analyze", description: "Dive into drug pipelines, clinical trials, catalysts, and insider activity." },
            { num: "03", title: "Trade", description: "Make informed decisions with catalyst dates, insider signals, and options data." },
          ].map((s) => (
            <div key={s.num} className="text-center group">
              <div className="w-14 h-14 rounded-full border-2 border-accent/30 flex items-center justify-center mx-auto mb-4 group-hover:border-accent group-hover:bg-accent/5 transition-all">
                <span className="text-accent font-bold text-lg">{s.num}</span>
              </div>
              <h3 className="font-semibold text-lg">{s.title}</h3>
              <p className="text-sm text-muted mt-2 max-w-xs mx-auto">{s.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Big Movers Section ── */
/* (replaced by TickerTape above the fold for impact) */

/* ── Pricing ── */
function Pricing() {
  const upgrade = useUpgrade();
  return (
    <section id="pricing" className="max-w-6xl mx-auto px-6 py-24">
      <div className="text-center mb-16">
        <p className="text-sm font-semibold text-accent uppercase tracking-wider">Pricing</p>
        <h2 className="text-3xl md:text-4xl font-bold mt-3">Simple, transparent pricing</h2>
        <p className="text-muted mt-4">Start free, upgrade when you need the full dataset.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-3xl mx-auto">
        {/* Free Plan */}
        <div className="rounded-xl border border-border bg-surface p-8">
          <h3 className="text-xl font-bold">Free</h3>
          <p className="text-sm text-muted mt-1">Get started with major biotech companies</p>
          <div className="flex items-baseline gap-1 mt-6">
            <span className="text-4xl font-bold">$0</span>
            <span className="text-muted text-sm">forever</span>
          </div>
          <Link href="/dashboard" className="block w-full text-center py-3 rounded-lg font-semibold text-sm mt-6 border border-border hover:bg-surface-hover transition-colors">
            Start Free
          </Link>
          <ul className="mt-8 space-y-3">
            {["Large-cap biotech companies", "Basic pipeline data", "Catalyst calendar", "Limited trial data"].map((f) => (
              <li key={f} className="flex items-start gap-3 text-sm">
                <Check className="w-4 h-4 text-accent shrink-0 mt-0.5" />
                {f}
              </li>
            ))}
            {["All companies & small-caps", "Full SEC filings & insider data", "Options flow analytics"].map((f) => (
              <li key={f} className="flex items-start gap-3 text-sm text-muted/50">
                <X className="w-4 h-4 text-muted/30 shrink-0 mt-0.5" />
                {f}
              </li>
            ))}
          </ul>
        </div>

        {/* Pro Plan */}
        <div className="rounded-xl border border-accent bg-accent/5 p-8 relative">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full bg-accent text-black text-xs font-bold">
            Most Popular
          </div>
          <h3 className="text-xl font-bold">Pro</h3>
          <p className="text-sm text-muted mt-1">Full access to all biotech data</p>
          <div className="flex items-baseline gap-1 mt-6">
            <span className="text-4xl font-bold">$19.99</span>
            <span className="text-muted text-sm">/month</span>
          </div>
          <button
            type="button"
            onClick={() => { upgrade(); }}
            className="block w-full text-center py-3 rounded-lg font-semibold text-sm mt-6 bg-accent text-black hover:bg-accent-hover transition-colors"
          >
            Upgrade to Pro
          </button>
          <ul className="mt-8 space-y-3">
            {[
              "All 1,000+ biotech companies",
              "Complete drug pipelines (2,800+)",
              "Full catalyst calendar with scoring",
              "5,400+ clinical trials",
              "18,000+ SEC filings & Form 4 tracking",
              "Insider activity signals",
              "Options flow analytics",
              "Priority data updates",
            ].map((f) => (
              <li key={f} className="flex items-start gap-3 text-sm">
                <Check className="w-4 h-4 text-accent shrink-0 mt-0.5" />
                {f}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

/* ── FAQ ── */
function FAQ() {
  const faqs = [
    { q: "Why invest in biotech?", a: "Biotech stocks can move 50-200% on a single FDA decision or clinical trial result. A Phase 3 success or new drug approval can double a stock overnight. This volatility creates huge opportunities for informed traders who track catalysts." },
    { q: "What is a PDUFA date?", a: "PDUFA (Prescription Drug User Fee Act) dates are FDA-mandated deadlines for drug approval decisions. The FDA must respond by the PDUFA date, making them the most predictable binary events in biotech. Stocks often move significantly on these dates." },
    { q: "What are clinical trial phases?", a: "Phase 1 tests safety in a small group. Phase 2 tests efficacy and dosing. Phase 3 is the pivotal trial with thousands of patients — success here often leads to FDA approval. Phase 4 is post-approval monitoring. Each phase advancement is a bullish catalyst." },
    { q: "What is a catalyst in biotech?", a: "A catalyst is any upcoming event that could move a stock's price — FDA decisions, clinical trial data readouts, advisory committee meetings, earnings, or conference presentations. Biotick scores each catalyst by significance so you know which ones matter most." },
    { q: "Where does the data come from?", a: "We aggregate from ClinicalTrials.gov (5,400+ trials), SEC EDGAR (18,000+ filings and insider trades), OpenFDA (approval data), and Finnhub (real-time market data). All data is normalized and cross-referenced." },
    { q: "How often is the data updated?", a: "Stock prices update every 15 minutes during market hours. SEC filings sync every 6 hours. Clinical trials and catalysts update daily. Options flow data refreshes daily." },
    { q: "What does the put/call ratio tell me?", a: "The put/call ratio measures bearish vs bullish options activity. A ratio above 1.0 means more puts (bearish bets) than calls. Below 0.7 is bullish. In biotech, a rising put/call ratio before a catalyst often signals institutional hedging." },
    { q: "Why can't I just short everything that looks bad?", a: "You could, but shorting has unlimited loss potential — one surprise FDA approval or buyout can send a stock up 200% overnight and wipe out all your gains in a single trade. That's why biotech shorting is extremely risky. Many experienced traders have been wiped out by a single binary event going against them." },
    { q: "Can I cancel my Pro subscription?", a: "Yes, cancel anytime from your Stripe billing portal. Your access continues until the end of your billing period. No questions asked." },
  ];

  return (
    <section id="faq" className="bg-surface/30 border-y border-border">
      <div className="max-w-3xl mx-auto px-6 py-24">
        <div className="text-center mb-12">
          <p className="text-sm font-semibold text-accent uppercase tracking-wider">FAQ</p>
          <h2 className="text-3xl font-bold mt-3">Frequently asked questions</h2>
        </div>
        <div className="space-y-3">
          {faqs.map((faq) => <FAQItem key={faq.q} question={faq.q} answer={faq.a} />)}
        </div>
      </div>
    </section>
  );
}

function FAQItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-border bg-surface overflow-hidden">
      <button onClick={() => setOpen(!open)} className="flex items-center justify-between w-full px-6 py-4 text-left text-sm font-medium hover:bg-surface-hover transition-colors">
        {question}
        {open ? <ChevronUp className="w-4 h-4 text-muted shrink-0" /> : <ChevronDown className="w-4 h-4 text-muted shrink-0" />}
      </button>
      <div className={cn("grid transition-all duration-200", open ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
        <div className="overflow-hidden">
          <div className="px-6 pb-4 text-sm text-muted leading-relaxed">{answer}</div>
        </div>
      </div>
    </div>
  );
}

/* ── Footer ── */
function Footer() {
  return (
    <footer className="border-t border-border bg-background">
      <div className="max-w-6xl mx-auto px-6 py-12 space-y-8">
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-md bg-accent flex items-center justify-center">
              <Activity className="w-3.5 h-3.5 text-black" />
            </div>
            <span className="font-bold text-sm">Biotick</span>
          </div>
          <div className="flex items-center gap-x-6 gap-y-2 text-sm text-muted flex-wrap justify-center">
            <a href="#features" className="hover:text-foreground transition">Features</a>
            <a href="#pricing" className="hover:text-foreground transition">Pricing</a>
            <a href="#faq" className="hover:text-foreground transition">FAQ</a>
            <Link href="/dashboard" className="hover:text-foreground transition">App</Link>
            <Link href="/privacy" className="hover:text-foreground transition">Privacy</Link>
            <Link href="/terms" className="hover:text-foreground transition">Terms</Link>
          </div>
          <p className="text-xs text-muted">&copy; {new Date().getFullYear()} Biotick.</p>
        </div>

        {/* Disclaimer — required wherever we're shown. Kept small and neutral-colored. */}
        <p className="text-[11px] leading-relaxed text-muted/60 max-w-3xl mx-auto text-center border-t border-border/50 pt-6">
          <span className="text-muted font-medium">Not financial advice.</span>{" "}
          Biotick is a research tool for informational purposes only. We are not a registered
          investment advisor. Nothing on this site is a recommendation to buy, sell, or hold any
          security. Biotech investing is volatile and you can lose your entire investment. Data
          is aggregated from public sources and provided without warranty — verify anything
          important against the primary source.
        </p>
      </div>
    </footer>
  );
}
