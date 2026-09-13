"""Cross-registry programme identity (Wave-1).

Collect nct / eu_ct / eudract / who_utn / primary_registry, normalize, sort,
then ``programme_id = "p_" + sha256("|".join(ids))[:16]``.

Records that share any identifier are merged with union-find so NCT ↔ EU CT
crosswalks collapse to one programme_id. Persistence is
``data/derived/identity/{programme_id}.json``.

This module is ingest/identity only. It does not call classify, score, or serve.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.db import dump_json, load_json
from src.paths import IDENTITY_DIR, ensure_dirs

SCHEMA_VERSION = "wave1.identity.v1"
ID_KINDS = ("nct", "eu_ct", "eudract", "who_utn", "primary_registry")

_NCT_RE = re.compile(r"^(?:NCT)?(\d{8})$", re.IGNORECASE)
_EU_CT_RE = re.compile(r"^\d{4}-\d{6}-\d{2}-\d{2}$")
_EUDRACT_RE = re.compile(r"^\d{4}-\d{6}-\d{2}$")


def nested(d: Any, *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def empty_ids() -> dict[str, list[str]]:
    return {kind: [] for kind in ID_KINDS}


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_nct(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    match = _NCT_RE.match(text)
    if match:
        return f"NCT{match.group(1)}"
    return text.upper()


def normalize_eu_ct(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    return text


def normalize_eudract(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    return text


def normalize_who_utn(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    return text.upper()


def normalize_primary_registry(value: Any) -> str | None:
    return _clean(value)


_NORMALIZERS = {
    "nct": normalize_nct,
    "eu_ct": normalize_eu_ct,
    "eudract": normalize_eudract,
    "who_utn": normalize_who_utn,
    "primary_registry": normalize_primary_registry,
}


def normalize_id(kind: str, value: Any) -> str | None:
    fn = _NORMALIZERS.get(kind)
    if fn is None:
        return _clean(value)
    return fn(value)


def collect_normalized(ids: Mapping[str, Sequence[str]] | Iterable[str]) -> list[str]:
    found: set[str] = set()
    if isinstance(ids, Mapping):
        for kind in ID_KINDS:
            for raw in ids.get(kind) or []:
                normalized = normalize_id(kind, raw)
                if normalized:
                    found.add(normalized)
    else:
        for raw in ids:
            text = _clean(raw)
            if text:
                found.add(text)
    return sorted(found)


def programme_id_for(ids: Mapping[str, Sequence[str]] | Iterable[str]) -> str:
    normalized = collect_normalized(ids)
    if not normalized:
        raise ValueError("programme_id requires at least one identifier")
    digest = hashlib.sha256("|".join(normalized).encode("utf-8")).hexdigest()[:16]
    return f"p_{digest}"


def merge_typed(*groups: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    out = empty_ids()
    for group in groups:
        for kind in ID_KINDS:
            seen = set(out[kind])
            for raw in group.get(kind) or []:
                normalized = normalize_id(kind, raw)
                if normalized and normalized not in seen:
                    out[kind].append(normalized)
                    seen.add(normalized)
            out[kind].sort()
    return out


def _registry_number(item: Any) -> str | None:
    if isinstance(item, str):
        return _clean(item)
    if not isinstance(item, dict):
        return None
    for key in ("number", "id", "code", "value"):
        if item.get(key) not in (None, ""):
            return _clean(item.get(key))
    return None


def _registry_name(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ("registry", "name", "type", "label"):
        if item.get(key):
            return str(item[key])
    return ""


def identifiers_from_ctis_retrieve(payload: dict[str, Any]) -> dict[str, list[str]]:
    """Live-verified CTIS retrieve crosswalk (2024-518143-38-00)."""
    ids = empty_ids()
    eu_ct = normalize_eu_ct(payload.get("ctNumber"))
    if eu_ct:
        ids["eu_ct"].append(eu_ct)

    eudract = normalize_eudract(
        nested(payload, "authorizedApplication", "eudraCt", "eudraCtCode")
    )
    if eudract:
        ids["eudract"].append(eudract)

    nct_obj = nested(
        payload,
        "authorizedApplication",
        "authorizedPartI",
        "trialDetails",
        "clinicalTrialIdentifiers",
        "secondaryIdentifyingNumbers",
        "nctNumber",
    )
    nct_raw = nct_obj.get("number") if isinstance(nct_obj, dict) else nct_obj
    nct = normalize_nct(nct_raw)
    if nct:
        ids["nct"].append(nct)

    extra = (
        nested(
            payload,
            "authorizedApplication",
            "authorizedPartI",
            "trialDetails",
            "clinicalTrialIdentifiers",
            "secondaryIdentifyingNumbers",
            "additionalRegistries",
        )
        or []
    )
    if isinstance(extra, dict):
        extra = [extra]
    for item in extra:
        number = _registry_number(item)
        if not number:
            continue
        name = _registry_name(item).lower()
        if "utn" in name or "who" in name:
            utn = normalize_who_utn(number)
            if utn:
                ids["who_utn"].append(utn)
        else:
            primary = normalize_primary_registry(number)
            if primary:
                ids["primary_registry"].append(primary)

    return merge_typed(ids)


def identifiers_from_nct(nct: str) -> dict[str, list[str]]:
    ids = empty_ids()
    normalized = normalize_nct(nct)
    if normalized:
        ids["nct"].append(normalized)
    return ids


def make_identity(
    ids: Mapping[str, Sequence[str]],
    *,
    sources: Iterable[str] | None = None,
    members: Iterable[Mapping[str, str]] | None = None,
    secondary_only_match: bool = False,
    updated_at: str | None = None,
) -> dict[str, Any]:
    typed = merge_typed(ids)
    normalized = collect_normalized(typed)
    return {
        "schema_version": SCHEMA_VERSION,
        "programme_id": programme_id_for(typed),
        "ids": typed,
        "normalized_ids": normalized,
        "sources": sorted({s for s in (sources or []) if s}),
        "members": [dict(m) for m in members or []],
        "secondary_only_match": bool(secondary_only_match),
        "updated_at": updated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


class UnionFind:
    """Disjoint-set over normalized registry identifiers."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        if item not in self.parent:
            self.parent[item] = item

    def find(self, item: str) -> str:
        self.add(item)
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left: str, right: str) -> str:
        root_l, root_r = self.find(left), self.find(right)
        if root_l != root_r:
            self.parent[root_r] = root_l
        return self.find(left)

    def union_all(self, items: Iterable[str]) -> str | None:
        seq = [item for item in items if item]
        if not seq:
            return None
        root = seq[0]
        for item in seq[1:]:
            root = self.union(root, item)
        return self.find(root)


