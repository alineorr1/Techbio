"""Persist wave-1b.rights-stub.v1.

Content PK is nct_id when present (`data/derived/rights/NCT….json`).
EU-only / no-NCT records use programme_id. Clustering stays on the existing
identity graph — no second cluster.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.db import dump_json, load_json
from src.paths import RIGHTS_DIR, ensure_dirs
from src.rights.schema import (
    RightsRecord,
    assert_empty_stub_not_ownable,
    content_key,
    empty_rights,
    utc_now,
)


def rights_dir_for_identity(identity_root: Path) -> Path:
    """Keep test tmp identity trees isolated from repo data/derived/rights."""
    if identity_root.name == "identity":
        return identity_root.parent / "rights"
    return identity_root / "rights"


def rights_path(
    programme_id: str | None = None,
    root: Path | None = None,
    *,
    nct_id: str | None = None,
) -> Path:
    key = content_key(nct_id=nct_id, programme_id=programme_id or "p_unknown")
    return (root or RIGHTS_DIR) / f"{key}.json"


def load_rights(
    key: str | None = None,
    root: Path | None = None,
    *,
    nct_id: str | None = None,
    programme_id: str | None = None,
) -> dict[str, Any] | None:
    directory = root or RIGHTS_DIR
    candidates: list[Path] = []
    if nct_id:
        candidates.append(directory / f"{nct_id}.json")
    if key:
        candidates.append(directory / f"{key}.json")
    if programme_id:
        candidates.append(directory / f"{programme_id}.json")
    for path in candidates:
        if path.exists():
            return load_json(path)
    return None


def write_rights(record: dict[str, Any], root: Path | None = None) -> Path:
    ensure_dirs()
    directory = root or RIGHTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    validated = RightsRecord.model_validate(record).model_dump()
    if validated.get("confidence") == "empty_stub":
        validated["ownership"]["ownable"] = False
        if validated.get("commercial_gate", {}).get("verdict") == "PASS":
            validated["commercial_gate"]["verdict"] = "empty_stub"
        validated["process"]["outreach"] = "none"
        assert_empty_stub_not_ownable(validated)
    key = content_key(nct_id=validated.get("nct_id"), programme_id=validated["programme_id"])
    path = directory / f"{key}.json"
    dump_json(path, validated)
    return path


def attach_empty_rights(
    programme_id: str,
    root: Path | None = None,
    *,
    nct_id: str | None = None,
    overwrite: bool = False,
    eu_ct: str | None = None,
    eudract: str | None = None,
) -> dict[str, Any]:
    """Write an empty rights stub if missing. Always create, even if taxonomy empty."""
    directory = root or RIGHTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = rights_path(programme_id, directory, nct_id=nct_id)
    if path.exists() and not overwrite:
        existing = load_json(path)
        if existing.get("confidence") == "empty_stub":
            existing.setdefault("ownership", {})["ownable"] = False
            if existing.get("commercial_gate", {}).get("verdict") == "PASS":
                existing["commercial_gate"]["verdict"] = "empty_stub"
            write_rights(existing, root=directory)
        return existing
    record = empty_rights(programme_id, nct_id=nct_id, updated_at=utc_now())
    record["identity"]["eu_ct"] = eu_ct
    record["identity"]["eudract"] = eudract
    write_rights(record, root=directory)
    return record


def merge_sponsor_entity(
    programme_id: str,
    sponsor_entity: dict[str, Any],
    root: Path | None = None,
    *,
    nct_id: str | None = None,
) -> dict[str, Any]:
    record = load_rights(nct_id=nct_id, programme_id=programme_id, root=root) or empty_rights(
        programme_id, nct_id=nct_id
    )
    entity = {**((record.get("counterparty") or {}).get("sponsor_entity") or {}), **sponsor_entity}
    record.setdefault("counterparty", {})["sponsor_entity"] = entity
    record["counterparty"]["holder_name"] = entity.get("legal_name") or entity.get("name")
    record["counterparty"]["holder_status"] = entity.get("resolution_status") or "not_yet_fetched"
    record["counterparty"]["present"] = entity.get("resolution_status") == "resolved"
    record["updated_at"] = utc_now()
    write_rights(record, root=root)
    return record


def rights_for_nct(nct: str, store: Any | None = None) -> dict[str, Any]:
    """Load attached rights for an NCT, or an empty stub clustered by programme_id."""
    from src.identity.programme import IdentityStore, identifiers_from_nct, programme_id_for

    identity = store or IdentityStore()
    rec = identity.lookup(nct) if hasattr(identity, "lookup") else None
    pid = (rec or {}).get("programme_id") or programme_id_for(identifiers_from_nct(nct))
    return load_rights(nct_id=nct, programme_id=pid) or empty_rights(pid, nct_id=nct)


def attach_empty_rights_safe(
    programme_id: str,
    identity_root: Path | None = None,
    identity_record: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Identity/ingest hook. One stub per NCT; EU-only uses programme_id. Never raises."""
    try:
        root = rights_dir_for_identity(identity_root) if identity_root is not None else None
        ids = (identity_record or {}).get("ids") or {}
        ncts = list(ids.get("nct") or [])
        eu_ct = (ids.get("eu_ct") or [None])[0]
        eudract = (ids.get("eudract") or [None])[0]
        if ncts:
            last = None
            for nct in ncts:
                last = attach_empty_rights(
                    programme_id,
                    root=root,
                    nct_id=nct,
                    eu_ct=eu_ct,
                    eudract=eudract,
                )
            return last
        return attach_empty_rights(programme_id, root=root, eu_ct=eu_ct, eudract=eudract)
    except Exception:
        return None
