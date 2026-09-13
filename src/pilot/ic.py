"""D2 half-page IC stub. Branch by T2 label + desk; gate empty-rights boilerplate."""

from __future__ import annotations

from typing import Any

from src.pilot.labels import LABEL_OPP, LABEL_RIGHTS_QUEUE, LABEL_TRIAGE, opp_eligible

IC_STATUS = "half_page"
KIND_WALK = "WALK"
KIND_CONTINGENT = "CONTINGENT"
KIND_COUNSEL = "COUNSEL_MAP"
KIND_HOLD = "HOLD"
KIND_OPP = "OPP"

EMPTY_RIGHTS_STAY = "Empty rights stay RIGHTS_QUEUE / NOT OPTIONABLE"
EMPTY_OPP_LINE = "OPP on empty_stub: no (empty rights are RIGHTS_QUEUE, never OPP)"


def empty_rights_boilerplate_allowed(*, empty_stub: bool) -> bool:
    """F3: empty-rights sentences only when the row is actually an empty stub."""
    return bool(empty_stub)


def grantor_ip_oneliner(*, grantor: str | None, patents: list[str] | None) -> str | None:
    grant = (grantor or "").strip().rstrip(".") or None
    if patents:
        patent_bit = ", ".join(patents)
        if grant:
            return f"{grant}. Patents: {patent_bit}."
        return f"Grantor: null. Patents: {patent_bit}."
    if grant:
        return f"{grant}. Patents: null (none found / empty docket)."
    return None


def path_readiness(path: dict[str, Any] | None) -> dict[str, Any]:
    block = path or {}
    cmc = block.get("cmc") or {}
    p505 = block.get("pathway_505b2") or {}
    excl = block.get("exclusivity") or {}
    started = bool(block.get("started"))
    pathway = str(p505.get("pathway") or "unknown")
    cmc_conf = str(cmc.get("confidence") or "empty_stub")
    excl_status = str(excl.get("status") or "unknown")
    thin_unknown = pathway in {"", "unknown"} and excl_status == "unknown"
    if not started:
        readiness = "unknown"
    elif thin_unknown:
        readiness = "thin"
    else:
        readiness = "ready"
    return {
        "readiness": readiness,
        "started": started,
        "cmc_confidence": cmc_conf,
        "cmc_notes": (cmc.get("notes") or "").strip() or None,
        "pathway_505b2": pathway,
        "pathway_confidence": str(p505.get("confidence") or "empty_stub"),
        "exclusivity": excl_status,
        "unknown_ok_if_marked": True,
        "note": "unknown OK if marked" if readiness in {"thin", "unknown"} else None,
    }


def _desk_of(rights: dict[str, Any] | None, labels: dict[str, Any] | None = None) -> str:
    rec = rights or {}
    return str(
        rec.get("desk_classification")
        or (labels or {}).get("desk")
        or ""
    ).upper()


def _next_step_default(
    *,
    kind: str,
    empty_stub: bool,
    human_fill: bool,
    auto_walk: bool,
    explicit: str | None,
) -> str:
    if explicit:
        return explicit
    if kind == KIND_WALK:
        return "None — closed."
    if kind == KIND_CONTINGENT:
        return "Hold until PATH ready; do not invent OPP."
    if kind == KIND_COUNSEL:
        return "Counsel map; do not invent OPP."
    if kind == KIND_OPP:
        return "Rights+path review; not a buy."
    if empty_stub and human_fill:
        return "Human fill the rights stub; do not invent OPP."
    if empty_stub and auto_walk:
        return "Auto-WALK; not a human-fill handoff. Empty rights stay RIGHTS_QUEUE / NOT OPTIONABLE."
    if empty_stub:
        return "Empty rights stay RIGHTS_QUEUE / NOT OPTIONABLE until human fill or auto-WALK."
    return "Hold. Hypothesis for human review only."


