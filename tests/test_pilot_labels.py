"""T2 labels: empty_stub is never OPP; high score is ignored."""

from __future__ import annotations

from src.pilot.labels import (
    LABEL_OPP,
    LABEL_RIGHTS_QUEUE,
    LABEL_TRIAGE,
    assign_label,
    is_empty_stub,
    opp_eligible,
    path_stub_started,
)
from src.rights.schema import empty_rights


def test_empty_stub_is_never_opp():
    asset = {
        "nct_id": "NCT00000001",
        "score": {"score": 99.0},
        "optionable": False,
        "rights": empty_rights("p_empty0000000001", nct_id="NCT00000001"),
        "cmc": {"confidence": "empty_stub"},
        "pathway_505b2": {"pathway": "unknown", "confidence": "empty_stub"},
    }
    assert is_empty_stub(asset)
    assert opp_eligible(asset) is False
    assert assign_label(asset)["label"] != LABEL_OPP
    assert assign_label(asset, in_active_queue=True)["label"] == LABEL_RIGHTS_QUEUE


def test_high_score_alone_is_not_opp():
    asset = {
        "nct_id": "NCT00000002",
        "score": {"score": 100.0},
        "optionable": False,
        "shortlist_ownable": False,
        "desk_classification": None,
        "rights": {"confidence": "high", "desk_classification": None, "ownership": {"ownable": False, "status": "resolved", "confidence": "high"}, "ip": {"patent_families": []}},
        "cmc": {"confidence": "high", "notes": "started"},
        "pathway_505b2": {"pathway": "505(b)(2)", "confidence": "high"},
    }
    assert path_stub_started(asset)
    assert opp_eligible(asset) is False


def test_opp_requires_rights_and_path():
    rights = {
        "confidence": "high",
        "desk_classification": "CONTINGENT",
        "ownership": {"ownable": False, "status": "resolved", "confidence": "high"},
        "ip": {
            "docket_empty": False,
            "patent_families": [
                {"title": "com", "publication_numbers": ["WO2007046392"], "jurisdiction": "WO"}
            ],
        },
        "modules": {"asset_ip_desk": {"public_patent_null": False, "adjacent_only": False}},
        "ind_regulatory": {
            "cmc": {"confidence": "high", "api_source_identified": "yes"},
            "pathway_505b2": {"pathway": "505(b)(2)", "confidence": "high", "rld_ref": "RLD-1"},
        },
    }
    asset = {
        "nct_id": "NCT00000003",
        "score": {"score": 12.0},
        "desk_classification": "CONTINGENT",
        "rights": rights,
        "cmc": rights["ind_regulatory"]["cmc"],
        "pathway_505b2": rights["ind_regulatory"]["pathway_505b2"],
    }
    assert opp_eligible(asset)
    assert assign_label(asset)["label"] == LABEL_OPP


def test_walk_away_is_triage_disregard():
    asset = {
        "nct_id": "NCT03481842",
        "desk_classification": "WALK_AWAY",
        "rights": {"confidence": "high", "desk_classification": "WALK_AWAY", "ownership": {"status": "resolved", "confidence": "high"}},
    }
    row = assign_label(asset, disregarded=True)
    assert row["label"] == LABEL_TRIAGE
    assert row["triage"] == "disregard"
    assert row["label"] != LABEL_OPP
