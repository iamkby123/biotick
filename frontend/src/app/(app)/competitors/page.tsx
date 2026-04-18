"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Grid3x3, Loader2, Search } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PHASE_LABELS } from "@/lib/constants";
import { PaywallGate } from "@/components/PaywallGate";
import { usePlan } from "@/hooks/usePlan";

interface IndicationRow {
  indication: string;
  total: number;
  companies: number;
  phases: Record<string, number>;
}

interface IndicationsResponse {
  indications: IndicationRow[];
  phases: string[];
}

export default function CompetitorsPage() {
  const [search, setSearch] = useState("");
  const { isPro } = usePlan();

  const { data, isLoading } = useQuery<IndicationsResponse>({
    queryKey: ["indication-matrix"],
    queryFn: () => fetchAPI("/competitors/indications?limit=30"),
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    if (!search.trim()) return data.indications;
    const q = search.toLowerCase();
    return data.indications.filter((i) => i.indication.toLowerCase().includes(q));
  }, [data, search]);

  // Determine heatmap intensity per phase column — find max count
  const maxByPhase = useMemo(() => {
    if (!data) return {} as Record<string, number>;
    const m: Record<string, number> = {};
    for (const p of data.phases) m[p] = 0;
    for (const row of data.indications) {
      for (const p of data.phases) {
        const v = row.phases[p] || 0;
        if (v > m[p]) m[p] = v;
      }
    }
    return m;
  }, [data]);

  const phases = data?.phases || ["PHASE1", "PHASE2", "PHASE3", "PHASE4", "APPROVED"];

  const content = (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <Grid3x3 className="w-4 h-4" />
          Competitive Landscape
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">Competitor Matrix</h1>
        <p className="text-sm text-muted mt-1">
          Top indications by drug count, broken out by clinical phase. Use this to spot crowded
          therapeutic areas and identify which companies are competing for the same patients.
        </p>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input
          type="text"
          placeholder="Filter indications…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2 rounded-md bg-surface border border-border text-sm placeholder:text-muted focus:outline-none focus:border-accent/50 transition"
        />
      </div>

      {/* Matrix */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <Grid3x3 className="w-6 h-6 text-muted/30 mx-auto mb-2" />
          <p className="text-sm text-muted">No indications match your filter</p>
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface/50 border-b border-border">
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Indication</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Drugs</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Companies</th>
                {phases.map((p) => (
                  <th
                    key={p}
                    className="text-center px-3 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted"
                  >
                    {PHASE_LABELS[p] || p}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={row.indication} className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors">
                  <td className="px-4 py-3 max-w-[320px]">
                    <Link
                      href={`/companies?search=${encodeURIComponent(row.indication)}`}
                      className="text-[13px] hover:text-accent transition-colors line-clamp-2"
                    >
                      {row.indication}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-sm font-semibold">{row.total}</td>
                  <td className="px-4 py-3 text-right font-mono text-sm text-muted">{row.companies}</td>
                  {phases.map((p) => {
                    const count = row.phases[p] || 0;
                    const max = maxByPhase[p] || 1;
                    const intensity = count / max;
                    const bgColor = getHeatmapClass(p, intensity);
                    return (
                      <td key={p} className="px-3 py-3 text-center">
                        {count > 0 ? (
                          <Link
                            href={`/companies?search=${encodeURIComponent(row.indication)}`}
                            className={cn(
                              "inline-flex items-center justify-center min-w-[2.25rem] h-7 rounded font-mono text-[12px] font-semibold transition-colors hover:opacity-80",
                              bgColor
                            )}
                          >
                            {count}
                          </Link>
                        ) : (
                          <span className="text-muted/40 text-xs">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && (
        <p className="text-xs text-muted text-right">
          Showing {filtered.length} of {data.indications.length} top indications by drug count
        </p>
      )}
    </div>
  );

  if (!isPro) {
    return <PaywallGate feature="Competitor Matrix">{content}</PaywallGate>;
  }
  return content;
}

function getHeatmapClass(phase: string, intensity: number): string {
  // Different base color per phase, intensity shifts opacity
  const baseColors: Record<string, string[]> = {
    PHASE1: ["bg-blue-500/10 text-blue-400", "bg-blue-500/20 text-blue-300", "bg-blue-500/40 text-blue-100", "bg-blue-500/60 text-white"],
    PHASE2: ["bg-yellow-500/10 text-yellow-400", "bg-yellow-500/20 text-yellow-300", "bg-yellow-500/40 text-yellow-100", "bg-yellow-500/60 text-white"],
    PHASE3: ["bg-orange-500/10 text-orange-400", "bg-orange-500/20 text-orange-300", "bg-orange-500/40 text-orange-100", "bg-orange-500/60 text-white"],
    PHASE4: ["bg-green-500/10 text-green-400", "bg-green-500/20 text-green-300", "bg-green-500/40 text-green-100", "bg-green-500/60 text-white"],
    APPROVED: ["bg-emerald-500/10 text-emerald-400", "bg-emerald-500/20 text-emerald-300", "bg-emerald-500/40 text-emerald-100", "bg-emerald-500/60 text-white"],
  };
  const tiers = baseColors[phase] || ["bg-surface-hover text-muted", "bg-surface-hover text-muted", "bg-surface-hover text-muted", "bg-surface-hover text-muted"];
  if (intensity >= 0.75) return tiers[3];
  if (intensity >= 0.5) return tiers[2];
  if (intensity >= 0.25) return tiers[1];
  return tiers[0];
}
