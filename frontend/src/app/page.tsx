"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Activity,
  Search,
  Calendar,
  Sparkles,
  FlaskConical,
  FileText,
  TrendingUp,
  ArrowRight,
  Check,
  X,
  ChevronDown,
  ChevronUp,
  BarChart3,
  Shield,
  Zap,
  Globe,
} from "lucide-react";
import { cn } from "@/lib/utils";

const STRIPE_PRO_URL = "https://buy.stripe.com/4gM14n9m1914cGm5lq73G02";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <Hero />
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
  return (
    <nav className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-lg">
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
          <Link
            href="/login"
            className="text-sm text-muted hover:text-foreground transition hidden sm:block"
          >
            Log In
          </Link>
          <Link
            href="/signup"
            className="px-4 py-2 rounded-md bg-accent text-black text-sm font-semibold hover:bg-accent-hover transition"
          >
            Get Started
          </Link>
        </div>
      </div>
    </nav>
  );
}

/* ── Hero ── */
function Hero() {
  return (
    <section className="relative overflow-hidden">
      {/* Gradient bg */}
      <div className="absolute inset-0 bg-gradient-to-b from-accent/5 via-transparent to-transparent" />

      <div className="relative max-w-6xl mx-auto px-6 pt-24 pb-20 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-accent/20 bg-accent/5 text-accent text-xs font-medium mb-6">
          <Zap className="w-3 h-3" />
          Professional Biotech Research
        </div>

        <h1 className="text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.1] max-w-4xl mx-auto">
          The edge you need in{" "}
          <span className="text-accent">biotech trading</span>
        </h1>

        <p className="text-lg md:text-xl text-muted mt-6 max-w-2xl mx-auto leading-relaxed">
          Track clinical trials, monitor FDA catalysts, analyze drug pipelines,
          and spot insider trading signals — all in one platform.
        </p>

        <div className="flex items-center justify-center gap-4 mt-10">
          <Link
            href="/dashboard"
            className="px-6 py-3 rounded-lg bg-accent text-black font-semibold text-sm hover:bg-accent-hover transition-colors flex items-center gap-2"
          >
            Start Free
            <ArrowRight className="w-4 h-4" />
          </Link>
          <a
            href="#pricing"
            className="px-6 py-3 rounded-lg border border-border text-sm font-medium hover:bg-surface-hover transition-colors"
          >
            View Pricing
          </a>
        </div>
      </div>
    </section>
  );
}

