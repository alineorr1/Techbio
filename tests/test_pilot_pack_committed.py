"""Committed sample pack proves the E4/E7/A6 path."""

from pathlib import Path

from src.paths import (
    D3_ROLLUP_PATH,
    KILL_BOOK_PATH,
    PILOT_CTIS_EXAMPLE_DIR,
    PILOT_EXPORT_DIR,
    PILOT_DIR,
    RIGHTS_QUEUE_PATH,
    ROOT,
)
from src.db import load_json
from src.pilot.export import EMPTY_QUEUE_SAMPLE_ID
from src.pilot.ic import EMPTY_RIGHTS_STAY, IC_STATUS
from src.rights.codes import BIOGENE_ELTA_NCT, LINZAGOLIX_NCT
from src.rights.gates import NOT_OPTIONABLE


def test_committed_pack_exists():
    assert (PILOT_DIR / "README.md").is_file()
    assert RIGHTS_QUEUE_PATH.is_file()
    assert KILL_BOOK_PATH.is_file()
    assert (PILOT_EXPORT_DIR / f"{BIOGENE_ELTA_NCT}.json").is_file()
    assert (PILOT_EXPORT_DIR / f"{BIOGENE_ELTA_NCT}.md").is_file()
    assert (PILOT_EXPORT_DIR / f"{LINZAGOLIX_NCT}.json").is_file()
    assert (PILOT_EXPORT_DIR / f"{LINZAGOLIX_NCT}.md").is_file()
    assert (PILOT_EXPORT_DIR / f"{EMPTY_QUEUE_SAMPLE_ID}.json").is_file()
    assert (PILOT_EXPORT_DIR / f"{EMPTY_QUEUE_SAMPLE_ID}.md").is_file()
    assert D3_ROLLUP_PATH.is_file()
    assert (PILOT_CTIS_EXAMPLE_DIR / "2023-599001-99-00.json").is_file()
    assert (PILOT_CTIS_EXAMPLE_DIR / "2023-599001-99-00.md").is_file()
    assert (PILOT_CTIS_EXAMPLE_DIR / "README.md").is_file()


def test_committed_queue_and_kill_book_contract():
    queue = load_json(RIGHTS_QUEUE_PATH)
    assert 30 <= queue["n_queue"] <= 50
    assert queue["n_opp"] == 0
    assert queue.get("n_rights_queue", 0) >= 500
    assert "RIGHTS_QUEUE" in (queue.get("note") or "")
    assert "fill queue" not in (queue.get("note") or "").lower()
    assert all(row["empty_stub"] for row in queue["queue"])
    assert all(row["label"] == "RIGHTS_QUEUE" for row in queue["queue"])
    assert BIOGENE_ELTA_NCT not in [row["nct_id"] for row in queue["queue"]]
    book = load_json(KILL_BOOK_PATH)
    assert book["n"] == 18
    assert book["n_opp"] == 0
    assert any(row["nct_id"] == BIOGENE_ELTA_NCT for row in book["rows"])


def test_committed_dossiers_are_not_opp():
    bio = load_json(PILOT_EXPORT_DIR / f"{BIOGENE_ELTA_NCT}.json")
    assert bio["label"] != "OPP"
    assert bio["score"]["gate_surface"] in {NOT_OPTIONABLE, "WALK_AWAY"}
    assert "economic_right" == bio["narrative_lock"]["unit"]
    ctis = load_json(PILOT_CTIS_EXAMPLE_DIR / "2023-599001-99-00.json")
    assert ctis["registry"]["eu_ct"] == "2023-599001-99-00"
    assert ctis["rights"]["empty_stub"] is True
    assert ctis["label"] == "RIGHTS_QUEUE"
    assert ctis["label"] != "OPP"
    assert ctis["score"]["gate_surface"] == NOT_OPTIONABLE
    readme = (PILOT_CTIS_EXAMPLE_DIR / "README.md").read_text()
    assert "python -m src.score.ctis --force-mock" in readme


def test_committed_ic_is_disposition_aware():
    bio = load_json(PILOT_EXPORT_DIR / f"{BIOGENE_ELTA_NCT}.json")
    linz = load_json(PILOT_EXPORT_DIR / f"{LINZAGOLIX_NCT}.json")
    empty = load_json(PILOT_EXPORT_DIR / f"{EMPTY_QUEUE_SAMPLE_ID}.json")
    bio_md = (PILOT_EXPORT_DIR / f"{BIOGENE_ELTA_NCT}.md").read_text()
    linz_md = (PILOT_EXPORT_DIR / f"{LINZAGOLIX_NCT}.md").read_text()
    empty_md = (PILOT_EXPORT_DIR / f"{EMPTY_QUEUE_SAMPLE_ID}.md").read_text()
    for row, md in ((bio, bio_md), (linz, linz_md)):
        assert row["ic_stub"]["status"] == IC_STATUS
        assert row["ic_stub"]["recommendation_kind"] == "WALK"
        assert row["rights"]["empty_stub"] is False
        assert EMPTY_RIGHTS_STAY not in row["ic_stub"]["recommendation"]
        assert EMPTY_RIGHTS_STAY not in md
        assert "desk closed" in row["ic_stub"]["recommendation"].lower()
        assert "OPP on empty_stub" not in md
    assert "WO2007/046392" in (linz["ic_stub"]["grantor_ip"]["one_liner"] or "")
    assert empty["label"] == "RIGHTS_QUEUE"
    assert empty["rights"]["empty_stub"] is True
    assert EMPTY_RIGHTS_STAY in empty["ic_stub"]["recommendation"]
    assert EMPTY_RIGHTS_STAY in empty_md
    rollup = load_json(D3_ROLLUP_PATH)
    assert rollup["n_opp"] == 0
    assert rollup["n_snapshot"] == 578
    assert rollup["by_label"].get("OPP", 0) == 0
    assert rollup["n_filled_walk_away"] >= 1
    assert rollup["n_rights_queue_empty"] >= 500


def test_snapshot_json_not_rewritten_by_this_pack():
    # Guard: the 578 CTG snapshot stays the committed unpaid corpus.
    snap = load_json(ROOT / "dashboard" / "public" / "data" / "snapshot.json")
    assert snap["snapshot_id"] == "20260913T054122Z"
    assert snap["counts"]["n_assets"] == 578
