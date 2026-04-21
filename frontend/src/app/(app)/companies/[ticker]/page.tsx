"use client";

import { use, useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { PaywallBanner } from "@/components/PaywallGate";
import { usePlan } from "@/hooks/usePlan";
import {
  ArrowLeft,
  ExternalLink,
  Globe,
  Loader2,
  FlaskConical,
  FileText,
  TrendingUp,
  TrendingDown,
  ArrowUpRight,
  ArrowDownRight,
  BarChart3,
  Calendar,
  Beaker,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import type { Company, Drug, Trial } from "@/lib/types";
import { formatMarketCap, formatPrice, formatPercent, cn, formatNumber } from "@/lib/utils";
import { PHASE_COLORS, PHASE_LABELS, THERAPEUTIC_AREA_COLORS, STATUS_COLORS, STATUS_LABELS } from "@/lib/constants";
import { FactorSummaryBadge, useBatchFactors } from "@/components/TrialFactors";
import { PriceHistoryChart } from "@/components/PriceHistoryChart";
import { ShortInterestCard } from "@/components/ShortInterestCard";

interface Filing {
  id: number;
  filing_type: string;
  filed_date: string | null;
  edgar_url: string | null;
  description: string | null;
}

interface InsiderTrade {
  id: number;
  insider_name: string;
  insider_title: string | null;
  trade_type: string;
  transaction_date: string | null;
  shares: number;
  price_per_share: number | null;
  total_value: number | null;
}

interface InsiderSummary {
  total_buy_value: number;
  total_sell_value: number;
  net_value: number;
  buy_transactions: number;
  sell_transactions: number;
  signal: string;
}

interface OptionRow {
  strike: number;
  bid: number;
  ask: number;
  last: number;
  volume: number;
  open_interest: number;
  iv: number;
  in_the_money: boolean;
}

interface NewsArticle {
  id: number | string;
  headline: string;
  summary: string;
  source: string;
  url: string;
  image: string;
  datetime: number;
  category: string;
  related: string;
}

interface InstitutionalHoldingRow {
  id: number;
  ticker: string;
  fund_name: string;
  fund_cik: string;
  shares: number | null;
  value: number | null;
  quarter_end: string | null;
  filing_date: string | null;
  edgar_url: string;
}

interface ETFHoldingRow {
  id: number;
  etf_ticker: string;
  ticker: string;
  weight: number | null;
  shares: number | null;
  market_value: number | null;
  updated_at: string | null;
}

interface PatentRow {
  id: number;
  patent_number: string;
  title: string | null;
  assignee_name: string | null;
  company_ticker: string | null;
  filing_date: string | null;
  grant_date: string | null;
  expiration_date: string | null;
  abstract: string | null;
  patent_type: string | null;
  uspto_url: string | null;
}

export default function CompanyDetailPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = use(params);
  const [activeTab, setActiveTab] = useState<"overview" | "price" | "pipeline" | "trials" | "options" | "filings" | "news" | "patents">("overview");

  const { data: company, isLoading } = useQuery<Company>({
    queryKey: ["company", ticker],
    queryFn: () => fetchAPI(`/companies/${ticker}`),
  });

  const { data: pipeline } = useQuery<Drug[]>({
    queryKey: ["pipeline", ticker],
    queryFn: () => fetchAPI(`/companies/${ticker}/pipeline`),
  });

  const { data: trialsData } = useQuery<{ trials: Trial[]; total: number }>({
    queryKey: ["all-trials", ticker],
    queryFn: () => fetchAPI(`/companies/${ticker}/all-trials?per_page=50`),
  });

  const { data: filingsData } = useQuery<{ filings: Filing[] }>({
    queryKey: ["filings", ticker],
    queryFn: () => fetchAPI(`/companies/${ticker}/filings?per_page=20`),
  });

  const { data: tradesData } = useQuery<{ trades: InsiderTrade[] }>({
    queryKey: ["insider-trades", ticker],
    // /form4 avoids ad-blocker filters that target "insider-trades" in URLs
    queryFn: () => fetchAPI(`/companies/${ticker}/form4?per_page=10`),
  });

  const { data: insiderSummary } = useQuery<InsiderSummary>({
    queryKey: ["insider-summary", ticker],
    queryFn: () => fetchAPI(`/companies/${ticker}/insider-summary`),
  });

  const { data: optionsVolume } = useQuery<{
    data: Array<{ expiration: string; call_volume: number; put_volume: number; call_iv: number; put_iv: number; avg_iv: number }>;
    total_call_volume: number;
    total_put_volume: number;
    avg_iv?: number;
    put_call_ratio: number;
  }>({
    queryKey: ["options-volume", ticker],
    queryFn: () => fetchAPI(`/options/${ticker}/volume-summary`),
    enabled: activeTab === "options",
  });

  const { data: competitorData } = useQuery<{
    therapeutic_areas: string[];
    competitors: Array<{ ticker: string; name: string; price: number | null; market_cap: number | null; pipeline_size: number; overlapping_areas: Record<string, number> }>;
  }>({
    queryKey: ["competitors", ticker],
    queryFn: () => fetchAPI(`/competitors/company/${ticker}`),
    enabled: activeTab === "overview",
  });

  const { data: shortData } = useQuery<{
    short_interest: Array<{ date: string; short_interest: number; days_to_cover: number }>;
    institutional_ownership: Array<{ name: string; shares: number; change: number }>;
    insider_sentiment: Array<{ month: string; change: number; mspr: number }>;
  }>({
    queryKey: ["short-interest", ticker],
    queryFn: () => fetchAPI(`/edge/short-interest/${ticker}`),
    enabled: activeTab === "overview",
  });

  const { data: newsData } = useQuery<{
    ticker: string;
    articles: NewsArticle[];
    total?: number;
  }>({
    queryKey: ["company-news", ticker],
    queryFn: () => fetchAPI(`/companies/${ticker}/news?days=7&limit=20`),
    enabled: activeTab === "news",
  });

  const { data: institutionalData } = useQuery<{
    ticker: string;
    holdings: InstitutionalHoldingRow[];
    total: number;
    total_value: number;
    total_shares: number;
  }>({
    queryKey: ["institutional", ticker],
    queryFn: () => fetchAPI(`/companies/${ticker}/institutional`),
    enabled: activeTab === "overview",
  });

  const { data: etfData } = useQuery<{
    ticker: string;
    etfs: ETFHoldingRow[];
    total: number;
  }>({
    queryKey: ["etfs", ticker],
    queryFn: () => fetchAPI(`/companies/${ticker}/etfs`),
    enabled: activeTab === "overview",
  });

  const { data: patentsData } = useQuery<{
    ticker: string;
    patents: PatentRow[];
    total: number;
    page: number;
    per_page: number;
    total_pages: number;
  }>({
    queryKey: ["patents", ticker],
    queryFn: () => fetchAPI(`/companies/${ticker}/patents?per_page=20`),
    enabled: activeTab === "patents",
  });

  const _unused_effect = useEffect; // keep import used

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-5 h-5 animate-spin text-accent" />
      </div>
    );
  }

  if (!company) {
    return (
      <div className="text-center py-20">
        <p className="text-muted">Company not found</p>
      </div>
    );
  }

  const changePositive = (company.price_change_pct ?? 0) >= 0;

  const tabs = [
    { id: "overview" as const, label: "Overview" },
    { id: "price" as const, label: "Price" },
    { id: "pipeline" as const, label: "Pipeline", count: pipeline?.length },
    { id: "trials" as const, label: "Clinical Trials", count: trialsData?.total },
    { id: "options" as const, label: "Options Flow" },
    { id: "filings" as const, label: "SEC Filings", count: filingsData?.filings?.length },
    { id: "news" as const, label: "News" },
    { id: "patents" as const, label: "Patents", count: patentsData?.total },
  ];

  return (
    <div className="space-y-6">
      {/* Back */}
      <Link href="/companies" className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-foreground transition">
        <ArrowLeft className="w-3.5 h-3.5" />
        Screener
      </Link>

      {/* Stock header */}
      <div className="flex items-start justify-between gap-6">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold">{company.name}</h1>
            <span className="text-xs bg-surface-hover px-2 py-0.5 rounded text-muted font-mono">{company.ticker}</span>
          </div>
          <div className="flex items-baseline gap-3 mt-2">
            <span className="text-4xl font-bold tracking-tight font-mono">{formatPrice(company.price)}</span>
            <span className={cn("text-lg font-semibold flex items-center gap-0.5", changePositive ? "text-positive" : "text-negative")}>
              {changePositive ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
              {formatPercent(company.price_change_pct)}
            </span>
          </div>
          <div className="flex gap-6 mt-3 text-xs">
            <Stat label="Market Cap" value={formatMarketCap(company.market_cap)} />
            <Stat label="Exchange" value={company.exchange || "N/A"} />
            <Stat label="Sector" value={company.sector || "Biotech"} />
            {company.website && (
              <a href={company.website} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-accent hover:underline">
                <Globe className="w-3 h-3" /> Website
              </a>
            )}
          </div>
        </div>

        {/* Insider summary */}
        {insiderSummary && (insiderSummary.buy_transactions > 0 || insiderSummary.sell_transactions > 0) && (
          <div className={cn("rounded-lg border p-4 text-right shrink-0 min-w-[180px]",
            insiderSummary.signal === "BULLISH" ? "border-positive/30 bg-positive/5" :
            insiderSummary.signal === "BEARISH" ? "border-negative/30 bg-negative/5" : "border-border bg-surface"
          )}>
            <p className="text-[10px] text-muted uppercase font-semibold">90-Day Insider</p>
            <p className={cn("text-xl font-bold font-mono mt-1",
              insiderSummary.signal === "BULLISH" ? "text-positive" : insiderSummary.signal === "BEARISH" ? "text-negative" : ""
            )}>
              {insiderSummary.signal}
            </p>
            <p className="text-[11px] text-muted mt-1">{insiderSummary.buy_transactions} buys / {insiderSummary.sell_transactions} sells</p>
          </div>
        )}
      </div>

      {company.description && (
        <p className="text-sm text-muted leading-relaxed max-w-3xl line-clamp-2">{company.description}</p>
      )}

      {/* Tabs */}
      <div className="border-b border-border">
        <div className="flex gap-0">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "px-4 py-2.5 text-[13px] font-medium border-b-2 transition-colors",
                activeTab === tab.id
                  ? "border-accent text-accent"
                  : "border-transparent text-muted hover:text-foreground"
              )}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span className="ml-1.5 text-[11px] text-muted">({tab.count})</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      {activeTab === "overview" && (
        <OverviewTab
          company={company}
          pipeline={pipeline || []}
          insiderSummary={insiderSummary}
          trialsTotal={trialsData?.total || 0}
          filingsCount={filingsData?.filings?.length || 0}
          competitors={competitorData}
          shortInterest={shortData}
          institutional={institutionalData}
          etfs={etfData}
        />
      )}

      {activeTab === "price" && (
        <div className="space-y-4">
          <PriceHistoryChart ticker={company.ticker} />
          <ShortInterestCard ticker={company.ticker} />
        </div>
      )}

      {activeTab === "pipeline" && (
        <PipelineTab pipeline={pipeline || []} />
      )}

      {activeTab === "trials" && (
        <TrialsTab trials={trialsData?.trials || []} total={trialsData?.total || 0} />
      )}

      {activeTab === "options" && (
        <>
          <PaywallBanner feature="Options Flow" />
          <OptionsFlowTab data={optionsVolume} />
        </>
      )}

      {activeTab === "filings" && (
        <>
          <PaywallBanner feature="Full SEC Filings & Insider Data" />
          <FilingsTab
            filings={filingsData?.filings || []}
            trades={tradesData?.trades || []}
          />
        </>
      )}

      {activeTab === "news" && (
        <NewsTab articles={newsData?.articles} />
      )}

      {activeTab === "patents" && (
        <PatentsTab patents={patentsData?.patents} total={patentsData?.total || 0} />
      )}
    </div>
  );
}

