import { useMemo, useState } from "react";
import { FailureBadge, FieldLabel, PageHeader, Panel, ScoreMark } from "../components/chrome";
import { prettyPhase } from "../lib/format";
import { hrefFor } from "../lib/hash";
import type { Asset, FailureMode, Snapshot } from "../lib/types";

const MODES: FailureMode[] = [
  "funding_or_sponsor",
  "recruitment",
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

export function RankedView({ snapshot }: { snapshot: Snapshot }) {
  const [query, setQuery] = useState("");
  const [indication, setIndication] = useState("all");
  const [mode, setMode] = useState("all");

  const indications = useMemo(() => {
    const keys = new Set<string>();
    for (const asset of snapshot.assets) keys.add(asset.indication || "other");
    return [...keys].sort();
  }, [snapshot.assets]);

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
      <PageHeader kicker="Ranked" title="Assets by score">
        <p>
          {rows.length} of {snapshot.assets.length} assets
          {snapshot.counts?.n_raw != null ? ` · ${snapshot.counts.n_raw} registry rows` : null}
        </p>
      </PageHeader>

      <Panel className="mb-[var(--space-5)] p-3 sm:p-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <label htmlFor="ranked-search" className="block">
            <FieldLabel>Search</FieldLabel>
            <input
              id="ranked-search"
              name="q"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="NCT, title, sponsor, target"
              className="mt-1.5 h-9 w-full rounded-none border border-line bg-cream px-2.5 font-sans text-[13px] text-ink"
            />
          </label>
          <label htmlFor="ranked-indication" className="block">
            <FieldLabel>Indication</FieldLabel>
            <select
              id="ranked-indication"
              name="indication"
              value={indication}
              onChange={(e) => setIndication(e.target.value)}
              className="mt-1.5 h-9 w-full rounded-none border border-line bg-cream px-2 font-sans text-[13px] text-ink"
            >
              <option value="all">All indications</option>
              {indications.map((key) => (
                <option key={key} value={key}>
                  {snapshot.indications[key]?.label || key}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="ranked-mode" className="block">
            <FieldLabel>Failure mode</FieldLabel>
            <select
              id="ranked-mode"
              name="failure_mode"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="mt-1.5 h-9 w-full rounded-none border border-line bg-cream px-2 font-sans text-[13px] text-ink"
            >
              <option value="all">All modes</option>
              {MODES.map((m) => (
                <option key={m} value={m}>
                  {m.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Panel>

      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-left">
            <caption className="sr-only">Assets ranked by triage score</caption>
            <thead>
              <tr className="border-b border-line text-left text-[10px] uppercase tracking-[0.16em] text-mute">
                <th scope="col" className="px-3 py-2.5 font-medium">
                  #
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium">
                  Score
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium">
                  Asset
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium">
                  Mode
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium">
                  Phase
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium">
                  Guard
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((asset, idx) => {
                const title = asset.brief_title || asset.official_title || asset.nct_id;
                const ruleB = asset.score?.rule_b_organon_guard;
                const ruleA = asset.score?.rule_a_safety_cap;
                return (
                  <tr key={asset.nct_id} className="border-b border-line last:border-0 hover:bg-champagne/35">
                    <td className="px-3 py-3 align-top font-mono text-xs text-mute">{idx + 1}</td>
                    <td className="px-3 py-3 align-top">
                      <ScoreMark score={asset.score?.score} className="text-[22px]" />
                    </td>
                    <td className="px-3 py-3 align-top">
                      <a href={hrefFor({ name: "asset", nct: asset.nct_id })} className="block no-underline">
                        <span className="font-mono text-[11px] text-wine">{asset.nct_id}</span>
                        <span className="mt-0.5 block font-serif text-[16px] leading-snug text-ink">{title}</span>
                      </a>
                      <p className="mt-1 text-[12px] text-mute">
                        {asset.indication_label || asset.indication}
                        {asset.sponsor_name ? ` · ${asset.sponsor_name}` : ""}
                      </p>
                    </td>
                    <td className="px-3 py-3 align-top">
                      <FailureBadge mode={asset.classification?.failure_mode} />
                    </td>
                    <td className="px-3 py-3 align-top text-[12px] text-mute">{prettyPhase(asset.phase)}</td>
                    <td className="px-3 py-3 align-top text-[11px] uppercase tracking-[0.12em] text-mute">
                      {ruleA ? <span className="text-terra">Rule A</span> : null}
                      {ruleA && ruleB ? " · " : null}
                      {ruleB ? <span className="text-wine">Rule B</span> : null}
                      {!ruleA && !ruleB ? "—" : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {rows.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-mute">No assets match these filters.</p>
        ) : null}
      </Panel>
    </div>
  );
}
