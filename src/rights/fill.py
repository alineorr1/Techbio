"""Async/stub fill path. Default is empty_stub; live keys raise NotConfigured.

Enrich and identity call attach, not this. `python -m src.rights` is the fill CLI.
No network: even with keys the live clients are unwired.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.rights import epo_ops, opencorporates, orange_book, uspto_odp
from src.rights.exceptions import NotConfigured
from src.rights.schema import utc_now
from src.rights.store import attach_empty_rights, load_rights, write_rights

MODULES = (
    uspto_odp,
    epo_ops,
    opencorporates,
    orange_book,
)


def _merge_module(record: dict[str, Any], section: dict[str, Any]) -> None:
    name = section.get("module") or "unknown"
    record.setdefault("modules", {})[name] = section
    families = section.get("patent_families")
    ip = record.setdefault("ip", {})
    if families:
        existing = ip.setdefault("patent_families", [])
        existing.extend(families)
        ip["docket_empty"] = False
    entity = section.get("sponsor_entity")
    if entity and entity.get("resolution_status") == "resolved":
        cp = record.setdefault("counterparty", {})
        cp["sponsor_entity"] = {**(cp.get("sponsor_entity") or {}), **entity}
        cp["present"] = True
        cp["holder_status"] = "resolved"
        cp["holder_name"] = entity.get("legal_name") or entity.get("name")
    if section.get("rld_ref") or section.get("listed_drug_ref"):
        path = record.setdefault("ind_regulatory", {}).setdefault("pathway_505b2", {})
        ob = ip.setdefault("orange_book", {})
        if section.get("rld_ref"):
            path["rld_ref"] = section["rld_ref"]
            ob["rld_ref"] = section["rld_ref"]
        if section.get("listed_drug_ref"):
            path["listed_drug_ref"] = section["listed_drug_ref"]
            ob["listed_drug_ref"] = section["listed_drug_ref"]
            ip["listed_drug_ref"] = section["listed_drug_ref"]
        if section.get("exclusivity_windows"):
            path["exclusivity_windows"] = section["exclusivity_windows"]
            ob["exclusivity_windows"] = section["exclusivity_windows"]
        if section.get("orange_book_url"):
            path["orange_book_url"] = section["orange_book_url"]
            ob["url"] = section["orange_book_url"]


def fill_rights(
    programme_id: str,
    *,
    live: bool = False,
    root: Path | None = None,
    nct_id: str | None = None,
) -> dict[str, Any]:
    """Fill or re-stub modules. live=False never raises; live=True raises NotConfigured per module."""
    record = load_rights(nct_id=nct_id, programme_id=programme_id, root=root) or attach_empty_rights(
        programme_id, root=root, nct_id=nct_id
    )
    errors: list[str] = []
    for mod in MODULES:
        try:
            section = mod.fetch(live=live)
        except NotConfigured as exc:
            if live:
                raise
            section = mod.stub_section()
            errors.append(str(exc))
        _merge_module(record, section)
    ip = record.get("ip") or {}
    filled = bool(ip.get("patent_families") or ip.get("listed_drug_ref"))
    if not filled:
        record["confidence"] = "empty_stub"
        record.setdefault("ownership", {})["ownable"] = False
        gate = record.setdefault("commercial_gate", {})
        if gate.get("verdict") == "PASS":
            gate["verdict"] = "empty_stub"
        record["notes"] = "Empty rights stub. Does not imply ownability."
        record.setdefault("process", {})["outreach"] = "none"
    record["updated_at"] = utc_now()
    if errors:
        record.setdefault("modules", {})["_errors"] = {"messages": errors}
    write_rights(record, root=root)
    return record


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Wave-1b rights stubs (empty attach / optional live raise)")
    parser.add_argument("--programme-id", action="append", dest="programme_ids")
    parser.add_argument("--nct", dest="nct_id", default=None)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Attempt live fill. Raises NotConfigured without keys; live clients are not wired.",
    )
    args = parser.parse_args(argv)
    ids = args.programme_ids or []
    if not ids:
        print("[rights] no programme_id; nothing to fill")
        return
    for pid in ids:
        rec = fill_rights(pid, live=args.live, nct_id=args.nct_id)
        print(f"[rights] {pid} confidence={rec.get('confidence')}")