/* ── News Tab ── */
function NewsTab({ articles }: { articles: NewsArticle[] | undefined }) {
  if (articles === undefined) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-5 h-5 animate-spin text-accent" />
      </div>
    );
  }

  if (articles.length === 0) {
    return <EmptyState text="No recent news found for this ticker" />;
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted">{articles.length} articles from the last 7 days</p>
      <div className="space-y-2">
        {articles.map((a) => (
          <a
            key={a.id}
            href={a.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex gap-4 rounded-lg border border-border p-4 hover:border-accent/30 hover:bg-surface-hover transition-all group"
          >
            {a.image && (
              <div className="shrink-0 w-32 h-20 rounded-md overflow-hidden bg-surface-hover hidden sm:block">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={a.image}
                  alt=""
                  className="w-full h-full object-cover"
                  loading="lazy"
                  onError={(e) => {
                    (e.currentTarget.parentElement as HTMLElement).style.display = "none";
                  }}
                />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1.5 text-[11px] text-muted">
                <span className="font-semibold text-accent">{a.source}</span>
                <span>·</span>
                <span>{formatArticleDate(a.datetime)}</span>
                {a.category && (
                  <>
                    <span>·</span>
                    <span className="px-1.5 py-0.5 rounded bg-surface-hover text-[10px] uppercase">{a.category}</span>
                  </>
                )}
              </div>
              <h3 className="text-sm font-semibold leading-snug group-hover:text-accent transition-colors line-clamp-2">
                {a.headline}
              </h3>
              {a.summary && (
                <p className="text-xs text-muted mt-1.5 line-clamp-2 leading-relaxed">{a.summary}</p>
              )}
            </div>
            <ExternalLink className="w-3.5 h-3.5 text-muted shrink-0 mt-1" />
          </a>
        ))}
      </div>
    </div>
  );
}

function formatArticleDate(ts: number): string {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  if (diffHours < 1) return "just now";
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString();
}

/* ── TradingView Chart ── */
function TradingViewChart({ ticker }: { ticker: string }) {
  const containerId = `tv-chart-${ticker}`;
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: false,
      width: "100%",
      height: 580,
      symbol: ticker,
      interval: "D",
      timezone: "America/New_York",
      theme: "dark",
      style: "1",
      locale: "en",
      backgroundColor: "rgba(0, 0, 0, 0)",
      gridColor: "rgba(255, 255, 255, 0.04)",
      hide_top_toolbar: false,
      hide_legend: false,
      allow_symbol_change: false,
      save_image: false,
      calendar: false,
      hide_volume: false,
      enable_publishing: false,
      withdateranges: false,
      isTransparent: true,
    });

    const container = document.getElementById(containerId);
    if (container) {
      container.innerHTML = "";
      const widget = document.createElement("div");
      widget.className = "tradingview-widget-container__widget";
      widget.style.height = "100%";
      widget.style.width = "100%";
      container.appendChild(widget);
      container.appendChild(script);
    }

    return () => {
      const container = document.getElementById(containerId);
      if (container) container.innerHTML = "";
    };
  }, [ticker, containerId, mounted]);

  if (!mounted) {
    return (
      <div className="rounded-lg border border-border bg-surface/50 flex items-center justify-center" style={{ height: "620px" }}>
        <p className="text-sm text-muted">Loading chart...</p>
      </div>
    );
  }

  return (
    <div
      id={containerId}
      className="tradingview-widget-container rounded-lg overflow-hidden border border-border"
      style={{ height: "620px", width: "100%", minWidth: "100%" }}
    />
  );
}

