export type FailureMode =
  | "funding_or_sponsor"
  | "recruitment"
  | "efficacy_uninterpretable"
  | "efficacy"
  | "safety"
  | "unclear"
  | "never_started";

export type PrePass = {
  verdict?: string;
  optionable?: boolean;
  shortlist_ownable?: boolean;
  surface?: string;
  md_status?: string;
  block_pass?: boolean;
  reason_codes?: string[];
  walk_away_codes?: string[];
  rights_unknown?: boolean;
  missing_ownership_fill?: boolean;
  empty_stub?: boolean;
};

export type Link = { label: string; url: string };

export type PopulationCheck = {
  field: string;
  captured: boolean;
  source: string;
};

export type ScoreComponent = {
  value: number;
  note?: string;
  [k: string]: unknown;
};

export type Asset = {
  nct_id: string;
  brief_title: string | null;
  official_title: string | null;
  indication: string;
  indication_label?: string;
  conditions: string[];
  phase: string[];
  overall_status: string;
  why_stopped: string | null;
  start_date: string | null;
  primary_completion_date: string | null;
  completion_date: string | null;
  last_update_date: string | null;
  year_stopped: string;
  sponsor_name: string | null;
  sponsor_class: string | null;
  sponsor_status: string;
  enrolment: { count?: number; type?: string } | null;
  has_results: boolean;
  interventions: { name: string; type: string }[];
  targets: { name: string; gene_symbol: string | null; modality?: string; confidence?: string }[];
  mechanism_summary: string | null;
  extraction: {
    nct_id: string;
    targets: Asset["targets"];
    mechanism_summary: string;
    population: Record<string, boolean | string | null>;
    stop_reason_raw: string | null;
    stop_reason_category: string;
    stop_reason_evidence: string;
    endpoint_quality: {
      primary_endpoint: string;
      endpoint_type: string;
      endpoint_appropriate_for_indication: string;
      reasoning: string;
    };
    extraction_confidence: string;
    unresolved: string[];
  };
  classification: {
    nct_id: string;
    failure_mode: FailureMode;
    confidence: string;
    signals: Record<string, unknown>;
    rule_fired: string;
    notes: string;
    commercial_gate?: Record<string, unknown>;
    disqualifier_codes?: string[];
    pre_pass?: PrePass;
    walk_away_codes?: string[];
  };
  score: {
    nct_id: string;
    score: number;
    raw_weighted_sum: number;
    arithmetic: string;
    weights: Record<string, number>;
    components: {
      mechanism_evidence: ScoreComponent;
      failure_mode: ScoreComponent;
      population_definition: ScoreComponent;
      asset_accessibility: ScoreComponent;
    };
    caps_applied: string[];
    rule_a_safety_cap: boolean;
    rule_b_organon_guard: boolean;
    pretrial_mechanism: {
      trial_start: string | null;
      has_pretrial_evidence: boolean;
      pretrial_count: number;
      posttrial_count: number;
      pretrial: Array<Record<string, unknown>>;
      posttrial: Array<Record<string, unknown>>;
    };
    uncertainty: {
      extraction_confidence: string;
      n_unresolved: number;
      unresolved: string[];
      high_uncertainty: boolean;
      interval_halfwidth: number;
      flag: string;
    };
    confidence_interval: [number, number];
    failure_mode: FailureMode;
    classification_rule: string;
    commercial_gate?: Record<string, unknown>;
    pre_pass?: PrePass;
    optionable?: boolean;
    shortlist_ownable?: boolean;
    gate_surface?: string;
    walk_away_codes?: string[];
  };
  pre_pass?: PrePass;
  optionable?: boolean;
  shortlist_ownable?: boolean;
  gate_surface?: string;
  walk_away_codes?: string[];
  enrichment: {
    open_targets: Record<string, unknown>;
    europepmc: {
      has_results_publication?: boolean;
      silence_after_completion?: boolean;
      papers: Array<{
        title?: string;
        url?: string;
        pub_year?: string;
        doi?: string;
        pmid?: string;
      }>;
      source_url?: string;
    };
    sponsor: {
      status?: string;
      sponsor_name?: string;
      source_url?: string | null;
      notes?: string;
      as_of?: string;
    };
  };
  population_checklist: PopulationCheck[];
  links: Link[];
  sources: Record<string, string>;
};

export type Snapshot = {
  snapshot_id: string;
  created_at: string;
  scoring: {
    weights: Record<string, number>;
    rules: Record<string, number>;
  };
  indications: Record<string, { label: string; efo_ids: string[]; mondo_ids: string[] }>;
  assets: Asset[];
  landscape: {
    n_assets: number;
    failure_modes_by_indication: Record<string, Record<string, number>>;
    score_histogram: { bin_start: number; bin_end: number; count: number }[];
    population_capture_rates: Record<
      string,
      { captured: number; n: number; rate: number }
    >;
    assets_by_year_stopped: Record<string, number>;
    mean_female_specific_capture: number;
  };
  weekly: {
    previous_snapshot: string | null;
    new_in_top20: Array<Record<string, unknown>>;
    moved_over_10pts: Array<Record<string, unknown>>;
    note?: string;
  };
  feedback: Array<Record<string, unknown>>;
  counts: { n_assets: number; n_raw: number };
};
