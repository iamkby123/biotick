"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Target, AlertTriangle, Loader2, Sparkles, TrendingUp, Flag } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn, formatMarketCap, formatPrice } from "@/lib/utils";
import { PaywallGate } from "@/components/PaywallGate";
import { usePlan } from "@/hooks/usePlan";

interface TrialPrediction {
  nct_id: string;
  ticker: string;
  phase: string;
  indication: string | null;
  overall_status: string | null;
  primary_completion_date: string | null;
  enrollment: number | null;
  title: string;
  shot_on_goal: number;
  risk_level: string;
  red_flags: string[];
  company_name: string | null;
  market_cap: number | null;
  price: number | null;
}

const FLAG_LABELS: Record<string, string> = {
  LOW_SPONSOR_TRACK_RECORD: "Weak sponsor history",
  TOUGH_INDICATION: "Low-success indication",
  UNDERPOWERED_TRIAL: "Small enrollment",
  SHORT_TIMELINE: "Rushed timeline",
  PAST_DUE_NO_COMPLETION: "Overdue (no completion)",
};

const PHASE_COLORS: Record<string, string> = {
  PHASE1: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  PHASE2: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  PHASE3: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  PHASE4: "bg-green-500/10 text-green-400 border-green-500/30",
};

export default function PredictionsPage() {
  const [view, setView] = useState<"conviction" | "flags">("conviction");
  const [minPhase, setMinPhase] = useState<"PHASE1" | "PHASE2" | "PHASE3">("PHASE2");
  const { isPro } = usePlan();

  const { data: modelInfo } = useQuery<{
    trained: boolean;
    auc?: number;
    cv_auc_mean?: number;
    cv_auc_std?: number;
    training_size?: number;
    feature_importance?: Array<{ feature: string; importance: number }>;
  }>({
    queryKey: ["model-info"],
    queryFn: () => fetchAPI("/predictions/model-info"),
  });

  const { data: conviction, isLoading: loading1 } = useQuery<{ trials: TrialPrediction[] }>({
    queryKey: ["high-conviction", minPhase],
    queryFn: () => fetchAPI(`/predictions/high-conviction?min_phase=${minPhase}&limit=50`),
    enabled: view === "conviction",
  });

  const { data: flagged, isLoading: loading2 } = useQuery<{ trials: TrialPrediction[] }>({
    queryKey: ["red-flags"],
    queryFn: () => fetchAPI(`/predictions/red-flags?limit=50`),
    enabled: view === "flags",
  });

  const trials = view === "conviction" ? conviction?.trials : flagged?.trials;
  const isLoading = view === "conviction" ? loading1 : loading2;

  const content = (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <Sparkles className="w-4 h-4" />
          Predictions
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">Trial Predictions</h1>
        <p className="text-sm text-muted mt-1 max-w-2xl">
          Shot on Goal score combines historical phase success rates, sponsor track record, indication difficulty,
          and enrollment quality into a single 0-100 probability score. Red flags surface structural risk signals.
        </p>
      </div>

      {/* View toggle */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setView("conviction")}
          className={cn(
            "px-4 py-2 rounded-md text-[13px] font-medium transition-colors flex items-center gap-2",
            view === "conviction" ? "bg-accent/15 text-accent" : "text-muted hover:text-foreground hover:bg-surface-hover"
          )}
        >
          <Target className="w-3.5 h-3.5" />
          High Conviction
        </button>
        <button
          onClick={() => setView("flags")}
          className={cn(
            "px-4 py-2 rounded-md text-[13px] font-medium transition-colors flex items-center gap-2",
            view === "flags" ? "bg-accent/15 text-accent" : "text-muted hover:text-foreground hover:bg-surface-hover"
          )}
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          Red Flags
        </button>

        {view === "conviction" && (
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-muted">Phase:</span>
            {(["PHASE1", "PHASE2", "PHASE3"] as const).map((p) => (
              <button
                key={p}
                onClick={() => setMinPhase(p)}
                className={cn(
                  "px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors",
                  minPhase === p ? "bg-accent/15 text-accent" : "text-muted hover:bg-surface-hover"
                )}
              >
                {p.replace("PHASE", "≥ Phase ")}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Model info card */}
      {modelInfo?.trained && (
        <div className="rounded-lg border border-accent/30 bg-accent/5 p-4">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-accent mb-3">
            <Sparkles className="w-3.5 h-3.5" />
            XGBoost Model
          </div>
          <div className="grid grid-cols-4 gap-4 mb-4">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted">AUC</p>
              <p className="text-xl font-bold text-positive">{(modelInfo.auc! * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted">CV AUC</p>
              <p className="text-xl font-bold">{(modelInfo.cv_auc_mean! * 100).toFixed(1)}%</p>
              <p className="text-[10px] text-muted">±{(modelInfo.cv_auc_std! * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted">Training Set</p>
              <p className="text-xl font-bold">{modelInfo.training_size?.toLocaleString()}</p>
              <p className="text-[10px] text-muted">historical trials</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted">Top Feature</p>
              <p className="text-sm font-bold mt-1">
                {modelInfo.feature_importance?.[0]?.feature.replace(/_/g, " ")}
              </p>
              <p className="text-[10px] text-muted">
                {((modelInfo.feature_importance?.[0]?.importance || 0) * 100).toFixed(0)}% importance
              </p>
            </div>
          </div>
          {modelInfo.feature_importance && (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted mb-2">Feature Importance</p>
              <div className="space-y-1.5">
                {modelInfo.feature_importance.slice(0, 8).map((f) => (
                  <div key={f.feature} className="flex items-center gap-3">
                    <span className="text-[11px] w-40 shrink-0">
                      {f.feature.replace(/_/g, " ")}
                    </span>
                    <div className="flex-1 h-1.5 bg-surface-hover rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent transition-all"
                        style={{ width: `${f.importance * 400}%`, maxWidth: "100%" }}
                      />
                    </div>
                    <span className="text-[10px] font-mono text-muted w-10 text-right">
                      {(f.importance * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Explanation card */}
      <div className="rounded-lg border border-border bg-surface/30 p-4 text-sm">
        {view === "conviction" ? (
          <div className="flex items-start gap-3">
            <Target className="w-5 h-5 text-positive shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">How Shot on Goal works</p>
              <p className="text-xs text-muted mt-1 leading-relaxed">
                50% historical success rate for this indication & phase combination, 30% sponsor's own trial track record,
                20% enrollment adequacy. Score ≥60 with zero red flags = high conviction. Based on {'>'}16,000 historical trials.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-3">
            <Flag className="w-5 h-5 text-negative shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Red Flag Detector</p>
              <p className="text-xs text-muted mt-1 leading-relaxed">
                Structural risk signals extracted from trial metadata: weak sponsor history, low-success indications,
                underpowered enrollment, rushed timelines, or overdue completion dates.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Trial list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-accent" />
        </div>
      ) : !trials || trials.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed p-16 text-center">
          <p className="text-sm text-muted">No trials match this filter</p>
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface/50 border-b border-border">
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Score</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Ticker</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Phase</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Indication</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Flags</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Price</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted">Mkt Cap</th>
              </tr>
            </thead>
            <tbody>
              {trials.map((t) => (
                <tr key={t.nct_id} className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <ScoreBadge score={t.shot_on_goal} />
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Link href={`/companies/${t.ticker}`} className="font-semibold text-[13px] text-accent hover:underline">
                      {t.ticker}
                    </Link>
                    {t.company_name && <span className="text-xs text-muted ml-2">{t.company_name.slice(0, 20)}</span>}
                  </td>
                  <td className="px-4 py-3">
                    <span className={cn("px-2 py-0.5 rounded text-[10px] font-medium border", PHASE_COLORS[t.phase] || "")}>
                      {t.phase.replace("PHASE", "P")}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[12px] max-w-[240px] truncate" title={t.indication || ""}>
                    {t.indication || "—"}
                  </td>
                  <td className="px-4 py-3">
                    {t.red_flags.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {t.red_flags.slice(0, 2).map((f) => (
                          <span key={f} className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-negative/10 text-negative">
                            {FLAG_LABELS[f] || f}
                          </span>
                        ))}
                        {t.red_flags.length > 2 && (
                          <span className="text-[10px] text-muted">+{t.red_flags.length - 2}</span>
                        )}
                      </div>
                    ) : (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-positive/10 text-positive">
                        Clean
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-sm">{t.price ? formatPrice(t.price) : "—"}</td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-muted">{formatMarketCap(t.market_cap)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  if (!isPro) {
    return <PaywallGate feature="Trial Predictions & Red Flags">{content}</PaywallGate>;
  }
  return content;
}

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 70 ? "text-positive bg-positive/15" :
    score >= 50 ? "text-warning bg-warning/15" :
    "text-negative bg-negative/15";
  return (
    <div className={cn("w-11 h-11 rounded-full flex items-center justify-center font-bold text-[13px]", color)}>
      {score}
    </div>
  );
}
