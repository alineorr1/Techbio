import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyNote, PageHeader, Panel } from "../components/chrome";
import type { ReactNode } from "react";
import { failureModeLabel, populationLabel } from "../lib/format";
import { CHART, CHART_SERIES, fmtPct } from "../lib/utils";
import type { Snapshot } from "../lib/types";

const tooltipStyle = {
  background: CHART.ivory,
  border: `1px solid ${CHART.hairline}`,
  borderRadius: 0,
  color: CHART.ink,
  fontSize: 12,
};

const MODES = [
  "funding_or_sponsor",
  "recruitment",
  "efficacy_uninterpretable",
  "efficacy",
  "safety",
  "unclear",
] as const;

export function LandscapeView({ snapshot }: { snapshot: Snapshot }) {
  const landscape = snapshot.landscape;
  if (!landscape) {
    return (
      <div>
        <PageHeader kicker="Landscape" title="Corpus shape" />
        <EmptyNote>This snapshot has no landscape block. Re-export with python -m src.serve.</EmptyNote>
      </div>
    );
  }

  const histogram = (landscape.score_histogram || []).map((bin) => ({
    label: `${bin.bin_start}–${bin.bin_end}`,
    count: bin.count,
  }));

  const capture = Object.entries(landscape.population_capture_rates || {}).map(([field, row]) => ({
    field: populationLabel(field),
    rate: row.rate,
    label: `${row.captured}/${row.n}`,
  }));

  const byYear = Object.entries(landscape.assets_by_year_stopped || {})
    .filter(([year]) => year && year !== "unknown")
    .map(([year, count]) => ({ year, count }));

  const stacked = Object.entries(landscape.failure_modes_by_indication || {}).map(([key, modes]) => {
    const row: Record<string, string | number> = {
      indication: snapshot.indications[key]?.label || key,
    };
    for (const mode of MODES) row[mode] = modes[mode] || 0;
    return row;
  });

  return (
    <div>
      <PageHeader kicker="Landscape" title="How the corpus is shaped">
        <p>
          {landscape.n_assets} assets · mean female-specific capture{" "}
          <span className="font-serif text-ink">{fmtPct(landscape.mean_female_specific_capture, 0)}</span>
        </p>
      </PageHeader>

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Stat label="Scored assets" value={String(landscape.n_assets)} />
        <Stat
          label="Mean population capture"
          value={fmtPct(landscape.mean_female_specific_capture, 0)}
          hint="Eight female-specific variables"
        />
        <Stat
          label="Severity / prior-Rx holes"
          value={`${fmtPct(landscape.population_capture_rates.disease_severity_stratified?.rate, 0)} / ${fmtPct(landscape.population_capture_rates.prior_treatment_history_specified?.rate, 0)}`}
          hint="Stage stated · prior treatment stated"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartPanel title="Score histogram" hint="Rule B caps most assets at 60 without pre-trial mechanism evidence.">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={histogram} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={CHART.hairline} vertical={false} />
              <XAxis dataKey="label" tick={{ fill: CHART.mute, fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fill: CHART.mute, fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(92,36,48,0.06)" }} />
              <Bar dataKey="count" fill={CHART.wine} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Failure modes by indication">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={stacked} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={CHART.hairline} vertical={false} />
              <XAxis dataKey="indication" tick={{ fill: CHART.mute, fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fill: CHART.mute, fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
              <Tooltip
                contentStyle={tooltipStyle}
                cursor={{ fill: "rgba(92,36,48,0.06)" }}
                formatter={(value, name) => [value, failureModeLabel(String(name))]}
              />
              {MODES.map((mode, i) => (
                <Bar key={mode} dataKey={mode} stackId="m" fill={CHART_SERIES[i % CHART_SERIES.length]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Population capture rates" hint="Inverted in scoring: missing variables raise the population component.">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={capture} layout="vertical" margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
              <CartesianGrid stroke={CHART.hairline} horizontal={false} />
              <XAxis
                type="number"
                domain={[0, 1]}
                tickFormatter={(v) => `${Math.round(Number(v) * 100)}%`}
                tick={{ fill: CHART.mute, fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="field"
                width={148}
                tick={{ fill: CHART.ink, fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(value) => [fmtPct(typeof value === "number" ? value : null, 0), "Captured"]}
              />
              <Bar dataKey="rate" fill={CHART.rose} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Assets by year stopped">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={byYear} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={CHART.hairline} vertical={false} />
              <XAxis dataKey="year" tick={{ fill: CHART.mute, fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fill: CHART.mute, fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(92,36,48,0.06)" }} />
              <Bar dataKey="count" fill={CHART.oxblood} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>
      </div>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Panel className="p-4">
      <p className="kicker">{label}</p>
      <p className="mt-2 font-serif text-[28px] leading-none text-wine">{value}</p>
      {hint ? <p className="mt-2 text-[12px] text-mute">{hint}</p> : null}
    </Panel>
  );
}

function ChartPanel({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <Panel className="p-4">
      <h2 className="text-[20px]">{title}</h2>
      {hint ? <p className="mt-1 text-[12px] text-mute">{hint}</p> : null}
      <div className="mt-4">{children}</div>
    </Panel>
  );
}
