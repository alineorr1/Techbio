"""wave-1b.rights-stub.v1 empty attach. Confidence stays empty_stub — never ownable."""

from __future__ import annotations

import json
from pathlib import Path

from src.enrich.sponsors import enrich_sponsor, sponsor_entity_from_row
from src.identity.programme import IdentityStore, identifiers_from_nct
from src.paths import ROOT
from src.rights.codes import FOR_6219_NCT, HARD_KILL_CODES, SOFT_CODES
from src.rights.query import decision_required, ownability_query
from src.rights.schema import REQUIRED_BLOCKS, SCHEMA_VERSION, RightsRecord, cmc_of, empty_rights, pathway_505b2_of, sponsor_entity_of
from src.rights.store import attach_empty_rights, load_rights, rights_dir_for_identity, write_rights


JSON_SCHEMA = ROOT / "src" / "rights" / "wave-1b.rights-stub.v1.json"


def test_empty_rights_schema_and_confidence():
    rec = empty_rights("p_deadbeefdeadbeef", nct_id="NCT00000001")
    assert rec["schema_version"] == SCHEMA_VERSION == "wave-1b.rights-stub.v1"
    assert rec["programme_id"] == "p_deadbeefdeadbeef"
    assert rec["nct_id"] == "NCT00000001"
    assert rec["identity"]["nct_id"] == "NCT00000001"
    assert rec["identity"]["thesis_mismatch"] is False
    assert rec["identity"]["taxonomy"]["empty"] is True
    assert rec["ip"]["right_class"] == "unknown"
    assert rec["ip"]["patent_families"] == []
    assert rec["ip"]["docket_empty"] is True
    assert rec["ip"]["orange_book"]["hook"] == "orange_book"
    assert rec["confidence"] == "empty_stub"
    assert rec["ownership"]["ownable"] is False
    assert rec["process"]["outreach"] == "none"
    assert rec["commercial_gate"]["verdict"] != "PASS"
    for block in REQUIRED_BLOCKS:
        assert block in rec
    cmc = cmc_of(rec)
    assert cmc["confidence"] == "empty_stub"
    assert cmc["api_source_identified"] == "unknown"
    path = pathway_505b2_of(rec)
    assert path["confidence"] == "empty_stub"
    assert path["rld_ref"] is None
    assert path["exclusivity_windows"] == []
    assert sponsor_entity_of(rec)["resolution_status"] == "not_yet_fetched"
    RightsRecord.model_validate(rec)


def test_empty_stub_cannot_be_written_as_pass(tmp_path: Path):
    rec = empty_rights("p_abcabcabcabcabca")
    rec["commercial_gate"]["verdict"] = "PASS"
    rec["ownership"]["ownable"] = True
    rec["confidence"] = "empty_stub"
    path = write_rights(rec, root=tmp_path)
    stored = load_rights("p_abcabcabcabcabca", root=tmp_path)
    assert path.exists()
    assert stored["confidence"] == "empty_stub"
    assert stored["commercial_gate"]["verdict"] != "PASS"
    assert stored["ownership"]["ownable"] is False


def test_attach_empty_rights_writes_nct_file_as_content_pk(tmp_path: Path):
    rec = attach_empty_rights("p_1111111111111111", root=tmp_path, nct_id="NCT00000002")
    assert rec["confidence"] == "empty_stub"
    on_disk = load_rights(nct_id="NCT00000002", root=tmp_path)
    assert on_disk is not None
    assert on_disk["schema_version"] == "wave-1b.rights-stub.v1"
    assert (tmp_path / "NCT00000002.json").exists()
    assert not (tmp_path / "p_1111111111111111.json").exists()


def test_eu_only_uses_programme_id_not_second_graph(tmp_path: Path):
    rec = attach_empty_rights("p_euonlyeuonlyeu", root=tmp_path, eu_ct="2024-518143-38-00")
    assert rec["nct_id"] is None
    assert rec["programme_id"] == "p_euonlyeuonlyeu"
    assert (tmp_path / "p_euonlyeuonlyeu.json").exists()


