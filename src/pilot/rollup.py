"""D3 rollup: counts by T2 label and desk. Does not invent OPP."""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.pilot.labels import LABEL_OPP, assign_label, is_empty_stub, opp_eligible
from src.pilot.queue import label_assets


def _desk(asset: dict[str, Any]) -> str:
    return str(
        asset.get("desk_classification")
        or (asset.get("rights") or {}).get("desk_classification")
        or (asset.get("ownability") or {}).get("desk_classification")
        or ""
    ).upper() or "(unset)"


def build_d3_rollup(
    assets: list[dict[str, Any]],
    *,
    labels: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tagged = labels if labels is not None else label_assets(assets)
    by_label: Counter[str] = Counter()
    by_desk: Counter[str] = Counter()
    by_label_desk: Counter[str] = Counter()
    by_empty: Counter[str] = Counter()
    n_opp_eligible = 0
    n_filled_walk = 0
    n_rights_queue_empty = 0
    for asset in assets:
        key = str(asset.get("nct_id") or asset.get("primary_display_id") or "")
        row = tagged.get(key) or assign_label(asset)
        label = str(row.get("label") or "")
        desk = _desk(asset)
        empty = is_empty_stub(asset)
        by_label[label] += 1
        by_desk[desk] += 1
        by_label_desk[f"{label}|{desk}"] += 1
        by_empty["true" if empty else "false"] += 1
        if opp_eligible(asset):
            n_opp_eligible += 1
        if label != "RIGHTS_QUEUE" and desk == "WALK_AWAY" and not empty:
            n_filled_walk += 1
        if label == "RIGHTS_QUEUE" and empty:
            n_rights_queue_empty += 1
    return {
        "schema_version": "pilot.d3.rollup.v1",
        "narrative": (
            "D3 counts by T2 label and desk. OPP is not invented from score. "
            "Filled WALK_AWAY is TRIAGE disregard, not RIGHTS_QUEUE."
        ),
        "n_snapshot": len(assets),
        "n_opp": by_label.get(LABEL_OPP, 0),
        "n_opp_eligible": n_opp_eligible,
        "n_filled_walk_away": n_filled_walk,
        "n_rights_queue_empty": n_rights_queue_empty,
        "by_label": dict(sorted(by_label.items())),
        "by_desk": dict(sorted(by_desk.items())),
        "by_label_desk": dict(sorted(by_label_desk.items())),
        "by_empty_stub": dict(sorted(by_empty.items())),
        "note": (
            "Hard gates untouched. Empty→NOT OPTIONABLE. CONTINGENT needs citable IP. "
            "0 OPP expected on the current unpaid corpus."
        ),
    }
