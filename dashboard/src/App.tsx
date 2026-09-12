import { lazy, Suspense, useEffect, useState } from "react";
import { EmptyNote } from "./components/chrome";
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
    <div className="min-h-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4">
        Skip to content
      </a>
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-5 sm:px-6">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-2xl font-medium">Failed asset triage</p>
              <p className="mt-1 max-w-xl text-sm text-mute">
                Read-only ledger of stopped endometriosis and PCOS programmes. A high score means the public record is
                compatible with a non-biological failure — not an investment recommendation.
              </p>
            </div>
            {snapshot ? (
              <p className="font-mono text-xs text-mute">
                {snapshot.snapshot_id}
                <br />
                {snapshot.counts.n_assets} assets
              </p>
            ) : null}
          </div>
          <nav aria-label="Dashboard sections" className="flex flex-wrap gap-4">
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

      <main id="main" className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        {loading ? <p className="text-sm text-mute">Loading snapshot…</p> : null}
        {error ? (
          <EmptyNote>
            {error} Generate it with <code className="font-mono">python -m src.serve</code> and keep{" "}
            <code className="font-mono">dashboard/public/data/snapshot.json</code> in the deploy.
          </EmptyNote>
        ) : null}
        {snapshot && route.name === "ranked" ? <RankedView snapshot={snapshot} /> : null}
        {snapshot && route.name === "landscape" ? (
          <Suspense fallback={<p className="text-sm text-mute">Loading landscape…</p>}>
            <LandscapeView snapshot={snapshot} />
          </Suspense>
        ) : null}
        {snapshot && route.name === "weekly" ? <WeeklyView snapshot={snapshot} /> : null}
        {snapshot && route.name === "asset" ? <AssetView snapshot={snapshot} nct={route.nct} /> : null}
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto max-w-6xl px-4 py-5 text-xs text-mute sm:px-6">
          Hash routes: <code className="font-mono">#/ranked</code>, <code className="font-mono">#/asset/NCT…</code>,{" "}
          <code className="font-mono">#/landscape</code>, <code className="font-mono">#/weekly</code>. Data is static{" "}
          <code className="font-mono">/data/snapshot.json</code>.
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
      className={cn("text-sm no-underline", active ? "font-medium text-ink underline" : "text-mute")}
    >
      {children}
    </a>
  );
}
