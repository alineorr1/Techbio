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
    if families:
        existing = record.setdefault("patent_families", [])
        existing.extend(families)
    entity = section.get("sponsor_entity")
    if entity and entity.get("resolution_status") == "resolved":
        record["sponsor_entity"] = {**(record.get("sponsor_entity") or {}), **entity}
    if section.get("rld_ref") or section.get("listed_drug_ref"):
        path = record.setdefault("pathway_505b2", {})
        if section.get("rld_ref"):
            path["rld_ref"] = section["rld_ref"]
        if section.get("listed_drug_ref"):
            path["listed_drug_ref"] = section["listed_drug_ref"]
            record["listed_drug_ref"] = section["listed_drug_ref"]
        if section.get("exclusivity_windows"):
            path["exclusivity_windows"] = section["exclusivity_windows"]
        if section.get("orange_book_url"):
            path["orange_book_url"] = section["orange_book_url"]


def fill_rights(
    programme_id: str,
    *,
    live: bool = False,
    root: Path | None = None,
) -> dict[str, Any]:
    """Fill or re-stub modules. live=False never raises; live=True raises NotConfigured per module."""
    record = load_rights(programme_id, root) or attach_empty_rights(programme_id, root=root)
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
    filled = bool(record.get("patent_families") or record.get("listed_drug_ref"))
    if not filled:
        record["confidence"] = "empty_stub"
        gate = record.setdefault("commercial_gate", {})
        if gate.get("verdict") == "PASS":
            gate["verdict"] = "empty_stub"
        record["notes"] = "Empty rights stub. Does not imply ownability."
    record["updated_at"] = utc_now()
    if errors:
        record.setdefault("modules", {})["_errors"] = {"messages": errors}
    write_rights(record, root=root)
    return record


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Wave-1b rights stubs (empty attach / optional live raise)")
    parser.add_argument("--programme-id", action="append", dest="programme_ids")
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
        rec = fill_rights(pid, live=args.live)
        print(f"[rights] {pid} confidence={rec.get('confidence')}")
