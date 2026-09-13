"""T1 + T3: auto-WALK generics/marketed, then cap ≤50 of RIGHTS_QUEUE for human fill."""

from __future__ import annotations

import re
from typing import Any

from src.pilot.labels import (
    LABEL_RIGHTS_QUEUE,
    LABEL_TRIAGE,
    TRIAGE_DISREGARD,
    TRIAGE_KEEP,
    assign_label,
    gate_surface_of,
    is_empty_stub,
    opp_eligible,
)
from src.pilot.rules import CAP_MAX, load_queue_rules
from src.rights.codes import DESK_WRITEBACK_NCTS
from src.rights.gates import WALK_AWAY_WITHDRAWN, WALK_AWAY_ZERO_ENROLMENT

TIER_INDUSTRY = "industry_single_grantor"
TIER_BIOTECH = "thin_biotech"
TIER_TT = "tt_named_asset"
TIER_OTHER = "other"
TIER_RANK = {TIER_INDUSTRY: 0, TIER_BIOTECH: 1, TIER_TT: 2, TIER_OTHER: 3}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def asset_blob(asset: dict[str, Any]) -> str:
    parts = [
        str(asset.get("brief_title") or ""),
        str(asset.get("official_title") or ""),
        str(asset.get("mechanism_summary") or ""),
        str(asset.get("sponsor_name") or ""),
    ]
    for item in asset.get("interventions") or []:
        if isinstance(item, dict):
            parts.append(str(item.get("name") or ""))
        else:
            parts.append(str(item))
    return _norm(" ".join(parts))


def _walk_codes(asset: dict[str, Any]) -> list[str]:
    codes = list(asset.get("walk_away_codes") or [])
    codes.extend((asset.get("pre_pass") or {}).get("walk_away_codes") or [])
    codes.extend((asset.get("classification") or {}).get("walk_away_codes") or [])
    return list(dict.fromkeys(str(c) for c in codes if c))


def _desk(asset: dict[str, Any]) -> str:
    return str(
        asset.get("desk_classification")
        or (asset.get("rights") or {}).get("desk_classification")
        or ""
    ).upper()


def enrolment_count(asset: dict[str, Any]) -> int | None:
    info = asset.get("enrolment") or {}
    if isinstance(info, dict) and info.get("count") is not None:
        try:
            return int(info["count"])
        except (TypeError, ValueError):
            return None
    return None


