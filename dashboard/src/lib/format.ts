import type { FailureMode } from "./types";

const FAILURE_MODE_LABELS: Record<FailureMode, string> = {
  funding_or_sponsor: "Funding / sponsor",
  recruitment: "Recruitment",
  efficacy_uninterpretable: "Efficacy uninterpretable",
  efficacy: "Efficacy",
  safety: "Safety",
  unclear: "Unclear",
};

const POPULATION_LABELS: Record<string, string> = {
  diagnosis_method_stated: "Diagnosis method",
  disease_severity_stratified: "Disease severity / stage",
  age_range_specified: "Age range",
  menopausal_status_specified: "Menopausal status",
  menstrual_cycle_phase_controlled: "Cycle-phase control",
  hormonal_contraceptive_use_addressed: "Hormonal contraception",
  prior_treatment_history_specified: "Prior treatment history",
  biomarker_or_molecular_subtype_used: "Biomarker / molecular subtype",
};

const COMPONENT_LABELS: Record<string, string> = {
  mechanism_evidence: "Mechanism evidence",
  failure_mode: "Failure mode",
  population_definition: "Population definition",
  asset_accessibility: "Asset accessibility",
};

export function failureModeLabel(mode: string | null | undefined): string {
  if (!mode) return "—";
  return FAILURE_MODE_LABELS[mode as FailureMode] ?? mode.replaceAll("_", " ");
}

export function failureModeWord(mode: string | null | undefined): string {
  if (!mode) return "unclear";
  return mode.replaceAll("_", "-");
}

export function populationLabel(field: string): string {
  return POPULATION_LABELS[field] ?? field.replaceAll("_", " ");
}

export function componentLabel(key: string): string {
  return COMPONENT_LABELS[key] ?? key.replaceAll("_", " ");
}

export function fmtScore(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

export function prettyPhase(phases: string[] | null | undefined): string {
  if (!phases?.length) return "—";
  return phases
    .map((p) =>
      p
        .replace(/^PHASE/, "Phase ")
        .replace("_PHASE", "/")
        .replace("EARLY_PHASE1", "Early Phase 1")
        .replace("NA", "N/A")
        .replace("UNKNOWN", "Unknown"),
    )
    .join(", ");
}

export function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}
