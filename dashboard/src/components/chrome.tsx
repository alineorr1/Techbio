import type { ReactNode } from "react";
import { Badge } from "./ui";
import { failureModeLabel } from "../lib/format";
import { hrefFor } from "../lib/hash";
import { cn } from "../lib/utils";

export const DILIGENCE_BANNER = "Non-buy · rights-unknown · inspectable triage";

export function DiligenceBanner() {
  return (
    <div className="sticky top-0 z-20 border-b border-line bg-raised">
      <p className="mx-auto max-w-6xl px-4 py-[var(--space-2)] font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-wine sm:px-6">
        {DILIGENCE_BANNER}
      </p>
    </div>
  );
}

export function Wordmark() {
  return (
    <a
      href={hrefFor({ name: "ranked" })}
      className="font-sans text-[15px] font-medium lowercase tracking-[-0.02em] text-ink no-underline"
    >
      we.are
    </a>
  );
}

export function Panel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={cn("rounded-none border border-line bg-panel p-0", className)}>{children}</section>;
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
    <header className="mb-[var(--space-5)] flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="kicker">{kicker}</p>
        <h1 className="mt-1 font-serif text-[28px] leading-tight tracking-[-0.025em] text-ink sm:text-[34px]">{title}</h1>
      </div>
      {children ? <div className="text-sm text-mute">{children}</div> : null}
    </header>
  );
}

export function FieldLabel({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("kicker block", className)}>{children}</span>;
}

export function FailureBadge({ mode }: { mode: string | null | undefined }) {
  const tone =
    mode === "safety"
      ? "terra"
      : mode === "efficacy_uninterpretable"
        ? "rose"
        : mode === "funding_or_sponsor"
          ? "wine"
          : mode === "recruitment"
            ? "champagne"
            : "muted";
  return <Badge tone={tone}>{failureModeLabel(mode)}</Badge>;
}

export function ScoreMark({
  score,
  className,
}: {
  score: number | null | undefined;
  className?: string;
}) {
  const text = score == null || Number.isNaN(score) ? "—" : score.toFixed(1);
  return (
    <span className={cn("font-serif text-[28px] leading-none tracking-tight text-wine", className)}>
      {text}
    </span>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-none border border-dashed border-line bg-raised px-4 py-6 text-sm text-mute">{children}</p>
  );
}
