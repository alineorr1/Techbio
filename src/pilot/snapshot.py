"""Load the committed unpaid dashboard snapshot without rewriting it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.paths import ROOT

DASHBOARD_SNAPSHOT = ROOT / "dashboard" / "public" / "data" / "snapshot.json"


def load_snapshot(path: Path | None = None) -> dict[str, Any]:
    dest = path or DASHBOARD_SNAPSHOT
    return json.loads(dest.read_text())


def snapshot_assets(path: Path | None = None) -> list[dict[str, Any]]:
    return list((load_snapshot(path).get("assets") or []))


def find_asset(key: str, *, assets: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    needle = (key or "").strip()
    if not needle:
        return None
    rows = assets if assets is not None else snapshot_assets()
    upper = needle.upper()
    for asset in rows:
        for field in ("nct_id", "primary_display_id", "programme_id", "eu_ct"):
            value = asset.get(field)
            if value and str(value).upper() == upper:
                return asset
    return None
