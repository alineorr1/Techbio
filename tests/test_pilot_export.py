"""E4 / E7 dossier export: D1 fields, PATH stubs, no OPP on empty_stub."""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.paths import ROOT
from src.pilot.ctis_example import DEFAULT_EU_CT, build_ctis_asset_in_memory
from src.pilot.dossier import build_dossier, render_markdown
from src.pilot.export import parse_ids, write_dossier
from src.pilot.labels import LABEL_OPP, LABEL_RIGHTS_QUEUE
from src.pilot.snapshot import find_asset, snapshot_assets
from src.rights.codes import BIOGENE_ELTA_NCT, LINZAGOLIX_NCT
from src.rights.gates import NOT_OPTIONABLE


def test_parse_ids():
    assert parse_ids("NCT03481842, NCT04372121") == ["NCT03481842", "NCT04372121"]


def test_walk_away_dossier_is_not_opp_and_has_d1_fields():
    asset = find_asset(BIOGENE_ELTA_NCT)
    assert asset is not None
    dossier = build_dossier(asset)
    assert dossier["label"] != LABEL_OPP
    assert dossier["rights"]["ownable"] is False
    assert dossier["rights"]["empty_stub"] is False
    assert dossier["rights"]["desk_classification"] == "WALK_AWAY"
    assert dossier["rights"]["patents"] is None
    assert dossier["rights"]["grantor"]
    assert dossier["path"]["cmc"]["confidence"] != "missing"
    assert dossier["path"]["pathway_505b2"]["pathway"] == "unknown"
    assert dossier["path"]["unknown_ok_if_marked"] is True
    assert dossier["score"]["gate_surface"] in {NOT_OPTIONABLE, "WALK_AWAY"}
    assert dossier["score"]["high_score_is_not_buy"] is True
    assert dossier["ic_stub"]["empty_stub_is_opp"] is False
    assert dossier["ic_stub"]["is_opp"] is False
    assert "economic right" in dossier["narrative_lock"]["unit_note"].lower() or dossier["narrative_lock"]["unit"] == "economic_right"
    md = render_markdown(dossier)
    assert "NOT OPTIONABLE" in md or "WALK_AWAY" in md
    assert "ownable portfolio" not in md.lower()
    assert "PASS / ownable" in md or "never uses PASS" in md


def test_linzagolix_path_stub_present():
    asset = find_asset(LINZAGOLIX_NCT)
    assert asset is not None
    dossier = build_dossier(asset)
    assert dossier["path"]["started"] is True
    assert dossier["label"] != LABEL_OPP
    assert dossier["rights"]["patents"]


def test_write_dossier_files(tmp_path: Path):
    asset = find_asset(BIOGENE_ELTA_NCT)
    dossier = build_dossier(asset)
    json_path, md_path = write_dossier(dossier, tmp_path)
    assert json_path.is_file()
    assert md_path.is_file()
    assert "hypothesis for human review" in md_path.read_text().lower()


def test_ctis_eu_example_not_optionable():
    asset = asyncio.run(build_ctis_asset_in_memory(DEFAULT_EU_CT))
    assert asset["eu_ct"] == DEFAULT_EU_CT
    assert asset["source"] == "ctis"
    assert asset["optionable"] is False
    assert asset["gate_surface"] == NOT_OPTIONABLE
    dossier = build_dossier(asset)
    assert dossier["registry"]["eu_ct"] == DEFAULT_EU_CT
    assert dossier["label"] == LABEL_RIGHTS_QUEUE
    assert dossier["label"] != LABEL_OPP
    assert dossier["rights"]["empty_stub"] is True
    assert dossier["score"]["gate_surface"] == NOT_OPTIONABLE
    assert dossier["ic_stub"]["is_opp"] is False


def test_ui_copy_holds_md_banner_and_drops_blind_md_hold():
    asset_view = (ROOT / "dashboard" / "src" / "views" / "AssetView.tsx").read_text()
    ranked = (ROOT / "dashboard" / "src" / "views" / "RankedView.tsx").read_text()
    chrome = (ROOT / "dashboard" / "src" / "components" / "chrome.tsx").read_text()
    app = (ROOT / "dashboard" / "src" / "App.tsx").read_text()
    labels = (ROOT / "dashboard" / "src" / "lib" / "labels.ts").read_text()
    blob = asset_view + ranked + chrome + app + labels
    assert "Blind MD stays HOLD" not in blob
    assert "MD-LIVE" not in blob
    assert "MD LIVE" not in blob
    assert "hypothesis for human review" in blob.lower()
    assert "NOT OPTIONABLE" in asset_view
    assert '|| "HOLD"' not in asset_view
    assert "mock" in chrome
    assert "Shortlist-ownable" not in asset_view
    assert "shortlist_ownable (gate)" in asset_view
    assert "fill queue" not in blob.lower()
    assert "RIGHTS_QUEUE" in ranked
    assert "never OPP" in ranked
    assert 'label: LABEL_RIGHTS_QUEUE' in labels
    assert "Triage-keep. Overflow" not in labels


def test_snapshot_not_required_for_queue_size():
    assert len(snapshot_assets()) >= 500
