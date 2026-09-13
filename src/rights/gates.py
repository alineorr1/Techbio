"""Commercial gates: Intermezzo (K4) and teratogen/REMS table.

Sex-diff / sex-dose alone is never PASS. Empty rights never imply ownability.
Matches are public-label / commercial-shape flags, not biology claims.
"""

from __future__ import annotations

import re
from typing import Any

from src.config import disqualifiers_config, scoring_config
from src.ingest.ctg import nested
from src.rights.schema import empty_rights

SEX_DIFF_ALONE = "SEX_DIFF_ALONE_NOT_PASS"
K4_INTERMEZZO = "K4_INTERMEZZO_NO_PRICING_POWER"
EMPTY_NOT_OWNABLE = "EMPTY_RIGHTS_NOT_OWNABLE"
REMS_CODE = "REMS_TERATOGEN"
TERATOGEN_CODE = "TERATOGEN_LABELED"
NOT_OPTIONABLE = "NOT OPTIONABLE"
NOT_OPTIONABLE_CODE = "NOT_OPTIONABLE"
RIGHTS_UNKNOWN = "RIGHTS_UNKNOWN"
MISSING_OWNERSHIP_FILL = "MISSING_OWNERSHIP_FILL"
WALK_AWAY_WITHDRAWN = "WALK_AWAY_WITHDRAWN"
WALK_AWAY_ZERO_ENROLMENT = "WALK_AWAY_ZERO_ENROLMENT"

RIGHTS_UNKNOWN_CONFIDENCE = frozenset({"", "empty_stub", "rights-unknown"})
UNFILLED_OWNERSHIP_STATUS = frozenset({"", "not_yet_fetched", "unknown"})


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _blob(study: dict[str, Any] | None, extra: list[str] | None = None) -> str:
    study = study or {}
    parts: list[str] = list(extra or [])
    ident = nested(study, "protocolSection", "identificationModule") or {}
    parts.append(str(ident.get("briefTitle") or ""))
    parts.append(str(ident.get("officialTitle") or ""))
    parts.append(str(ident.get("acronym") or ""))
    ints = nested(study, "protocolSection", "armsInterventionsModule", "interventions") or []
    for item in ints:
        if isinstance(item, dict):
            parts.append(str(item.get("name") or ""))
            parts.append(str(item.get("description") or ""))
        else:
            parts.append(str(item))
    return _norm(" ".join(parts))


def _intervention_names(study: dict[str, Any] | None, extra: list[str] | None = None) -> list[str]:
    names = list(extra or [])
    ints = nested(study or {}, "protocolSection", "armsInterventionsModule", "interventions") or []
    for item in ints:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
        elif item:
            names.append(str(item))
    return names


def _has_active_exclusivity(rights: dict[str, Any]) -> bool:
    path = (rights or {}).get("pathway_505b2") or ((rights or {}).get("ind_regulatory") or {}).get("pathway_505b2") or {}
    windows = path.get("exclusivity_windows") or []
    return any(isinstance(w, dict) and w.get("status") == "active" for w in windows)


def _sex_diff(rights: dict[str, Any]) -> bool:
    shape = (rights or {}).get("commercial_shape") or {}
    return bool(shape.get("sex_dose_differentiation") or shape.get("sex_diff_labeling"))


def _cheap_generic_no_power(rights: dict[str, Any]) -> bool:
    shape = (rights or {}).get("commercial_shape") or {}
    generic = shape.get("generic_available")
    pricing = shape.get("pricing_power") or "unknown"
    if _has_active_exclusivity(rights):
        return False
    if generic is True and pricing in {"none", "unknown"}:
        return True
    if pricing == "none" and not _has_active_exclusivity(rights):
        return True
    return False


def rights_unknown(rights: dict[str, Any] | None) -> bool:
    """empty_stub / rights-unknown / missing confidence is not a filled right."""
    conf = str((rights or {}).get("confidence") or "empty_stub").strip().lower()
    return conf in RIGHTS_UNKNOWN_CONFIDENCE


