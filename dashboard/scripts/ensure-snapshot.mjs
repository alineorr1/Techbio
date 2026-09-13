import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const snapshotPath = resolve(root, "public/data/snapshot.json");

function fail(message) {
  console.error(`ensure-snapshot: ${message}`);
  console.error(
    "vite preview serves dist/. Without this file at build time, /data/snapshot.json returns index.html and JSON.parse fails.",
  );
  process.exit(1);
}

if (!existsSync(snapshotPath)) {
  fail(`missing ${snapshotPath}. Commit the smoke snapshot or run python -m src.serve.`);
}

let data;
try {
  data = JSON.parse(readFileSync(snapshotPath, "utf8"));
} catch (err) {
  const detail = err instanceof Error ? err.message : String(err);
  fail(`${snapshotPath} is not valid JSON (${detail}).`);
}

if (!data || !Array.isArray(data.assets) || data.assets.length === 0) {
  fail(`${snapshotPath} must be a snapshot object with a non-empty assets array.`);
}

console.log(`ensure-snapshot: ${data.assets.length} assets (${data.snapshot_id ?? "no snapshot_id"})`);
