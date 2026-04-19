"use client";

import { useQuery } from "@tanstack/react-query";
import { Target, AlertTriangle, ShieldCheck, CircleDot } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";

/** What the backend returns from /api/predictions/trial/{nct_id}. */
interface TrialPrediction {
  nct_id: string;
  scored: boolean;
  shot_on_goal?: number | null;
  phase_success_rate?: number | null;
  indication_difficulty?: number | null;
  sponsor_credibility?: number | null;
  red_flags?: string[];
  risk_level?: "LOW" | "MEDIUM" | "HIGH" | null;
  updated_at?: string | null;
}

interface BatchResponse {
  predictions: Record<
    string,
    { shot_on_goal: number; risk_level: string; red_flags: string[] }
  >;
}

/** Colors for the score circle, matching the /predictions page conventions. */
function scoreColors(score: number) {
  if (score >= 75) return "bg-positive/15 text-positive border-positive/30";
  if (score >= 50) return "bg-accent/15 text-accent border-accent/30";
  if (score >= 25) return "bg-warning/15 text-warning border-warning/30";
  return "bg-negative/15 text-negative border-negative/30";
}

function riskBadge(level: string | null | undefined) {
  if (level === "LOW") return "bg-positive/10 text-positive";
  if (level === "MEDIUM") return "bg-warning/10 text-warning";
  if (level === "HIGH") return "bg-negative/10 text-negative";
  return "bg-surface-hover text-muted";
}

/**
 * Full Shot on Goal card — use on a trial detail page.
 * Fetches its own data; just give it an NCT id.
 */