def build_ic_stub(
    *,
    asset: dict[str, Any] | None = None,
    labels: dict[str, Any],
    rights: dict[str, Any],
    stop: dict[str, Any],
    path: dict[str, Any],
    empty_stub: bool,
    buyer_class: str | None = None,
    next_diligence: str | None = None,
) -> dict[str, Any]:
    """Disposition-aware half-page IC. OPP only if opp_eligible."""
    label = str(labels.get("label") or "")
    desk = _desk_of(rights, labels)
    kill_codes = list(rights.get("kill_codes") or [])
    grantor = rights.get("grantor")
    patents = rights.get("patents")
    has_citable = bool(rights.get("has_citable_ip"))
    human_fill = bool(labels.get("human_fill"))
    auto_walk = bool(labels.get("auto_walk"))
    triage = labels.get("triage")
    oneliner = grantor_ip_oneliner(grantor=grantor, patents=patents if isinstance(patents, list) else None)
    path_block = path_readiness(path)
    eligible = label == LABEL_OPP and not empty_stub
    if eligible and asset is not None and not opp_eligible(asset):
        eligible = False

    if eligible:
        kind = KIND_OPP
        not_opp_reason = None
        recommendation = (
            "OPP candidate — rights+path only; not a buy. OPP is not invented from score."
        )
    elif label == LABEL_TRIAGE and desk == "WALK_AWAY" and not empty_stub:
        kind = KIND_WALK
        codes = ", ".join(kill_codes) or "WALK_AWAY"
        ip_bit = oneliner or "grantor/IP: null"
        not_opp_reason = "desk closed — filled WALK_AWAY, not empty rights"
        recommendation = (
            f"WALK / disregard. Desk closed this row (filled WALK_AWAY, TRIAGE disregard). "
            f"Kill codes: {codes}. Grantor/IP: {ip_bit} "
            "Not an OPP because the desk closed, not because rights are empty."
        )
    elif label == LABEL_RIGHTS_QUEUE and empty_stub:
        kind = KIND_HOLD
        not_opp_reason = "empty rights stay RIGHTS_QUEUE / NOT OPTIONABLE"
        handoff = (
            "Human fill the rights stub"
            if human_fill
            else ("Auto-WALK" if auto_walk else "Human fill or auto-WALK")
        )
        recommendation = (
            f"Not an OPP. {EMPTY_RIGHTS_STAY}. {handoff}; do not invent OPP from score. "
            "Hypothesis for human review only."
        )
    elif desk == "CONTINGENT" and has_citable:
        kind = KIND_CONTINGENT
        ip_bit = oneliner or "numbered IP present"
        not_opp_reason = "CONTINGENT numbered IP; path not ready"
        recommendation = (
            f"CONTINGENT path. Numbered IP is present ({ip_bit}). "
            "Not an OPP until the path is ready. Hypothesis for human review only."
        )
    elif desk == "NEEDS_COUNSEL":
        kind = KIND_COUNSEL
        not_opp_reason = "counsel map; not opp_eligible"
        recommendation = (
            "Counsel map. Not an OPP until the counsel path is ready. "
            "Hypothesis for human review only."
        )
    else:
        kind = KIND_HOLD
        not_opp_reason = "not opp_eligible"
        recommendation = (
            "HOLD. Not an OPP. Hypothesis for human review only."
        )

    why = stop.get("why_stopped") or stop.get("notes") or None
    return {
        "title": "Investment committee (half-page)",
        "status": IC_STATUS,
        "is_opp": eligible,
        "empty_stub_is_opp": False,
        "recommendation_kind": kind,
        "recommendation": recommendation,
        "not_opp_reason": not_opp_reason,
        "stop": {
            "mode": stop.get("mode") or stop.get("classification"),
            "status": stop.get("overall_status"),
            "why": why,
            "rule_fired": stop.get("rule_fired"),
        },
        "desk": {
            "label": label,
            "disposition": desk or None,
            "triage": triage,
            "kill_codes": kill_codes,
            "empty_stub": empty_stub,
        },
        "grantor_ip": {
            "grantor": grantor or None,
            "patents": patents if isinstance(patents, list) else None,
            "one_liner": oneliner,
        },
        "path": path_block,
        "buyer_class": buyer_class or None,
        "next_step": _next_step_default(
            kind=kind,
            empty_stub=empty_stub,
            human_fill=human_fill,
            auto_walk=auto_walk,
            explicit=next_diligence,
        ),
        "note": (
            "Half-page IC. Does not claim PASS or an ownable book. "
            "Dashboard MD banner remains held by CoS. No MD-LIVE chrome."
        ),
    }


def opp_line_for_markdown(*, empty_stub: bool, not_opp_reason: str | None) -> str:
    """F3: row-specific OPP line. Empty-rights sentence only on empty stubs."""
    if empty_rights_boilerplate_allowed(empty_stub=empty_stub):
        return f"- {EMPTY_OPP_LINE.replace('OPP on empty_stub: no', 'OPP on empty_stub: **no**')}"
    reason = not_opp_reason or "not opp_eligible"
    return f"- OPP: **no** ({reason})"
