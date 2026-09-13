"""One-command D1 dossier export: JSON + Markdown. Also queue + kill-book.

    python -m src.pilot.export --ncts NCT03481842,NCT04372121 --out data/pilot/exports/
    python -m src.pilot.export --ncts 2023-599001-99-00 --out data/pilot/ctis-eu-example/
    python -m src.pilot.export --pack
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any

from src.db import dump_json
from src.paths import (
    D3_ROLLUP_PATH,
    KILL_BOOK_PATH,
    PILOT_CTIS_EXAMPLE_DIR,
    PILOT_DIR,
    PILOT_EXPORT_DIR,
    RIGHTS_QUEUE_PATH,
    ensure_dirs,
)
from src.pilot.ctis_example import DEFAULT_EU_CT, REGEN_CMD, build_ctis_asset_in_memory, regeneration_readme
from src.pilot.dossier import build_dossier, render_markdown
from src.pilot.killbook import build_kill_book
from src.pilot.labels import assign_label
from src.pilot.queue import build_rights_queue, disregard_hit, label_assets
from src.pilot.rollup import build_d3_rollup
from src.pilot.snapshot import find_asset, load_snapshot, snapshot_assets
from src.rights.gates import NOT_OPTIONABLE

_EU_CT_RE = re.compile(r"^\d{4}-\d{6}-\d{2}-\d{2}$")
_NCT_RE = re.compile(r"^NCT\d{8}$", re.I)

# Re-QA pair: filled WALK_AWAY (BioGene, linzagolix) + one RIGHTS_QUEUE empty.
WALK_SAMPLE_IDS = ["NCT03481842", "NCT04372121"]
EMPTY_QUEUE_SAMPLE_ID = "NCT03411980"
SAMPLE_EXPORT_IDS = [*WALK_SAMPLE_IDS, EMPTY_QUEUE_SAMPLE_ID]


def parse_ids(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        parts = raw
    else:
        parts = [p.strip() for p in raw.replace(" ", "").split(",") if p.strip()]
    return [p for p in parts if p]


def _public_queue_payload(built: dict[str, Any]) -> dict[str, Any]:
    """Machine-readable queue: full capped list, counts for the rest (keep the file small)."""
    return {
        "schema_version": built["schema_version"],
        "narrative": built["narrative"],
        "cap": built["cap"],
        "cap_min": built["cap_min"],
        "cap_max": built["cap_max"],
        "n_snapshot": built["n_snapshot"],
        "n_empty_stub": built["n_empty_stub"],
        "n_opp": built["n_opp"],
        "n_disregarded": built["n_disregarded"],
        "n_candidates": built["n_candidates"],
        "n_queue": built["n_queue"],
        "n_overflow": built["n_overflow"],
        "sort_order": built["sort_order"],
        "disregarded_counts": built["disregarded_counts"],
        "rules": built["rules"],
        "queue": built["queue"],
        "overflow_ncts": [row.get("nct_id") for row in built.get("overflow") or []],
        "n_rights_queue": built.get("n_empty_stub", 0),
        "note": (
            "Empty-rights survivors are RIGHTS_QUEUE, never OPP. OPP is not invented from score. "
            "The `queue` array is the ≤50 human-fill handoff after auto-WALK of "
            "generics/marketed. Overflow stays RIGHTS_QUEUE but is not handed to a human yet. "
            f"Gate surface stays {NOT_OPTIONABLE} until rights+path clear."
        ),
    }


async def resolve_asset(key: str, *, assets: list[dict[str, Any]]) -> dict[str, Any]:
    found = find_asset(key, assets=assets)
    if found:
        return found
    if _EU_CT_RE.match(key) or key.startswith("p_"):
        eu = key if _EU_CT_RE.match(key) else DEFAULT_EU_CT
        return await build_ctis_asset_in_memory(eu)
    raise SystemExit(f"unknown id {key}: not in snapshot and not a CTIS EU CT / programme_id")


def write_dossier(dossier: dict[str, Any], dest: Path) -> tuple[Path, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    display = (
        (dossier.get("registry") or {}).get("primary_display_id")
        or (dossier.get("registry") or {}).get("nct_id")
        or (dossier.get("registry") or {}).get("eu_ct")
        or "unknown"
    )
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(display))
    json_path = dest / f"{safe}.json"
    md_path = dest / f"{safe}.md"
    dump_json(json_path, dossier)
    md_path.write_text(render_markdown(dossier), encoding="utf-8")
    return json_path, md_path


async def export_ids(
    ids: list[str],
    *,
    out: Path,
    assets: list[dict[str, Any]] | None = None,
    labels: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    rows = assets if assets is not None else snapshot_assets()
    label_map = labels if labels is not None else label_assets(rows)
    written: list[dict[str, str]] = []
    for key in ids:
        asset = await resolve_asset(key, assets=rows)
        lookup = str(asset.get("nct_id") or asset.get("primary_display_id") or key)
        row = label_map.get(lookup)
        if row is None:
            row = assign_label(asset, disregarded=bool(disregard_hit(asset)))
        dossier = build_dossier(asset, label_row=row)
        json_path, md_path = write_dossier(dossier, out)
        written.append({"id": lookup, "json": str(json_path), "md": str(md_path)})
        print(f"[pilot.export] {lookup} -> {json_path} + {md_path}")
    return written


def export_queue(assets: list[dict[str, Any]] | None = None, *, dest: Path | None = None) -> Path:
    rows = assets if assets is not None else snapshot_assets()
    built = build_rights_queue(rows)
    if built["n_queue"] > 50:
        raise RuntimeError(f"rights queue cap violated: n_queue={built['n_queue']}")
    path = dest or RIGHTS_QUEUE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, _public_queue_payload(built))
    print(f"[pilot.export] rights_queue n={built['n_queue']} disregarded={built['n_disregarded']} -> {path}")
    return path


def export_kill_book(assets: list[dict[str, Any]] | None = None, *, dest: Path | None = None) -> Path:
    rows = assets if assets is not None else snapshot_assets()
    book = build_kill_book(assets=rows)
    path = dest or KILL_BOOK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, book)
    print(f"[pilot.export] kill-book n={book['n']} -> {path}")
    return path


def write_pilot_readme(dest: Path | None = None) -> Path:
    path = (dest or PILOT_DIR) / "README.md"
    path.write_text(
        "# Pilot pack (Ali D1 + Pharma Exec bar)\n"
        "\n"
        "Unpaid mock extract only. No paid LLM. No public marketing. No MD-LIVE dashboard banner.\n"
        "Desk vocabulary: TRIAGE / RIGHTS_QUEUE / OPP.\n"
        "\n"
        "## Commands\n"
        "\n"
        "```bash\n"
        "python -m src.pilot.export --ncts NCT03481842,NCT04372121,NCT03411980 --out data/pilot/exports/\n"
        "python -m src.pilot.export --ncts 2023-599001-99-00 --out data/pilot/ctis-eu-example/\n"
        "python -m src.pilot.export --pack\n"
        "```\n"
        "\n"
        "## Filter rules (rights queue)\n"
        "\n"
        "Source of truth: `config/rights-queue.json`.\n"
        "\n"
        "1. **Locked WALK_AWAY** (Asset IP desk / kill-book) — not a fill item.\n"
        "2. **Withdrawn** or **0-enrolment** — E3 walk-away stays locked.\n"
        "3. **Modality / RLD disregard** — generic SOC (metformin, OCP, naltrexone, …), "
        "nutraceutical (fiber / inositol / vitamin), marketed class (Lunabell / Caronositol / "
        "Nexplanon / elagolix brands), imaging-only, blood-product / PRP.\n"
        "4. Remaining **empty-stub / NOT OPTIONABLE** rows that survived those hard kills "
        "are sorted: industry single-grantor → thin biotech → TT named-asset → other.\n"
        "5. **Cap ≤50** (floor 30 / ceiling 50) of RIGHTS_QUEUE before anything is handed "
        "to human fill. Overflow stays **RIGHTS_QUEUE** (never OPP); it is not the handoff set.\n"
        "\n"
        "Auto-WALK does **not** loosen: empty→NOT OPTIONABLE; CONTINGENT needs citable IP; "
        "Intermezzo; REMS; Rule B.\n"
        "\n"
        "Desk vocabulary: **TRIAGE** / **RIGHTS_QUEUE** / **OPP**. Empty-rights survivors "
        "(~514 on this corpus) are **RIGHTS_QUEUE**, never OPP. OPP is not invented from score.\n"
        "\n"
        "## E7 CTIS EU example\n"
        "\n"
        f"See `data/pilot/ctis-eu-example/`. Regenerate scores (ephemeral derived files) with "
        f"`{REGEN_CMD}` then re-export the EU CT id. Snapshot.json is not rewritten.\n"
        "\n"
        "## Kill-book\n"
        "\n"
        "`data/pilot/kill-book.json` — locked WALK_AWAYs (BioGene, linzagolix, Viramal, BOL, …). "
        "Negative labels are product.\n"
        "\n"
        "## D2 IC / D3 rollup\n"
        "\n"
        "IC half-page branches by label + desk. Filled WALK_AWAY does **not** reuse empty-rights "
        "boilerplate. `data/pilot/d3-rollup.json` counts by T2 label and desk.\n",
        encoding="utf-8",
    )
    return path


async def export_pack() -> dict[str, Any]:
    ensure_dirs()
    snap = load_snapshot()
    assets = list(snap.get("assets") or [])
    labels = label_assets(assets)
    written = await export_ids(
        SAMPLE_EXPORT_IDS,
        out=PILOT_EXPORT_DIR,
        assets=assets,
        labels=labels,
    )
    ctis_asset = await build_ctis_asset_in_memory(DEFAULT_EU_CT)
    ctis_dossier = build_dossier(
        ctis_asset,
        label_row=assign_label(ctis_asset, disregarded=bool(disregard_hit(ctis_asset))),
    )
    json_path, md_path = write_dossier(ctis_dossier, PILOT_CTIS_EXAMPLE_DIR)
    (PILOT_CTIS_EXAMPLE_DIR / "README.md").write_text(regeneration_readme(DEFAULT_EU_CT), encoding="utf-8")
    written.append({"id": DEFAULT_EU_CT, "json": str(json_path), "md": str(md_path)})
    queue_path = export_queue(assets)
    kill_path = export_kill_book(assets)
    rollup_path = export_rollup(assets, labels=labels)
    readme = write_pilot_readme()
    return {
        "dossiers": written,
        "queue": str(queue_path),
        "kill_book": str(kill_path),
        "rollup": str(rollup_path),
        "readme": str(readme),
    }


def export_rollup(
    assets: list[dict[str, Any]] | None = None,
    *,
    labels: dict[str, dict[str, Any]] | None = None,
    dest: Path | None = None,
) -> Path:
    rows = assets if assets is not None else snapshot_assets()
    book = build_d3_rollup(rows, labels=labels)
    path = dest or D3_ROLLUP_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, book)
    print(f"[pilot.export] d3-rollup n={book['n_snapshot']} opp={book['n_opp']} -> {path}")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Pilot D1 dossier export (JSON + Markdown)")
    parser.add_argument("--ncts", default=None, help="Comma-separated NCT / EU CT / programme_id")
    parser.add_argument("--out", type=Path, default=PILOT_EXPORT_DIR)
    parser.add_argument("--queue", action="store_true", help="Write data/pilot/rights_queue.json")
    parser.add_argument("--kill-book", action="store_true", help="Write data/pilot/kill-book.json")
    parser.add_argument("--pack", action="store_true", help="Write sample dossiers + queue + kill-book + README")
    parser.add_argument("--rollup", action="store_true", help="Write data/pilot/d3-rollup.json")
    args = parser.parse_args(argv)

    ids = parse_ids(args.ncts)
    if args.pack:
        result = asyncio.run(export_pack())
        print(json.dumps({k: v for k, v in result.items() if k != "dossiers"}, indent=2))
        return
    if ids:
        asyncio.run(export_ids(ids, out=args.out))
    if args.queue:
        export_queue()
    if args.kill_book:
        export_kill_book()
    if args.rollup:
        export_rollup()
    if not ids and not args.queue and not args.kill_book and not args.rollup:
        parser.error("pass --ncts, --queue, --kill-book, --rollup, and/or --pack")


if __name__ == "__main__":
    main()