def missing_ownership_fill(rights: dict[str, Any] | None) -> bool:
    """Ownership block absent or still a stub — Asset IP has not filled it."""
    own = (rights or {}).get("ownership")
    if not isinstance(own, dict) or not own:
        return True
    conf = str(own.get("confidence") or "empty_stub").strip().lower()
    status = str(own.get("status") or "not_yet_fetched").strip().lower()
    if conf in RIGHTS_UNKNOWN_CONFIDENCE:
        return True
    if status in UNFILLED_OWNERSHIP_STATUS:
        return True
    return False


def named_intermezzo(study: dict[str, Any] | None, cfg: dict[str, Any] | None = None, extra: list[str] | None = None) -> bool:
    gate = (cfg or disqualifiers_config()).get("intermezzo_gate") or {}
    blob = _blob(study, extra)
    for product in gate.get("named_products") or []:
        for alias in product.get("aliases") or [product.get("name")]:
            token = _norm(str(alias or ""))
            if token and token in blob:
                return True
    return False


def apply_teratogen_rems(
    *,
    study: dict[str, Any] | None = None,
    intervention_names: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return table matches. action is hard_disqualify or strong_downrank."""
    table = (cfg or disqualifiers_config()).get("teratogen_rems") or {}
    default_action = table.get("default_action") or "hard_disqualify"
    blob = _blob(study, intervention_names)
    matches: list[dict[str, Any]] = []
    hard = False
    downrank = False
    codes: list[str] = []
    for entry in table.get("entries") or []:
        aliases = entry.get("aliases") or [entry.get("substance")]
        hit = None
        for alias in aliases:
            token = _norm(str(alias or ""))
            if token and re.search(rf"\b{re.escape(token)}\b", blob):
                hit = token
                break
        if not hit:
            continue
        action = entry.get("action") or default_action
        code = entry.get("reason_code") or REMS_CODE
        rec = {
            "substance": entry.get("substance"),
            "alias": hit,
            "program": entry.get("program"),
            "reason_code": code,
            "action": action,
            "note": entry.get("note") or "Labeled teratogen/REMS. Not a biology-failure claim.",
        }
        matches.append(rec)
        codes.append(code)
        if action == "hard_disqualify":
            hard = True
        else:
            downrank = True
    return {
        "matched": bool(matches),
        "hard_disqualify": hard,
        "strong_downrank": downrank and not hard,
        "matches": matches,
        "reason_codes": codes,
        "note": table.get("note") or "",
    }


def evaluate_commercial_gate(
    *,
    study: dict[str, Any] | None = None,
    rights: dict[str, Any] | None = None,
    intervention_names: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
    scoring_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return verdict + reason codes. Never PASS on empty_stub, rights-unknown, or sex-diff alone."""
    dq = cfg or disqualifiers_config()
    inter = dq.get("intermezzo_gate") or {}
    rights = dict(rights or empty_rights("p_unknown"))
    rems = apply_teratogen_rems(study=study, intervention_names=intervention_names, cfg=dq)
    sex = _sex_diff(rights)
    cheap = _cheap_generic_no_power(rights)
    named = named_intermezzo(study, dq, extra=intervention_names)
    unknown = rights_unknown(rights)
    missing_own = missing_ownership_fill(rights)
    empty = unknown or (rights.get("confidence") or "empty_stub") == "empty_stub"
    k4_code = inter.get("reason_code") or K4_INTERMEZZO
    sex_code = inter.get("sex_diff_alone_reason_code") or SEX_DIFF_ALONE

    codes: list[str] = []
    notes: list[str] = []
    verdict = "empty_stub" if empty else "HOLD"

    if rems["hard_disqualify"]:
        verdict = "FAIL"
        codes.extend(rems["reason_codes"])
        notes.append("REMS/teratogen hard disqualifier (table match, not a biology claim).")
    elif rems["strong_downrank"]:
        codes.extend(rems["reason_codes"])
        notes.append("Labeled teratogen strong downrank (table match, not a biology claim).")

    intermezzo_shaped = named or (sex and cheap)
    if intermezzo_shaped and (cheap or named) and not _has_active_exclusivity(rights):
        verdict = "FAIL"
        if k4_code not in codes:
            codes.append(k4_code)
        notes.append("Intermezzo-shaped: cheap generic / no exclusivity or pricing power is not PASS (K4).")
    elif sex:
        if sex_code not in codes:
            codes.append(sex_code)
        notes.append("Sex-diff / sex-dose alone is not a commercial PASS.")
        if verdict == "PASS":
            verdict = "HOLD"
        if empty and verdict != "FAIL":
            verdict = "empty_stub"

    if empty or unknown:
        if EMPTY_NOT_OWNABLE not in codes:
            codes.append(EMPTY_NOT_OWNABLE)
        if RIGHTS_UNKNOWN not in codes:
            codes.append(RIGHTS_UNKNOWN)
        if NOT_OPTIONABLE_CODE not in codes:
            codes.append(NOT_OPTIONABLE_CODE)
        if verdict == "PASS":
            verdict = "empty_stub" if empty else "HOLD"
        notes.append("Rights confidence is empty_stub / rights-unknown; does not imply ownability.")

    if missing_own:
        if MISSING_OWNERSHIP_FILL not in codes:
            codes.append(MISSING_OWNERSHIP_FILL)
        if NOT_OPTIONABLE_CODE not in codes:
            codes.append(NOT_OPTIONABLE_CODE)
        if verdict == "PASS":
            verdict = "HOLD"
        notes.append("Ownership fill is missing; empty rights are not optionable.")

    ownable_class = (rights.get("right_class") or (rights.get("ip") or {}).get("right_class")) in {
        "option",
        "505(b)(2)",
        "method_of_use",
    }
    pricing = ((rights.get("commercial_shape") or {}).get("pricing_power")) == "present"
    ownership_ownable = bool((rights.get("ownership") or {}).get("ownable"))
    if (
        verdict not in {"FAIL"}
        and not empty
        and not unknown
        and not missing_own
        and ownership_ownable
        and ownable_class
        and (pricing or _has_active_exclusivity(rights))
        and not sex
        and not rems["hard_disqualify"]
        and not rems["strong_downrank"]
        and not named
    ):
        verdict = "PASS"
        notes.append("Resolved economic right with exclusivity or pricing power.")

    if verdict == "PASS" and (
        sex or empty or unknown or missing_own or not ownership_ownable or rems["hard_disqualify"] or intermezzo_shaped
    ):
        verdict = "FAIL" if (rems["hard_disqualify"] or intermezzo_shaped) else "HOLD"

    rules = (scoring_cfg or scoring_config()).get("rules") or {}
    return {
        "verdict": verdict,
        "reason_codes": codes,
        "notes": " ".join(notes).strip(),
        "intermezzo": {
            "named": named,
            "sex_diff": sex,
            "cheap_generic_no_power": cheap,
            "shaped": intermezzo_shaped,
        },
        "teratogen_rems": rems,
        "caps": {
            "intermezzo": float(rules.get("intermezzo_score_cap") or 20),
            "rems_hard": float(rules.get("teratogen_rems_hard_cap") or 10),
            "rems_downrank": float(rules.get("teratogen_rems_downrank_cap") or 25),
            "walk_away": float(rules.get("walk_away_score_cap") or 20),
        },
        "empty_stub": empty,
        "rights_unknown": unknown,
        "missing_ownership_fill": missing_own,
    }


def apply_score_caps(raw_score: float, gate: dict[str, Any]) -> tuple[float, list[str]]:
    """Apply Intermezzo / REMS caps. Does not replace Organon Rule B."""
    caps_applied: list[str] = []
    capped = raw_score
    rems = gate.get("teratogen_rems") or {}
    cap_vals = gate.get("caps") or {}
    if rems.get("hard_disqualify"):
        hard = float(cap_vals.get("rems_hard") or 10)
        if capped > hard:
            codes = ",".join(rems.get("reason_codes") or [REMS_CODE])
            caps_applied.append(f"REMS/teratogen hard disqualifier ({codes}); cap {hard}")
            capped = hard
    elif rems.get("strong_downrank"):
        down = float(cap_vals.get("rems_downrank") or 25)
        if capped > down:
            codes = ",".join(rems.get("reason_codes") or [TERATOGEN_CODE])
            caps_applied.append(f"REMS/teratogen strong downrank ({codes}); cap {down}")
            capped = down
    if gate.get("verdict") == "FAIL" and (gate.get("intermezzo") or {}).get("shaped"):
        ice = float(cap_vals.get("intermezzo") or 20)
        if capped > ice:
            caps_applied.append(f"Intermezzo commercial gate (K4); cap {ice}")
            capped = ice
    return capped, caps_applied


def evaluate_pre_pass(
    *,
    study: dict[str, Any] | None = None,
    rights: dict[str, Any] | None = None,
    intervention_names: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
    scoring_cfg: dict[str, Any] | None = None,
    gate: dict[str, Any] | None = None,
    walk_away_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Hard pre-PASS / shortlist-ownable gate. Empty rights are NOT OPTIONABLE.

    Blind MD stays HOLD when rights are empty or unfilled. Intermezzo (K4 / sex-diff
    alone) and REMS/teratogen table hits also block PASS. This is infra, not a
    claim that any asset is ownable.
    """
    gate = gate or evaluate_commercial_gate(
        study=study,
        rights=rights,
        intervention_names=intervention_names,
        cfg=cfg,
        scoring_cfg=scoring_cfg,
    )
    unknown = bool(gate.get("rights_unknown")) or rights_unknown(rights)
    missing_own = bool(gate.get("missing_ownership_fill")) or missing_ownership_fill(rights)
    empty = bool(gate.get("empty_stub")) or unknown
    remS = gate.get("teratogen_rems") or {}
    inter = gate.get("intermezzo") or {}
    verdict = gate.get("verdict") or ("empty_stub" if empty else "HOLD")
    codes = list(gate.get("reason_codes") or [])
    walk_codes = list(walk_away_codes or [])

    rights_block = empty or unknown or missing_own
    commercial_block = (
        verdict == "FAIL"
        or bool(remS.get("hard_disqualify"))
        or bool(inter.get("shaped"))
        or bool(inter.get("sex_diff"))
    )
    if rights_block:
        if NOT_OPTIONABLE_CODE not in codes:
            codes.append(NOT_OPTIONABLE_CODE)
        if unknown and RIGHTS_UNKNOWN not in codes:
            codes.append(RIGHTS_UNKNOWN)
        if missing_own and MISSING_OWNERSHIP_FILL not in codes:
            codes.append(MISSING_OWNERSHIP_FILL)
        if empty and EMPTY_NOT_OWNABLE not in codes:
            codes.append(EMPTY_NOT_OWNABLE)
        surface = NOT_OPTIONABLE
        md_status = "HOLD"
        if verdict == "PASS":
            verdict = "empty_stub" if empty else "HOLD"
    elif commercial_block:
        surface = "FAIL" if verdict == "FAIL" or remS.get("hard_disqualify") or inter.get("shaped") else "HOLD"
        md_status = "HOLD" if surface == "HOLD" else "FAIL"
        if verdict == "PASS":
            verdict = "FAIL" if remS.get("hard_disqualify") or inter.get("shaped") else "HOLD"
    elif verdict == "PASS":
        surface = "PASS"
        md_status = "PASS"
    else:
        surface = "HOLD"
        md_status = "HOLD"

    optionable = (
        verdict == "PASS"
        and not rights_block
        and not commercial_block
        and bool(((rights or {}).get("ownership") or {}).get("ownable"))
    )
    if not optionable and verdict == "PASS":
        verdict = "HOLD"
        surface = NOT_OPTIONABLE if rights_block else "HOLD"
        md_status = "HOLD"
    shortlist_ownable = optionable and verdict == "PASS"

    return {
        "verdict": verdict,
        "optionable": optionable,
        "shortlist_ownable": shortlist_ownable,
        "surface": surface,
        "md_status": md_status,
        "block_pass": not shortlist_ownable,
        "reason_codes": list(dict.fromkeys([*codes, *walk_codes])),
        "commercial_gate": gate,
        "walk_away_codes": walk_codes,
        "rights_unknown": unknown,
        "missing_ownership_fill": missing_own,
        "empty_stub": empty,
    }
