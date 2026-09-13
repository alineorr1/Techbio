import type { ReactNode } from "react";
import { failureModeWord } from "../lib/format";
import { cn } from "../lib/utils";

export function Panel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={cn("border-t border-line p-0", className)}>{children}</section>;
}

export function PageHeader({
  kicker,
  title,
  children,
}: {
  kicker: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <header className="mb-10 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="kicker">{kicker}</p>
        <h1 className="mt-2 font-serif text-[2rem] font-medium leading-none tracking-tight">{title}</h1>
      </div>
      {children ? <div className="text-sm text-mute">{children}</div> : null}
    </header>
  );
}

export function FieldLabel({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("kicker", className)}>{children}</span>;
}

export function StatusWord({ children }: { children: ReactNode }) {
  return <span className="font-mono text-[11px] text-mute">{children}</span>;
}

export function FailureBadge({ mode }: { mode: string | null | undefined }) {
  return <StatusWord>{failureModeWord(mode)}</StatusWord>;
}

export function ScoreMark({
  score,
  className,
}: {
  score: number | null | undefined;
  className?: string;
}) {
  const text = score == null || Number.isNaN(score) ? "—" : score.toFixed(1);
  return <span className={cn("font-mono text-sm tabular-nums text-ink", className)}>{text}</span>;
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="border border-dashed border-line px-4 py-6 text-sm text-mute">{children}</p>;
}

export function DiligenceBanner() {
  return (
    <p className="font-mono text-[11px] tracking-[0.04em] text-mute">
      non-buy · rights-unknown · honest
    </p>
  );
}
