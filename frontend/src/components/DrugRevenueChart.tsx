"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { DollarSign } from "lucide-react";
import { fetchAPI } from "@/lib/api";

interface SalesItem {
  drug_name: string;
  fiscal_year: number;
  revenue_usd: number | null;
  source_accession: string | null;
}

interface SalesResponse {
  ticker: string;
  items: SalesItem[];
}

function fmtUSD(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toFixed(0)}`;
}

/** Bar chart of per-drug revenue over the years we have data for.
 *  Shown on drug detail pages — filters to matching drug_name. */
export function DrugRevenueChart({
  ticker,
  drugName,
}: {
  ticker: string;
  drugName: string;
}) {
  const { data } = useQuery<SalesResponse>({
    queryKey: ["drug-sales", ticker],
    queryFn: () => fetchAPI(`/drug-sales/${ticker}`),
    staleTime: 30 * 60 * 1000,
  });

  if (!data || data.items.length === 0) return null;

  // Match either exact name or case-insensitive substring so a pipeline
  // entry like "Imfinzi (durvalumab)" still matches a 10-K line of
  // "Imfinzi" or "durvalumab".
  const nameLower = drugName.toLowerCase();
  const matched = data.items.filter(
    (i) =>
      i.drug_name.toLowerCase().includes(nameLower) ||
      nameLower.includes(i.drug_name.toLowerCase())
  );
  if (matched.length === 0) return null;

  const chart = matched
    .filter((m) => m.revenue_usd != null)
    .sort((a, b) => a.fiscal_year - b.fiscal_year)
    .map((m) => ({
      year: String(m.fiscal_year),
      revenue: m.revenue_usd ?? 0,
    }));

  if (chart.length === 0) return null;

  return (
    <div className="rounded-lg border border-border p-5">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-1 flex items-center gap-2">
        <DollarSign className="w-3.5 h-3.5 text-accent" />
        Annual Revenue
      </h3>
      <p className="text-[11px] text-muted mb-3">
        Extracted from {ticker} 10-K filings via AI. Latest:{" "}
        <span className="text-foreground font-semibold">
          {fmtUSD(chart[chart.length - 1].revenue)}
        </span>{" "}
        in FY{chart[chart.length - 1].year}.
      </p>
      <div className="h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chart}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--color-border)"
              opacity={0.4}
            />
            <XAxis
              dataKey="year"
              tick={{ fontSize: 11, fill: "var(--color-muted)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--color-muted)" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => fmtUSD(Number(v))}
              width={60}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: 8,
                fontSize: 12,
              }}
              formatter={(v) => {
                const n = typeof v === "number" ? v : Number(v ?? 0);
                return [fmtUSD(n), "Revenue"];
              }}
            />
            <Bar dataKey="revenue" fill="#10b981" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
