"""T2 desk vocabulary (Asset IP / Aline): TRIAGE / RIGHTS_QUEUE / OPP.

Empty-rights survivors are RIGHTS_QUEUE, never OPP.
OPP is not invented from score alone (Eng or Asset IP).
"""

from __future__ import annotations

from typing import Any

from src.rights.gates import (
    NOT_OPTIONABLE,
    has_citable_patent_number,
    missing_ownership_fill,
    rights_unknown,
)
from src.rights.schema import cmc_of, pathway_505b2_of

LABEL_TRIAGE = "TRIAGE"
LABEL_RIGHTS_QUEUE = "RIGHTS_QUEUE"
LABEL_OPP = "OPP"
TRIAGE_KEEP = "keep"
TRIAGE_DISREGARD = "disregard"

CMC_FILL_KEYS = (
    "api_source_identified",
    "formulation_described",
    "impurity_profile_available",
    "stability_data_available",
    "manufacturing_site_known",
    "spec_available",
    "ctd_module_3_available",
)


def _rights_of(asset: dict[str, Any] | None) -> dict[str, Any]:
    asset = asset or {}
    rights = asset.get("rights")
    return rights if isinstance(rights, dict) else {}


def is_empty_stub(asset: dict[str, Any] | None, rights: dict[str, Any] | None = None) -> bool:
    rec = rights if rights is not None else _rights_of(asset)
    if not rec:
        return True
    if rights_unknown(rec):
        return True
    return str(rec.get("confidence") or "empty_stub").strip().lower() == "empty_stub"


def path_stub_started(asset: dict[str, Any] | None, rights: dict[str, Any] | None = None) -> bool:
    """True when a CMC / 505(b)(2) / exclusivity stub has been filled past empty defaults."""
    rec = rights if rights is not None else _rights_of(asset)
    asset = asset or {}
    cmc = asset.get("cmc") if isinstance(asset.get("cmc"), dict) else cmc_of(rec or {})
    path = (
        asset.get("pathway_505b2")
        if isinstance(asset.get("pathway_505b2"), dict)
        else pathway_505b2_of(rec or {})
    )
    cmc = cmc or {}
    path = path or {}
    if str(cmc.get("confidence") or "") not in {"", "empty_stub"}:
        return True
    if str(path.get("confidence") or "") not in {"", "empty_stub"}:
        return True
    if path.get("rld_ref") or path.get("listed_drug_name") or path.get("listed_drug_ref"):
        return True
    if path.get("exclusivity_windows"):
        return True
    if path.get("pathway") not in (None, "", "unknown"):
        return True
    if any(cmc.get(key) in {"yes", "no"} for key in CMC_FILL_KEYS):
        return True
    if (cmc.get("notes") or "").strip():
        return True
    return False


def _desk(asset: dict[str, Any] | None, rights: dict[str, Any] | None = None) -> str:
    rec = rights if rights is not None else _rights_of(asset)
    asset = asset or {}
    return str(
        asset.get("desk_classification")
        or rec.get("desk_classification")
        or (asset.get("ownability") or {}).get("desk_classification")
        or ""
    ).upper()


def _optionable_candidate(asset: dict[str, Any] | None, rights: dict[str, Any] | None = None) -> bool:
    rec = rights if rights is not None else _rights_of(asset)
    asset = asset or {}
    return bool(
        asset.get("optionable")
        or asset.get("shortlist_ownable")
        or rec.get("optionable_candidate")
        or rec.get("shortlist_ownable")
        or (asset.get("pre_pass") or {}).get("optionable")
        or (asset.get("pre_pass") or {}).get("shortlist_ownable")
    )


def opp_eligible(asset: dict[str, Any] | None, rights: dict[str, Any] | None = None) -> bool:
    """Rare. Empty stub is never OPP. High score is ignored."""
    rec = rights if rights is not None else _rights_of(asset)
    if is_empty_stub(asset, rec):
        return False
    if missing_ownership_fill(rec):
        return False
    desk = _desk(asset, rec)
    if desk == "WALK_AWAY":
        return False
    contingent_numbered = desk == "CONTINGENT" and has_citable_patent_number(rec)
    counsel_capped = desk == "NEEDS_COUNSEL" and has_citable_patent_number(rec)
    rights_clear = _optionable_candidate(asset, rec) or contingent_numbered or counsel_capped
    return bool(rights_clear and path_stub_started(asset, rec))


def gate_surface_of(asset: dict[str, Any] | None, rights: dict[str, Any] | None = None) -> str:
    rec = rights if rights is not None else _rights_of(asset)
    asset = asset or {}
    desk = _desk(asset, rec)
    if desk in {"WALK_AWAY", "CONTINGENT"}:
        return desk
    surface = (
        (asset.get("pre_pass") or {}).get("surface")
        or asset.get("gate_surface")
        or (asset.get("ownability") or {}).get("surface")
        or rec.get("desk_classification")
    )
    if surface:
        return str(surface)
    return NOT_OPTIONABLE


def assign_label(
    asset: dict[str, Any] | None,
    *,
    rights: dict[str, Any] | None = None,
    disregarded: bool = False,
    in_active_queue: bool = False,
    auto_walk: bool = False,
    human_fill: bool | None = None,
) -> dict[str, Any]:
    """T2 label. Empty rights → RIGHTS_QUEUE. Locked filled WALK_AWAY → TRIAGE.

    ``disregarded`` / ``auto_walk`` / ``human_fill`` do not invent OPP and do not
    relabel empty-rights survivors as TRIAGE. The ≤50 human-fill handoff is a
    subset of RIGHTS_QUEUE after auto-WALK of generics/marketed.
    """
    rec = rights if rights is not None else _rights_of(asset)
    empty = is_empty_stub(asset, rec)
    handed = in_active_queue if human_fill is None else human_fill
    if opp_eligible(asset, rec):
        return {
            "label": LABEL_OPP,
            "triage": TRIAGE_KEEP,
            "human_fill": False,
            "auto_walk": False,
            "note": "OPP is not invented from score. Rights+path only.",
        }
    if _desk(asset, rec) == "WALK_AWAY" and not empty:
        return {
            "label": LABEL_TRIAGE,
            "triage": TRIAGE_DISREGARD,
            "human_fill": False,
            "auto_walk": True,
            "note": "Locked WALK_AWAY. Not RIGHTS_QUEUE (rights were filled). Not OPP.",
        }
    if empty:
        return {
            "label": LABEL_RIGHTS_QUEUE,
            "triage": TRIAGE_DISREGARD if (disregarded or auto_walk) else TRIAGE_KEEP,
            "human_fill": bool(handed),
            "auto_walk": bool(auto_walk or disregarded),
            "note": "Empty rights are RIGHTS_QUEUE, never OPP. OPP is not invented from score.",
        }
    return {
        "label": LABEL_TRIAGE,
        "triage": TRIAGE_DISREGARD if disregarded else TRIAGE_KEEP,
        "human_fill": False,
        "auto_walk": bool(auto_walk or disregarded),
        "note": "TRIAGE (stop-mode). Not OPP.",
    }
