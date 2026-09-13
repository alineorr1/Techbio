"""Queryable ownability / Decision Required gate (Asset IP lock).

Fields that must stay queryable: identity.thesis_mismatch, kill.triggered, kill.codes.
"""

from __future__ import annotations

from typing import Any

from src.rights.codes import HARD_KILL_CODES
from src.rights.gates import (
    MISSING_OWNERSHIP_FILL,
    NOT_OPTIONABLE,
    NOT_OPTIONABLE_CODE,
    RIGHTS_UNKNOWN,
    missing_ownership_fill,
    rights_unknown,
)
from src.rights.schema import empty_rights


def ownability_query(record: dict[str, Any] | None) -> dict[str, Any]:
    rec = record or empty_rights("p_unknown")
    identity = rec.get("identity") or {}
    kill = rec.get("kill") or {}
    ownership = rec.get("ownership") or {}
    thesis = bool(identity.get("thesis_mismatch"))
    triggered = bool(kill.get("triggered"))
    codes = list(kill.get("codes") or [])
    confidence = rec.get("confidence") or "empty_stub"
    unknown = rights_unknown(rec)
    missing_own = missing_ownership_fill(rec)
    ownable = (
        bool(ownership.get("ownable"))
        and not unknown
        and not missing_own
        and confidence != "empty_stub"
        and not triggered
        and not thesis
    )
    decision = thesis or triggered or unknown or missing_own or not ownable
    if unknown and RIGHTS_UNKNOWN not in codes:
        codes.append(RIGHTS_UNKNOWN)
    if missing_own and MISSING_OWNERSHIP_FILL not in codes:
        codes.append(MISSING_OWNERSHIP_FILL)
    if not ownable and NOT_OPTIONABLE_CODE not in codes:
        codes.append(NOT_OPTIONABLE_CODE)
    return {
        "schema_version": rec.get("schema_version"),
        "nct_id": rec.get("nct_id") or identity.get("nct_id"),
        "programme_id": rec.get("programme_id") or identity.get("programme_id"),
        "thesis_mismatch": thesis,
        "kill_triggered": triggered,
        "kill_codes": codes,
        "hard_codes": list(kill.get("hard") or []),
        "soft_codes": list(kill.get("soft") or []),
        "ownership_ownable": ownable,
        "optionable": ownable,
        "shortlist_ownable": ownable,
        "surface": NOT_OPTIONABLE if not ownable else "PASS",
        "md_status": "HOLD" if not ownable else "PASS",
        "confidence": confidence,
        "rights_unknown": unknown,
        "missing_ownership_fill": missing_own,
        "decision_required": decision,
    }


def decision_required(record: dict[str, Any] | None) -> bool:
    return bool(ownability_query(record)["decision_required"])


def apply_kill_codes(record: dict[str, Any], *, hard: list[str] | None = None, soft: list[str] | None = None) -> dict[str, Any]:
    """Merge kill codes. triggered iff any hard code is present."""
    kill = dict(record.get("kill") or {})
    hard_set = list(dict.fromkeys([*(kill.get("hard") or []), *(hard or [])]))
    soft_set = list(dict.fromkeys([*(kill.get("soft") or []), *(soft or [])]))
    if (record.get("identity") or {}).get("thesis_mismatch") and "K_THESIS_MISMATCH" not in hard_set:
        hard_set.append("K_THESIS_MISMATCH")
    kill["hard"] = [c for c in hard_set if c in HARD_KILL_CODES or c.startswith("K_")]
    kill["soft"] = soft_set
    kill["codes"] = list(dict.fromkeys([*kill["hard"], *kill["soft"]]))
    kill["triggered"] = bool(kill["hard"])
    record["kill"] = kill
    if kill["triggered"] and record.get("confidence") == "empty_stub":
        record.setdefault("ownership", {})["ownable"] = False
        record.setdefault("commercial_gate", {})
        if record["commercial_gate"].get("verdict") == "PASS":
            record["commercial_gate"]["verdict"] = "FAIL"
    return record


def apply_gate_to_rights(record: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    """Map Intermezzo / REMS commercial-gate results onto Asset IP kill codes."""
    hard: list[str] = []
    soft: list[str] = []
    remS = gate.get("teratogen_rems") or {}
    inter = gate.get("intermezzo") or {}
    if remS.get("hard_disqualify"):
        hard.append("K_REG_CAPTURE_DESTROY")
    if inter.get("shaped") and gate.get("verdict") == "FAIL":
        hard.append("K_COM_ELSEWHERE")
        hard.append("K_VALUE_NOT_CAPTURED")
    if gate.get("empty_stub"):
        soft.append("S_LICENSE_MAP_MISSING")
    record = apply_kill_codes(record, hard=hard, soft=soft)
    record["commercial_gate"] = {
        "verdict": gate.get("verdict") or "empty_stub",
        "reason_codes": list(gate.get("reason_codes") or []),
        "notes": gate.get("notes") or "",
    }
    return record
