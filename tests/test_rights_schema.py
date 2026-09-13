"""wave1.rights.v0 empty attach. Confidence stays empty_stub — never ownable."""

from __future__ import annotations

from pathlib import Path

from src.enrich.sponsors import enrich_sponsor, sponsor_entity_from_row
from src.identity.programme import IdentityStore, identifiers_from_nct
from src.rights.schema import SCHEMA_VERSION, RightsRecord, empty_rights
from src.rights.store import attach_empty_rights, load_rights, rights_dir_for_identity, write_rights


def test_empty_rights_schema_and_confidence():
    rec = empty_rights("p_deadbeefdeadbeef")
    assert rec["schema_version"] == SCHEMA_VERSION == "wave1.rights.v0"
    assert rec["programme_id"] == "p_deadbeefdeadbeef"
    assert rec["right_class"] == "unknown"
    assert rec["patent_families"] == []
    assert rec["listed_drug_ref"] is None
    assert rec["confidence"] == "empty_stub"
    assert rec["commercial_gate"]["verdict"] != "PASS"
    assert rec["cmc"]["confidence"] == "empty_stub"
    assert rec["cmc"]["api_source_identified"] == "unknown"
    assert rec["pathway_505b2"]["confidence"] == "empty_stub"
    assert rec["pathway_505b2"]["rld_ref"] is None
    assert rec["pathway_505b2"]["exclusivity_windows"] == []
    assert rec["pathway_505b2"]["orange_book_hook"] == "orange_book"
    assert rec["sponsor_entity"]["resolution_status"] == "not_yet_fetched"
    RightsRecord.model_validate(rec)


def test_empty_stub_cannot_be_written_as_pass(tmp_path: Path):
    rec = empty_rights("p_abcabcabcabcabca")
    rec["commercial_gate"]["verdict"] = "PASS"
    rec["confidence"] = "empty_stub"
    path = write_rights(rec, root=tmp_path)
    stored = load_rights("p_abcabcabcabcabca", root=tmp_path)
    assert path.exists()
    assert stored["confidence"] == "empty_stub"
    assert stored["commercial_gate"]["verdict"] != "PASS"


def test_attach_empty_rights_writes_programme_file(tmp_path: Path):
    rec = attach_empty_rights("p_1111111111111111", root=tmp_path)
    assert rec["confidence"] == "empty_stub"
    on_disk = load_rights("p_1111111111111111", root=tmp_path)
    assert on_disk is not None
    assert on_disk["schema_version"] == "wave1.rights.v0"
    assert on_disk["programme_id"] == "p_1111111111111111"


def test_identity_upsert_attaches_empty_rights(tmp_path: Path):
    store = IdentityStore(tmp_path / "identity")
    record = store.upsert(identifiers_from_nct("NCT03693677"), source="ctg", native_id="NCT03693677")
    pid = record["programme_id"]
    rights_root = rights_dir_for_identity(tmp_path / "identity")
    attached = load_rights(pid, root=rights_root)
    assert attached is not None
    assert attached["confidence"] == "empty_stub"
    assert attached["commercial_gate"]["verdict"] != "PASS"
    assert store.lookup("NCT03693677")["programme_id"] == pid


def test_sponsor_entity_unknown_vs_not_yet_fetched_vs_resolved():
    empty = empty_rights("p_sponsor")["sponsor_entity"]
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
    for key in (
        "api_source_identified",
        "formulation_described",
        "impurity_profile_available",
        "stability_data_available",
        "manufacturing_site_known",
        "spec_available",
        "ctd_module_3_available",
    ):
        assert rec["cmc"][key] == "unknown"
    assert rec["cmc"]["comparability_risk"] == "unknown"
    assert rec["cmc"]["notes"] == ""
    assert rec["pathway_505b2"]["pathway"] == "unknown"
    assert rec["pathway_505b2"]["exclusivity_windows"] == []
    assert rec["pathway_505b2"]["orange_book_url"] is None
