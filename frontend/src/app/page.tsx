"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import {
  Activity,
  Search,
  Calendar,
  FlaskConical,
  FileText,
  TrendingUp,
  TrendingDown,
  ArrowRight,
  Check,
  X,
  ChevronDown,
  ChevronUp,
  BarChart3,
  Zap,
  Dna,
  Microscope,
  Pill,
  HeartPulse,
} from "lucide-react";
import { cn } from "@/lib/utils";

const STRIPE_PRO_URL = "https://buy.stripe.com/4gM14n9m1914cGm5lq73G02";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <Hero />
      <TickerTape />
      <Stats />
      <Features />
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
  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handler);
    return () => window.removeEventListener("scroll", handler);
  }, []);

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
          <Link href="/login" className="text-sm text-muted hover:text-foreground transition hidden sm:block">
            Log In
          </Link>
          <Link href="/signup" className="px-4 py-2 rounded-md bg-accent text-black text-sm font-semibold hover:bg-accent-hover transition">
            Get Started
          </Link>
        </div>
      </div>
    </nav>
  );
}

/* ── Hero with biotech background ── */
function Hero() {
  return (
    <section className="relative overflow-hidden min-h-[85vh] flex items-center">
      {/* Animated background */}
      <div className="absolute inset-0">
        {/* DNA helix gradient */}
        <div className="absolute inset-0 bg-gradient-to-b from-accent/8 via-accent/3 to-transparent" />
        {/* Floating molecule dots */}
        <div className="absolute inset-0 overflow-hidden">
          {Array.from({ length: 30 }).map((_, i) => (
            <div
              key={i}
              className="absolute rounded-full bg-accent/20 animate-pulse"
              style={{
                width: `${Math.random() * 4 + 2}px`,
                height: `${Math.random() * 4 + 2}px`,
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                animationDelay: `${Math.random() * 5}s`,
                animationDuration: `${Math.random() * 3 + 2}s`,
              }}
            />
          ))}
        </div>
        {/* Grid overlay */}
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: "linear-gradient(var(--color-accent) 1px, transparent 1px), linear-gradient(90deg, var(--color-accent) 1px, transparent 1px)",
            backgroundSize: "60px 60px",
          }}
        />
        {/* Floating biotech icons */}
        <div className="absolute top-20 left-[10%] text-accent/10 animate-bounce" style={{ animationDuration: "6s" }}>
          <Dna className="w-16 h-16" />
        </div>
        <div className="absolute top-40 right-[15%] text-accent/10 animate-bounce" style={{ animationDuration: "8s", animationDelay: "2s" }}>
          <Microscope className="w-12 h-12" />
        </div>
        <div className="absolute bottom-32 left-[20%] text-accent/10 animate-bounce" style={{ animationDuration: "7s", animationDelay: "1s" }}>
          <Pill className="w-10 h-10" />
        </div>
        <div className="absolute bottom-20 right-[25%] text-accent/10 animate-bounce" style={{ animationDuration: "9s", animationDelay: "3s" }}>
          <HeartPulse className="w-14 h-14" />
        </div>
      </div>

      <div className="relative max-w-6xl mx-auto px-6 py-24 text-center">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-accent/20 bg-accent/5 text-accent text-xs font-medium mb-8 animate-fade-in">
          <Zap className="w-3 h-3" />
          Real-time biotech intelligence for serious traders
        </div>

        <h1 className="text-5xl md:text-6xl lg:text-[80px] font-bold tracking-tight leading-[1.05] max-w-5xl mx-auto animate-fade-in" style={{ animationDelay: "0.1s" }}>
          Your unfair advantage in{" "}
          <span className="relative">
            <span className="text-accent">biotech</span>
            <span className="absolute -bottom-2 left-0 right-0 h-1 bg-accent/30 rounded-full" />
          </span>
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
            Start Free
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
function TickerTape() {
  const tickers = [
    { sym: "LLY", price: 905.03, change: -1.89 },
    { sym: "NVO", price: 39.32, change: 3.53 },
    { sym: "ABBV", price: 210.26, change: 1.84 },
    { sym: "MRNA", price: 54.26, change: 2.69 },
    { sym: "PFE", price: 27.11, change: -0.76 },
    { sym: "AMGN", price: 350.95, change: 0.30 },
    { sym: "GILD", price: 140.45, change: 1.02 },
    { sym: "VRTX", price: 444.28, change: 1.01 },
    { sym: "REGN", price: 668.85, change: -0.44 },
    { sym: "BIIB", price: 134.20, change: -2.10 },
    { sym: "ALNY", price: 333.39, change: -1.77 },
    { sym: "INCY", price: 55.80, change: 0.92 },
  ];

  // Double for seamless scroll
  const doubled = [...tickers, ...tickers];

  return (
    <div className="border-y border-border bg-surface/50 overflow-hidden">
      <div className="flex animate-ticker-scroll">
        {doubled.map((t, i) => (
          <div key={i} className="flex items-center gap-3 px-6 py-3 shrink-0 border-r border-border/50">
            <span className="font-bold text-sm">{t.sym}</span>
            <span className="font-mono text-sm">${t.price.toFixed(2)}</span>
            <span className={cn(
              "font-mono text-xs font-semibold px-1.5 py-0.5 rounded",
              t.change >= 0 ? "text-positive bg-positive/10" : "text-negative bg-negative/10"
            )}>
              {t.change >= 0 ? "+" : ""}{t.change.toFixed(2)}%
            </span>
          </div>
        ))}
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
          { value: "1,054", label: "Biotech Companies", icon: Search },
          { value: "5,400+", label: "Clinical Trials", icon: FlaskConical },
          { value: "2,800+", label: "Drug Programs", icon: Pill },
          { value: "18,000+", label: "SEC Filings", icon: FileText },
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
    { icon: Search, title: "Company Screener", description: "Filter and sort 1,000+ US-listed biotech companies by market cap, exchange, therapeutic area, and pipeline stage." },
    { icon: FlaskConical, title: "Drug Pipeline Tracker", description: "Track every drug from Phase 1 through approval. See indications, mechanisms, and trial timelines at a glance." },
    { icon: Calendar, title: "Catalyst Calendar", description: "Never miss an FDA decision or data readout. Catalysts scored by significance with confidence levels." },
    { icon: BarChart3, title: "Options Flow", description: "Visualize call vs put volume by expiration. Put/call ratio and sentiment analysis for every biotech stock." },
    { icon: FileText, title: "SEC Filings", description: "Monitor 10-K, 10-Q, 8-K filings and Form 4 insider trades. Spot insider buying before the market does." },
    { icon: TrendingUp, title: "Insider Activity", description: "Track insider buying and selling with net activity signals. See who's putting their money where their mouth is." },
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
          <a
            href={STRIPE_PRO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full text-center py-3 rounded-lg font-semibold text-sm mt-6 bg-accent text-black hover:bg-accent-hover transition-colors"
          >
            Upgrade to Pro
          </a>
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
    { q: "Where does the data come from?", a: "We pull data from ClinicalTrials.gov, SEC EDGAR, OpenFDA, and Finnhub. All data is normalized and cross-referenced for trading relevance." },
    { q: "How often is the data updated?", a: "Market data updates every 15 minutes during trading hours. SEC filings sync every 6 hours. Clinical trials update daily." },
    { q: "Can I cancel my Pro subscription?", a: "Yes, cancel anytime. Your access continues until the end of your billing period. No questions asked." },
    { q: "Is there an API?", a: "Not yet, but we're planning a developer API. Join the waitlist by signing up for a free account." },
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
      <div className="max-w-6xl mx-auto px-6 py-12">
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-md bg-accent flex items-center justify-center">
              <Activity className="w-3.5 h-3.5 text-black" />
            </div>
            <span className="font-bold text-sm">Biotick</span>
          </div>
          <div className="flex items-center gap-6 text-sm text-muted">
            <a href="#features" className="hover:text-foreground transition">Features</a>
            <a href="#pricing" className="hover:text-foreground transition">Pricing</a>
            <a href="#faq" className="hover:text-foreground transition">FAQ</a>
            <Link href="/dashboard" className="hover:text-foreground transition">App</Link>
          </div>
          <p className="text-xs text-muted">&copy; {new Date().getFullYear()} Biotick. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}
