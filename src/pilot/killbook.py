"""A6: first-class kill-book of locked WALK_AWAY closes. Negative labels are product."""

from __future__ import annotations

from typing import Any

from src.pilot.labels import LABEL_TRIAGE, TRIAGE_DISREGARD, gate_surface_of
from src.rights.codes import DESK_WRITEBACK_NCTS
from src.rights.gates import has_citable_patent_number
from src.rights.schema import cmc_of, pathway_505b2_of
from src.rights.writeback import desk_fills

SCHEMA_VERSION = "pilot.kill-book.v1"

NARRATIVE = (
    "Locked WALK_AWAY closes. Negative labels are product. "
    "These rows are not optionable, not OPP, and not a rights-fill queue. "
    "Economic right unit only — a high triage score does not reopen a kill."
)


def _citations(desk: dict[str, Any], rights: dict[str, Any] | None = None) -> list[str]:
    found: list[str] = []
    for item in desk.get("patents") or []:
        if not isinstance(item, dict):
            continue
        number = item.get("number")
        if number and not item.get("adjacent"):
            found.append(str(number))
    rec = rights or {}
    for family in (rec.get("ip") or {}).get("patent_families") or []:
        if not isinstance(family, dict):
            continue
        title = str(family.get("title") or "").lower()
        if "adjacent" in title:
            continue
        for number in family.get("publication_numbers") or []:
            if number and str(number) not in found:
                found.append(str(number))
    return found


def _rationale(desk: dict[str, Any]) -> str:
    note = (desk.get("patents_note") or desk.get("thesis_reason") or "").strip()
    if note:
        return note.split("\n")[0][:280]
    codes = ", ".join(desk.get("hard") or []) or "WALK_AWAY"
    return f"{desk.get('asset_name') or desk.get('nct_id')}: {codes}. ownable=false. NOT OPTIONABLE."


def kill_row(desk: dict[str, Any], *, asset: dict[str, Any] | None = None) -> dict[str, Any]:
    rights = (asset or {}).get("rights") if asset else None
    citations = _citations(desk, rights if isinstance(rights, dict) else None)
    return {
        "nct_id": desk["nct_id"],
        "asset_name": desk.get("asset_name"),
        "title": desk.get("title") or (asset or {}).get("brief_title"),
        "classification": desk.get("classification") or "WALK_AWAY",
        "label": LABEL_TRIAGE,
        "triage": TRIAGE_DISREGARD,
        "kill_codes": list(desk.get("hard") or []),
        "soft_codes": list(desk.get("soft") or []),
        "rationale": _rationale(desk),
        "citations": citations,
        "grantor": desk.get("who_can_grant"),
        "ownable": False,
        "optionable": False,
        "optionable_candidate": False,
        "gate_surface": gate_surface_of(asset or {}, rights if isinstance(rights, dict) else None)
        if asset
        else "WALK_AWAY",
        "empty_stub": False,
        "opp": False,
        "path_stub_started": bool(
            (desk.get("cmc_note") or "")
            or (asset and ((asset.get("cmc") or {}).get("confidence") not in (None, "empty_stub")))
        ),
        "has_citable_ip": has_citable_patent_number(rights) if isinstance(rights, dict) else bool(citations),
        "cmc_unknown": not (desk.get("cmc_note") or ""),
        "pathway_505b2": pathway_505b2_of(rights).get("pathway") if isinstance(rights, dict) else "unknown",
    }


def build_kill_book(
    *,
    assets: list[dict[str, Any]] | None = None,
    fills: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    by_nct = {str(a.get("nct_id")): a for a in (assets or []) if a.get("nct_id")}
    rows = [kill_row(desk, asset=by_nct.get(desk["nct_id"])) for desk in (fills or desk_fills())]
    return {
        "schema_version": SCHEMA_VERSION,
        "narrative": NARRATIVE,
        "n": len(rows),
        "ncts": [row["nct_id"] for row in rows],
        "desk_writeback_ncts": list(DESK_WRITEBACK_NCTS),
        "n_optionable": 0,
        "n_opp": 0,
        "rows": rows,
    }


def attach_path_unknown(row: dict[str, Any], rights: dict[str, Any] | None) -> dict[str, Any]:
    cmc = cmc_of(rights or {})
    path = pathway_505b2_of(rights or {})
    row["cmc"] = cmc
    row["pathway_505b2"] = path
    return row