def disregard_hit(asset: dict[str, Any], rules: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """First matching pre-queue disregard rule, or None if the row may be queued."""
    cfg = rules or load_queue_rules()
    nct = str(asset.get("nct_id") or asset.get("primary_display_id") or "")
    codes = set(_walk_codes(asset))
    desk = _desk(asset)
    status = str(asset.get("overall_status") or "").upper()
    count = enrolment_count(asset)
    blob = asset_blob(asset)

    if desk == "WALK_AWAY" or nct in DESK_WRITEBACK_NCTS:
        return {"code": "DESK_WALK_AWAY", "note": "Locked Asset IP WALK_AWAY."}
    if status == "WITHDRAWN" or WALK_AWAY_WITHDRAWN in codes:
        return {"code": "WALK_AWAY_WITHDRAWN", "note": "Withdrawn — E3 walk-away stays locked."}
    if count == 0 or WALK_AWAY_ZERO_ENROLMENT in codes:
        return {"code": "WALK_AWAY_ZERO_ENROLMENT", "note": "0-enrolment — E3 walk-away stays locked."}

    for rule in cfg.get("disregard") or []:
        if rule.get("kind") != "pattern":
            continue
        for pat in rule.get("patterns") or []:
            needle = _norm(str(pat))
            if needle and needle in blob:
                return {
                    "code": str(rule.get("code") or "PATTERN"),
                    "note": str(rule.get("note") or ""),
                    "matched": pat,
                }
    return None


def _is_industry(asset: dict[str, Any]) -> bool:
    return str(asset.get("sponsor_class") or "").upper() == "INDUSTRY"


def _is_large_cap(asset: dict[str, Any], rules: dict[str, Any]) -> bool:
    name = _norm(str(asset.get("sponsor_name") or ""))
    for token in rules.get("large_cap_industry") or []:
        if _norm(str(token)) and _norm(str(token)) in name:
            return True
    return False


def _named_non_generic(asset: dict[str, Any], rules: dict[str, Any]) -> bool:
    """True when an intervention name does not collapse to a disregard pattern."""
    blob = asset_blob(asset)
    for rule in rules.get("disregard") or []:
        if rule.get("kind") != "pattern":
            continue
        for pat in rule.get("patterns") or []:
            if _norm(str(pat)) and _norm(str(pat)) in blob:
                return False
    names = [
        str(i.get("name") or "")
        for i in (asset.get("interventions") or [])
        if isinstance(i, dict) and i.get("name")
    ]
    return any(len(n.strip()) >= 4 for n in names)


def queue_tier(asset: dict[str, Any], rules: dict[str, Any] | None = None) -> str:
    cfg = rules or load_queue_rules()
    if _is_industry(asset):
        status = str(asset.get("sponsor_status") or "").lower()
        thin = status in {"ceased", "restructured", "acquired", "unknown"} or not _is_large_cap(asset, cfg)
        return TIER_BIOTECH if thin else TIER_INDUSTRY
    if _named_non_generic(asset, cfg):
        return TIER_TT
    return TIER_OTHER


def _score(asset: dict[str, Any]) -> float:
    raw = (asset.get("score") or {}).get("score")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def sort_key(asset: dict[str, Any], rules: dict[str, Any] | None = None) -> tuple:
    cfg = rules or load_queue_rules()
    tier = queue_tier(asset, cfg)
    return (TIER_RANK.get(tier, 9), -_score(asset), str(asset.get("nct_id") or ""))


def label_assets(assets: list[dict[str, Any]], *, cap: int | None = None) -> dict[str, dict[str, Any]]:
    """Map id → T2 label. Empty-rights survivors are RIGHTS_QUEUE (never OPP)."""
    built = build_rights_queue(assets, cap=cap)
    by_id = {str(a.get("nct_id") or a.get("primary_display_id") or ""): a for a in assets}
    out: dict[str, dict[str, Any]] = {}
    handed = {str(r.get("nct_id") or "") for r in built["queue"]}
    for row in built["disregarded"]:
        key = str(row.get("nct_id") or "")
        asset = by_id.get(key) or {}
        if not key:
            continue
        tagged = assign_label(asset, disregarded=True, auto_walk=True, human_fill=False)
        tagged["queue_tier"] = None
        tagged["disregard"] = {"code": row.get("disregard_code"), "note": row.get("disregard_note")}
        out[key] = tagged
    for row in built["overflow"]:
        key = str(row.get("nct_id") or "")
        if key:
            tagged = assign_label(by_id.get(key) or {}, human_fill=False)
            tagged["queue_tier"] = row.get("queue_tier")
            out[key] = tagged
    for row in built["queue"]:
        key = str(row.get("nct_id") or "")
        if key:
            tagged = assign_label(by_id.get(key) or {}, human_fill=True)
            tagged["queue_tier"] = row.get("queue_tier")
            out[key] = tagged
    for asset in assets:
        key = str(asset.get("nct_id") or asset.get("primary_display_id") or "")
        if key and key not in out:
            out[key] = assign_label(asset, human_fill=key in handed)
    return out


def _row(asset: dict[str, Any], *, tier: str | None, disregard: dict[str, Any] | None = None) -> dict[str, Any]:
    nct = str(asset.get("nct_id") or asset.get("primary_display_id") or "")
    return {
        "nct_id": nct,
        "primary_display_id": asset.get("primary_display_id") or nct,
        "programme_id": asset.get("programme_id"),
        "title": asset.get("brief_title") or asset.get("official_title"),
        "sponsor_name": asset.get("sponsor_name"),
        "sponsor_class": asset.get("sponsor_class"),
        "sponsor_status": asset.get("sponsor_status"),
        "indication": asset.get("indication"),
        "score": (asset.get("score") or {}).get("score"),
        "failure_mode": (asset.get("classification") or {}).get("failure_mode"),
        "gate_surface": gate_surface_of(asset),
        "ownable": False,
        "optionable": False,
        "empty_stub": is_empty_stub(asset),
        "queue_tier": tier,
        "disregard_code": (disregard or {}).get("code"),
        "disregard_note": (disregard or {}).get("note"),
        "matched": (disregard or {}).get("matched"),
        "_asset": asset,
    }


def build_rights_queue(
    assets: list[dict[str, Any]],
    *,
    cap: int | None = None,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = rules or load_queue_rules()
    limit = cap if cap is not None else int(cfg.get("cap") or CAP_MAX)
    limit = max(1, min(CAP_MAX, int(limit)))

    disregarded: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    n_empty = 0
    n_opp = 0

    for asset in assets:
        if is_empty_stub(asset):
            n_empty += 1
        if opp_eligible(asset):
            n_opp += 1
            continue
        hit = disregard_hit(asset, cfg)
        if hit:
            counts[str(hit["code"])] = counts.get(str(hit["code"]), 0) + 1
            disregarded.append(_row(asset, tier=None, disregard=hit))
            continue
        if not is_empty_stub(asset) and _desk(asset) in {"CONTINGENT", "NEEDS_COUNSEL", "PASS"}:
            # Filled desk that is not OPP — not a human empty-rights backlog item.
            continue
        if not is_empty_stub(asset):
            continue
        tier = queue_tier(asset, cfg)
        candidates.append(_row(asset, tier=tier))

    candidates.sort(key=lambda r: sort_key(r["_asset"], cfg))
    queue = candidates[:limit]
    overflow = candidates[limit:]
    for idx, row in enumerate(queue, start=1):
        row["rank"] = idx
        row["label"] = LABEL_RIGHTS_QUEUE
        row["triage"] = TRIAGE_KEEP
        row["human_fill"] = True
        row["auto_walk"] = False
    for row in overflow:
        row["label"] = LABEL_RIGHTS_QUEUE
        row["triage"] = TRIAGE_KEEP
        row["human_fill"] = False
        row["auto_walk"] = False
    for row in disregarded:
        empty = bool(row.get("empty_stub"))
        row["label"] = LABEL_RIGHTS_QUEUE if empty else LABEL_TRIAGE
        row["triage"] = TRIAGE_DISREGARD
        row["human_fill"] = False
        row["auto_walk"] = True

    public_queue = [{k: v for k, v in row.items() if k != "_asset"} for row in queue]
    public_overflow = [{k: v for k, v in row.items() if k != "_asset"} for row in overflow]
    public_disregarded = [{k: v for k, v in row.items() if k != "_asset"} for row in disregarded]

    return {
        "schema_version": cfg.get("schema_version") or "pilot.rights-queue.v1",
        "narrative": cfg.get("narrative"),
        "cap": limit,
        "cap_min": cfg.get("cap_min"),
        "cap_max": cfg.get("cap_max"),
        "n_snapshot": len(assets),
        "n_empty_stub": n_empty,
        "n_opp": n_opp,
        "n_disregarded": len(disregarded),
        "n_candidates": len(candidates),
        "n_queue": len(queue),
        "n_overflow": len(overflow),
        "sort_order": list(cfg.get("sort_order") or []),
        "disregarded_counts": dict(sorted(counts.items())),
        "rules": {
            "codes": [r.get("code") for r in (cfg.get("disregard") or [])],
            "note": (
                "Disregard is pre-queue only. Locked gates stay: empty→NOT OPTIONABLE; "
                "CONTINGENT needs citable IP; withdrawn/0-enrolment; Intermezzo; REMS; Rule B."
            ),
        },
        "queue": public_queue,
        "overflow": public_overflow,
        "disregarded": public_disregarded,
        "_queue_assets": [row["_asset"] for row in queue],
        "_disregarded_assets": [row["_asset"] for row in disregarded],
        "_overflow_assets": [row["_asset"] for row in overflow],
    }
