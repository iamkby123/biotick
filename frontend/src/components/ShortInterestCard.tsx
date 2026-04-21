"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { TrendingDown } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ShortInterestPoint {
  date: string;
  short_volume: number;
  total_volume: number;
  short_pct: number | null;
}

interface ShortInterestResponse {
  ticker: string;
  days: number;
  items: ShortInterestPoint[];
  summary: {
    latest_date: string;
    latest_short_pct: number | null;
    avg_5d_short_pct: number;
    avg_20d_short_pct: number;
  } | null;
}

/** Compact card showing short-volume % with a sparkline.
 *  Rendered on the company Overview tab. */
export function ShortInterestCard({ ticker }: { ticker: string }) {
  const { data, isLoading } = useQuery<ShortInterestResponse>({
    queryKey: ["short-interest", ticker],
    queryFn: () => fetchAPI(`/short-interest/${ticker}?days=30`),
    staleTime: 10 * 60 * 1000,
  });

  if (isLoading || !data || !data.summary || data.items.length === 0) {
    return null;
  }

  const pct = data.summary.latest_short_pct ?? 0;
  const pctDisplay = (pct * 100).toFixed(1);
  const avg20 = (data.summary.avg_20d_short_pct * 100).toFixed(1);

  // Sparkline expects an array of { date, pct } — reuse items directly.
  const sparkData = data.items.map((p) => ({
    date: p.date,
    pct: (p.short_pct ?? 0) * 100,
  }));

  // Color: >50% short = hot, 30-50% = watch, <30% = normal.
  const tone =
    pct >= 0.5 ? "negative" : pct >= 0.3 ? "warning" : "muted";

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted">
            <TrendingDown className="w-3 h-3" />
            Short Activity (30d)
          </div>
          <p
            className={cn(
              "text-2xl font-bold font-mono mt-1",
              tone === "negative" && "text-negative",
              tone === "warning" && "text-warning"
            )}
          >
            {pctDisplay}%
          </p>
          <p className="text-[11px] text-muted mt-0.5">
            20d avg {avg20}%
          </p>
        </div>
        <div className="w-28 h-14">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparkData}>
              <defs>
                <linearGradient id="siSpark" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f97316" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#f97316" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="pct"
                stroke="#f97316"
                strokeWidth={1.5}
                fill="url(#siSpark)"
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--color-surface)",
                  border: "1px solid var(--color-border)",
                  borderRadius: 6,
                  fontSize: 11,
                  padding: "4px 6px",
                }}
                labelFormatter={(d) => d}
                formatter={(v) => {
                  const n = typeof v === "number" ? v : Number(v ?? 0);
                  return [`${n.toFixed(1)}%`, "Short"];
                }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
      <p className="text-[10px] text-muted/60 mt-2">
        Daily short-sale volume as % of total, FINRA Reg SHO.
      </p>
    </div>
  );
}
