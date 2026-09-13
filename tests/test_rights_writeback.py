"""Asset IP public-only writeback: 18 NCTs, none ownable / optionable."""

from __future__ import annotations

from pathlib import Path

from src.rights.codes import (
    BOL_NCT,
    DESK_WRITEBACK_NCTS,
    LINZAGOLIX_NCT,
    VIRAMAL_NCT,
)
from src.rights.fill import fill_rights
from src.rights.gates import evaluate_pre_pass
from src.rights.query import ownability_query
from src.rights.schema import RightsRecord, empty_rights
from src.rights.store import load_rights, write_rights
from src.rights.writeback import desk_fills, map_desk_to_rights, write_desk_fills


def test_eighteen_desk_fills_are_walk_away_not_optionable(tmp_path: Path):
    assert len(DESK_WRITEBACK_NCTS) == 18
    assert len(desk_fills()) == 18
    written = write_desk_fills(root=tmp_path)
    assert len(written) == 18
    contingent = 0
    for nct in DESK_WRITEBACK_NCTS:
        rec = load_rights(nct_id=nct, root=tmp_path)
        assert rec is not None
        RightsRecord.model_validate(rec)
        assert rec["schema_version"] == "wave-1b.rights-stub.v1"
        assert rec["ownership"]["ownable"] is False
        assert rec["shortlist_ownable"] is False
        assert rec["optionable_candidate"] is False
        assert rec["process"]["outreach"] == "none"
        assert rec["confidence"] != "empty_stub"
        assert rec["ownership"]["confidence"] != "empty_stub"
        assert rec["ownership"]["status"] == "resolved"
        assert rec["desk_classification"] == "WALK_AWAY"
        assert rec["commercial_gate"]["verdict"] != "PASS"
        assert rec["kill"]["triggered"] is True
        assert "desk_classification=WALK_AWAY" in (rec["ownership"]["note"] + rec["notes"])
        q = ownability_query(rec)
        assert q["ownership_ownable"] is False
        assert q["shortlist_ownable"] is False
        assert q["optionable"] is False
        pre = evaluate_pre_pass(rights=rec)
        assert pre["shortlist_ownable"] is False
        assert pre["optionable"] is False
        assert pre["verdict"] != "PASS"
        if rec["desk_classification"] == "CONTINGENT":
            contingent += 1
    assert contingent == 0


def test_linzagolix_is_walk_away_not_needs_counsel(tmp_path: Path):
    write_desk_fills(root=tmp_path, nct_ids=[LINZAGOLIX_NCT])
    rec = load_rights(nct_id=LINZAGOLIX_NCT, root=tmp_path)
    assert rec["desk_classification"] == "WALK_AWAY"
    assert rec["desk_classification"] != "NEEDS_COUNSEL"
    assert rec["ownership"]["ownable"] is False
    assert "K_VALUE_NOT_CAPTURED" in rec["kill"]["hard"]
    assert "S_LICENSE_MAP_MISSING" in rec["kill"]["soft"]
    pubs = [n for f in rec["ip"]["patent_families"] for n in f.get("publication_numbers") or []]
    assert any("WO2007" in n or "WO2007/046392" in n for n in pubs)
    assert "None — closed" in rec["modules"]["asset_ip_desk"]["next_diligence_step"]


def test_viramal_and_bol_flipped_to_walk_away(tmp_path: Path):
    write_desk_fills(root=tmp_path, nct_ids=[VIRAMAL_NCT, BOL_NCT])
    vir = load_rights(nct_id=VIRAMAL_NCT, root=tmp_path)
    bol = load_rights(nct_id=BOL_NCT, root=tmp_path)
    assert vir["desk_classification"] == "WALK_AWAY"
    assert bol["desk_classification"] == "WALK_AWAY"
    assert vir["modules"]["asset_ip_desk"]["public_patent_null"] is True
    assert bol["modules"]["asset_ip_desk"]["adjacent_only"] is True
    assert vir["ownership"]["ownable"] is False
    assert bol["ownership"]["ownable"] is False
    assert "reformulation path" in vir["ownership"]["note"]
    assert "not CONTINGENT" in vir["notes"]
    assert "watchlist note only" in bol["ownership"]["note"]
    assert "not a CONTINGENT reopen" in bol["notes"]
    assert evaluate_pre_pass(rights=vir)["verdict"] != "PASS"
    assert evaluate_pre_pass(rights=bol)["verdict"] != "PASS"


def test_empty_stub_path_untouched_for_other_ncts(tmp_path: Path):
    write_desk_fills(root=tmp_path)
    rec = empty_rights("p_untoucheduntouch", nct_id="NCT00001111")
    path = write_rights(rec, root=tmp_path)
    stored = load_rights(nct_id="NCT00001111", root=tmp_path)
    assert path.exists()
    assert stored["confidence"] == "empty_stub"
    assert stored["desk_classification"] is None
    assert stored["ownership"]["ownable"] is False
    assert stored["shortlist_ownable"] is False
    assert stored["optionable_candidate"] is False
    assert stored["commercial_gate"]["verdict"] != "PASS"


def test_fill_rights_does_not_clobber_desk_writeback(tmp_path: Path):
    write_desk_fills(root=tmp_path, nct_ids=["NCT02669238"])
    before = load_rights(nct_id="NCT02669238", root=tmp_path)
    pid = before["programme_id"]
    after = fill_rights(pid, live=False, root=tmp_path, nct_id="NCT02669238")
    assert after["desk_classification"] == "WALK_AWAY"
    assert after["confidence"] != "empty_stub"
    assert after["ownership"]["ownable"] is False
    assert after["process"]["outreach"] == "none"


def test_map_preserves_programme_id_pin():
    rec = map_desk_to_rights(next(d for d in desk_fills() if d["nct_id"] == "NCT04372121"))
    assert rec["programme_id"] == "p_d79ac79555e6767e"
    RightsRecord.model_validate(rec)
