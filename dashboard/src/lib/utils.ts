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

/** we.are chart series — wine first, never default Recharts blue. */
export const CHART = {
  wine: "#5C2430",
  rose: "#C17B7E",
  terra: "#B85C4A",
  champagne: "#E8D5C4",
  mucosa: "#A85A64",
  oxblood: "#3D1822",
  ink: "#0A0A0A",
  ivory: "#F5F3EE",
  ground: "#F5F3EE",
  cream: "#F3EBE3",
  hairline: "rgba(92, 36, 48, 0.16)",
  mute: "#6E565C",
} as const;

export const CHART_SERIES = [
  CHART.wine,
  CHART.rose,
  CHART.terra,
  CHART.champagne,
  CHART.mucosa,
  CHART.oxblood,
] as const;