export function ShotOnGoalCard({ nctId }: { nctId: string }) {
  const { data, isLoading } = useQuery<TrialPrediction>({
    queryKey: ["trial-prediction", nctId],
    queryFn: () => fetchAPI(`/predictions/trial/${nctId}`),
    staleTime: 10 * 60 * 1000,
  });

  if (isLoading) return null;
  if (!data || !data.scored || data.shot_on_goal == null) {
    // Trial wasn't scored (e.g., Phase 4 post-approval, or too little data).
    // Show nothing rather than a confusing empty state.
    return null;
  }

  const score = Math.round(data.shot_on_goal);
  const flags = data.red_flags || [];

  return (
    <div
      className={cn(
        "rounded-lg border p-5",
        score >= 75
          ? "border-positive/30 bg-positive/5"
          : score >= 50
            ? "border-accent/30 bg-accent/5"
            : score >= 25
              ? "border-warning/30 bg-warning/5"
              : "border-negative/30 bg-negative/5"
      )}
    >
      <div className="flex items-start gap-5">
        {/* Score circle */}
        <div
          className={cn(
            "w-20 h-20 rounded-full border-2 flex flex-col items-center justify-center shrink-0",
            scoreColors(score)
          )}
        >
          <span className="text-2xl font-bold leading-none">{score}</span>
          <span className="text-[9px] uppercase tracking-wider mt-0.5">/100</span>
        </div>

        {/* Label + explanation */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-bold text-[15px] flex items-center gap-1.5">
              <Target className="w-4 h-4 text-accent" />
              Shot on Goal
            </h3>
            {data.risk_level && (
              <span
                className={cn(
                  "text-[10px] font-semibold px-2 py-0.5 rounded uppercase tracking-wider",
                  riskBadge(data.risk_level)
                )}
              >
                {data.risk_level} Risk
              </span>
            )}
            {flags.length === 0 && (
              <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded bg-positive/10 text-positive uppercase tracking-wider">
                <ShieldCheck className="w-3 h-3" />
                Clean
              </span>
            )}
          </div>
          <p className="text-xs text-muted mt-1.5 leading-relaxed">
            Percentile rank vs. every other active Phase 1–3 biotech trial.{" "}
            <span className="text-foreground font-medium">{score}</span> means this
            trial scores higher on completion likelihood than{" "}
            <span className="text-foreground font-medium">{score}%</span> of its peers.
            Features: indication success rate, sponsor track record, enrollment size, phase.
          </p>

          {/* Sub-scores */}
          <div className="grid grid-cols-3 gap-3 mt-4">
            <SubScore
              label="Phase success rate"
              value={data.phase_success_rate}
              format="pct"
            />
            <SubScore
              label="Sponsor credibility"
              value={data.sponsor_credibility}
              format="pct"
            />
            <SubScore
              label="Indication difficulty"
              value={data.indication_difficulty}
              format="pct"
              inverted
            />
          </div>

          {/* Red flags */}
          {flags.length > 0 && (
            <div className="mt-4 rounded-md border border-negative/20 bg-negative/5 p-3">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-negative mb-2">
                <AlertTriangle className="w-3.5 h-3.5" />
                Red Flags ({flags.length})
              </div>
              <ul className="space-y-1">
                {flags.map((flag, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-[12px] text-foreground"
                  >
                    <CircleDot className="w-3 h-3 text-negative mt-0.5 shrink-0" />
                    {flag}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SubScore({
  label,
  value,
  format,
  inverted,
}: {
  label: string;
  value: number | null | undefined;
  format: "pct";
  inverted?: boolean;
}) {
  if (value == null) {
    return (
      <div>
        <p className="text-[10px] text-muted uppercase font-semibold tracking-wider">
          {label}
        </p>
        <p className="text-sm text-muted/60 mt-0.5">—</p>
      </div>
    );
  }
  const pct = format === "pct" ? Math.round(value * 100) : value;
  const good = inverted ? pct < 50 : pct >= 50;
  return (
    <div>
      <p className="text-[10px] text-muted uppercase font-semibold tracking-wider">
        {label}
      </p>
      <p
        className={cn(
          "text-sm font-semibold font-mono mt-0.5",
          good ? "text-positive" : pct >= 30 ? "text-warning" : "text-negative"
        )}
      >
        {pct}%
      </p>
    </div>
  );
}

/**
 * Compact badge — use in trial list rows (drug detail, company detail).
 * Takes the prediction data directly so the parent can do one batch fetch.
 */
export function ShotOnGoalBadge({
  score,
  risk,
  flags,
  size = "sm",
}: {
  score: number | null | undefined;
  risk?: string | null;
  flags?: string[];
  size?: "sm" | "md";
}) {
  if (score == null) return null;
  const s = Math.round(score);
  const flagCount = flags?.length ?? 0;

  const box =
    size === "md"
      ? "w-12 h-12 text-base"
      : "w-9 h-9 text-[13px]";

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 shrink-0",
        size === "md" ? "gap-3" : "gap-2"
      )}
      title={`Shot on Goal ${s}/100${risk ? ` · ${risk} risk` : ""}${
        flagCount > 0 ? ` · ${flagCount} red flag${flagCount > 1 ? "s" : ""}` : ""
      }`}
    >
      <div
        className={cn(
          "rounded-full border flex items-center justify-center font-bold",
          box,
          scoreColors(s)
        )}
      >
        {s}
      </div>
      {flagCount > 0 && (
        <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-negative">
          <AlertTriangle className="w-3 h-3" />
          {flagCount}
        </span>
      )}
    </div>
  );
}

/**
 * Hook: batch-fetch predictions for a list of NCT ids.
 * Returns a map keyed by NCT id. Safe to call with an empty list.
 */
export function useBatchPredictions(nctIds: string[]) {
  const idsKey = [...nctIds].sort().join(",");

  return useQuery<BatchResponse["predictions"]>({
    queryKey: ["predictions-batch", idsKey],
    queryFn: async () => {
      if (!idsKey) return {};
      const res = await fetchAPI<BatchResponse>(
        `/predictions/batch?ids=${encodeURIComponent(idsKey)}`
      );
      return res.predictions;
    },
    enabled: nctIds.length > 0,
    staleTime: 10 * 60 * 1000,
  });
}
