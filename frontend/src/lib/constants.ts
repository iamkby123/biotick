export const PHASE_COLORS: Record<string, string> = {
  PHASE1: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  PHASE2: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  PHASE3: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  PHASE4: "bg-green-500/20 text-green-400 border-green-500/30",
  APPROVED: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  PRECLINICAL: "bg-gray-500/20 text-gray-400 border-gray-500/30",
};

export const PHASE_LABELS: Record<string, string> = {
  PHASE1: "Phase 1",
  PHASE2: "Phase 2",
  PHASE3: "Phase 3",
  PHASE4: "Phase 4",
  APPROVED: "Approved",
  PRECLINICAL: "Preclinical",
};

export const STATUS_COLORS: Record<string, string> = {
  RECRUITING: "text-green-400",
  ACTIVE_NOT_RECRUITING: "text-blue-400",
  COMPLETED: "text-emerald-400",
  TERMINATED: "text-red-400",
  WITHDRAWN: "text-gray-500",
  SUSPENDED: "text-yellow-400",
  NOT_YET_RECRUITING: "text-gray-400",
  ENROLLING_BY_INVITATION: "text-blue-300",
};

export const STATUS_LABELS: Record<string, string> = {
  RECRUITING: "Recruiting",
  ACTIVE_NOT_RECRUITING: "Active",
  COMPLETED: "Completed",
  TERMINATED: "Terminated",
  WITHDRAWN: "Withdrawn",
  SUSPENDED: "Suspended",
  NOT_YET_RECRUITING: "Not Yet Recruiting",
  ENROLLING_BY_INVITATION: "Enrolling by Invitation",
};

export const THERAPEUTIC_AREA_COLORS: Record<string, string> = {
  Oncology: "bg-red-500/20 text-red-400",
  Immunology: "bg-purple-500/20 text-purple-400",
  "CNS/Neurology": "bg-indigo-500/20 text-indigo-400",
  Cardiovascular: "bg-pink-500/20 text-pink-400",
  Metabolic: "bg-amber-500/20 text-amber-400",
  "Infectious Disease": "bg-teal-500/20 text-teal-400",
  "Rare Disease": "bg-violet-500/20 text-violet-400",
  "Gene/Cell Therapy": "bg-cyan-500/20 text-cyan-400",
  Respiratory: "bg-sky-500/20 text-sky-400",
  Ophthalmology: "bg-lime-500/20 text-lime-400",
  Other: "bg-gray-500/20 text-gray-400",
};
