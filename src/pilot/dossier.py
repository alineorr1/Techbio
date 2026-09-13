"""D1 / IC / PATH dossier: JSON + human Markdown. Economic right unit only."""

from __future__ import annotations

from typing import Any

from src.pilot.ic import build_ic_stub, opp_line_for_markdown
from src.pilot.labels import (
    LABEL_OPP,
    LABEL_RIGHTS_QUEUE,
    assign_label,
    gate_surface_of,
    is_empty_stub,
    path_stub_started,
)
from src.rights.gates import NOT_OPTIONABLE, has_citable_patent_number
from src.rights.query import ownability_query
from src.rights.schema import cmc_of, pathway_505b2_of
from src.rights.store import load_rights

SCHEMA_VERSION = "pilot.d2.v1"

NARRATIVE_LOCK = {
    "unit": "economic_right",
    "unit_note": (
        "The unit of value is an economic right (option / 505(b)(2) / method-of-use), "
        "not a ranked list and not an ownable portfolio."
    ),
    "high_score_is_not_a_buy": True,
    "high_score_is_not_opp": True,
    "empty_stub_is_not_opp": True,
    "pass_language": False,
    "ownable_portfolio_language": False,
    "hypothesis_for_human_review": True,
}


def _rights(asset: dict[str, Any]) -> dict[str, Any]:
    rec = asset.get("rights")
    if isinstance(rec, dict) and rec:
        return rec
    nct = asset.get("nct_id")
    pid = asset.get("programme_id")
    loaded = load_rights(nct_id=nct if nct and str(nct).startswith("NCT") else None, programme_id=pid)
    return loaded or rec or {}


def _grantor(rights: dict[str, Any], asset: dict[str, Any]) -> str | None:
    desk = ((rights.get("modules") or {}).get("asset_ip_desk") or {})
    if desk.get("who_can_grant_rights"):
        return str(desk["who_can_grant_rights"])
    holder = (rights.get("ownership") or {}).get("holder")
    if holder:
        return str(holder)
    counter = rights.get("counterparty") or {}
    if counter.get("holder_name"):
        return str(counter["holder_name"])
    return asset.get("sponsor_name")


def _patents(rights: dict[str, Any]) -> list[str] | None:
    if (rights.get("ip") or {}).get("docket_empty") and not ((rights.get("ip") or {}).get("patent_families")):
        return None
    desk = ((rights.get("modules") or {}).get("asset_ip_desk") or {})
    if desk.get("public_patent_null"):
        return None
    numbers: list[str] = []
    for family in (rights.get("ip") or {}).get("patent_families") or []:
        if not isinstance(family, dict):
            continue
        if "adjacent" in str(family.get("title") or "").lower():
            continue
        for raw in family.get("publication_numbers") or []:
            if raw:
                numbers.append(str(raw))
    return numbers or None


def _exclusivity(path: dict[str, Any]) -> dict[str, Any]:
    windows = path.get("exclusivity_windows") or []
    return {
        "status": "unknown" if not windows else "listed",
        "windows": windows,
        "note": "unknown OK if marked" if not windows else None,
    }


