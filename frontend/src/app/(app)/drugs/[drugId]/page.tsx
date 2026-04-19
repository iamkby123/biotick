"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft, ExternalLink, Loader2, FlaskConical, Calendar } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import type { DrugWithTrials } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  PHASE_COLORS,
  PHASE_LABELS,
  STATUS_COLORS,
  STATUS_LABELS,
  THERAPEUTIC_AREA_COLORS,
} from "@/lib/constants";

export default function DrugDetailPage({
  params,
}: {
  params: Promise<{ drugId: string }>;
}) {
  const { drugId } = use(params);

  const { data: drug, isLoading } = useQuery<DrugWithTrials>({
    queryKey: ["drug", drugId],
    queryFn: () => fetchAPI(`/drugs/${drugId}`),
  });

  const { data: competitors } = useQuery<{
    competitors: Array<{ drug_id: string; drug_name: string; company_ticker: string; company_name: string | null; highest_phase: string | null; indication: string | null; mechanism: string | null }>;
  }>({
    queryKey: ["drug-competitors", drugId],
    queryFn: () => fetchAPI(`/competitors/drug/${drugId}`),
    enabled: !!drug,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-accent" />
      </div>
    );
  }

  if (!drug) {
    return (
      <div className="text-center py-20">
        <p className="text-muted">Drug not found</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        href={`/companies/${drug.company_ticker}`}
        className="inline-flex items-center gap-1 text-sm text-muted hover:text-foreground transition"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to {drug.company_ticker}
      </Link>

      {/* Drug header */}
      <div className="rounded-lg border border-border bg-surface p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <FlaskConical className="w-6 h-6 text-accent" />
              <h1 className="text-2xl font-bold">{drug.drug_name}</h1>
            </div>
            <div className="flex items-center gap-3 mt-2">
              <Link
                href={`/companies/${drug.company_ticker}`}
                className="text-accent hover:underline text-sm"
              >
                {drug.company_ticker}
              </Link>
              {drug.highest_phase && (
                <span
                  className={cn(
                    "px-2 py-0.5 rounded-full text-xs font-medium border",
                    PHASE_COLORS[drug.highest_phase] || PHASE_COLORS.PRECLINICAL
                  )}
                >
                  {PHASE_LABELS[drug.highest_phase] || drug.highest_phase}
                </span>
              )}
              {drug.therapeutic_area && (
                <span
                  className={cn(
                    "px-2 py-0.5 rounded-full text-xs",
                    THERAPEUTIC_AREA_COLORS[drug.therapeutic_area] ||
                      THERAPEUTIC_AREA_COLORS.Other
                  )}
                >
                  {drug.therapeutic_area}
                </span>
              )}
            </div>
          </div>
        </div>

        {drug.indication && (
          <p className="text-sm text-muted mt-3">
            <span className="font-medium text-foreground">Indication:</span>{" "}
            {drug.indication}
          </p>
        )}
        {drug.mechanism && (
          <p className="text-sm text-muted mt-1">
            <span className="font-medium text-foreground">Mechanism:</span>{" "}
            {drug.mechanism}
          </p>
        )}
      </div>

      {/* Phase timeline */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Phase Progression</h2>
        <div className="flex items-center gap-1">
          {["PHASE1", "PHASE2", "PHASE3", "PHASE4"].map((phase) => {
            const isReached =
              drug.highest_phase &&
              phaseRank(drug.highest_phase) >= phaseRank(phase);
            return (
              <div key={phase} className="flex-1">
                <div
                  className={cn(
                    "h-2 rounded-full",
                    isReached ? "bg-accent" : "bg-border"
                  )}
                />
                <p
                  className={cn(
                    "text-xs mt-1 text-center",
                    isReached ? "text-accent font-medium" : "text-muted"
                  )}
                >
                  {PHASE_LABELS[phase]}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Competing Drugs */}
      {competitors && competitors.competitors.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
            <FlaskConical className="w-5 h-5 text-warning" />
            Competing Drugs
            <span className="text-sm text-muted font-normal">
              ({competitors.competitors.length} targeting {drug.indication || "similar indications"})
            </span>
          </h2>
          <div className="rounded-lg border border-border overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface/50 border-b border-border">
                  <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Drug</th>
                  <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Company</th>
                  <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Phase</th>
                  <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Indication</th>
                </tr>
              </thead>
              <tbody>
                {competitors.competitors.slice(0, 20).map((c) => (
                  <tr key={c.drug_id} className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors">
                    <td className="px-4 py-3">
                      <Link href={`/drugs/${c.drug_id}`} className="text-[13px] font-medium hover:text-accent transition-colors">
                        {c.drug_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <Link href={`/companies/${c.company_ticker}`} className="text-accent hover:underline text-[12px] font-semibold">
                        {c.company_ticker}
                      </Link>
                      {c.company_name && (
                        <span className="text-xs text-muted ml-2">{c.company_name.slice(0, 20)}</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {c.highest_phase && (
                        <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-medium border", PHASE_COLORS[c.highest_phase] || PHASE_COLORS.PRECLINICAL)}>
                          {PHASE_LABELS[c.highest_phase] || c.highest_phase}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted max-w-[300px] truncate">{c.indication || "--"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Trials */}
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
          <Calendar className="w-5 h-5 text-accent" />
          Clinical Trials
          <span className="text-sm text-muted font-normal">
            ({drug.trials.length} trials)
          </span>
        </h2>

        {drug.trials.length > 0 ? (
          <div className="space-y-3">
            {drug.trials.map((trial) => (
              <Link
                key={trial.nct_id}
                href={`/trials/${trial.nct_id}`}
                className="rounded-lg border border-border bg-surface p-4 hover:bg-surface-hover hover:border-accent/30 transition-all block group"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-accent group-hover:underline text-sm font-mono">
                        {trial.nct_id}
                      </span>
                      {trial.phase && (
                        <span
                          className={cn(
                            "px-2 py-0.5 rounded-full text-xs font-medium border",
                            PHASE_COLORS[trial.phase] || PHASE_COLORS.PRECLINICAL
                          )}
                        >
                          {PHASE_LABELS[trial.phase] || trial.phase}
                        </span>
                      )}
                      {trial.overall_status && (
                        <span
                          className={cn(
                            "text-xs font-medium",
                            STATUS_COLORS[trial.overall_status] || "text-muted"
                          )}
                        >
                          {STATUS_LABELS[trial.overall_status] ||
                            trial.overall_status}
                        </span>
                      )}
                    </div>
                    <p className="text-sm mt-1 line-clamp-2">{trial.title}</p>
                  </div>
                </div>

                {/* Trial dates and details */}
                <div className="flex flex-wrap gap-x-6 gap-y-1 mt-3 text-xs text-muted">
                  {trial.start_date && (
                    <span>Start: {trial.start_date}</span>
                  )}
                  {trial.primary_completion_date && (
                    <span>
                      Primary completion:{" "}
                      <span className="text-foreground font-medium">
                        {trial.primary_completion_date}
                      </span>
                    </span>
                  )}
                  {trial.enrollment && (
                    <span>Enrollment: {trial.enrollment.toLocaleString()}</span>
                  )}
                  {trial.indication && (
                    <span>Indication: {trial.indication}</span>
                  )}
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-border bg-surface p-8 text-center">
            <p className="text-muted">No trials found for this drug</p>
          </div>
        )}
      </div>
    </div>
  );
}

function phaseRank(phase: string): number {
  const ranks: Record<string, number> = {
    PRECLINICAL: 0,
    PHASE1: 1,
    PHASE2: 2,
    PHASE3: 3,
    PHASE4: 4,
    APPROVED: 5,
  };
  return ranks[phase] ?? 0;
}
