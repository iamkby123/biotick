"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, AlertTriangle, Scale } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Factor {
  label: string;
  type: "positive" | "negative";
  detail: string;
}

interface TrialFactorsResponse {
  nct_id: string;
  scored: boolean;
  factors: Factor[];
  counts: { positive: number; negative: number };
}

interface BatchResponse {
  predictions: Record<string, { positive: number; negative: number }>;
}

/**
 * Full factor list — pros above, cons below.
 * Drop this on any trial detail page; it fetches its own data.
 */
export function TrialFactorsCard({ nctId }: { nctId: string }) {
  const { data, isLoading } = useQuery<TrialFactorsResponse>({
    queryKey: ["trial-factors", nctId],
    queryFn: () => fetchAPI(`/predictions/trial/${nctId}`),
    staleTime: 10 * 60 * 1000,
  });

  if (isLoading) return null;
  if (!data || !data.scored || data.factors.length === 0) return null;

  const positives = data.factors.filter((f) => f.type === "positive");
  const negatives = data.factors.filter((f) => f.type === "negative");

  return (
    <div className="rounded-lg border border-border p-5">
      <div className="flex items-center gap-2 mb-4">
        <Scale className="w-4 h-4 text-accent" />
        <h3 className="text-xs font-semibold uppercase tracking-widest text-muted">
          Trial Factors
        </h3>
        <div className="ml-auto flex items-center gap-2 text-[11px]">
          {positives.length > 0 && (
            <span className="inline-flex items-center gap-1 font-semibold text-positive">
              <CheckCircle2 className="w-3 h-3" /> {positives.length}
            </span>
          )}
          {negatives.length > 0 && (
            <span className="inline-flex items-center gap-1 font-semibold text-negative">
              <AlertTriangle className="w-3 h-3" /> {negatives.length}
            </span>
          )}
        </div>
      </div>

      <p className="text-[11px] text-muted mb-4 leading-relaxed">
        Rule-based signals from trial design, sponsor history, and indication
        difficulty. Not a prediction — just the factors that push for or against
        this trial completing successfully.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {positives.length > 0 && (
          <div>
            <h4 className="text-[10px] font-semibold uppercase tracking-widest text-positive mb-2 flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Positives ({positives.length})
            </h4>
            <ul className="space-y-2">
              {positives.map((f, i) => (
                <FactorRow key={`p-${i}`} factor={f} />
              ))}
            </ul>
          </div>
        )}

        {negatives.length > 0 && (
          <div>
            <h4 className="text-[10px] font-semibold uppercase tracking-widest text-negative mb-2 flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              Concerns ({negatives.length})
            </h4>
            <ul className="space-y-2">
              {negatives.map((f, i) => (
                <FactorRow key={`n-${i}`} factor={f} />
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function FactorRow({ factor }: { factor: Factor }) {
  const isPos = factor.type === "positive";
  return (
    <li
      className={cn(
        "rounded-md border p-3",
        isPos
          ? "border-positive/20 bg-positive/5"
          : "border-negative/20 bg-negative/5"
      )}
    >
      <p
        className={cn(
          "text-[13px] font-semibold",
          isPos ? "text-positive" : "text-negative"
        )}
      >
        {factor.label}
      </p>
      <p className="text-[12px] text-muted mt-1 leading-relaxed">
        {factor.detail}
      </p>
    </li>
  );
}

/**
 * Compact +N / -N chip for list rows. Takes counts directly so the
 * parent can do one batch fetch for many trials.
 */
export function FactorSummaryBadge({
  positive,
  negative,
}: {
  positive: number;
  negative: number;
}) {
  if (positive === 0 && negative === 0) return null;
  return (
    <div
      className="inline-flex items-center gap-1.5 shrink-0"
      title={`${positive} positive factor${positive === 1 ? "" : "s"}, ${negative} negative factor${negative === 1 ? "" : "s"}`}
    >
      {positive > 0 && (
        <span className="inline-flex items-center gap-0.5 text-[11px] font-semibold text-positive bg-positive/10 border border-positive/20 rounded px-1.5 py-0.5">
          <CheckCircle2 className="w-3 h-3" />
          {positive}
        </span>
      )}
      {negative > 0 && (
        <span className="inline-flex items-center gap-0.5 text-[11px] font-semibold text-negative bg-negative/10 border border-negative/20 rounded px-1.5 py-0.5">
          <AlertTriangle className="w-3 h-3" />
          {negative}
        </span>
      )}
    </div>
  );
}

/**
 * Batch-fetch factor counts for a list of NCT ids. Cached keyed on the sorted
 * id list so re-renders with the same trials don't re-fetch.
 */
export function useBatchFactors(nctIds: string[]) {
  const idsKey = [...nctIds].sort().join(",");
  return useQuery<BatchResponse["predictions"]>({
    queryKey: ["factors-batch", idsKey],
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
