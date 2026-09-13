"""Persist wave1.rights.v0 under data/derived/rights/{programme_id}.json.

Empty attach is cheap and must not block ingest/identity. Fill is a separate stub.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.db import dump_json, load_json
from src.paths import RIGHTS_DIR, ensure_dirs
from src.rights.schema import RightsRecord, empty_rights, utc_now


def rights_dir_for_identity(identity_root: Path) -> Path:
    """Keep test tmp identity trees isolated from repo data/derived/rights."""
    if identity_root.name == "identity":
        return identity_root.parent / "rights"
    return identity_root / "rights"


def rights_path(programme_id: str, root: Path | None = None) -> Path:
    return (root or RIGHTS_DIR) / f"{programme_id}.json"


def load_rights(programme_id: str, root: Path | None = None) -> dict[str, Any] | None:
    path = rights_path(programme_id, root)
    if not path.exists():
        return None
    return load_json(path)


def write_rights(record: dict[str, Any], root: Path | None = None) -> Path:
    ensure_dirs()
    directory = root or RIGHTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    validated = RightsRecord.model_validate(record).model_dump()
    if validated.get("confidence") == "empty_stub" and validated.get("commercial_gate", {}).get("verdict") == "PASS":
        validated["commercial_gate"]["verdict"] = "empty_stub"
        validated["commercial_gate"].setdefault("reason_codes", []).append("EMPTY_RIGHTS_NOT_OWNABLE")
    path = directory / f"{validated['programme_id']}.json"
    dump_json(path, validated)
    return path


def attach_empty_rights(
    programme_id: str,
    root: Path | None = None,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Write an empty rights stub if missing. Never implies ownability."""
    directory = root or RIGHTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{programme_id}.json"
    if path.exists() and not overwrite:
        existing = load_json(path)
        if existing.get("confidence") == "empty_stub" and existing.get("commercial_gate", {}).get("verdict") == "PASS":
            existing["commercial_gate"]["verdict"] = "empty_stub"
            write_rights(existing, root=directory)
        return existing
    record = empty_rights(programme_id, updated_at=utc_now())
    write_rights(record, root=directory)
    return record


def merge_sponsor_entity(programme_id: str, sponsor_entity: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    record = load_rights(programme_id, root) or empty_rights(programme_id)
    record["sponsor_entity"] = {**(record.get("sponsor_entity") or {}), **sponsor_entity}
    record["updated_at"] = utc_now()
    write_rights(record, root=root)
    return record


def rights_for_nct(nct: str, store: Any | None = None) -> dict[str, Any]:
    """Load attached rights for an NCT, or an empty stub keyed by programme_id."""
    from src.identity.programme import IdentityStore, identifiers_from_nct, programme_id_for

    identity = store or IdentityStore()
    rec = identity.lookup(nct) if hasattr(identity, "lookup") else None
    pid = (rec or {}).get("programme_id") or programme_id_for(identifiers_from_nct(nct))
    return load_rights(pid) or empty_rights(pid)


def attach_empty_rights_safe(programme_id: str, identity_root: Path | None = None) -> dict[str, Any] | None:
    """Identity/ingest hook. Failures never raise to the caller."""
    try:
        root = rights_dir_for_identity(identity_root) if identity_root is not None else None
        return attach_empty_rights(programme_id, root=root)
    except Exception:
        return None
