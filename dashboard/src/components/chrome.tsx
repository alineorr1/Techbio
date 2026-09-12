import type { ReactNode } from "react";
import { Badge } from "./ui";
import { failureModeLabel } from "../lib/format";
import { cn } from "../lib/utils";

export function Panel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("border border-wine/16 bg-ivory", className)}>{children}</section>
  );
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
        <p className="kicker">{kicker}</p>
        <h1 className="mt-1 text-[28px] leading-tight sm:text-[34px]">{title}</h1>
      </div>
      {children ? <div className="text-sm text-mute">{children}</div> : null}
    </header>
  );
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
    <p className="border border-dashed border-wine/20 bg-cream/60 px-4 py-6 text-sm text-mute">{children}</p>
  );
}
