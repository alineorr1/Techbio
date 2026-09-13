"""CONTINGENT requires ≥1 citable indication-specific patent/application number."""

from __future__ import annotations

from src.rights.codes import PROVISIONAL_CONTINGENT_NCTS
from src.rights.gates import (
    CONTINGENT_NEEDS_CITABLE_PATENT,
    apply_contingent_patent_bar,
    has_citable_patent_number,
)
from src.rights.schema import RightsRecord, empty_rights


def _contingent_shell(nct: str = "NCT00000999") -> dict:
    rec = empty_rights("p_contingentbar0001", nct_id=nct)
    rec["confidence"] = "high"
    rec["desk_classification"] = "CONTINGENT"
    rec["ownership"]["status"] = "resolved"
    rec["ownership"]["confidence"] = "high"
    rec["ownership"]["ownable"] = False
    rec["ip"]["docket_empty"] = True
    rec["ip"]["patent_families"] = []
    rec["modules"] = {"asset_ip_desk": {"public_patent_null": True, "provisional_contingent": False}}
    return rec


def test_contingent_without_citable_number_is_forced_walk_away():
    assert PROVISIONAL_CONTINGENT_NCTS == frozenset()
    rec = _contingent_shell()
    out = apply_contingent_patent_bar(rec)
    assert out["desk_classification"] == "WALK_AWAY"
    assert out["ownership"]["ownable"] is False
    assert out["shortlist_ownable"] is False
    assert out["optionable_candidate"] is False
    assert out["commercial_gate"]["verdict"] != "PASS"
    assert out["kill"]["triggered"] is True
    assert CONTINGENT_NEEDS_CITABLE_PATENT in out["kill"]["codes"]
    RightsRecord.model_validate(out)


def test_adjacent_only_families_do_not_satisfy_contingent_bar():
    rec = _contingent_shell("NCT04174911")
    rec["modules"]["asset_ip_desk"]["public_patent_null"] = False
    rec["modules"]["asset_ip_desk"]["adjacent_only"] = True
    rec["ip"]["patent_families"] = [
        {
            "family_id": None,
            "jurisdiction": "AU",
            "publication_numbers": ["AU2024230822A1"],
            "status": "unknown",
            "title": "adjacent pMDI BOL+Kindeva",
        }
    ]
    rec["ip"]["docket_empty"] = False
    assert has_citable_patent_number(rec) is False
    out = apply_contingent_patent_bar(rec)
    assert out["desk_classification"] == "WALK_AWAY"
    assert out["ownership"]["ownable"] is False


def test_contingent_with_citable_endo_number_stays_contingent():
    rec = _contingent_shell("NCT00000888")
    rec["modules"]["asset_ip_desk"]["public_patent_null"] = False
    rec["ip"]["docket_empty"] = False
    rec["ip"]["patent_families"] = [
        {
            "family_id": None,
            "jurisdiction": "WO",
            "publication_numbers": ["WO2007046392"],
            "status": "unknown",
            "title": "com",
        }
    ]
    out = apply_contingent_patent_bar(rec)
    assert out["desk_classification"] == "CONTINGENT"
    assert out["ownership"]["ownable"] is False
    assert out["commercial_gate"].get("verdict") != "PASS"
