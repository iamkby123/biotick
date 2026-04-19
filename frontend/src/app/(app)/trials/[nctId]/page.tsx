"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  ArrowLeft,
  ExternalLink,
  Loader2,
  FlaskConical,
  Users,
  Calendar,
  MapPin,
  Shield,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  FileText,
  Target,
  Beaker,
  Pill,
  Octagon,
  BarChart3,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PHASE_COLORS, PHASE_LABELS, STATUS_COLORS, STATUS_LABELS, THERAPEUTIC_AREA_COLORS } from "@/lib/constants";
import { TrialFactorsCard } from "@/components/TrialFactors";

interface TrialDetail {
  nct_id: string;
  title: string;
  brief_title: string;
  acronym: string | null;
  status: string;
  start_date: string | null;
  primary_completion_date: string | null;
  completion_date: string | null;
  brief_summary: string | null;
  detailed_description: string | null;
  study_type: string | null;
  phases: string[];
  allocation: string | null;
  intervention_model: string | null;
  primary_purpose: string | null;
  masking: string | null;
  masking_details: string | null;
  who_masked: string[];
  enrollment: number | null;
  enrollment_type: string | null;
  arms: Array<{ label: string; type: string; description: string | null }>;
  interventions: Array<{ name: string; type: string; description: string | null; arm_labels: string[] }>;
  primary_outcomes: Array<{ measure: string; description: string | null; timeframe: string | null }>;
  secondary_outcomes: Array<{ measure: string; description: string | null; timeframe: string | null }>;
  eligibility: {
    criteria: string | null;
    sex: string | null;
    minimum_age: string | null;
    maximum_age: string | null;
    healthy_volunteers: string | null;
  };
  sponsor: string | null;
  sponsor_type: string | null;
  collaborators: string[];
  conditions: string[];
  keywords: string[];
  has_dmc: boolean | null;
  is_fda_regulated_drug: boolean | null;
  is_fda_regulated_device: boolean | null;
  locations_count: number;
  references: Array<{ pmid: string | null; citation: string | null; type: string | null }>;
  url: string;
}

interface DBTrial {
  nct_id: string;
  drug_id: string | null;
  company_ticker: string | null;
  why_stopped: string | null;
  has_results: boolean;
  results_first_posted: string | null;
  therapeutic_area: string | null;
  indication: string | null;
}

interface DrugInfo {
  drug_id: string;
  drug_name: string;
  company_ticker: string;
  generic_name: string | null;
  mechanism: string | null;
  therapeutic_area: string | null;
  indication: string | null;
  highest_phase: string | null;
  status: string | null;
  first_approval_date: string | null;
}

