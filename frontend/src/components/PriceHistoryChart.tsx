"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Loader2 } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatPrice } from "@/lib/utils";

interface Candle {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

interface PriceResponse {
  ticker: string;
  range: string;
  candles: Candle[];
}

const RANGES: { id: string; label: string }[] = [
  { id: "1m", label: "1M" },
  { id: "3m", label: "3M" },
  { id: "6m", label: "6M" },
  { id: "1y", label: "1Y" },
  { id: "2y", label: "2Y" },
  { id: "5y", label: "5Y" },
];

const SHORT_MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function formatXAxis(dateStr: string, range: string): string {
  const d = new Date(dateStr + "T12:00:00");
  if (range === "5y" || range === "2y") return `${SHORT_MONTHS[d.getMonth()]} ${d.getFullYear() % 100}`;
  if (range === "1y" || range === "6m") return `${SHORT_MONTHS[d.getMonth()]} ${d.getDate()}`;
  return `${SHORT_MONTHS[d.getMonth()]} ${d.getDate()}`;
}

export function PriceHistoryChart({ ticker }: { ticker: string }) {
  const [range, setRange] = useState<string>("1y");

  const { data, isLoading } = useQuery<PriceResponse>({
    queryKey: ["price-history", ticker, range],
    queryFn: () => fetchAPI(`/historical/prices/${ticker}?range=${range}`),
    staleTime: 5 * 60 * 1000,
  });

  const candles = data?.candles ?? [];
  const first = candles[0]?.close;
  const last = candles[candles.length - 1]?.close;
  const pct =
    first && last ? ((last - first) / first) * 100 : null;
  const isUp = pct != null && pct >= 0;

  return (
    <div className="rounded-lg border border-border p-5">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted">
            Price History
          </h3>
          {pct != null && (
            <p className="text-sm mt-1">
              <span
                className={cn(
                  "font-mono font-semibold",
                  isUp ? "text-positive" : "text-negative"
                )}
              >
                {isUp ? "+" : ""}
                {pct.toFixed(2)}%
              </span>
              <span className="text-muted ml-2">over {range.toUpperCase()}</span>
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {RANGES.map((r) => (
            <button
              key={r.id}
              onClick={() => setRange(r.id)}
              className={cn(
                "px-2.5 py-1 rounded text-[11px] font-medium transition-colors",
                range === r.id
                  ? "bg-accent/15 text-accent"
                  : "text-muted hover:text-foreground hover:bg-surface-hover"
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-[300px]">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : candles.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-[300px] text-center px-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/10 text-accent text-[10px] font-semibold uppercase tracking-widest mb-3">
            Coming soon
          </div>
          <p className="text-sm text-foreground">Historical price charts on the way</p>
          <p className="text-xs text-muted mt-1 max-w-sm">
            Yahoo and Stooq rate-limit our backend&apos;s datacenter IP range.
            We&apos;re wiring up a paid EOD feed (Polygon) — check back shortly.
          </p>
        </div>
      ) : (
        <div className="w-full h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={candles}
              margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
            >
              <defs>
                <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="0%"
                    stopColor={isUp ? "#10b981" : "#ef4444"}
                    stopOpacity={0.35}
                  />
                  <stop
                    offset="100%"
                    stopColor={isUp ? "#10b981" : "#ef4444"}
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="var(--color-border)"
                opacity={0.4}
              />
              <XAxis
                dataKey="date"
                tickFormatter={(d) => formatXAxis(d, range)}
                tick={{ fontSize: 11, fill: "var(--color-muted)" }}
                axisLine={false}
                tickLine={false}
                minTickGap={30}
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fontSize: 11, fill: "var(--color-muted)" }}
                axisLine={false}
                tickLine={false}
                width={50}
                tickFormatter={(v) => formatPrice(v)}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--color-surface)",
                  border: "1px solid var(--color-border)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelFormatter={(d) => {
                  const date = new Date(d + "T12:00:00");
                  return `${SHORT_MONTHS[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
                }}
                formatter={(value, name) => {
                  if (typeof value !== "number") return [String(value ?? ""), String(name ?? "")];
                  if (name === "close") return [formatPrice(value), "Close"];
                  return [value, String(name ?? "")];
                }}
              />
              <Area
                type="monotone"
                dataKey="close"
                stroke={isUp ? "#10b981" : "#ef4444"}
                strokeWidth={2}
                fill="url(#priceGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
