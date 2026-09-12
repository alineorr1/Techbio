import { lazy, Suspense, useEffect, useState } from "react";
import { DiligenceBanner, EmptyNote, Wordmark } from "./components/chrome";
import { hrefFor, parseHash, type Route } from "./lib/hash";
import type { Snapshot } from "./lib/types";
import { cn } from "./lib/utils";
import { AssetView } from "./views/AssetView";
import { RankedView } from "./views/RankedView";
import { WeeklyView } from "./views/WeeklyView";

const LandscapeView = lazy(async () => {
  const mod = await import("./views/LandscapeView");
  return { default: mod.LandscapeView };
});

function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash());

  useEffect(() => {
    if (!window.location.hash) {
      window.history.replaceState(null, "", hrefFor({ name: "ranked" }));
    }
    const onChange = () => setRoute(parseHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return route;
}

function useSnapshot() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch("/data/snapshot.json")
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`Could not load /data/snapshot.json (${res.status}).`);
        }
        return (await res.json()) as Snapshot;
      })
      .then((data) => {
        if (!cancelled) setSnapshot(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load snapshot.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { snapshot, error, loading };
}

export default function App() {
  const route = useHashRoute();
  const { snapshot, error, loading } = useSnapshot();

  useEffect(() => {
    if (!snapshot) return;
    if (route.name === "asset") {
      const asset = snapshot.assets.find((row) => row.nct_id.toUpperCase() === route.nct);
      document.title = `${asset?.nct_id ?? route.nct} — Failed asset triage`;
      return;
    }
    const titles = {
      ranked: "Ranked assets — Failed asset triage",
      landscape: "Landscape — Failed asset triage",
      weekly: "Weekly changes — Failed asset triage",
    };
    document.title = titles[route.name];
  }, [route, snapshot]);

  return (
    <div className="min-h-full bg-ground text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-40 focus:bg-wine focus:px-3 focus:py-2 focus:text-ground focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-wine"
      >
        Skip to content
      </a>
      <DiligenceBanner />
      <header className="border-b border-line bg-ground">
        <div className="mx-auto flex max-w-6xl flex-col gap-[var(--space-4)] px-4 py-[var(--space-5)] sm:px-6">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <Wordmark />
              <p className="mt-1 font-serif text-[26px] leading-tight tracking-[-0.025em] text-ink sm:text-[30px]">
                Failed asset triage
              </p>
              <p className="mt-1 max-w-xl text-[13px] text-mute">
                Read-only ledger of stopped endometriosis and PCOS programmes. A high score means the public record is
                compatible with a non-biological failure — not an investment recommendation.
              </p>
            </div>
            {snapshot ? (
              <p className="font-mono text-[11px] text-mute">
                {snapshot.snapshot_id}
                <br />
                {snapshot.counts.n_assets} assets
              </p>
            ) : null}
          </div>
          <nav aria-label="Dashboard sections" className="flex flex-wrap gap-1">
            <NavLink href={hrefFor({ name: "ranked" })} active={route.name === "ranked"}>
              Ranked
            </NavLink>
            <NavLink href={hrefFor({ name: "landscape" })} active={route.name === "landscape"}>
              Landscape
            </NavLink>
            <NavLink href={hrefFor({ name: "weekly" })} active={route.name === "weekly"}>
              Weekly
            </NavLink>
            {route.name === "asset" ? (
              <NavLink href={hrefFor(route)} active>
                {route.nct}
              </NavLink>
            ) : null}
          </nav>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-6xl px-4 py-[var(--space-6)] sm:px-6">
        {loading ? <p className="ledger-pulse text-sm text-mute">Loading snapshot…</p> : null}
        {error ? (
          <EmptyNote>
            {error} Generate it with <code className="font-mono">python -m src.serve</code> and keep{" "}
            <code className="font-mono">dashboard/public/data/snapshot.json</code> in the deploy.
          </EmptyNote>
        ) : null}
        {snapshot && route.name === "ranked" ? <RankedView snapshot={snapshot} /> : null}
        {snapshot && route.name === "landscape" ? (
          <Suspense fallback={<p className="ledger-pulse text-sm text-mute">Loading landscape…</p>}>
            <LandscapeView snapshot={snapshot} />
          </Suspense>
        ) : null}
        {snapshot && route.name === "weekly" ? <WeeklyView snapshot={snapshot} /> : null}
        {snapshot && route.name === "asset" ? <AssetView snapshot={snapshot} nct={route.nct} /> : null}
      </main>

      <footer className="border-t border-line bg-ground">
        <div className="mx-auto max-w-6xl px-4 py-[var(--space-5)] text-[12px] text-mute sm:px-6">
          Hash routes: <code className="font-mono">#/ranked</code>, <code className="font-mono">#/asset/NCT…</code>,{" "}
          <code className="font-mono">#/landscape</code>, <code className="font-mono">#/weekly</code>. Data is static{" "}
          <code className="font-mono">/data/snapshot.json</code>. No buy path.
        </div>
      </footer>
    </div>
  );
}

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: string;
}) {
  return (
    <a
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "inline-flex h-8 items-center rounded-none px-2.5 text-[10px] font-medium uppercase tracking-[0.16em] no-underline",
        active ? "bg-wine text-ground" : "text-mute hover:bg-champagne/70 hover:text-ink",
      )}
    >
      {children}
    </a>
  );
}
