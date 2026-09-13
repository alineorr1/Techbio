import rules from "./rightsQueueRules.json" with { type: "json" };
import type { Asset } from "./types";

export const LABEL_TRIAGE = "TRIAGE";
export const LABEL_RIGHTS_QUEUE = "RIGHTS_QUEUE";
export const LABEL_OPP = "OPP";

export type StageLabel = typeof LABEL_TRIAGE | typeof LABEL_RIGHTS_QUEUE | typeof LABEL_OPP;
export type TriageDisposition = "keep" | "disregard";

export type LabelRow = {
  label: StageLabel;
  triage: TriageDisposition;
  note: string;
  queueTier?: string | null;
};

type QueueRules = {
  cap: number;
  large_cap_industry: string[];
  disregard: Array<{ code: string; kind: string; patterns?: string[] }>;
};

const QUEUE_RULES = rules as QueueRules;

function norm(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function assetBlob(asset: Asset): string {
  const names = (asset.interventions || []).map((item) => item.name || "");
  return norm(
    [asset.brief_title, asset.official_title, asset.mechanism_summary, asset.sponsor_name, ...names]
      .filter(Boolean)
      .join(" "),
  );
}

function deskOf(asset: Asset): string {
  return String(
    asset.desk_classification || asset.ownability?.desk_classification || "",
  ).toUpperCase();
}

function rightsConfidence(asset: Asset): string {
  const rec = (asset as Asset & { rights?: { confidence?: string } }).rights;
  return String(rec?.confidence || "empty_stub").toLowerCase();
}

function isEmptyStub(asset: Asset): boolean {
  return rightsConfidence(asset) === "empty_stub" || !asset.rights;
}

function pathStubStarted(asset: Asset): boolean {
  const cmc = asset.cmc;
  const path = asset.pathway_505b2;
  if (cmc && cmc.confidence && cmc.confidence !== "empty_stub") return true;
  if (path && path.confidence && path.confidence !== "empty_stub") return true;
  if (path?.rld_ref || path?.listed_drug_name || path?.listed_drug_ref) return true;
  if ((path?.exclusivity_windows || []).length) return true;
  if (path?.pathway && path.pathway !== "unknown") return true;
  return false;
}

function hasNumberedIp(asset: Asset): boolean {
  const families = asset.rights?.ip?.patent_families || [];
  const adjacent = Boolean(asset.rights?.modules?.asset_ip_desk?.adjacent_only);
  if (adjacent || asset.rights?.modules?.asset_ip_desk?.public_patent_null) return false;
  return families.some((family) => {
    const title = String(family.title || "").toLowerCase();
    if (title.includes("adjacent")) return false;
    return (family.publication_numbers || []).some((n) => /^(WO|US|EP|AU|CN|JP|CA|KR)/i.test(n));
  });
}

export function oppEligible(asset: Asset): boolean {
  if (isEmptyStub(asset)) return false;
  const desk = deskOf(asset);
  if (desk === "WALK_AWAY") return false;
  const optionable = Boolean(asset.optionable || asset.shortlist_ownable || asset.pre_pass?.optionable);
  const contingentNumbered = desk === "CONTINGENT" && hasNumberedIp(asset);
  const counselCapped = desk === "NEEDS_COUNSEL" && hasNumberedIp(asset);
  return (optionable || contingentNumbered || counselCapped) && pathStubStarted(asset);
}

function enrolmentCount(asset: Asset): number | null {
  const count = asset.enrolment?.count;
  return typeof count === "number" ? count : null;
}

function isLargeCap(asset: Asset): boolean {
  const name = norm(asset.sponsor_name || "");
  return QUEUE_RULES.large_cap_industry.some((token) => name.includes(norm(token)));
}

function namedNonGeneric(asset: Asset): boolean {
  const blob = assetBlob(asset);
  for (const rule of QUEUE_RULES.disregard) {
    if (rule.kind !== "pattern") continue;
    if ((rule.patterns || []).some((pat) => blob.includes(norm(pat)))) return false;
  }
  return (asset.interventions || []).some((item) => (item.name || "").trim().length >= 4);
}

function queueTier(asset: Asset): string {
  if (String(asset.sponsor_class || "").toUpperCase() === "INDUSTRY") {
    const status = String(asset.sponsor_status || "").toLowerCase();
    const thin = ["ceased", "restructured", "acquired", "unknown"].includes(status) || !isLargeCap(asset);
    return thin ? "thin_biotech" : "industry_single_grantor";
  }
  return namedNonGeneric(asset) ? "tt_named_asset" : "other";
}

export function disregardHit(asset: Asset): { code: string; note: string } | null {
  const desk = deskOf(asset);
  const status = String(asset.overall_status || "").toUpperCase();
  const count = enrolmentCount(asset);
  const codes = [
    ...(asset.walk_away_codes || []),
    ...(asset.pre_pass?.walk_away_codes || []),
    ...(asset.classification?.walk_away_codes || []),
  ];
  if (desk === "WALK_AWAY") return { code: "DESK_WALK_AWAY", note: "Locked WALK_AWAY." };
  if (status === "WITHDRAWN" || codes.includes("WALK_AWAY_WITHDRAWN")) {
    return { code: "WALK_AWAY_WITHDRAWN", note: "Withdrawn." };
  }
  if (count === 0 || codes.includes("WALK_AWAY_ZERO_ENROLMENT")) {
    return { code: "WALK_AWAY_ZERO_ENROLMENT", note: "0-enrolment." };
  }
  const blob = assetBlob(asset);
  for (const rule of QUEUE_RULES.disregard) {
    if (rule.kind !== "pattern") continue;
    const matched = (rule.patterns || []).find((pat) => blob.includes(norm(pat)));
    if (matched) return { code: rule.code, note: matched };
  }
  return null;
}

function scoreOf(asset: Asset): number {
  const n = asset.score?.score;
  return typeof n === "number" && Number.isFinite(n) ? n : 0;
}

const TIER_RANK: Record<string, number> = {
  industry_single_grantor: 0,
  thin_biotech: 1,
  tt_named_asset: 2,
  other: 3,
};

export function labelSnapshot(assets: Asset[], cap = QUEUE_RULES.cap): Map<string, LabelRow> {
  const limit = Math.max(30, Math.min(50, cap));
  const out = new Map<string, LabelRow>();
  const candidates: Asset[] = [];

  for (const asset of assets) {
    const key = asset.nct_id;
    if (oppEligible(asset)) {
      out.set(key, {
        label: LABEL_OPP,
        triage: "keep",
        note: "OPP is not a high score. Rights+path only.",
      });
      continue;
    }
    const hit = disregardHit(asset);
    if (hit) {
      out.set(key, {
        label: LABEL_TRIAGE,
        triage: "disregard",
        note: hit.note,
      });
      continue;
    }
    if (!isEmptyStub(asset)) {
      out.set(key, {
        label: LABEL_TRIAGE,
        triage: "keep",
        note: "Triage-keep. High score ≠ OPP.",
      });
      continue;
    }
    candidates.push(asset);
  }

  candidates.sort((a, b) => {
    const ta = TIER_RANK[queueTier(a)] ?? 9;
    const tb = TIER_RANK[queueTier(b)] ?? 9;
    if (ta !== tb) return ta - tb;
    return scoreOf(b) - scoreOf(a) || a.nct_id.localeCompare(b.nct_id);
  });

  candidates.forEach((asset, idx) => {
    if (idx < limit) {
      out.set(asset.nct_id, {
        label: LABEL_RIGHTS_QUEUE,
        triage: "keep",
        note: "Survived hard-kill disregard; rights empty / NOT OPTIONABLE.",
        queueTier: queueTier(asset),
      });
      return;
    }
    out.set(asset.nct_id, {
      label: LABEL_TRIAGE,
      triage: "keep",
      note: "Triage-keep. Overflow — not in the capped rights-fill queue.",
      queueTier: queueTier(asset),
    });
  });

  return out;
}

export function extractModelLabel(snapshot: {
  extract_model?: string | null;
  extract_mode?: string | null;
} | null): string {
  const explicit = snapshot?.extract_model || snapshot?.extract_mode;
  if (!explicit) return "mock";
  return explicit.toLowerCase().startsWith("mock") ? "mock" : explicit;
}

export function labelWord(row: LabelRow | undefined): string {
  if (!row) return "TRIAGE keep";
  if (row.label === LABEL_OPP) return "OPP";
  if (row.label === LABEL_RIGHTS_QUEUE) return "RIGHTS_QUEUE";
  return `TRIAGE ${row.triage}`;
}