/* ── Stats ── */
function Stats() {
  const stats = [
    { value: "500+", label: "Biotech Companies" },
    { value: "200K+", label: "Clinical Trials" },
    { value: "600+", label: "Drug Pipelines" },
    { value: "Real-time", label: "Catalyst Tracking" },
  ];

  return (
    <section className="border-y border-border bg-surface/30">
      <div className="max-w-6xl mx-auto px-6 py-10">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          {stats.map((s) => (
            <div key={s.label} className="text-center">
              <p className="text-3xl font-bold text-accent">{s.value}</p>
              <p className="text-sm text-muted mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Features ── */
function Features() {
  const features = [
    {
      icon: Search,
      title: "Company Screener",
      description: "Filter and sort all US-listed biotech companies by market cap, exchange, therapeutic area, and pipeline stage.",
    },
    {
      icon: FlaskConical,
      title: "Drug Pipeline Tracker",
      description: "Track every drug from Phase 1 through approval. See indications, mechanisms, and trial timelines at a glance.",
    },
    {
      icon: Calendar,
      title: "Catalyst Calendar",
      description: "Never miss an FDA decision or data readout. Catalysts scored by significance with confidence levels.",
    },
    {
      icon: BarChart3,
      title: "Options Flow",
      description: "Visualize call vs put volume by expiration. Put/call ratio and sentiment analysis for every biotech stock.",
    },
    {
      icon: FileText,
      title: "SEC Filings",
      description: "Monitor 10-K, 10-Q, 8-K filings and Form 4 insider trades. Spot insider buying before the market does.",
    },
    {
      icon: TrendingUp,
      title: "Insider Activity",
      description: "Track insider buying and selling with net activity signals. See who's putting their money where their mouth is.",
    },
  ];

  return (
    <section id="features" className="max-w-6xl mx-auto px-6 py-24">
      <div className="text-center mb-16">
        <p className="text-sm font-semibold text-accent uppercase tracking-wider">Features</p>
        <h2 className="text-3xl md:text-4xl font-bold mt-3">
          Everything you need to trade biotech
        </h2>
        <p className="text-muted mt-4 max-w-lg mx-auto">
          Comprehensive data from ClinicalTrials.gov, SEC EDGAR, and market feeds — normalized and ready for trading decisions.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {features.map((f) => (
          <div
            key={f.title}
            className="rounded-xl border border-border bg-surface p-6 hover:border-accent/30 transition-colors group"
          >
            <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center mb-4 group-hover:bg-accent/15 transition-colors">
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
  const steps = [
    { num: "01", title: "Search", description: "Find biotech companies by name, ticker, therapeutic area, or pipeline stage." },
    { num: "02", title: "Analyze", description: "Dive into drug pipelines, clinical trials, catalysts, and insider activity." },
    { num: "03", title: "Trade", description: "Make informed decisions with catalyst dates, insider signals, and options data at your fingertips." },
  ];

  return (
    <section className="bg-surface/30 border-y border-border">
      <div className="max-w-6xl mx-auto px-6 py-24">
        <div className="text-center mb-16">
          <p className="text-sm font-semibold text-accent uppercase tracking-wider">How It Works</p>
          <h2 className="text-3xl md:text-4xl font-bold mt-3">Three steps to smarter trades</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {steps.map((s) => (
            <div key={s.num} className="text-center">
              <div className="w-14 h-14 rounded-full border-2 border-accent/30 flex items-center justify-center mx-auto mb-4">
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

/* ── Pricing ── */
function Pricing() {
  const plans = [
    {
      name: "Free",
      price: "$0",
      period: "forever",
      description: "Get started with major biotech companies",
      cta: "Start Free",
      ctaHref: "/dashboard",
      highlight: false,
      features: [
        { text: "Large-cap biotech companies (>$10B)", included: true },
        { text: "Basic pipeline data", included: true },
        { text: "Catalyst calendar", included: true },
        { text: "Limited trial data", included: true },
        { text: "All companies & small-caps", included: false },
        { text: "Full SEC filings & insider data", included: false },
        { text: "Options analytics", included: false },
      ],
    },
    {
      name: "Pro",
      price: "$19.99",
      period: "/month",
      description: "Full access to all biotech data",
      cta: "Upgrade to Pro",
      ctaHref: STRIPE_PRO_URL,
      highlight: true,
      features: [
        { text: "All biotech companies (500+)", included: true },
        { text: "Complete drug pipelines", included: true },
        { text: "Full catalyst calendar with scoring", included: true },
        { text: "200K+ clinical trials", included: true },
        { text: "SEC filings & Form 4 tracking", included: true },
        { text: "Insider activity signals", included: true },
        { text: "Priority data updates", included: true },
      ],
    },
  ];

  return (
    <section id="pricing" className="max-w-6xl mx-auto px-6 py-24">
      <div className="text-center mb-16">
        <p className="text-sm font-semibold text-accent uppercase tracking-wider">Pricing</p>
        <h2 className="text-3xl md:text-4xl font-bold mt-3">Simple, transparent pricing</h2>
        <p className="text-muted mt-4">Start free, upgrade when you need the full dataset.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-3xl mx-auto">
        {plans.map((plan) => (
          <div
            key={plan.name}
            className={cn(
              "rounded-xl border p-8 relative",
              plan.highlight
                ? "border-accent bg-accent/5"
                : "border-border bg-surface"
            )}
          >
            {plan.highlight && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full bg-accent text-black text-xs font-bold">
                Most Popular
              </div>
            )}

            <h3 className="text-xl font-bold">{plan.name}</h3>
            <p className="text-sm text-muted mt-1">{plan.description}</p>

            <div className="flex items-baseline gap-1 mt-6">
              <span className="text-4xl font-bold">{plan.price}</span>
              <span className="text-muted text-sm">{plan.period}</span>
            </div>

            <a
              href={plan.ctaHref}
              target={plan.highlight ? "_blank" : undefined}
              rel={plan.highlight ? "noopener noreferrer" : undefined}
              className={cn(
                "block w-full text-center py-3 rounded-lg font-semibold text-sm mt-6 transition-colors",
                plan.highlight
                  ? "bg-accent text-black hover:bg-accent-hover"
                  : "border border-border hover:bg-surface-hover"
              )}
            >
              {plan.cta}
            </a>

            <ul className="mt-8 space-y-3">
              {plan.features.map((f) => (
                <li key={f.text} className="flex items-start gap-3 text-sm">
                  {f.included ? (
                    <Check className="w-4 h-4 text-accent shrink-0 mt-0.5" />
                  ) : (
                    <X className="w-4 h-4 text-muted/30 shrink-0 mt-0.5" />
                  )}
                  <span className={f.included ? "" : "text-muted/50"}>
                    {f.text}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ── FAQ ── */
function FAQ() {
  const faqs = [
    {
      q: "Where does the data come from?",
      a: "We pull data from ClinicalTrials.gov (clinical trials), SEC EDGAR (filings and insider trades), and market data APIs. All data is normalized and cross-referenced for trading relevance.",
    },
    {
      q: "How often is the data updated?",
      a: "Clinical trial data syncs every 6 hours. Market data updates every 15 minutes during market hours. SEC filings sync every 4 hours.",
    },
    {
      q: "What data sources do you use?",
      a: "We aggregate data from ClinicalTrials.gov (444K+ trials), SEC EDGAR (filings and insider trades), FDA databases, and real-time market feeds. All data is normalized and cross-referenced for trading relevance.",
    },
    {
      q: "Can I cancel my Pro subscription?",
      a: "Yes, you can cancel anytime. Your access continues until the end of your billing period.",
    },
  ];

  return (
    <section id="faq" className="bg-surface/30 border-y border-border">
      <div className="max-w-3xl mx-auto px-6 py-24">
        <div className="text-center mb-12">
          <p className="text-sm font-semibold text-accent uppercase tracking-wider">FAQ</p>
          <h2 className="text-3xl font-bold mt-3">Frequently asked questions</h2>
        </div>

        <div className="space-y-3">
          {faqs.map((faq) => (
            <FAQItem key={faq.q} question={faq.q} answer={faq.a} />
          ))}
        </div>
      </div>
    </section>
  );
}

function FAQItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-border bg-surface overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full px-6 py-4 text-left text-sm font-medium hover:bg-surface-hover transition-colors"
      >
        {question}
        {open ? (
          <ChevronUp className="w-4 h-4 text-muted shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-muted shrink-0" />
        )}
      </button>
      {open && (
        <div className="px-6 pb-4 text-sm text-muted leading-relaxed">
          {answer}
        </div>
      )}
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

          <p className="text-xs text-muted">
            &copy; {new Date().getFullYear()} Biotick. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