def test_identity_upsert_attaches_empty_rights(tmp_path: Path):
    store = IdentityStore(tmp_path / "identity")
    record = store.upsert(identifiers_from_nct("NCT03693677"), source="ctg", native_id="NCT03693677")
    pid = record["programme_id"]
    rights_root = rights_dir_for_identity(tmp_path / "identity")
    attached = load_rights(nct_id="NCT03693677", programme_id=pid, root=rights_root)
    assert attached is not None
    assert attached["confidence"] == "empty_stub"
    assert attached["nct_id"] == "NCT03693677"
    assert attached["programme_id"] == pid
    assert attached["commercial_gate"]["verdict"] != "PASS"
    assert store.lookup("NCT03693677")["programme_id"] == pid


def test_for_6219_empty_taxonomy_still_creates_stub(tmp_path: Path):
    rec = attach_empty_rights("p_for6219for6219", root=tmp_path, nct_id=FOR_6219_NCT)
    assert rec["identity"]["taxonomy"]["empty"] is True
    assert rec["nct_id"] == FOR_6219_NCT
    assert "S_TAXONOMY_FIX" in rec["kill"]["soft"]
    assert rec["kill"]["triggered"] is False
    assert rec["ownership"]["ownable"] is False
    assert (tmp_path / f"{FOR_6219_NCT}.json").exists()


def test_kill_codes_and_thesis_mismatch_are_queryable():
    rec = empty_rights("p_queryablequery", nct_id="NCT00000003")
    rec["identity"]["thesis_mismatch"] = True
    rec["kill"]["hard"] = ["K_THESIS_MISMATCH"]
    rec["kill"]["codes"] = ["K_THESIS_MISMATCH", "S_TAXONOMY_FIX"]
    rec["kill"]["triggered"] = True
    q = ownability_query(rec)
    assert q["thesis_mismatch"] is True
    assert q["kill_triggered"] is True
    assert "K_THESIS_MISMATCH" in q["kill_codes"]
    assert q["decision_required"] is True
    assert q["ownership_ownable"] is False
    assert decision_required(rec) is True
    for code in HARD_KILL_CODES:
        assert code.startswith("K_")
    for code in SOFT_CODES:
        assert code.startswith("S_")


def test_json_schema_file_lists_required_blocks():
    spec = json.loads(JSON_SCHEMA.read_text())
    assert spec["$id"] == "wave-1b.rights-stub.v1"
    required = set(spec["required"])
    for block in REQUIRED_BLOCKS:
        assert block in required
    rec = empty_rights("p_jschemajschema", nct_id="NCT00000004")
    for block in spec["required"]:
        assert block in rec


def test_sponsor_entity_unknown_vs_not_yet_fetched_vs_resolved():
    empty = sponsor_entity_of(empty_rights("p_sponsor"))
    assert empty["resolution_status"] == "not_yet_fetched"
    assert empty["source"] == "none"

    unknown = sponsor_entity_from_row(None, lead_name="Some Unknown Biotech LLC")
    assert unknown["resolution_status"] == "unknown"
    assert unknown["name"] == "Some Unknown Biotech LLC"
    assert unknown["source"] == "unstructured_registry"

    resolved = sponsor_entity_from_row(
        {"sponsor_name": "Millendo Therapeutics US Inc.", "matched_lead": "Millendo Therapeutics US, Inc."},
        lead_name="Millendo Therapeutics US, Inc.",
    )
    assert resolved["resolution_status"] == "resolved"
    assert resolved["source"] == "curated_csv"
    assert resolved["legal_name"] == "Millendo Therapeutics US Inc."

    study = {
        "protocolSection": {
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Millendo Therapeutics US, Inc."}}
        }
    }
    sponsor = enrich_sponsor(study)
    assert sponsor["sponsor_entity"]["resolution_status"] == "resolved"
    assert "sponsor_entity" in sponsor


def test_cmc_and_505b2_are_desk_grade_not_poetry():
    rec = empty_rights("p_cmc")
    cmc = cmc_of(rec)
    for key in (
        "api_source_identified",
        "formulation_described",
        "impurity_profile_available",
        "stability_data_available",
        "manufacturing_site_known",
        "spec_available",
        "ctd_module_3_available",
    ):
        assert cmc[key] == "unknown"
    assert cmc["comparability_risk"] == "unknown"
    assert cmc["notes"] == ""
    path = pathway_505b2_of(rec)
    assert path["pathway"] == "unknown"
    assert path["exclusivity_windows"] == []
    assert path["orange_book_url"] is None
