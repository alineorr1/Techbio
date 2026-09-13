import { useMemo, useState } from "react";
import { FailureBadge, FieldLabel, PageHeader, ScoreMark, StatusWord } from "../components/chrome";
import { gateSurface, prettyPhase } from "../lib/format";
import { labelSnapshot, labelWord } from "../lib/labels";
import { hrefFor } from "../lib/hash";
import type { Asset, FailureMode, Snapshot } from "../lib/types";

const MODES: FailureMode[] = [
  "funding_or_sponsor",
  "recruitment",
  "never_started",
  "efficacy_uninterpretable",
  "efficacy",
  "safety",
  "unclear",
];

function matchesQuery(asset: Asset, q: string): boolean {
  if (!q) return true;
  const hay = [
    asset.nct_id,
    asset.brief_title,
    asset.official_title,
    asset.sponsor_name,
    asset.indication,
    asset.indication_label,
    asset.why_stopped,
    ...(asset.interventions || []).map((i) => i.name),
    ...(asset.targets || []).map((t) => `${t.name} ${t.gene_symbol ?? ""}`),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return hay.includes(q);
}

function padRank(n: number): string {
  return String(n).padStart(2, "0");
}

export function RankedView({ snapshot }: { snapshot: Snapshot }) {
  const [query, setQuery] = useState("");
  const [indication, setIndication] = useState("all");
  const [mode, setMode] = useState("all");

  const indications = useMemo(() => {
    const keys = new Set<string>();
    for (const asset of snapshot.assets) keys.add(asset.indication || "other");
    return [...keys].sort();
  }, [snapshot.assets]);

  const labels = useMemo(() => labelSnapshot(snapshot.assets), [snapshot.assets]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return snapshot.assets.filter((asset) => {
      if (indication !== "all" && (asset.indication || "other") !== indication) return false;
      if (mode !== "all" && asset.classification?.failure_mode !== mode) return false;
      return matchesQuery(asset, q);
    });
  }, [snapshot.assets, query, indication, mode]);

  return (
    <div>
      <PageHeader kicker="ranked" title="Assets by score">
        <p>
          {rows.length} of {snapshot.assets.length}
          {snapshot.counts?.n_raw != null ? ` · ${snapshot.counts.n_raw} registry rows` : null}
          {" · TRIAGE / RIGHTS_QUEUE / OPP — OPP is not a high score"}
        </p>
      </PageHeader>

      <div className="mb-12 flex flex-col gap-4 sm:flex-row sm:items-end sm:gap-8">
        <label htmlFor="ranked-search" className="block min-w-0 flex-1">
          <FieldLabel>Search</FieldLabel>
          <input
            id="ranked-search"
            name="q"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="NCT, title, sponsor, target"
            className="mt-2 h-8 w-full border-0 border-b border-line px-0 text-sm"
          />
        </label>
        <label htmlFor="ranked-indication" className="block sm:w-44">
          <FieldLabel>Indication</FieldLabel>
          <select
            id="ranked-indication"
            name="indication"
            value={indication}
            onChange={(e) => setIndication(e.target.value)}
            className="mt-2 h-8 w-full border-0 border-b border-line px-0 text-sm"
          >
            <option value="all">All indications</option>
            {indications.map((key) => (
              <option key={key} value={key}>
                {snapshot.indications[key]?.label || key}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="ranked-mode" className="block sm:w-48">
          <FieldLabel>Failure mode</FieldLabel>
          <select
            id="ranked-mode"
            name="failure_mode"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            className="mt-2 h-8 w-full border-0 border-b border-line px-0 text-sm"
          >
            <option value="all">All modes</option>
            {MODES.map((m) => (
              <option key={m} value={m}>
                {m.replaceAll("_", "-")}
              </option>
            ))}
          </select>
        </label>
      </div>

      <ol className="list-none p-0">
        {rows.map((asset, idx) => {
          const title = asset.brief_title || asset.official_title || asset.nct_id;
          const ruleB = asset.score?.rule_b_organon_guard;
          const ruleA = asset.score?.rule_a_safety_cap;
          return (
            <li key={asset.nct_id} className="border-t border-line py-8 first:border-t-0">
              <article className="grid grid-cols-[auto_1fr] items-start gap-x-6 gap-y-2 sm:gap-x-10">
                <p className="font-serif text-3xl font-medium tabular-nums leading-none tracking-tight">
                  {padRank(idx + 1)}
                </p>
                <div className="min-w-0">
                  <h2 className="text-xl font-medium leading-snug tracking-tight">
                    <a
                      href={hrefFor({ name: "asset", nct: asset.nct_id })}
                      className="text-ink no-underline hover:underline"
                    >
                      {title}
                    </a>
                  </h2>
                  <p className="mt-3 font-mono text-[11px] text-mute">
                    {asset.nct_id}
                    {" · "}
                    <ScoreMark score={asset.score?.score} className="text-[11px] text-mute" />
                    {" · "}
                    {prettyPhase(asset.phase).toLowerCase()}
                    {asset.indication_label || asset.indication
                      ? ` · ${(asset.indication_label || asset.indication).toLowerCase()}`
                      : null}
                    {asset.sponsor_name ? ` · ${asset.sponsor_name}` : null}
                  </p>
                  <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                    <FailureBadge mode={asset.classification?.failure_mode} />
                    <StatusWord>{gateSurface(asset)}</StatusWord>
                    <StatusWord>{labelWord(labels.get(asset.nct_id))}</StatusWord>
                    {ruleA ? <StatusWord>rule-a</StatusWord> : null}
                    {ruleB ? <StatusWord>rule-b</StatusWord> : null}
                    {!ruleA && !ruleB ? <StatusWord>non-buy</StatusWord> : null}
                  </p>
                </div>
              </article>
            </li>
          );
        })}
      </ol>
      {rows.length === 0 ? (
        <p className="border-t border-line py-12 text-sm text-mute">No assets match these filters.</p>
      ) : null}
    </div>
  );
}
