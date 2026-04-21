"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { TrendingUp, Loader2 } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";

interface FlowPoint {
  date: string;
  shares_outstanding: number | null;
  aum: number | null;
  nav: number | null;
  delta_shares: number | null;
  delta_aum: number | null;
}

interface FlowResponse {
  etf_ticker: string;
  days: number;
  series: FlowPoint[];
}

interface ListItem {
  etf_ticker: string;
  latest_date: string;
  shares_outstanding: number | null;
  aum: number | null;
  net_share_change: number;
  net_aum_change: number;
}

interface ListResponse {
  days: number;
  etfs: ListItem[];
}

const ETFS = ["XBI", "IBB", "LABU", "SBIO"];

function formatBig(v: number | null | undefined): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function formatShares(v: number | null | undefined): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "+";
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(0)}K`;
  return `${sign}${abs.toFixed(0)}`;
}

export default function ETFFlowsPage() {
  const [selected, setSelected] = useState<string>("XBI");
  const [days, setDays] = useState(30);

  const { data: summary } = useQuery<ListResponse>({
    queryKey: ["etf-flows-summary", days],
    queryFn: () => fetchAPI(`/etf-flows?days=${days}`),
    staleTime: 5 * 60 * 1000,
  });

  const { data: detail, isLoading } = useQuery<FlowResponse>({
    queryKey: ["etf-flows-detail", selected, days],
    queryFn: () => fetchAPI(`/etf-flows/${selected}?days=${days}`),
    staleTime: 5 * 60 * 1000,
  });

  const chartData = (detail?.series ?? [])
    .filter((p) => p.delta_shares != null)
    .map((p) => ({
      date: p.date.slice(5),
      delta_shares: p.delta_shares ?? 0,
      delta_aum: p.delta_aum ?? 0,
    }));

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <TrendingUp className="w-4 h-4" />
          Edge
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">ETF Flows</h1>
        <p className="text-sm text-muted mt-1">
          Daily creations / redemptions across the major biotech ETFs. Positive
          bars = new money in (shares created), negative = redemptions.
        </p>
      </div>

      {/* Summary grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {ETFS.map((etf) => {
          const item = summary?.etfs.find((e) => e.etf_ticker === etf);
          const isSelected = selected === etf;
          return (
            <button
              key={etf}
              onClick={() => setSelected(etf)}
              className={cn(
                "rounded-lg border p-4 text-left transition-colors",
                isSelected
                  ? "border-accent bg-accent/5"
                  : "border-border hover:border-accent/30"
              )}
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm">{etf}</span>
                {item && (
                  <span
                    className={cn(
                      "text-[11px] font-mono font-semibold",
                      item.net_share_change > 0
                        ? "text-positive"
                        : item.net_share_change < 0
                          ? "text-negative"
                          : "text-muted"
                    )}
                  >
                    {formatShares(item.net_share_change)} sh
                  </span>
                )}
              </div>
              {item ? (
                <>
                  <p className="text-xs text-muted mt-2">AUM</p>
                  <p className="text-sm font-mono">{formatBig(item.aum)}</p>
                  <p
                    className={cn(
                      "text-[11px] font-mono mt-1",
                      item.net_aum_change > 0
                        ? "text-positive"
                        : item.net_aum_change < 0
                          ? "text-negative"
                          : "text-muted"
                    )}
                  >
                    {item.net_aum_change > 0 ? "+" : ""}
                    {formatBig(item.net_aum_change)} over {days}d
                  </p>
                </>
              ) : (
                <p className="text-xs text-muted mt-2">No data yet</p>
              )}
            </button>
          );
        })}
      </div>

      {/* Window chips */}
      <div className="flex items-center gap-2">
        {[14, 30, 90].map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={cn(
              "px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors",
              days === d
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-hover"
            )}
          >
            {d}d
          </button>
        ))}
        <span className="text-xs text-muted ml-auto">
          Showing daily share changes for {selected}
        </span>
      </div>

      {/* Chart */}
      <div className="rounded-lg border border-border p-5">
        {isLoading ? (
          <div className="flex items-center justify-center h-[320px]">
            <Loader2 className="w-5 h-5 animate-spin text-accent" />
          </div>
        ) : chartData.length === 0 ? (
          <div className="flex items-center justify-center h-[320px] text-sm text-muted text-center px-6">
            No ETF flow data yet. The daily snapshot runs post-close;
            deltas appear after the second consecutive day of data.
          </div>
        ) : (
          <div className="h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--color-border)"
                  opacity={0.4}
                />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: "var(--color-muted)" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "var(--color-muted)" }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => {
                    const n = typeof v === "number" ? v : Number(v);
                    return formatShares(n).replace(/^\+/, "");
                  }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--color-surface)",
                    border: "1px solid var(--color-border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(v, name) => {
                    const n = typeof v === "number" ? v : Number(v ?? 0);
                    if (name === "delta_shares") return [formatShares(n), "Δ Shares"];
                    return [n, String(name ?? "")];
                  }}
                />
                <Bar dataKey="delta_shares">
                  {chartData.map((row, i) => (
                    <Cell
                      key={i}
                      fill={row.delta_shares >= 0 ? "#10b981" : "#ef4444"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}
