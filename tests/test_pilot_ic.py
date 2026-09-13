"""D2 IC half-page: filled WALK ≠ empty RIGHTS_QUEUE boilerplate."""

from __future__ import annotations

from src.pilot.dossier import build_dossier, render_markdown
from src.pilot.export import EMPTY_QUEUE_SAMPLE_ID
from src.pilot.ic import EMPTY_OPP_LINE, EMPTY_RIGHTS_STAY, IC_STATUS, KIND_CONTINGENT, KIND_WALK
from src.pilot.labels import LABEL_OPP, LABEL_RIGHTS_QUEUE, LABEL_TRIAGE, assign_label
from src.pilot.snapshot import find_asset
from src.rights.codes import BIOGENE_ELTA_NCT, LINZAGOLIX_NCT
from src.rights.schema import empty_rights


def _contingent_asset(*, path_ready: bool) -> dict:
    path = {
        "pathway": "505(b)(2)" if path_ready else "unknown",
        "confidence": "high" if path_ready else "empty_stub",
        "rld_ref": "RLD-1" if path_ready else None,
    }
    cmc = {
        "confidence": "high" if path_ready else "empty_stub",
        "api_source_identified": "yes" if path_ready else "unknown",
        "notes": "started" if path_ready else "",
    }
    rights = {
        "confidence": "high",
        "desk_classification": "CONTINGENT",
        "ownership": {"ownable": False, "status": "resolved", "confidence": "high"},
        "kill": {"codes": [], "hard": [], "soft": []},
        "ip": {
            "docket_empty": False,
            "patent_families": [
                {"title": "com", "publication_numbers": ["WO2007046392"], "jurisdiction": "WO"}
            ],
        },
        "modules": {"asset_ip_desk": {"public_patent_null": False, "adjacent_only": False}},
        "ind_regulatory": {"cmc": cmc, "pathway_505b2": path},
    }
    return {
        "nct_id": "NCT00000003" if path_ready else "NCT00000004",
        "score": {"score": 12.0},
        "desk_classification": "CONTINGENT",
        "sponsor_class": "INDUSTRY",
        "rights": rights,
        "cmc": cmc,
        "pathway_505b2": path,
        "classification": {"failure_mode": "recruitment"},
        "overall_status": "TERMINATED",
        "why_stopped": "Enrolment",
    }


def test_filled_walk_ic_is_not_empty_rights_boilerplate():
    asset = find_asset(BIOGENE_ELTA_NCT)
    assert asset is not None
    dossier = build_dossier(asset)
    ic = dossier["ic_stub"]
    md = render_markdown(dossier)
    assert dossier["label"] == LABEL_TRIAGE
    assert dossier["rights"]["empty_stub"] is False
    assert dossier["rights"]["desk_classification"] == "WALK_AWAY"
    assert ic["status"] == IC_STATUS
    assert ic["status"] != "thin_stub"
    assert ic["is_opp"] is False
    assert ic["recommendation_kind"] == KIND_WALK
    assert EMPTY_RIGHTS_STAY not in ic["recommendation"]
    assert "empty rights" not in ic["recommendation"].lower()
    assert "desk closed" in ic["recommendation"].lower()
    assert "WALK_AWAY" in ic["recommendation"]
    assert "K_NO_COUNTERPARTY" in ic["recommendation"]
    assert ic["not_opp_reason"] == "desk closed — filled WALK_AWAY, not empty rights"
    assert ic["grantor_ip"]["one_liner"]
    assert ic["path"]["readiness"] in {"thin", "ready", "unknown"}
    assert ic["next_step"]
    assert EMPTY_RIGHTS_STAY not in md
    assert EMPTY_OPP_LINE not in md
    assert "OPP on empty_stub" not in md
    assert "desk closed" in md.lower()
    assert "## IC (half-page)" in md
    assert "thin_stub" not in md


def test_linzagolix_ic_cites_patents_not_empty_rights():
    asset = find_asset(LINZAGOLIX_NCT)
    assert asset is not None
    dossier = build_dossier(asset)
    ic = dossier["ic_stub"]
    md = render_markdown(dossier)
    assert dossier["rights"]["empty_stub"] is False
    assert dossier["rights"]["patents"]
    assert ic["recommendation_kind"] == KIND_WALK
    assert EMPTY_RIGHTS_STAY not in ic["recommendation"]
    assert "empty rights" not in ic["recommendation"].lower()
    assert "desk closed" in ic["recommendation"].lower()
    assert "WO2007/046392" in (ic["grantor_ip"]["one_liner"] or "")
    assert "empty rights" not in md.lower() or "not because rights are empty" in md.lower()
    assert EMPTY_RIGHTS_STAY not in md
    assert "WO2007/046392" in md


def test_empty_rights_queue_keeps_boilerplate():
    asset = find_asset(EMPTY_QUEUE_SAMPLE_ID)
    assert asset is not None
    dossier = build_dossier(asset)
    ic = dossier["ic_stub"]
    md = render_markdown(dossier)
    assert dossier["label"] == LABEL_RIGHTS_QUEUE
    assert dossier["rights"]["empty_stub"] is True
    assert ic["is_opp"] is False
    assert ic["status"] == IC_STATUS
    assert EMPTY_RIGHTS_STAY in ic["recommendation"]
    assert ic["not_opp_reason"] == "empty rights stay RIGHTS_QUEUE / NOT OPTIONABLE"
    assert ic["recommendation_kind"] != KIND_WALK
    assert EMPTY_RIGHTS_STAY in md
    assert "OPP on empty_stub" in md


def test_synthetic_empty_stub_ic_is_rights_queue_boilerplate():
    asset = {
        "nct_id": "NCT00000001",
        "score": {"score": 99.0},
        "optionable": False,
        "sponsor_class": "OTHER",
        "rights": empty_rights("p_empty0000000001", nct_id="NCT00000001"),
        "cmc": {"confidence": "empty_stub"},
        "pathway_505b2": {"pathway": "unknown", "confidence": "empty_stub"},
        "classification": {"failure_mode": "unclear"},
    }
    dossier = build_dossier(asset)
    ic = dossier["ic_stub"]
    assert dossier["label"] == LABEL_RIGHTS_QUEUE
    assert EMPTY_RIGHTS_STAY in ic["recommendation"]
    walk = build_dossier(find_asset(BIOGENE_ELTA_NCT))
    assert walk["ic_stub"]["recommendation"] != ic["recommendation"]


def test_contingent_numbered_ip_is_not_opp_until_path_ready():
    thin = build_dossier(_contingent_asset(path_ready=False))
    ready = build_dossier(_contingent_asset(path_ready=True))
    assert thin["ic_stub"]["recommendation_kind"] == KIND_CONTINGENT
    assert thin["ic_stub"]["is_opp"] is False
    assert "not an opp until the path is ready" in thin["ic_stub"]["recommendation"].lower()
    assert EMPTY_RIGHTS_STAY not in thin["ic_stub"]["recommendation"]
    assert assign_label(_contingent_asset(path_ready=True))["label"] == LABEL_OPP
    assert ready["ic_stub"]["is_opp"] is True
    assert ready["label"] == LABEL_OPP
    assert ready["ic_stub"]["recommendation_kind"] == "OPP"
    assert EMPTY_RIGHTS_STAY not in ready["ic_stub"]["recommendation"]