def build_dossier(
    asset: dict[str, Any],
    *,
    label_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rights = _rights(asset)
    empty = is_empty_stub(asset, rights)
    labels = label_row or assign_label(asset, rights=rights)
    if empty and labels.get("label") == LABEL_OPP:
        labels = {
            **labels,
            "label": LABEL_RIGHTS_QUEUE,
            "triage": "keep",
            "human_fill": False,
            "note": "Empty rights are RIGHTS_QUEUE, never OPP. OPP is not invented from score.",
        }
    pre = asset.get("pre_pass") or {}
    clf = asset.get("classification") or {}
    cmc = asset.get("cmc") if isinstance(asset.get("cmc"), dict) else cmc_of(rights)
    path = (
        asset.get("pathway_505b2")
        if isinstance(asset.get("pathway_505b2"), dict)
        else pathway_505b2_of(rights)
    )
    own = ownability_query(rights) if rights else {}
    started = path_stub_started(asset, rights)
    display = asset.get("primary_display_id") or asset.get("nct_id") or asset.get("eu_ct")
    desk_mod = ((rights.get("modules") or {}).get("asset_ip_desk") or {})
    next_diligence = desk_mod.get("next_diligence_step")
    stop = {
        "mode": clf.get("failure_mode"),
        "classification": clf.get("failure_mode"),
        "rule_fired": clf.get("rule_fired"),
        "notes": clf.get("notes"),
        "overall_status": asset.get("overall_status"),
        "why_stopped": asset.get("why_stopped"),
        "enrolment": asset.get("enrolment"),
    }
    rights_block = {
        "ownable": False if empty else bool((rights.get("ownership") or {}).get("ownable")),
        "optionable": False,
        "desk_classification": rights.get("desk_classification") or asset.get("desk_classification"),
        "kill_codes": list((rights.get("kill") or {}).get("codes") or own.get("kill_codes") or []),
        "hard_codes": list((rights.get("kill") or {}).get("hard") or []),
        "soft_codes": list((rights.get("kill") or {}).get("soft") or []),
        "patents": _patents(rights),
        "grantor": _grantor(rights, asset),
        "confidence": rights.get("confidence") or "empty_stub",
        "empty_stub": empty,
        "has_citable_ip": has_citable_patent_number(rights),
    }
    path_block = {
        "started": started,
        "cmc": cmc or {"confidence": "empty_stub", "notes": "unknown"},
        "pathway_505b2": path or {"pathway": "unknown", "confidence": "empty_stub"},
        "exclusivity": _exclusivity(path or {}),
        "unknown_ok_if_marked": True,
    }
    ic = build_ic_stub(
        asset=asset,
        labels=labels,
        rights=rights_block,
        stop=stop,
        path=path_block,
        empty_stub=empty,
        buyer_class=asset.get("sponsor_class"),
        next_diligence=next_diligence if isinstance(next_diligence, str) else None,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "narrative_lock": NARRATIVE_LOCK,
        "label": labels.get("label"),
        "triage": labels.get("triage"),
        "human_fill": bool(labels.get("human_fill")),
        "auto_walk": bool(labels.get("auto_walk")),
        "label_note": labels.get("note"),
        "registry": {
            "nct_id": asset.get("nct_id") if str(asset.get("nct_id") or "").startswith("NCT") else None,
            "programme_id": asset.get("programme_id"),
            "primary_display_id": display,
            "eu_ct": asset.get("eu_ct"),
            "eudract": ((rights.get("identity") or {}).get("eudract")),
            "source": asset.get("source") or "ctg",
        },
        "stop": stop,
        "rights": rights_block,
        "path": path_block,
        "score": {
            "score": (asset.get("score") or {}).get("score"),
            "arithmetic": (asset.get("score") or {}).get("arithmetic"),
            "pre_pass": {
                "verdict": pre.get("verdict"),
                "surface": pre.get("surface") or gate_surface_of(asset, rights),
                "optionable": False,
                "shortlist_ownable": False,
                "md_status": pre.get("md_status"),
                "reason_codes": pre.get("reason_codes") or [],
            },
            "gate_surface": gate_surface_of(asset, rights) or NOT_OPTIONABLE,
            "high_score_is_not_buy": True,
            "high_score_is_not_opp": True,
        },
        "sources": asset.get("sources") or {},
        "links": asset.get("links") or [],
        "ic_stub": ic,
        "title": asset.get("brief_title") or asset.get("official_title"),
        "sponsor_name": asset.get("sponsor_name"),
        "indication": asset.get("indication_label") or asset.get("indication"),
    }


def render_markdown(dossier: dict[str, Any]) -> str:
    reg = dossier.get("registry") or {}
    stop = dossier.get("stop") or {}
    rights = dossier.get("rights") or {}
    path = dossier.get("path") or {}
    score = dossier.get("score") or {}
    pre = score.get("pre_pass") or {}
    ic = dossier.get("ic_stub") or {}
    cmc = path.get("cmc") or {}
    p505 = path.get("pathway_505b2") or {}
    patents = rights.get("patents")
    patent_line = "null (none found / empty docket)" if patents is None else ", ".join(patents) or "null"
    enrol = stop.get("enrolment")
    if isinstance(enrol, dict):
        enrol_line = f"{enrol.get('count', '—')} ({str(enrol.get('type') or 'unknown').lower()})"
    else:
        enrol_line = str(enrol or "—")
    display = reg.get("primary_display_id") or reg.get("nct_id") or reg.get("eu_ct") or "unknown"
    lines = [
        f"# Dossier {display}",
        "",
        f"**{dossier.get('title') or display}**",
        "",
        "## Narrative lock",
        "",
        "- Unit of value: **economic right** (option / 505(b)(2) / method-of-use), not a ranked buy list.",
        "- A high triage score is **not** a recommendation to buy and does **not** make an asset OPP.",
        (
            "- Empty rights are **NOT OPTIONABLE**. This note never uses PASS / ownable-portfolio language."
            if rights.get("empty_stub")
            else "- This note never uses PASS / ownable-portfolio language. Filled desk close is not an empty-rights row."
        ),
        "- Hypothesis for human review only.",
        "",
        "## Labels (T2)",
        "",
        f"- Label: `{dossier.get('label')}`",
        f"- Triage: `{dossier.get('triage')}`",
        f"- Human-fill handoff: `{'yes' if dossier.get('human_fill') else 'no'}`",
        f"- Auto-WALK: `{'yes' if dossier.get('auto_walk') else 'no'}`",
        f"- Note: {dossier.get('label_note') or '—'}",
        opp_line_for_markdown(
            empty_stub=bool(rights.get("empty_stub")),
            not_opp_reason=ic.get("not_opp_reason"),
        ),
        "",
        "## Registry",
        "",
        f"- NCT: {reg.get('nct_id') or '—'}",
        f"- EU CT: {reg.get('eu_ct') or '—'}",
        f"- programme_id: `{reg.get('programme_id') or '—'}`",
        f"- source: {reg.get('source') or '—'}",
        "",
        "## Stop / classification",
        "",
        f"- Mode: {stop.get('mode') or '—'}",
        f"- Status: {stop.get('overall_status') or '—'}",
        f"- Why stopped: {stop.get('why_stopped') or 'Not stated.'}",
        f"- Enrolment: {enrol_line}",
        f"- Rule: {stop.get('rule_fired') or '—'}",
        "",
        "## Rights stub",
        "",
        f"- Ownable: `{rights.get('ownable')}`",
        f"- Desk: `{rights.get('desk_classification') or '—'}`",
        f"- Kill codes: {', '.join(rights.get('kill_codes') or []) or '—'}",
        f"- Patents: {patent_line}",
        f"- Grantor: {rights.get('grantor') or '—'}",
        f"- Confidence: `{rights.get('confidence')}`",
        f"- Empty stub: `{rights.get('empty_stub')}`",
        "",
        "## PATH stubs (CMC / 505(b)(2) / exclusivity)",
        "",
        f"- PATH started: `{path.get('started')}` (unknown is OK if marked)",
        f"- CMC confidence: `{cmc.get('confidence') or 'empty_stub'}`"
        + (f" — {cmc.get('notes')}" if cmc.get("notes") else " — fields unknown"),
        f"- 505(b)(2) pathway: `{p505.get('pathway') or 'unknown'}`"
        f" (confidence `{p505.get('confidence') or 'empty_stub'}`)",
        f"- Exclusivity: `{(path.get('exclusivity') or {}).get('status') or 'unknown'}`",
        "",
        "## Score / pre-PASS / gate",
        "",
        f"- Score: {score.get('score') if score.get('score') is not None else 'unknown (marked)'}",
        f"- Gate surface: **{score.get('gate_surface') or NOT_OPTIONABLE}**",
        f"- pre_pass surface: `{pre.get('surface') or NOT_OPTIONABLE}`",
        f"- Optionable: `false`",
        f"- High score ≠ buy; high score ≠ OPP.",
        "",
        "## IC (half-page)",
        "",
        f"- Stop: { (ic.get('stop') or {}).get('mode') or stop.get('mode') or '—' }"
        f" / {(ic.get('stop') or {}).get('status') or stop.get('overall_status') or '—'}"
        f" — {(ic.get('stop') or {}).get('why') or stop.get('why_stopped') or 'Not stated.'}",
        f"- Desk: `{(ic.get('desk') or {}).get('label') or dossier.get('label')}`"
        f" · `{(ic.get('desk') or {}).get('disposition') or rights.get('desk_classification') or '—'}`"
        f" · kill codes: {', '.join((ic.get('desk') or {}).get('kill_codes') or rights.get('kill_codes') or []) or '—'}",
        f"- Grantor / IP: {(ic.get('grantor_ip') or {}).get('one_liner') or 'null'}",
        f"- PATH: `{(ic.get('path') or {}).get('readiness') or 'unknown'}`"
        f" — CMC `{(ic.get('path') or {}).get('cmc_confidence') or cmc.get('confidence') or 'empty_stub'}`;"
        f" 505(b)(2) `{(ic.get('path') or {}).get('pathway_505b2') or p505.get('pathway') or 'unknown'}`;"
        f" exclusivity `{(ic.get('path') or {}).get('exclusivity') or 'unknown'}`"
        " (unknown OK if marked)",
        f"- Recommendation (`{ic.get('recommendation_kind') or 'HOLD'}`): {ic.get('recommendation')}",
        f"- Not OPP: {ic.get('not_opp_reason') or 'not opp_eligible'}",
        f"- Buyer class: {ic.get('buyer_class') or 'null'}",
        f"- Next step: {ic.get('next_step') or '—'}",
        f"- {ic.get('note')}",
        "",
        "## Sources",
        "",
    ]
    for key, value in (dossier.get("sources") or {}).items():
        lines.append(f"- {key}: `{value}`")
    if not dossier.get("sources"):
        lines.append("- (none listed)")
    lines.append("")
    return "\n".join(lines)