export default function TrialDetailPage({
  params,
}: {
  params: Promise<{ nctId: string }>;
}) {
  const { nctId } = use(params);

  const { data: trial, isLoading, error } = useQuery<TrialDetail>({
    queryKey: ["trial-detail", nctId],
    queryFn: () => fetchAPI(`/trials/${nctId}/detail`),
  });

  // Our DB row — has drug_id, why_stopped, has_results
  const { data: dbTrial } = useQuery<DBTrial>({
    queryKey: ["trial-db", nctId],
    queryFn: () => fetchAPI(`/trials/${nctId}`),
    retry: false,
  });

  // Linked drug, if we have a drug_id
  const { data: drug } = useQuery<DrugInfo>({
    queryKey: ["trial-drug", dbTrial?.drug_id],
    queryFn: () => fetchAPI(`/drugs/${dbTrial?.drug_id}`),
    enabled: !!dbTrial?.drug_id,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-5 h-5 animate-spin text-accent" />
        <span className="ml-2 text-sm text-muted">Loading trial data from ClinicalTrials.gov...</span>
      </div>
    );
  }

  if (error || !trial) {
    return (
      <div className="text-center py-20">
        <p className="text-muted">Trial not found</p>
        <p className="text-xs text-muted mt-1">Could not load data for {nctId}</p>
      </div>
    );
  }

  const phase = trial.phases?.[trial.phases.length - 1] || null;

  // Detect potential design flaws/considerations
  const designNotes = getDesignNotes(trial);

  return (
    <div className="space-y-6">
      {/* Back */}
      <button onClick={() => window.history.back()} className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-foreground transition">
        <ArrowLeft className="w-3.5 h-3.5" />
        Back
      </button>

      {/* Header */}
      <div>
        <div className="flex items-center gap-3 flex-wrap">
          <a
            href={trial.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent font-mono text-sm hover:underline flex items-center gap-1"
          >
            {trial.nct_id} <ExternalLink className="w-3 h-3" />
          </a>
          {phase && (
            <span className={cn("px-2 py-0.5 rounded text-[11px] font-medium border", PHASE_COLORS[phase] || PHASE_COLORS.PRECLINICAL)}>
              {PHASE_LABELS[phase] || phase}
            </span>
          )}
          <span className={cn("text-[12px] font-medium", STATUS_COLORS[trial.status] || "text-muted")}>
            {STATUS_LABELS[trial.status] || trial.status}
          </span>
          {trial.is_fda_regulated_drug && (
            <span className="text-[10px] px-2 py-0.5 rounded bg-accent/10 text-accent">FDA Regulated</span>
          )}
        </div>
        <h1 className="text-xl font-bold mt-2 leading-tight">{trial.title}</h1>
        {trial.acronym && <p className="text-sm text-accent mt-1">{trial.acronym}</p>}
        <p className="text-sm text-muted mt-2">
          Sponsored by <span className="text-foreground font-medium">{trial.sponsor}</span>
          {trial.collaborators.length > 0 && (
            <span> &middot; with {trial.collaborators.join(", ")}</span>
          )}
        </p>
      </div>

      {/* Factor analysis — pros/cons. Hides itself if nothing to show. */}
      <TrialFactorsCard nctId={trial.nct_id} />

      {/* Key stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatBox icon={Users} label="Enrollment" value={trial.enrollment ? trial.enrollment.toLocaleString() : "N/A"} sublabel={trial.enrollment_type || ""} />
        <StatBox icon={Calendar} label="Start" value={trial.start_date || "N/A"} />
        <StatBox icon={Target} label="Primary Completion" value={trial.primary_completion_date || "N/A"} />
        <StatBox icon={MapPin} label="Locations" value={String(trial.locations_count)} sublabel="sites" />
      </div>

      {/* Why Stopped banner (from our DB) */}
      {dbTrial?.why_stopped && (
        <div className="rounded-lg border border-negative/30 bg-negative/5 p-5">
          <div className="flex items-start gap-3">
            <Octagon className="w-5 h-5 text-negative shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="text-xs font-semibold uppercase tracking-widest text-negative mb-1">
                Trial Stopped
              </h3>
              <p className="text-sm text-foreground leading-relaxed">{dbTrial.why_stopped}</p>
            </div>
          </div>
        </div>
      )}

      {/* Results available link */}
      {dbTrial?.has_results && (
        <div className="rounded-lg border border-positive/30 bg-positive/5 p-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <BarChart3 className="w-5 h-5 text-positive shrink-0" />
            <div>
              <p className="text-sm font-semibold">Results Available</p>
              <p className="text-xs text-muted">
                {dbTrial.results_first_posted
                  ? `Results first posted ${dbTrial.results_first_posted}`
                  : "This trial has posted results on ClinicalTrials.gov"}
              </p>
            </div>
          </div>
          <a
            href={`https://clinicaltrials.gov/study/${trial.nct_id}?tab=results`}
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 rounded-md bg-positive text-black text-xs font-semibold hover:opacity-90 transition flex items-center gap-1.5 shrink-0"
          >
            View Results
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      )}

      {/* Linked drug card */}
      {drug && (
        <div className="rounded-lg border border-accent/30 bg-accent/5 p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-accent mb-3 flex items-center gap-2">
            <Pill className="w-4 h-4" />
            Drug Program
          </h3>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <Link
                href={`/drugs/${drug.drug_id}`}
                className="text-lg font-bold hover:text-accent transition-colors inline-flex items-center gap-1"
              >
                {drug.drug_name}
                <ExternalLink className="w-3.5 h-3.5 text-muted" />
              </Link>
              {drug.generic_name && drug.generic_name !== drug.drug_name && (
                <p className="text-xs text-muted mt-0.5">Generic: {drug.generic_name}</p>
              )}
              <div className="flex items-center gap-2 flex-wrap mt-2">
                {drug.highest_phase && (
                  <span className={cn("px-2 py-0.5 rounded text-[11px] font-medium border", PHASE_COLORS[drug.highest_phase] || PHASE_COLORS.PRECLINICAL)}>
                    {PHASE_LABELS[drug.highest_phase] || drug.highest_phase}
                  </span>
                )}
                {drug.therapeutic_area && (
                  <span className={cn("px-2 py-0.5 rounded text-[11px]", THERAPEUTIC_AREA_COLORS[drug.therapeutic_area] || THERAPEUTIC_AREA_COLORS.Other)}>
                    {drug.therapeutic_area}
                  </span>
                )}
                {drug.status && (
                  <span className="px-2 py-0.5 rounded text-[11px] bg-surface-hover text-muted border border-border">
                    {drug.status}
                  </span>
                )}
              </div>
            </div>
            {drug.company_ticker && (
              <Link
                href={`/companies/${drug.company_ticker}`}
                className="rounded-md border border-border px-3 py-2 hover:border-accent/30 hover:bg-surface-hover transition-all text-center"
              >
                <p className="text-[10px] text-muted uppercase font-semibold">Developer</p>
                <p className="text-sm font-bold font-mono text-accent">{drug.company_ticker}</p>
              </Link>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 mt-4 text-[13px]">
            {drug.mechanism && (
              <div>
                <p className="text-[10px] uppercase tracking-widest text-muted font-semibold">Mechanism</p>
                <p className="text-sm mt-0.5">{drug.mechanism}</p>
              </div>
            )}
            {drug.indication && (
              <div>
                <p className="text-[10px] uppercase tracking-widest text-muted font-semibold">Indication</p>
                <p className="text-sm mt-0.5">{drug.indication}</p>
              </div>
            )}
            {drug.first_approval_date && (
              <div>
                <p className="text-[10px] uppercase tracking-widest text-muted font-semibold">First Approval</p>
                <p className="text-sm mt-0.5 font-mono">{drug.first_approval_date}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Design notes / potential concerns */}
      {designNotes.length > 0 && (
        <div className="rounded-lg border border-warning/30 bg-warning/5 p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-warning mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            Design Considerations
          </h3>
          <ul className="space-y-2">
            {designNotes.map((note, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className={cn("w-1.5 h-1.5 rounded-full mt-2 shrink-0", note.level === "warning" ? "bg-warning" : "bg-muted")} />
                <div>
                  <span className="font-medium">{note.title}:</span>{" "}
                  <span className="text-muted">{note.description}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Summary */}
      {trial.brief_summary && (
        <Section title="Summary" icon={FileText}>
          <p className="text-sm text-muted leading-relaxed whitespace-pre-line">{trial.brief_summary}</p>
        </Section>
      )}

      {/* Study Design */}
      <Section title="Study Design" icon={Beaker}>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-3 text-[13px]">
          <DesignRow label="Study Type" value={trial.study_type} />
          <DesignRow label="Allocation" value={trial.allocation} />
          <DesignRow label="Intervention Model" value={trial.intervention_model} />
          <DesignRow label="Primary Purpose" value={trial.primary_purpose} />
          <DesignRow label="Masking" value={trial.masking} />
          <DesignRow label="Who Masked" value={trial.who_masked.length > 0 ? trial.who_masked.join(", ") : null} />
          <DesignRow label="Has DMC" value={trial.has_dmc ? "Yes" : trial.has_dmc === false ? "No" : null} />
          <DesignRow label="FDA Drug" value={trial.is_fda_regulated_drug ? "Yes" : trial.is_fda_regulated_drug === false ? "No" : null} />
        </div>
      </Section>

      {/* Arms & Interventions */}
      {(trial.arms.length > 0 || trial.interventions.length > 0) && (
        <Section title="Arms & Interventions" icon={FlaskConical}>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {trial.arms.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-widest text-muted mb-2">Arms</h4>
                <div className="space-y-2">
                  {trial.arms.map((arm, i) => (
                    <div key={i} className="rounded-md border border-border p-3">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">{arm.label}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-hover text-muted">{arm.type}</span>
                      </div>
                      {arm.description && <p className="text-xs text-muted mt-1">{arm.description}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {trial.interventions.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-widest text-muted mb-2">Interventions</h4>
                <div className="space-y-2">
                  {trial.interventions.map((intv, i) => (
                    <div key={i} className="rounded-md border border-border p-3">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">{intv.name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent">{intv.type}</span>
                      </div>
                      {intv.description && <p className="text-xs text-muted mt-1 line-clamp-3">{intv.description}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Section>
      )}

      {/* Endpoints / Outcomes */}
      {(trial.primary_outcomes.length > 0 || trial.secondary_outcomes.length > 0) && (
        <Section title="Endpoints" icon={Target}>
          {trial.primary_outcomes.length > 0 && (
            <div className="mb-4">
              <h4 className="text-xs font-semibold uppercase tracking-widest text-accent mb-2">Primary</h4>
              <div className="space-y-2">
                {trial.primary_outcomes.map((o, i) => (
                  <div key={i} className="rounded-md border border-accent/20 bg-accent/5 p-3">
                    <p className="text-sm font-medium">{o.measure}</p>
                    {o.timeframe && <p className="text-xs text-muted mt-1">Timeframe: {o.timeframe}</p>}
                    {o.description && <p className="text-xs text-muted mt-1">{o.description}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
          {trial.secondary_outcomes.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-widest text-muted mb-2">Secondary ({trial.secondary_outcomes.length})</h4>
              <div className="space-y-2">
                {trial.secondary_outcomes.slice(0, 5).map((o, i) => (
                  <div key={i} className="rounded-md border border-border p-3">
                    <p className="text-sm">{o.measure}</p>
                    {o.timeframe && <p className="text-xs text-muted mt-1">Timeframe: {o.timeframe}</p>}
                  </div>
                ))}
                {trial.secondary_outcomes.length > 5 && (
                  <p className="text-xs text-muted">+{trial.secondary_outcomes.length - 5} more secondary endpoints</p>
                )}
              </div>
            </div>
          )}
        </Section>
      )}

      {/* Eligibility */}
      {trial.eligibility.criteria && (
        <Section title="Eligibility" icon={Users}>
          <div className="flex gap-4 mb-3 text-xs">
            {trial.eligibility.sex && <span className="px-2 py-1 rounded bg-surface-hover">Sex: {trial.eligibility.sex}</span>}
            {trial.eligibility.minimum_age && <span className="px-2 py-1 rounded bg-surface-hover">Min Age: {trial.eligibility.minimum_age}</span>}
            {trial.eligibility.maximum_age && <span className="px-2 py-1 rounded bg-surface-hover">Max Age: {trial.eligibility.maximum_age}</span>}
            {trial.eligibility.healthy_volunteers && <span className="px-2 py-1 rounded bg-surface-hover">Healthy Volunteers: {trial.eligibility.healthy_volunteers}</span>}
          </div>
          <div className="rounded-md border border-border p-4 max-h-[300px] overflow-y-auto">
            <pre className="text-xs text-muted whitespace-pre-wrap font-sans leading-relaxed">
              {trial.eligibility.criteria}
            </pre>
          </div>
        </Section>
      )}

      {/* Conditions & Keywords */}
      <div className="flex flex-wrap gap-2">
        {trial.conditions.map((c, i) => (
          <span key={i} className="px-2.5 py-1 rounded-md text-xs bg-surface-hover border border-border">{c}</span>
        ))}
        {trial.keywords.map((k, i) => (
          <span key={`k-${i}`} className="px-2.5 py-1 rounded-md text-xs text-muted bg-surface/50">{k}</span>
        ))}
      </div>

      {/* References */}
      {trial.references.length > 0 && (
        <Section title="References" icon={FileText}>
          <div className="space-y-2">
            {trial.references.slice(0, 10).map((ref, i) => (
              <div key={i} className="text-xs text-muted">
                {ref.pmid && (
                  <a
                    href={`https://pubmed.ncbi.nlm.nih.gov/${ref.pmid}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline mr-2"
                  >
                    PMID: {ref.pmid}
                  </a>
                )}
                {ref.citation && <span className="line-clamp-2">{ref.citation}</span>}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ClinicalTrials.gov link */}
      <div className="text-center pt-4 pb-8">
        <a
          href={trial.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border hover:border-accent/30 hover:bg-surface-hover transition-all text-sm"
        >
          View full record on ClinicalTrials.gov
          <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>
    </div>
  );
}

/* ── Design Notes Generator ── */
function getDesignNotes(trial: TrialDetail): Array<{ title: string; description: string; level: "warning" | "info" }> {
  const notes: Array<{ title: string; description: string; level: "warning" | "info" }> = [];

  // Open label
  if (trial.masking === "NONE" || trial.masking === "NONE_OPEN") {
    notes.push({
      title: "Open Label Design",
      description: "No blinding — participants and investigators know who receives treatment. This can introduce bias in subjective endpoints.",
      level: "warning",
    });
  }

  // Single arm
  if (trial.intervention_model === "SINGLE_GROUP" || trial.arms.length <= 1) {
    notes.push({
      title: "Single Arm Study",
      description: "No control group for comparison. Results are harder to interpret without a placebo or active comparator arm.",
      level: "warning",
    });
  }

  // Small enrollment
  if (trial.enrollment && trial.enrollment < 50) {
    notes.push({
      title: "Small Sample Size",
      description: `Only ${trial.enrollment} participants enrolled. Small studies have lower statistical power and results may not be generalizable.`,
      level: "warning",
    });
  }

  // No DMC
  if (trial.has_dmc === false) {
    notes.push({
      title: "No Data Monitoring Committee",
      description: "No independent DMC to monitor safety. This is unusual for late-phase trials and may indicate less rigorous oversight.",
      level: "info",
    });
  }

  // Phase 3 with small enrollment
  if (trial.phases.includes("PHASE3") && trial.enrollment && trial.enrollment < 200) {
    notes.push({
      title: "Phase 3 With Limited Enrollment",
      description: `${trial.enrollment} participants is relatively small for a Phase 3 trial, which typically requires hundreds to thousands for statistical significance.`,
      level: "warning",
    });
  }

  // Very long running trial
  if (trial.start_date && trial.primary_completion_date) {
    const start = new Date(trial.start_date);
    const end = new Date(trial.primary_completion_date);
    const years = (end.getTime() - start.getTime()) / (365.25 * 24 * 60 * 60 * 1000);
    if (years > 7) {
      notes.push({
        title: "Extended Duration",
        description: `Trial spans ${Math.round(years)} years from start to primary completion. Extended timelines may indicate enrollment challenges or complex endpoints.`,
        level: "info",
      });
    }
  }

  // Surrogate endpoints
  const primaryMeasures = trial.primary_outcomes.map(o => o.measure.toLowerCase()).join(" ");
  if (primaryMeasures.includes("biomarker") || primaryMeasures.includes("response rate") || primaryMeasures.includes("surrogate")) {
    notes.push({
      title: "Surrogate Endpoint",
      description: "Primary endpoint uses a surrogate marker rather than clinical outcome (like overall survival). FDA may require confirmatory trials.",
      level: "info",
    });
  }

  // Terminated/suspended
  if (trial.status === "TERMINATED") {
    notes.push({
      title: "Trial Terminated",
      description: "This trial was stopped early, potentially due to safety concerns, lack of efficacy, or business decisions.",
      level: "warning",
    });
  }

  if (trial.status === "SUSPENDED") {
    notes.push({
      title: "Trial Suspended",
      description: "Enrollment or activities temporarily halted. May resume or be permanently discontinued.",
      level: "warning",
    });
  }

  return notes;
}

/* ── Helper Components ── */
function Section({ title, icon: Icon, children }: { title: string; icon: React.ComponentType<{ className?: string }>; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border p-5">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3 flex items-center gap-2">
        <Icon className="w-4 h-4 text-accent" />
        {title}
      </h3>
      {children}
    </div>
  );
}

function StatBox({ icon: Icon, label, value, sublabel }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string; sublabel?: string }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-3.5 h-3.5 text-muted" />
        <p className="text-[10px] text-muted uppercase font-semibold">{label}</p>
      </div>
      <p className="text-lg font-bold">{value}</p>
      {sublabel && <p className="text-[11px] text-muted">{sublabel}</p>}
    </div>
  );
}

function DesignRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex justify-between py-1.5 border-b border-border/50">
      <span className="text-muted">{label}</span>
      <span className="font-medium">{value || "N/A"}</span>
    </div>
  );
}