def merge_identifier_groups(
    groups: Sequence[Mapping[str, Sequence[str]]],
) -> list[dict[str, Any]]:
    """Union-find merge of typed identifier dicts into ProgrammeIdentity records."""
    uf = UnionFind()
    typed_groups = [merge_typed(group) for group in groups]
    for typed in typed_groups:
        uf.union_all(collect_normalized(typed))

    buckets: dict[str, list[int]] = {}
    for index, typed in enumerate(typed_groups):
        normalized = collect_normalized(typed)
        if not normalized:
            continue
        buckets.setdefault(uf.find(normalized[0]), []).append(index)

    merged: list[dict[str, Any]] = []
    for indexes in buckets.values():
        typed = merge_typed(*(typed_groups[i] for i in indexes))
        merged.append(make_identity(typed))
    merged.sort(key=lambda rec: rec["programme_id"])
    return merged


class IdentityStore:
    """Disk-backed programme identity set under data/derived/identity/."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or IDENTITY_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self._programmes: dict[str, dict[str, Any]] = {}
        self._id_to_pid: dict[str, str] = {}
        self.load()

    def load(self) -> None:
        self._programmes.clear()
        self._id_to_pid.clear()
        if not self.root.exists():
            return
        for path in sorted(self.root.glob("p_*.json")):
            record = load_json(path)
            pid = record.get("programme_id")
            if not pid:
                continue
            self._programmes[pid] = record
            for nid in record.get("normalized_ids") or []:
                self._id_to_pid[str(nid)] = pid

    def all(self) -> list[dict[str, Any]]:
        return [dict(rec) for rec in sorted(self._programmes.values(), key=lambda r: r["programme_id"])]

    def upsert(
        self,
        ids: Mapping[str, Sequence[str]],
        *,
        source: str,
        native_id: str | None = None,
        secondary_only_match: bool = False,
    ) -> dict[str, Any]:
        typed = merge_typed(ids)
        normalized = collect_normalized(typed)
        if not normalized:
            raise ValueError("cannot upsert a programme with no identifiers")

        overlapping = {self._id_to_pid[n] for n in normalized if n in self._id_to_pid}
        sources = {source}
        members: list[dict[str, str]] = []
        secondary = bool(secondary_only_match)
        for pid in overlapping:
            existing = self._programmes[pid]
            typed = merge_typed(typed, existing.get("ids") or {})
            sources.update(existing.get("sources") or [])
            secondary = secondary or bool(existing.get("secondary_only_match"))
            for member in existing.get("members") or []:
                if member not in members:
                    members.append(dict(member))

        if native_id:
            member = {"source": source, "native_id": native_id}
            if member not in members:
                members.append(member)

        record = make_identity(
            typed,
            sources=sources,
            members=members,
            secondary_only_match=secondary,
        )
        new_pid = record["programme_id"]

        stale = [pid for pid in overlapping if pid != new_pid]
        for pid in stale:
            path = self.root / f"{pid}.json"
            if path.exists():
                path.unlink()
            self._programmes.pop(pid, None)

        dump_json(self.root / f"{new_pid}.json", record)
        self._programmes[new_pid] = record
        for nid in record["normalized_ids"]:
            self._id_to_pid[nid] = new_pid
        from src.rights.store import attach_empty_rights_safe

        attach_empty_rights_safe(new_pid, identity_root=self.root, identity_record=record)
        return record

    def lookup(self, native_id: str) -> dict[str, Any] | None:
        """Resolve a registry id (NCT, EU CT, …) to a stored programme record."""
        keys = {str(native_id).strip()}
        for kind in ID_KINDS:
            normalized = normalize_id(kind, native_id)
            if normalized:
                keys.add(normalized)
        for key in keys:
            pid = self._id_to_pid.get(key)
            if pid and pid in self._programmes:
                return dict(self._programmes[pid])
        return None

    def programme_id_for_native(self, native_id: str) -> str | None:
        rec = self.lookup(native_id)
        return None if rec is None else rec.get("programme_id")


def write_identity(record: Mapping[str, Any], root: Path | None = None) -> Path:
    ensure_dirs()
    directory = root or IDENTITY_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['programme_id']}.json"
    dump_json(path, record)
    from src.rights.store import attach_empty_rights_safe

    attach_empty_rights_safe(
        str(record["programme_id"]),
        identity_root=directory,
        identity_record=dict(record),
    )
    return path


def load_identity(programme_id: str, root: Path | None = None) -> dict[str, Any]:
    directory = root or IDENTITY_DIR
    return load_json(directory / f"{programme_id}.json")
