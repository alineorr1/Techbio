export type Route =
  | { name: "ranked" }
  | { name: "landscape" }
  | { name: "weekly" }
  | { name: "asset"; nct: string };

export function parseHash(hash: string = typeof window === "undefined" ? "" : window.location.hash): Route {
  const raw = hash.replace(/^#\/?/, "").trim();
  if (!raw) return { name: "ranked" };
  const [head, ...rest] = raw.split("/");
  const page = (head || "ranked").toLowerCase();
  if (page === "asset") {
    const nct = (rest[0] || "").trim().toUpperCase();
    if (nct) return { name: "asset", nct };
    return { name: "ranked" };
  }
  if (page === "landscape") return { name: "landscape" };
  if (page === "weekly") return { name: "weekly" };
  return { name: "ranked" };
}

export function hrefFor(route: Route): string {
  if (route.name === "asset") return `#/asset/${route.nct}`;
  return `#/${route.name}`;
}
