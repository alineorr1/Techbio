import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtPct(n: number | null | undefined, digits = 0): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

export function sourceHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Sparse mono chart series — no tissue rainbow, no wine fills. */
export const CHART = {
  ink: "#0A0A0A",
  mute: "#6B6B6B",
  ground: "#FFFFFF",
  hairline: "rgba(10, 10, 10, 0.12)",
  track: "#F0F0F0",
  mid: "#8A8A8A",
  faint: "#C8C8C8",
} as const;

export const CHART_SERIES = [
  CHART.ink,
  "#2E2E2E",
  "#4A4A4A",
  "#6B6B6B",
  "#8A8A8A",
  "#B0B0B0",
] as const;