/* ── Overview Tab ── */
function OverviewTab({
  company,
  pipeline,
  insiderSummary,
  trialsTotal,
  filingsCount,
  competitors,
  shortInterest,
  institutional,
  etfs,
}: {
  company: Company;
  pipeline: Drug[];
  insiderSummary: InsiderSummary | undefined;
  trialsTotal: number;
  filingsCount: number;
  competitors: { therapeutic_areas: string[]; competitors: Array<{ ticker: string; name: string; price: number | null; market_cap: number | null; pipeline_size: number }> } | undefined;
  shortInterest: { short_interest: Array<{ date: string; short_interest: number; days_to_cover: number }>; institutional_ownership: Array<{ name: string; shares: number; change: number }>; insider_sentiment: Array<{ month: string; change: number; mspr: number }> } | undefined;
  institutional: { ticker: string; holdings: InstitutionalHoldingRow[]; total: number; total_value: number; total_shares: number } | undefined;
  etfs: { ticker: string; etfs: ETFHoldingRow[]; total: number } | undefined;
}) {
  // Count drugs by phase
  const phaseCount: Record<string, number> = {};
  pipeline.forEach((d) => {
    const p = d.highest_phase || "OTHER";
    phaseCount[p] = (phaseCount[p] || 0) + 1;
  });

  // Count by therapeutic area
  const areaCount: Record<string, number> = {};
  pipeline.forEach((d) => {
    const a = d.therapeutic_area || "Other";
    areaCount[a] = (areaCount[a] || 0) + 1;
  });

  return (
    <div className="space-y-6">
      {/* TradingView Chart */}
      {/* Chart breaks out of container for full width */}
      <div className="-mx-6 lg:-mx-10">
        <TradingViewChart ticker={company.ticker} />
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MiniStat label="Pipeline" value={String(pipeline.length)} sublabel="drug programs" />
        <MiniStat label="Trials" value={String(trialsTotal)} sublabel="clinical trials" />
        <MiniStat label="Filings" value={String(filingsCount)} sublabel="SEC filings" />
        <MiniStat
          label="Insider Signal"
          value={insiderSummary?.signal || "N/A"}
          sublabel="90-day activity"
          color={
            insiderSummary?.signal === "BULLISH"
              ? "text-positive"
              : insiderSummary?.signal === "BEARISH"
                ? "text-negative"
                : undefined
          }
        />
      </div>

      {/* Cash Runway & Dilution Risk */}
      {(company.cash_and_equivalents !== null || company.runway_months !== null) && (
        <div className="rounded-lg border border-border p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">Cash & Runway</h3>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted">Cash</p>
              <p className="text-xl font-bold mt-1">
                {company.cash_and_equivalents ? formatMarketCap(company.cash_and_equivalents) : "—"}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted">Annual Burn</p>
              <p className={cn("text-xl font-bold mt-1", company.annual_burn_rate && company.annual_burn_rate < 0 ? "text-negative" : "text-muted")}>
                {company.annual_burn_rate ? formatMarketCap(Math.abs(company.annual_burn_rate)) : "—"}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted">Runway</p>
              {company.runway_months === null ? (
                <p className="text-xl font-bold mt-1 text-muted">—</p>
              ) : company.runway_months >= 999 ? (
                <p className="text-xl font-bold mt-1 text-positive">∞ Profitable</p>
              ) : (
                <>
                  <p className={cn("text-xl font-bold mt-1",
                    company.runway_months < 6 ? "text-negative" :
                    company.runway_months < 12 ? "text-warning" :
                    company.runway_months < 24 ? "text-accent" : "text-positive"
                  )}>
                    {company.runway_months}mo
                  </p>
                  <p className="text-[10px] text-muted mt-0.5">
                    {company.runway_months < 6 ? "Critical — likely dilution soon" :
                     company.runway_months < 12 ? "Low — watch for financing" :
                     company.runway_months < 24 ? "Moderate" : "Strong"}
                  </p>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Company Info + Financials */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Key Financials */}
        <div className="rounded-lg border border-border p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">Key Data</h3>
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-[13px]">
            <DataRow label="Market Cap" value={formatMarketCap(company.market_cap)} />
            <DataRow label="Revenue" value={company.revenue ? formatMarketCap(company.revenue) : "N/A"} />
            <DataRow label="P/E Ratio" value={company.pe_ratio ? company.pe_ratio.toFixed(1) : "N/A"} />
            <DataRow label="Beta" value={company.beta ? company.beta.toFixed(2) : "N/A"} />
            <DataRow label="Profit Margin" value={company.profit_margin ? `${(company.profit_margin * 100).toFixed(1)}%` : "N/A"} />
            <DataRow label="Dividend Yield" value={company.dividend_yield ? `${(company.dividend_yield * 100).toFixed(2)}%` : "N/A"} />
            <DataRow label="52W High" value={company.fifty_two_week_high ? `$${company.fifty_two_week_high.toFixed(2)}` : "N/A"} />
            <DataRow label="52W Low" value={company.fifty_two_week_low ? `$${company.fifty_two_week_low.toFixed(2)}` : "N/A"} />
            <DataRow label="Avg Volume" value={company.avg_volume ? formatNumber(company.avg_volume) : "N/A"} />
            <DataRow label="Shares Out" value={company.shares_outstanding ? formatMarketCap(company.shares_outstanding) : "N/A"} />
            <DataRow label="Employees" value={company.employees ? formatNumber(company.employees) : "N/A"} />
            <DataRow label="Founded" value={company.founded_year || "N/A"} />
          </div>
        </div>

        {/* Location + Map */}
        <div className="rounded-lg border border-border p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">Headquarters</h3>
          {company.city || company.state || company.country ? (
            <div className="space-y-3">
              <div className="text-sm">
                {company.address && <p>{company.address}</p>}
                <p>
                  {[company.city, company.state, company.zip_code].filter(Boolean).join(", ")}
                </p>
                {company.country && <p className="text-muted">{company.country}</p>}
                {company.phone && <p className="text-muted mt-1">{company.phone}</p>}
              </div>
              {/* Google Maps embed */}
              <div className="rounded-lg overflow-hidden border border-border h-[180px]">
                <iframe
                  src={`https://www.google.com/maps/embed/v1/place?key=AIzaSyBFw0Qbyq9zTFTd-tUY6dZWTgaQzuU17R8&q=${encodeURIComponent(
                    [company.address, company.city, company.state, company.country].filter(Boolean).join(", ")
                  )}&zoom=12`}
                  width="100%"
                  height="100%"
                  style={{ border: 0, filter: "invert(90%) hue-rotate(180deg)" }}
                  allowFullScreen
                  loading="lazy"
                  referrerPolicy="no-referrer-when-downgrade"
                />
              </div>
            </div>
          ) : (
            <div className="text-sm text-muted">
              <p>Location data not available yet.</p>
              <p className="text-[11px] mt-1">Run market data sync to populate.</p>
            </div>
          )}
        </div>
      </div>

      {/* About */}
      {company.description && (
        <div className="rounded-lg border border-border p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-2">About</h3>
          <p className="text-sm text-muted leading-relaxed">{company.description}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pipeline by Phase */}
        {pipeline.length > 0 && (
          <div className="rounded-lg border border-border p-5">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">Pipeline by Phase</h3>
            <div className="space-y-2">
              {["PHASE3", "PHASE2", "PHASE1", "PHASE4"].map((phase) => {
                const count = phaseCount[phase] || 0;
                if (count === 0) return null;
                const total = pipeline.length;
                const pct = Math.round((count / total) * 100);
                return (
                  <div key={phase} className="flex items-center gap-3">
                    <span className={cn("text-[11px] font-medium w-16", PHASE_COLORS[phase] ? "text-foreground" : "text-muted")}>
                      {PHASE_LABELS[phase] || phase}
                    </span>
                    <div className="flex-1 h-2 rounded-full bg-surface-hover overflow-hidden">
                      <div
                        className={cn("h-full rounded-full", phase === "PHASE3" ? "bg-orange-500" : phase === "PHASE2" ? "bg-yellow-500" : phase === "PHASE1" ? "bg-blue-500" : "bg-green-500")}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-[11px] font-mono text-muted w-8 text-right">{count}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Pipeline by Therapeutic Area */}
        {Object.keys(areaCount).length > 0 && (
          <div className="rounded-lg border border-border p-5">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">By Therapeutic Area</h3>
            <div className="flex flex-wrap gap-2">
              {Object.entries(areaCount)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 8)
                .map(([area, count]) => (
                  <span
                    key={area}
                    className={cn("px-2.5 py-1 rounded-md text-[11px] font-medium", THERAPEUTIC_AREA_COLORS[area] || THERAPEUTIC_AREA_COLORS.Other)}
                  >
                    {area} ({count})
                  </span>
                ))}
            </div>
          </div>
        )}
      </div>

      {/* Top pipeline drugs preview */}
      {pipeline.length > 0 && (
        <div className="rounded-lg border border-border p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">Lead Programs</h3>
          <div className="space-y-2">
            {pipeline.slice(0, 5).map((drug) => (
              <Link
                key={drug.drug_id}
                href={`/drugs/${drug.drug_id}`}
                className="flex items-center justify-between py-2 px-3 rounded-md hover:bg-surface-hover transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <FlaskConical className="w-4 h-4 text-accent" />
                  <div>
                    <p className="text-[13px] font-medium group-hover:text-accent transition-colors">{drug.drug_name}</p>
                    <p className="text-[11px] text-muted">{drug.indication || drug.therapeutic_area || "N/A"}</p>
                  </div>
                </div>
                {drug.highest_phase && (
                  <span className={cn("px-2 py-0.5 rounded text-[10px] font-medium border", PHASE_COLORS[drug.highest_phase] || PHASE_COLORS.PRECLINICAL)}>
                    {PHASE_LABELS[drug.highest_phase]}
                  </span>
                )}
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Competitors */}
      {competitors && competitors.competitors.length > 0 && (
        <div className="rounded-lg border border-border p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-1">Competitors</h3>
          <p className="text-[11px] text-muted mb-3">Companies with overlapping drug pipelines in {competitors.therapeutic_areas.join(", ")}</p>
          <div className="rounded-lg border border-border overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="bg-surface/50 border-b border-border">
                  <th className="text-left px-4 py-2 text-[10px] font-semibold uppercase text-muted">Company</th>
                  <th className="text-right px-4 py-2 text-[10px] font-semibold uppercase text-muted">Price</th>
                  <th className="text-right px-4 py-2 text-[10px] font-semibold uppercase text-muted">Market Cap</th>
                  <th className="text-right px-4 py-2 text-[10px] font-semibold uppercase text-muted">Overlap</th>
                </tr>
              </thead>
              <tbody>
                {competitors.competitors.slice(0, 8).map((c) => (
                  <tr key={c.ticker} className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors">
                    <td className="px-4 py-2.5">
                      <Link href={`/companies/${c.ticker}`} className="group flex items-center gap-2">
                        <div className="w-6 h-6 rounded bg-surface-hover flex items-center justify-center text-[9px] font-bold text-accent">{c.ticker.slice(0, 2)}</div>
                        <div>
                          <p className="font-medium text-[12px] group-hover:text-accent transition-colors">{c.ticker}</p>
                          <p className="text-[10px] text-muted truncate max-w-[140px]">{c.name}</p>
                        </div>
                      </Link>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono">{c.price ? `$${c.price.toFixed(2)}` : "N/A"}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-muted">{c.market_cap ? formatMarketCap(c.market_cap) : "N/A"}</td>
                    <td className="px-4 py-2.5 text-right">
                      <span className="text-[11px] font-medium text-accent">{c.pipeline_size} drugs</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Smart Money Holders (13F) */}
      <SmartMoneySection institutional={institutional} />

      {/* ETF Membership */}
      <ETFMembershipSection etfs={etfs} />

      {/* Institutional Ownership */}
      {shortInterest && shortInterest.institutional_ownership.length > 0 && (
        <div className="rounded-lg border border-border p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">Top Institutional Holders</h3>
          <div className="space-y-2">
            {shortInterest.institutional_ownership.slice(0, 6).map((h, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-b-0 text-[13px]">
                <span className="truncate max-w-[250px]">{h.name}</span>
                <div className="flex items-center gap-4">
                  <span className="font-mono text-muted">{h.shares ? formatNumber(h.shares) : "N/A"} shares</span>
                  {h.change !== 0 && (
                    <span className={cn("text-[11px] font-medium", h.change > 0 ? "text-positive" : "text-negative")}>
                      {h.change > 0 ? "+" : ""}{formatNumber(h.change)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Short Interest */}
      {shortInterest && shortInterest.short_interest.length > 0 && (
        <div className="rounded-lg border border-border p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">Short Interest History</h3>
          <div className="grid grid-cols-3 gap-3 mb-3">
            {shortInterest.short_interest.slice(-1).map((s, i) => (
              <div key={i}>
                <p className="text-[10px] text-muted uppercase">Latest Short Interest</p>
                <p className="text-lg font-bold font-mono">{s.short_interest ? formatNumber(s.short_interest) : "N/A"}</p>
                <p className="text-[11px] text-muted">{s.days_to_cover?.toFixed(1)} days to cover</p>
              </div>
            ))}
          </div>
          <div className="rounded-lg border border-border overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="bg-surface/50 border-b border-border">
                  <th className="text-left px-3 py-2 text-[10px] font-semibold text-muted">Date</th>
                  <th className="text-right px-3 py-2 text-[10px] font-semibold text-muted">Short Interest</th>
                  <th className="text-right px-3 py-2 text-[10px] font-semibold text-muted">Days to Cover</th>
                </tr>
              </thead>
              <tbody>
                {shortInterest.short_interest.map((s, i) => (
                  <tr key={i} className="border-b border-border last:border-b-0">
                    <td className="px-3 py-1.5 font-mono text-muted">{s.date}</td>
                    <td className="px-3 py-1.5 text-right font-mono">{s.short_interest ? formatNumber(s.short_interest) : "N/A"}</td>
                    <td className="px-3 py-1.5 text-right font-mono">{s.days_to_cover?.toFixed(1) || "N/A"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-1 border-b border-border/50 last:border-b-0">
      <span className="text-muted">{label}</span>
      <span className="font-medium font-mono">{value}</span>
    </div>
  );
}

function MiniStat({ label, value, sublabel, color }: { label: string; value: string; sublabel: string; color?: string }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-[10px] text-muted uppercase font-semibold">{label}</p>
      <p className={cn("text-xl font-bold mt-1", color)}>{value}</p>
      <p className="text-[11px] text-muted">{sublabel}</p>
    </div>
  );
}

/* ── Pipeline Tab ── */
function PipelineTab({ pipeline }: { pipeline: Drug[] }) {
  if (pipeline.length === 0) {
    return <EmptyState text="No pipeline data yet" />;
  }

  return (
    <div className="rounded-lg border border-border overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-surface/50 border-b border-border">
            <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Drug</th>
            <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Phase</th>
            <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Area</th>
            <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Indication</th>
          </tr>
        </thead>
        <tbody>
          {pipeline.map((drug) => (
            <tr key={drug.drug_id} className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors">
              <td className="px-4 py-3">
                <Link href={`/drugs/${drug.drug_id}`} className="font-medium text-[13px] text-accent hover:underline">
                  {drug.drug_name}
                </Link>
              </td>
              <td className="px-4 py-3">
                {drug.highest_phase && (
                  <span className={cn("px-2 py-0.5 rounded text-[11px] font-medium border", PHASE_COLORS[drug.highest_phase] || PHASE_COLORS.PRECLINICAL)}>
                    {PHASE_LABELS[drug.highest_phase] || drug.highest_phase}
                  </span>
                )}
              </td>
              <td className="px-4 py-3">
                {drug.therapeutic_area && (
                  <span className={cn("px-2 py-0.5 rounded text-[11px]", THERAPEUTIC_AREA_COLORS[drug.therapeutic_area] || THERAPEUTIC_AREA_COLORS.Other)}>
                    {drug.therapeutic_area}
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-[13px] text-muted max-w-[250px] truncate">{drug.indication || "N/A"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Trials Tab ── */
function TrialsTab({ trials, total }: { trials: Trial[]; total: number }) {
  const { data: factorCounts } = useBatchFactors(trials.map((t) => t.nct_id));

  if (trials.length === 0) {
    return <EmptyState text="No clinical trials found" />;
  }

  return (
    <div>
      <p className="text-xs text-muted mb-3">{total} trials found</p>
      <div className="rounded-lg border border-border overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface/50 border-b border-border">
              <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Score</th>
              <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">NCT ID</th>
              <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Title</th>
              <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Phase</th>
              <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Status</th>
              <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Dates</th>
              <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Results</th>
            </tr>
          </thead>
          <tbody>
            {trials.map((t) => {
              const isCompleted = t.overall_status === "COMPLETED" || t.overall_status === "TERMINATED";
              const isTerminated = t.overall_status === "TERMINATED" || t.overall_status === "WITHDRAWN" || t.overall_status === "SUSPENDED";
              const hasResults = !!t.results_first_posted || !!t.has_results;

              return (
                <>
                  <tr key={t.nct_id} className={cn("border-b border-border hover:bg-surface/80 transition-colors", t.why_stopped && "border-b-0")}>
                    <td className="px-4 py-3">
                      {factorCounts?.[t.nct_id] ? (
                        <FactorSummaryBadge
                          positive={factorCounts[t.nct_id].positive}
                          negative={factorCounts[t.nct_id].negative}
                        />
                      ) : (
                        <span className="text-muted/30 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Link href={`/trials/${t.nct_id}`}
                        className="text-accent hover:underline text-[12px] font-mono">
                        {t.nct_id}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <Link href={`/trials/${t.nct_id}`} className="text-[12px] hover:text-accent transition-colors max-w-[280px] truncate block">
                        {t.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      {t.phase && (
                        <span className={cn("px-2 py-0.5 rounded text-[10px] font-medium border", PHASE_COLORS[t.phase] || PHASE_COLORS.PRECLINICAL)}>
                          {PHASE_LABELS[t.phase] || t.phase}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("text-[11px] font-medium", STATUS_COLORS[t.overall_status || ""] || "text-muted")}>
                        {STATUS_LABELS[t.overall_status || ""] || t.overall_status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-[11px] font-mono text-muted">
                        {t.start_date && <span>{t.start_date}</span>}
                        {t.primary_completion_date && <span className="text-foreground"> → {t.primary_completion_date}</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {hasResults ? (
                        <a
                          href={`https://clinicaltrials.gov/study/${t.nct_id}?tab=results`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-positive/10 text-positive hover:bg-positive/20 transition-colors"
                        >
                          View Results
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      ) : isCompleted ? (
                        <span className="text-[11px] px-2 py-0.5 rounded bg-warning/10 text-warning">
                          Pending
                        </span>
                      ) : (
                        <span className="text-[11px] text-muted">—</span>
                      )}
                    </td>
                  </tr>
                  {t.why_stopped && (
                    <tr key={`${t.nct_id}-reason`} className="border-b border-border bg-negative/[0.03]">
                      <td colSpan={7} className="px-4 pb-3 pt-0">
                        <div className="flex items-start gap-2 text-[11px]">
                          <span className={cn("font-semibold uppercase tracking-wider shrink-0", isTerminated ? "text-negative" : "text-muted")}>
                            {isTerminated ? "Stopped:" : "Note:"}
                          </span>
                          <span className="text-muted italic">{t.why_stopped}</span>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Options Flow Tab ── */
function OptionsFlowTab({ data }: {
  data: {
    data: Array<{ expiration: string; call_volume: number; put_volume: number; call_iv: number; put_iv: number; avg_iv: number }>;
    total_call_volume: number;
    total_put_volume: number;
    avg_iv?: number;
    put_call_ratio: number;
  } | undefined;
}) {
  if (!data || data.data.length === 0) {
    return <EmptyState text="No options data available for this ticker" />;
  }

  const { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } = require("recharts");

  const chartData = data.data.map((d) => ({
    date: d.expiration.slice(5), // MM-DD
    Calls: d.call_volume,
    Puts: d.put_volume,
  }));

  const ivChartData = data.data.map((d) => ({
    date: d.expiration.slice(5),
    "Call IV": d.call_iv || null,
    "Put IV": d.put_iv || null,
  }));

  const totalVol = data.total_call_volume + data.total_put_volume;

  return (
    <div className="space-y-6">
      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4">
        <div className="rounded-lg border border-border p-4">
          <p className="text-[10px] uppercase tracking-widest text-muted mb-1">Call Volume</p>
          <p className="text-xl font-bold text-positive">{data.total_call_volume.toLocaleString()}</p>
        </div>
        <div className="rounded-lg border border-border p-4">
          <p className="text-[10px] uppercase tracking-widest text-muted mb-1">Put Volume</p>
          <p className="text-xl font-bold text-negative">{data.total_put_volume.toLocaleString()}</p>
        </div>
        <div className="rounded-lg border border-border p-4">
          <p className="text-[10px] uppercase tracking-widest text-muted mb-1">Put/Call Ratio</p>
          <p className={cn("text-xl font-bold", data.put_call_ratio > 1 ? "text-negative" : "text-positive")}>
            {data.put_call_ratio}
          </p>
          <p className="text-[10px] text-muted mt-0.5">
            {data.put_call_ratio > 1.2 ? "Bearish" : data.put_call_ratio < 0.8 ? "Bullish" : "Neutral"}
          </p>
        </div>
        <div className="rounded-lg border border-border p-4">
          <p className="text-[10px] uppercase tracking-widest text-muted mb-1">Avg IV</p>
          <p className={cn("text-xl font-bold", (data.avg_iv || 0) > 80 ? "text-warning" : (data.avg_iv || 0) > 40 ? "text-accent" : "text-muted")}>
            {data.avg_iv ? `${data.avg_iv}%` : "--"}
          </p>
          <p className="text-[10px] text-muted mt-0.5">
            {(data.avg_iv || 0) > 80 ? "Very volatile" : (data.avg_iv || 0) > 40 ? "Elevated" : "Normal"}
          </p>
        </div>
      </div>

      {/* Chart */}
      <div className="rounded-lg border border-border p-4">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-4">
          Volume by Expiration
        </h3>
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: "var(--color-muted)" }}
              axisLine={{ stroke: "var(--color-border)" }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--color-muted)" }}
              axisLine={{ stroke: "var(--color-border)" }}
              tickFormatter={(v: number) => v >= 1000 ? `${(v/1000).toFixed(0)}k` : String(v)}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: "8px",
                fontSize: 12,
              }}
              formatter={(value: number, name: string) => [value.toLocaleString(), name]}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line
              type="monotone"
              dataKey="Calls"
              stroke="#22c55e"
              strokeWidth={2}
              dot={{ r: 3, fill: "#22c55e" }}
              activeDot={{ r: 5 }}
            />
            <Line
              type="monotone"
              dataKey="Puts"
              stroke="#ef4444"
              strokeWidth={2}
              dot={{ r: 3, fill: "#ef4444" }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Implied Volatility Chart */}
      <div className="rounded-lg border border-border p-4">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-1">
          Implied Volatility Term Structure
        </h3>
        <p className="text-[11px] text-muted mb-4">
          Higher IV at near expirations suggests imminent catalyst expectations
        </p>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={ivChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: "var(--color-muted)" }}
              axisLine={{ stroke: "var(--color-border)" }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--color-muted)" }}
              axisLine={{ stroke: "var(--color-border)" }}
              tickFormatter={(v: number) => `${v}%`}
              domain={[0, 'auto']}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: "8px",
                fontSize: 12,
              }}
              formatter={(value: number) => [`${value}%`, "IV"]}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line
              type="monotone"
              dataKey="Call IV"
              stroke="#22c55e"
              strokeWidth={2}
              dot={{ r: 3, fill: "#22c55e" }}
              activeDot={{ r: 5 }}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="Put IV"
              stroke="#ef4444"
              strokeWidth={2}
              dot={{ r: 3, fill: "#ef4444" }}
              activeDot={{ r: 5 }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Sentiment bar */}
      <div className="rounded-lg border border-border p-4">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">
          Call / Put Split
        </h3>
        <div className="flex h-3 rounded-full overflow-hidden">
          <div
            className="bg-positive transition-all"
            style={{ width: `${totalVol > 0 ? (data.total_call_volume / totalVol) * 100 : 50}%` }}
          />
          <div
            className="bg-negative transition-all"
            style={{ width: `${totalVol > 0 ? (data.total_put_volume / totalVol) * 100 : 50}%` }}
          />
        </div>
        <div className="flex justify-between mt-2 text-[11px]">
          <span className="text-positive font-medium">
            Calls {totalVol > 0 ? Math.round((data.total_call_volume / totalVol) * 100) : 50}%
          </span>
          <span className="text-negative font-medium">
            Puts {totalVol > 0 ? Math.round((data.total_put_volume / totalVol) * 100) : 50}%
          </span>
        </div>
      </div>
    </div>
  );
}

/* ── Filings Tab ── */
function FilingsTab({ filings, trades }: { filings: Filing[]; trades: InsiderTrade[] }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* SEC Filings */}
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">SEC Filings</h3>
        {filings.length > 0 ? (
          <div className="rounded-lg border border-border overflow-x-auto">
            {filings.map((f, i) => (
              <a
                key={f.id}
                href={f.edgar_url || "#"}
                target="_blank"
                rel="noopener noreferrer"
                className={cn("flex items-center justify-between px-4 py-2.5 hover:bg-surface-hover transition-colors",
                  i < filings.length - 1 && "border-b border-border")}
              >
                <div className="flex items-center gap-3">
                  <span className="text-[10px] font-bold bg-surface-hover px-2 py-0.5 rounded min-w-[40px] text-center font-mono">{f.filing_type}</span>
                  <div>
                    <p className="text-[12px]">{f.description || f.filing_type}</p>
                    <p className="text-[11px] text-muted">{f.filed_date}</p>
                  </div>
                </div>
                <ExternalLink className="w-3 h-3 text-muted" />
              </a>
            ))}
          </div>
        ) : (
          <EmptyState text="No filings yet" />
        )}
      </div>

      {/* Insider Trades */}
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">Insider Trades</h3>
        {trades.length > 0 ? (
          <div className="rounded-lg border border-border overflow-x-auto">
            {trades.map((t, i) => (
              <div key={t.id} className={cn("flex items-center justify-between px-4 py-2.5 hover:bg-surface-hover transition-colors",
                i < trades.length - 1 && "border-b border-border")}>
                <div className="flex items-center gap-3">
                  <div className={cn("w-6 h-6 rounded-full flex items-center justify-center",
                    t.trade_type === "PURCHASE" ? "bg-positive/10 text-positive" : "bg-negative/10 text-negative")}>
                    {t.trade_type === "PURCHASE" ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                  </div>
                  <div>
                    <p className="text-[12px] font-medium">{t.insider_name}</p>
                    <p className="text-[11px] text-muted">{t.insider_title} · {t.transaction_date}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={cn("text-[12px] font-mono font-medium",
                    t.trade_type === "PURCHASE" ? "text-positive" : "text-negative")}>
                    {t.trade_type === "PURCHASE" ? "+" : "-"}{formatNumber(Math.round(t.shares))}
                  </p>
                  {t.total_value && <p className="text-[11px] text-muted font-mono">${t.total_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState text="No insider trades found" />
        )}
      </div>
    </div>
  );
}

/* ── Helpers ── */
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] text-muted uppercase font-semibold">{label}</p>
      <p className="font-semibold mt-0.5">{value}</p>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-border border-dashed p-12 text-center">
      <p className="text-sm text-muted">{text}</p>
    </div>
  );
}

/* ── Smart Money Holders (13F) ── */
function SmartMoneySection({
  institutional,
}: {
  institutional: { ticker: string; holdings: InstitutionalHoldingRow[]; total: number; total_value: number; total_shares: number } | undefined;
}) {
  if (!institutional || institutional.holdings.length === 0) {
    return null;
  }

  return (
    <div className="rounded-lg border border-border p-5">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-1">Smart Money Holders</h3>
      <p className="text-[11px] text-muted mb-3">
        Specialist biotech funds reporting this position in their latest 13F filing
        {" · "}
        <span className="font-mono">{formatMarketCap(institutional.total_value)}</span> total
      </p>
      <div className="rounded-lg border border-border overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="bg-surface/50 border-b border-border">
              <th className="text-left px-4 py-2 text-[10px] font-semibold uppercase text-muted">Fund</th>
              <th className="text-right px-4 py-2 text-[10px] font-semibold uppercase text-muted">Position</th>
              <th className="text-right px-4 py-2 text-[10px] font-semibold uppercase text-muted">Shares</th>
              <th className="text-right px-4 py-2 text-[10px] font-semibold uppercase text-muted">Quarter</th>
            </tr>
          </thead>
          <tbody>
            {institutional.holdings.map((h) => (
              <tr key={h.id} className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors">
                <td className="px-4 py-2.5">
                  <a
                    href={h.edgar_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 font-medium text-[12px] text-accent hover:underline"
                  >
                    {h.fund_name}
                    <ExternalLink className="w-3 h-3" />
                  </a>
                  <p className="text-[10px] text-muted font-mono">CIK {h.fund_cik}</p>
                </td>
                <td className="px-4 py-2.5 text-right font-mono">{h.value ? formatMarketCap(h.value) : "N/A"}</td>
                <td className="px-4 py-2.5 text-right font-mono text-muted">{h.shares ? formatNumber(Math.round(h.shares)) : "N/A"}</td>
                <td className="px-4 py-2.5 text-right font-mono text-muted text-[12px]">{h.quarter_end || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── ETF Membership ── */
const ETF_COLORS: Record<string, string> = {
  XBI: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  IBB: "bg-purple-500/10 text-purple-400 border-purple-500/30",
  LABU: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  SBIO: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
};

const ETF_NAMES: Record<string, string> = {
  XBI: "SPDR S&P Biotech",
  IBB: "iShares Biotechnology",
  LABU: "Direxion Daily S&P Biotech Bull 3X",
  SBIO: "ALPS Medical Breakthroughs",
};

function ETFMembershipSection({
  etfs,
}: {
  etfs: { ticker: string; etfs: ETFHoldingRow[]; total: number } | undefined;
}) {
  if (!etfs || etfs.etfs.length === 0) {
    return null;
  }

  return (
    <div className="rounded-lg border border-border p-5">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-1">ETF Membership</h3>
      <p className="text-[11px] text-muted mb-3">Biotech ETFs holding this stock with their weight</p>
      <div className="flex flex-wrap gap-2">
        {etfs.etfs.map((e) => {
          const colorClass = ETF_COLORS[e.etf_ticker] || "bg-surface-hover text-foreground border-border";
          return (
            <div
              key={e.id}
              className={cn("inline-flex items-center gap-2 rounded-md border px-3 py-1.5", colorClass)}
            >
              <span className="font-mono font-bold text-[12px]">{e.etf_ticker}</span>
              <span className="text-[10px] opacity-70">{ETF_NAMES[e.etf_ticker] || ""}</span>
              <span className="font-mono font-semibold text-[12px] ml-1">
                {e.weight !== null ? `${e.weight.toFixed(2)}%` : "—"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Patents Tab ── */
function PatentsTab({ patents, total }: { patents: PatentRow[] | undefined; total: number }) {
  if (patents === undefined) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-5 h-5 animate-spin text-accent" />
      </div>
    );
  }

  if (patents.length === 0) {
    return <EmptyState text="No patent data available yet." />;
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted">{total} patents found</p>
      <div className="rounded-lg border border-border overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface/50 border-b border-border">
              <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Title</th>
              <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Patent #</th>
              <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Granted</th>
              <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Expires</th>
            </tr>
          </thead>
          <tbody>
            {patents.map((p) => (
              <tr key={p.id} className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors">
                <td className="px-4 py-3 max-w-[440px]">
                  <p className="text-[12px] font-medium line-clamp-2">{p.title || "—"}</p>
                  {p.assignee_name && (
                    <p className="text-[10px] text-muted mt-0.5 truncate">{p.assignee_name}</p>
                  )}
                </td>
                <td className="px-4 py-3">
                  {p.uspto_url ? (
                    <a
                      href={p.uspto_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 font-mono text-[12px] text-accent hover:underline"
                    >
                      US{p.patent_number}
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  ) : (
                    <span className="font-mono text-[12px] text-muted">{p.patent_number}</span>
                  )}
                </td>
                <td className="px-4 py-3 font-mono text-[12px] text-muted">{p.grant_date || "—"}</td>
                <td className="px-4 py-3 font-mono text-[12px] text-muted">{p.expiration_date || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
