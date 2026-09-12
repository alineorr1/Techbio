import { EmptyNote, FailureBadge, PageHeader, Panel, ScoreMark } from "../components/chrome";
import { asNumber, asString, fmtScore } from "../lib/format";
import { hrefFor } from "../lib/hash";
import type { Snapshot } from "../lib/types";

function asRows(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((row): row is Record<string, unknown> => !!row && typeof row === "object");
}

export function WeeklyView({ snapshot }: { snapshot: Snapshot }) {
  const weekly = snapshot.weekly;
  if (!weekly) {
    return (
      <div>
        <PageHeader kicker="Weekly" title="Change report" />
        <EmptyNote>This snapshot has no weekly block. Re-export with python -m src.serve after a second run.</EmptyNote>
      </div>
    );
  }

  const incoming = asRows(weekly.new_in_top20);
  const moved = asRows(weekly.moved_over_10pts);
  const note = weekly.note;

  return (
    <div>
      <PageHeader kicker="Weekly" title="What moved since last snapshot">
        <p>
          {weekly.previous_snapshot
            ? `Compared with ${String(weekly.previous_snapshot).split("/").pop()}`
            : "Baseline snapshot — no prior file to diff."}
        </p>
      </PageHeader>

      {note ? <EmptyNote>{note}</EmptyNote> : null}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Panel className="p-4">
          <h2 className="text-[20px]">New in the top 20</h2>
          <p className="mt-1 text-[12px] text-mute">{incoming.length} assets entered the top twenty.</p>
          <ul className="mt-4 divide-y divide-line">
            {incoming.map((row) => {
              const nct = asString(row.nct_id) || "unknown";
              return (
                <li key={nct} className="py-3">
                  <a href={hrefFor({ name: "asset", nct })}>
                    <span className="font-mono text-xs">{nct}</span>
                    <span className="mt-0.5 block">{asString(row.title) || nct}</span>
                  </a>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <ScoreMark score={asNumber(row.score)} className="text-[18px]" />
                    <FailureBadge mode={asString(row.failure_mode)} />
                  </div>
                  {asString(row.why) ? <p className="mt-2 font-mono text-[11px] text-mute">{asString(row.why)}</p> : null}
                </li>
              );
            })}
          </ul>
          {incoming.length === 0 ? <p className="mt-4 text-sm text-mute">None this week.</p> : null}
        </Panel>

        <Panel className="p-4">
          <h2 className="text-[20px]">Moved more than 10 points</h2>
          <p className="mt-1 text-[12px] text-mute">{moved.length} assets with |Δ| &gt; 10.</p>
          <ul className="mt-4 divide-y divide-line">
            {moved.map((row) => {
              const nct = asString(row.nct_id) || "unknown";
              const delta = asNumber(row.delta);
              return (
                <li key={nct} className="py-3">
                  <a href={hrefFor({ name: "asset", nct })}>
                    <span className="font-mono text-xs">{nct}</span>
                    <span className="mt-0.5 block">{asString(row.title) || nct}</span>
                  </a>
                  <p className="mt-1.5 text-sm">
                    <span>
                      {delta == null ? "—" : `${delta > 0 ? "+" : ""}${fmtScore(delta)}`}
                    </span>
                    <span className="text-mute">
                      {" "}
                      ({fmtScore(asNumber(row.from))} → {fmtScore(asNumber(row.to))})
                    </span>
                  </p>
                  {row.why != null ? (
                    <p className="mt-1 font-mono text-[11px] text-mute">
                      {Array.isArray(row.why) ? row.why.join("; ") : String(row.why)}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {moved.length === 0 ? <p className="mt-4 text-sm text-mute">No swings above the 10-point threshold.</p> : null}
        </Panel>
      </div>
    </div>
  );
}
