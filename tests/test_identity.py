"""Programme identity: union-find merge and NCT ↔ EU CT dedup."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.identity.programme import (
    IdentityStore,
    UnionFind,
    identifiers_from_ctis_retrieve,
    identifiers_from_nct,
    merge_identifier_groups,
    programme_id_for,
)
from src.paths import ROOT

FIXTURES = ROOT / "tests" / "fixtures" / "ctis"

SMOKE_NORMALIZED = ["2017-004309-41", "2024-518143-38-00", "NCT03693677"]
SMOKE_PROGRAMME_ID = "p_" + hashlib.sha256("|".join(SMOKE_NORMALIZED).encode()).hexdigest()[:16]


def load_retrieve(name: str = "retrieve_2024-518143-38-00.json") -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_crosswalk_paths_on_live_smoke_fixture():
    payload = load_retrieve()
    ids = identifiers_from_ctis_retrieve(payload)
    assert ids["eu_ct"] == ["2024-518143-38-00"]
    assert ids["nct"] == ["NCT03693677"]
    assert ids["eudract"] == ["2017-004309-41"]
    assert ids["who_utn"] == []
    assert programme_id_for(ids) == SMOKE_PROGRAMME_ID


def test_programme_id_formula():
    assert programme_id_for({"nct": ["NCT03693677"], "eu_ct": [], "eudract": [], "who_utn": [], "primary_registry": []}) == (
        "p_" + hashlib.sha256(b"NCT03693677").hexdigest()[:16]
    )
    assert programme_id_for(SMOKE_NORMALIZED) == SMOKE_PROGRAMME_ID


def test_union_find_merges_overlapping_ids():
    uf = UnionFind()
    uf.union_all(["NCT03693677", "2024-518143-38-00"])
    uf.union_all(["NCT03693677", "2017-004309-41"])
    assert uf.find("2024-518143-38-00") == uf.find("2017-004309-41")


def test_w1_k4_one_programme_id_for_nct_and_eu_ct(tmp_path: Path):
    payload = load_retrieve()
    store = IdentityStore(tmp_path)
    first = store.upsert(identifiers_from_nct("NCT03693677"), source="ctg", native_id="NCT03693677")
    second = store.upsert(
        identifiers_from_ctis_retrieve(payload),
        source="ctis",
        native_id="2024-518143-38-00",
    )
    assert first["programme_id"] != second["programme_id"]
    programmes = store.all()
    assert len(programmes) == 1
    record = programmes[0]
    assert record["programme_id"] == SMOKE_PROGRAMME_ID
    assert record["normalized_ids"] == SMOKE_NORMALIZED
    assert record["ids"]["nct"] == ["NCT03693677"]
    assert record["ids"]["eu_ct"] == ["2024-518143-38-00"]
    assert record["ids"]["eudract"] == ["2017-004309-41"]
    assert {m["source"] for m in record["members"]} == {"ctg", "ctis"}
    files = list(tmp_path.glob("p_*.json"))
    assert len(files) == 1
    assert files[0].name == f"{SMOKE_PROGRAMME_ID}.json"
    # nct-only file must not remain after merge
    leftover = [
        path
        for path in files
        if json.loads(path.read_text())["normalized_ids"] == ["NCT03693677"]
    ]
    assert leftover == []


def test_merge_identifier_groups_collapses_split_records():
    payload = load_retrieve()
    groups = [
        identifiers_from_nct("NCT03693677"),
        identifiers_from_ctis_retrieve(payload),
    ]
    merged = merge_identifier_groups(groups)
    assert len(merged) == 1
    assert merged[0]["programme_id"] == SMOKE_PROGRAMME_ID


def test_null_nct_is_skipped():
    payload = load_retrieve("retrieve_2025-523076-23-00.json")
    ids = identifiers_from_ctis_retrieve(payload)
    assert ids["nct"] == []
    assert ids["eu_ct"] == ["2025-523076-23-00"]
