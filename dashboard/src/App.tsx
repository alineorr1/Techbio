import { lazy, Suspense, useEffect, useState } from "react";
import { DiligenceBanner, EmptyNote } from "./components/chrome";
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

function Atmosphere() {
  return (
    <div className="atmosphere h-16 sm:h-20" aria-hidden="true">
      <img className="atmosphere-poster" src="/atmosphere-poster.svg" alt="" />
      <video
        className="atmosphere-video"
        poster="/atmosphere-poster.svg"
        muted
        playsInline
        loop
        preload="none"
      />
    </div>
  );
}

export default function App() {
  const route = useHashRoute();
  const { snapshot, error, loading } = useSnapshot();

  useEffect(() => {
    if (!snapshot) return;
    if (route.name === "asset") {
      const asset = snapshot.assets.find((row) => row.nct_id.toUpperCase() === route.nct);
      document.title = `${asset?.nct_id ?? route.nct} — we.are`;
      return;
    }
    const titles = {
      ranked: "Ranked assets — we.are",
      landscape: "Landscape — we.are",
      weekly: "Weekly changes — we.are",
    };
    document.title = titles[route.name];
  }, [route, snapshot]);

  return (
    <div className="min-h-full bg-ground text-ink">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4">
        Skip to content
      </a>
      <Atmosphere />
      <header>
        <div className="mx-auto flex max-w-5xl flex-col gap-8 px-5 py-8 sm:px-8">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-baseline sm:justify-between">
            <p className="font-sans text-2xl font-medium tracking-tight">we.are</p>
            <nav aria-label="Dashboard sections" className="flex flex-wrap gap-x-6 gap-y-2">
              <NavLink href={hrefFor({ name: "ranked" })} active={route.name === "ranked"}>
                ranked
              </NavLink>
              <NavLink href={hrefFor({ name: "landscape" })} active={route.name === "landscape"}>
                landscape
              </NavLink>
              <NavLink href={hrefFor({ name: "weekly" })} active={route.name === "weekly"}>
                weekly
              </NavLink>
              {route.name === "asset" ? (
                <NavLink href={hrefFor(route)} active>
                  {route.nct}
                </NavLink>
              ) : null}
            </nav>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="max-w-xl">
              <DiligenceBanner />
              <p className="mt-4 text-sm text-mute">
                Failed asset triage. A high score means the public record is compatible with a
                non-biological failure — not a recommendation to buy.
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
        </div>
      </header>

      <main id="main" className="mx-auto max-w-5xl px-5 pb-16 pt-2 sm:px-8">
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

      <footer>
        <div className="mx-auto max-w-5xl px-5 py-8 font-mono text-[11px] text-mute sm:px-8">
          #/ranked · #/asset/NCT… · #/landscape · #/weekly · /data/snapshot.json
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
        "text-sm no-underline",
        active ? "text-ink underline decoration-1 underline-offset-4" : "text-mute hover:text-ink",
      )}
    >
      {children}
    </a>
  );
}
