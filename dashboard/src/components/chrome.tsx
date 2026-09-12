import type { ReactNode } from "react";
import { Badge } from "./ui";
import { failureModeLabel } from "../lib/format";
import { cn } from "../lib/utils";

/** Structural wrappers only. Brand tokens land later from weare-brand-system.md. */

export function Panel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={cn("border border-line p-0", className)}>{children}</section>;
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
    <header className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-sm text-mute">{kicker}</p>
        <h1 className="mt-1 text-2xl font-medium">{title}</h1>
      </div>
      {children ? <div className="text-sm text-mute">{children}</div> : null}
    </header>
  );
}

export function FieldLabel({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("block text-sm text-mute", className)}>{children}</span>;
}

export function FailureBadge({ mode }: { mode: string | null | undefined }) {
  return <Badge tone="muted">{failureModeLabel(mode)}</Badge>;
}

export function ScoreMark({
  score,
  className,
}: {
  score: number | null | undefined;
  className?: string;
}) {
  const text = score == null || Number.isNaN(score) ? "—" : score.toFixed(1);
  return <span className={cn("font-mono text-xl tabular-nums", className)}>{text}</span>;
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="border border-dashed border-line px-4 py-6 text-sm text-mute">{children}</p>;
}
