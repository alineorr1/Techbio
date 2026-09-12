import { useMemo, useState } from "react";
import { Badge, Button } from "../components/ui";
import { EmptyNote, FailureBadge, FieldLabel, PageHeader, Panel, ScoreMark } from "../components/chrome";
import { asNumber, asString, componentLabel, populationLabel, prettyPhase } from "../lib/format";
import { hrefFor } from "../lib/hash";
import { cn, sourceHost } from "../lib/utils";
import type { Asset, Snapshot } from "../lib/types";

const FEEDBACK_KEY = "wh-triage-feedback.v1";

type Verdict = "agree" | "too_high" | "too_low" | "wrong_failure_mode";

type FeedbackRow = {
  v: 1;
  nct_id: string;
  at: string;
  verdict: Verdict;
  note: string;
};

function loadFeedback(): FeedbackRow[] {
  try {
    const raw = localStorage.getItem(FEEDBACK_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as FeedbackRow[]) : [];
  } catch {
    return [];
  }
}

function saveFeedback(rows: FeedbackRow[]): void {
  localStorage.setItem(FEEDBACK_KEY, JSON.stringify(rows));
}

export function AssetView({ snapshot, nct }: { snapshot: Snapshot; nct: string }) {
  const asset = useMemo(
    () => snapshot.assets.find((row) => row.nct_id.toUpperCase() === nct.toUpperCase()),
    [snapshot.assets, nct],
  );

  if (!asset) {
    return (
      <div>
        <PageHeader kicker="Asset" title={nct} />
        <EmptyNote>
          {nct} is not in this snapshot.{" "}
          <a href={hrefFor({ name: "ranked" })}>Return to the ranked list</a>.
        </EmptyNote>
      </div>
    );
  }

  const title = asset.brief_title || asset.official_title || asset.nct_id;
  const [lo, hi] = asset.score?.confidence_interval || [];
  const weights = asset.score?.weights || {};
  const components = asset.score?.components;
  const pretrial = asset.score?.pretrial_mechanism;
  const checklist = asset.population_checklist || [];
  const captured = checklist.filter((item) => item.captured).length;

  return (
    <div>
      <p className="mb-3">
        <a href={hrefFor({ name: "ranked" })} className="text-[11px] uppercase tracking-[0.16em] no-underline">
          ← Ranked list
        </a>
      </p>
      <PageHeader kicker={asset.nct_id} title={title}>
        <p>
          {asset.indication_label || asset.indication}
          {asset.sponsor_name ? ` · ${asset.sponsor_name}` : ""}
          {asset.overall_status ? ` · ${asset.overall_status}` : ""}
        </p>
      </PageHeader>

      <div className="mb-[var(--space-5)] grid gap-[var(--space-4)] lg:grid-cols-[220px_1fr]">
        <Panel className="p-4">
          <FieldLabel>Triage score</FieldLabel>
          <ScoreMark score={asset.score?.score} className="mt-2 block text-[44px]" />
          <p className="mt-2 font-mono text-[11px] text-mute">
            CI {lo ?? "—"}–{hi ?? "—"}
            {asset.score?.uncertainty?.flag === "HIGH_UNCERTAINTY" ? " · high uncertainty" : ""}
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <FailureBadge mode={asset.classification?.failure_mode} />
            {asset.score?.rule_a_safety_cap ? <Badge tone="terra">Rule A</Badge> : null}
            {asset.score?.rule_b_organon_guard ? <Badge tone="wine">Rule B</Badge> : null}
          </div>
        </Panel>
        <Panel className="p-4">
          <FieldLabel>Arithmetic</FieldLabel>
          <p className="mt-2 font-mono text-[12px] leading-relaxed text-ink">{asset.score?.arithmetic || "—"}</p>
          {(asset.score?.caps_applied || []).length > 0 ? (
            <ul className="mt-3 space-y-1 text-[13px] text-wine">
              {asset.score.caps_applied.map((cap) => (
                <li key={cap}>{cap}</li>
              ))}
            </ul>
          ) : null}
          <p className="mt-3 text-[13px] text-mute">{asset.classification?.notes || asset.classification?.rule_fired}</p>
        </Panel>
      </div>

      <div className="grid gap-[var(--space-5)] lg:grid-cols-2">
        <Panel className="p-4">
          <h2 className="text-[20px]">Score breakdown</h2>
          <ul className="mt-4 space-y-4">
            {components
              ? Object.entries(components).map(([key, comp]) => (
                  <li key={key}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-[13px] text-ink">{componentLabel(key)}</span>
                      <span className="font-mono text-[12px] text-mute">
                        {comp.value.toFixed(1)} × {weights[key] ?? "—"}
                      </span>
                    </div>
                    <div className="mt-1.5 h-1.5 bg-champagne">
                      <div className="h-full bg-wine" style={{ width: `${Math.max(0, Math.min(100, comp.value))}%` }} />
                    </div>
                    {comp.note ? <p className="mt-1.5 text-[12px] text-mute">{comp.note}</p> : null}
                  </li>
                ))
              : null}
          </ul>
        </Panel>

        <Panel className="p-4">
          <h2 className="text-[20px]">Organon Rule B / pre-trial mechanism</h2>
          <p className="mt-2 text-[13px] text-mute">
            Scores cannot exceed 60 unless independent mechanism evidence predates the trial start.
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-[13px]">
            <Fact label="Trial start" value={pretrial?.trial_start || "—"} />
            <Fact label="Pre-trial evidence" value={pretrial?.has_pretrial_evidence ? "Yes" : "None"} />
            <Fact label="Pre-trial items" value={String(pretrial?.pretrial_count ?? 0)} />
            <Fact label="Post-trial items" value={String(pretrial?.posttrial_count ?? 0)} />
          </dl>
          {asset.score?.rule_b_organon_guard ? (
            <p className="mt-4 border border-line bg-raised px-3 py-2 text-[13px] text-wine">
              Rule B is active: no pre-trial independent mechanism evidence in this snapshot.
            </p>
          ) : (
            <p className="mt-4 text-[13px] text-ink">Pre-trial evidence is present; the Organon guard does not cap this score.</p>
          )}
          <EvidenceList heading="Pre-trial" items={pretrial?.pretrial || []} />
          <EvidenceList heading="Post-trial" items={pretrial?.posttrial || []} />
        </Panel>

        <Panel className="p-4">
          <h2 className="text-[20px]">Population checklist</h2>
          <p className="mt-1 text-[12px] text-mute">
            {captured} of {checklist.length || 8} female-specific variables captured. Missing variables raise the
            population component because the trial could not have falsified the biology.
          </p>
          <ul className="mt-4 divide-y divide-line">
            {checklist.map((item) => (
              <li key={item.field} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span>{populationLabel(item.field)}</span>
                <span
                  className={cn(
                    "font-mono text-[10px] uppercase tracking-[0.14em]",
                    item.captured ? "text-wine" : "text-terra",
                  )}
                >
                  {item.captured ? "Captured" : "Missing"}
                </span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel className="p-4">
          <h2 className="text-[20px]">Record</h2>
          <dl className="mt-4 grid gap-3 text-[13px] sm:grid-cols-2">
            <Fact label="Phase" value={prettyPhase(asset.phase)} />
            <Fact label="Status" value={asset.overall_status || "—"} />
            <Fact label="Sponsor" value={`${asset.sponsor_name || "—"} (${asset.sponsor_status || "unknown"})`} />
            <Fact label="Enrolment" value={enrolmentLabel(asset)} />
            <Fact label="Started" value={asset.start_date || "—"} />
            <Fact label="Stopped / completed" value={asset.completion_date || asset.primary_completion_date || "—"} />
          </dl>
          <p className="mt-4 text-[13px] text-ink">
            <FieldLabel className="mb-1">Why stopped</FieldLabel>
            {asset.why_stopped || asset.extraction?.stop_reason_raw || "Not stated in the registry record."}
          </p>
          {asset.extraction?.stop_reason_evidence ? (
            <blockquote className="mt-3 border-l-2 border-wine/30 pl-3 font-serif text-[15px] italic text-ink">
              {asset.extraction.stop_reason_evidence}
            </blockquote>
          ) : null}
          <p className="mt-4 text-sm text-mute">
            <FieldLabel className="mb-1">Mechanism</FieldLabel>
            {asset.mechanism_summary || asset.extraction?.mechanism_summary || "—"}
          </p>
          {(asset.targets || []).length > 0 ? (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {asset.targets.map((t) => (
                <li key={`${t.name}-${t.gene_symbol}`}>
                  <Badge tone="champagne">
                    {t.name}
                    {t.gene_symbol ? ` (${t.gene_symbol})` : ""}
                  </Badge>
                </li>
              ))}
            </ul>
          ) : null}
        </Panel>

        <Panel className="p-4">
          <h2 className="text-[20px]">Links</h2>
          <ul className="mt-3 space-y-2">
            {(asset.links || []).map((link) => (
              <li key={link.url}>
                <a href={link.url} target="_blank" rel="noreferrer">
                  {link.label}
                </a>
                <span className="ml-2 font-mono text-[11px] text-mute">{sourceHost(link.url)}</span>
              </li>
            ))}
          </ul>
          <h3 className="kicker mt-6">On-disk sources</h3>
          <ul className="mt-2 space-y-1 font-mono text-[11px] text-mute">
            {Object.entries(asset.sources || {}).map(([key, path]) => (
              <li key={key}>
                {key}: {path}
              </li>
            ))}
          </ul>
        </Panel>

        <FeedbackPanel nct={asset.nct_id} />
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="kicker">{label}</dt>
      <dd className="mt-1 text-ink">{value}</dd>
    </div>
  );
}

function enrolmentLabel(asset: Asset): string {
  const count = asset.enrolment?.count;
  const type = asset.enrolment?.type;
  if (count == null) return "—";
  return type ? `${count} (${type.toLowerCase()})` : String(count);
}

function EvidenceList({ heading, items }: { heading: string; items: Array<Record<string, unknown>> }) {
  if (!items.length) return null;
  return (
    <div className="mt-4">
      <p className="kicker">{heading}</p>
      <ul className="mt-2 space-y-2">
        {items.slice(0, 8).map((item, idx) => {
          const label =
            asString(item.label) ||
            asString(item.title) ||
            asString(item.datatype) ||
            asString(item.source) ||
            `Item ${idx + 1}`;
          const year = asString(item.publication_year) || asString(item.evidence_year) || asNumber(item.publication_year);
          const url = asString(item.url);
          return (
            <li key={`${label}-${idx}`} className="text-[13px]">
              {url ? (
                <a href={url} target="_blank" rel="noreferrer">
                  {label}
                </a>
              ) : (
                label
              )}
              {year != null ? <span className="ml-2 text-mute">{String(year)}</span> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function FeedbackPanel({ nct }: { nct: string }) {
  const [verdict, setVerdict] = useState<Verdict>("agree");
  const [note, setNote] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [existing, setExisting] = useState<FeedbackRow[]>(() =>
    loadFeedback().filter((row) => row.nct_id === nct),
  );

  function persist() {
    const row: FeedbackRow = {
      v: 1,
      nct_id: nct,
      at: new Date().toISOString(),
      verdict,
      note: note.trim(),
    };
    const next = [...loadFeedback(), row];
    saveFeedback(next);
    setExisting(next.filter((item) => item.nct_id === nct));
    const jsonl = next.map((item) => JSON.stringify(item)).join("\n");
    void navigator.clipboard.writeText(jsonl).then(
      () => setStatus("Saved locally and copied JSONL to the clipboard."),
      () => setStatus("Saved locally. Clipboard copy was blocked."),
    );
    setNote("");
  }

  return (
    <Panel className="p-4">
      <h2 className="text-[20px]">Reviewer feedback</h2>
      <p className="mt-1 text-[12px] text-mute">
        Stays in this browser (localStorage) and copies JSONL to the clipboard. Nothing is posted to a server.
      </p>
      <label htmlFor="feedback-verdict" className="mt-4 block">
        <FieldLabel>Verdict</FieldLabel>
        <select
          id="feedback-verdict"
          name="verdict"
          value={verdict}
          onChange={(e) => setVerdict(e.target.value as Verdict)}
          className="mt-1.5 h-9 w-full rounded-none border border-line bg-cream px-2 font-sans text-[13px] text-ink"
        >
          <option value="agree">Agree with score</option>
          <option value="too_high">Score too high</option>
          <option value="too_low">Score too low</option>
          <option value="wrong_failure_mode">Wrong failure mode</option>
        </select>
      </label>
      <label htmlFor="feedback-note" className="mt-3 block">
        <FieldLabel>Note</FieldLabel>
        <textarea
          id="feedback-note"
          name="note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          className="mt-1.5 w-full rounded-none border border-line bg-cream px-2.5 py-2 font-sans text-[13px] text-ink"
        />
      </label>
      <div className="mt-3">
        <Button type="button" size="sm" onClick={persist}>
          Save + copy JSONL
        </Button>
      </div>
      {status ? <p className="mt-2 text-[12px] text-wine">{status}</p> : null}
      {existing.length > 0 ? (
        <p className="mt-3 text-[12px] text-mute">
          {existing.length} local note{existing.length === 1 ? "" : "s"} on this asset
          {existing[existing.length - 1]?.verdict ? ` · last: ${existing[existing.length - 1].verdict}` : ""}.
        </p>
      ) : null}
    </Panel>
  );
}
