"""Hard pre-PASS gates: empty_stub / Intermezzo / REMS block PASS and shortlist-ownable."""

from __future__ import annotations

from src.classify.rules import classify_record
from src.extract.schema import Classification, Extraction, Population, EndpointQuality, Target
from src.rights.gates import (
    K4_INTERMEZZO,
    MISSING_OWNERSHIP_FILL,
    NOT_OPTIONABLE,
    NOT_OPTIONABLE_CODE,
    RIGHTS_UNKNOWN,
    evaluate_commercial_gate,
    evaluate_pre_pass,
)
from src.rights.schema import empty_rights
from src.score.compute import score_asset


def _study(title="Test", intervention="DrugX", status="TERMINATED", count=80):
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000000", "briefTitle": title},
            "statusModule": {
                "overallStatus": status,
                "startDateStruct": {"date": "2018-01-01"},
                "completionDateStruct": {"date": "2018-07-20"},
            },
            "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": count, "type": "ACTUAL"}},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Bayer"}},
            "armsInterventionsModule": {"interventions": [{"name": intervention, "type": "DRUG"}]},
        }
    }


def _ext(name="DrugX"):
    return Extraction(
        nct_id="NCT00000000",
        targets=[Target(name=name)],
        mechanism_summary="A named drug was tested.",
        population=Population(),
        stop_reason_category="not_stated",
        stop_reason_evidence="Overall status: TERMINATED",
        endpoint_quality=EndpointQuality(
            primary_endpoint="pain VAS",
            endpoint_type="patient_reported",
            endpoint_appropriate_for_indication="yes",
            reasoning="pain scale",
        ),
        extraction_confidence="medium",
    )


def _clf(mode="funding_or_sponsor"):
    return Classification(
        nct_id="NCT00000000",
        failure_mode=mode,
        confidence="high",
        signals={},
        rule_fired="test",
    )


def _rich_enrich():
    return {
        "open_targets": {
            "overall_association_score": 0.9,
            "genetic_association_score": 0.8,
            "known_drugs": [{"drug": "x"}],
            "literature_only": False,
            "evidence_items": [
                {
                    "publication_year": 2010,
                    "publication_date": "2010-01-01",
                    "datasource_id": "ot_genetics_portal",
                    "datatype_id": "genetic_association",
                }
            ],
        },
        "sponsor": {"status": "ceased"},
    }


def test_empty_stub_is_not_optionable_and_not_pass():
    rights = empty_rights("p_empty")
    pre = evaluate_pre_pass(study=_study(), rights=rights)
    assert pre["verdict"] != "PASS"
    assert pre["surface"] == NOT_OPTIONABLE
    assert pre["optionable"] is False
    assert pre["shortlist_ownable"] is False
    assert pre["md_status"] == "HOLD"
    assert pre["block_pass"] is True
    assert NOT_OPTIONABLE_CODE in pre["reason_codes"]
    assert RIGHTS_UNKNOWN in pre["reason_codes"]
    assert MISSING_OWNERSHIP_FILL in pre["reason_codes"]

    clf = classify_record(_study(), _ext(), rights=rights)
    assert clf.pre_pass["surface"] == NOT_OPTIONABLE
    assert clf.pre_pass["shortlist_ownable"] is False
    assert clf.commercial_gate["verdict"] != "PASS"

    scored = score_asset(_study(), _ext(), _clf(), _rich_enrich(), rights=rights)
    assert scored["commercial_gate"]["verdict"] != "PASS"
    assert scored["pre_pass"]["surface"] == NOT_OPTIONABLE
    assert scored["shortlist_ownable"] is False
    assert scored["optionable"] is False


def test_rights_unknown_confidence_blocks_pass():
    rights = empty_rights("p_unknown_conf")
    rights["confidence"] = "rights-unknown"
    rights["ownership"]["confidence"] = "high"
    rights["ownership"]["status"] = "resolved"
    rights["ownership"]["ownable"] = True
    rights["ip"]["right_class"] = "option"
    rights["commercial_shape"] = {"pricing_power": "present"}
    gate = evaluate_commercial_gate(study=_study(), rights=rights)
    assert gate["verdict"] != "PASS"
    pre = evaluate_pre_pass(study=_study(), rights=rights, gate=gate)
    assert pre["surface"] == NOT_OPTIONABLE
    assert pre["shortlist_ownable"] is False
    assert RIGHTS_UNKNOWN in pre["reason_codes"]


def test_intermezzo_gate_blocks_pass_and_shortlist():
    rights = empty_rights("p_k4")
    rights["commercial_shape"] = {
        "sex_dose_differentiation": True,
        "generic_available": True,
        "pricing_power": "none",
    }
    study = _study(title="Intermezzo MOTN", intervention="Intermezzo")
    pre = evaluate_pre_pass(study=study, rights=rights, intervention_names=["Intermezzo"])
    assert pre["verdict"] == "FAIL"
    assert pre["shortlist_ownable"] is False
    assert pre["optionable"] is False
    assert K4_INTERMEZZO in pre["reason_codes"]
    scored = score_asset(study, _ext("Intermezzo"), _clf(), _rich_enrich(), rights=rights)
    assert scored["shortlist_ownable"] is False
    assert scored["commercial_gate"]["verdict"] == "FAIL"
    assert scored["score"] <= 20


def test_rems_hard_disqualify_blocks_pass_and_shortlist():
    rights = empty_rights("p_rems")
    study = _study(intervention="thalidomide")
    pre = evaluate_pre_pass(study=study, rights=rights, intervention_names=["thalidomide"])
    assert pre["verdict"] == "FAIL"
    assert pre["shortlist_ownable"] is False
    assert "REMS_TERATOGEN" in pre["reason_codes"]
    scored = score_asset(study, _ext("thalidomide"), _clf(), _rich_enrich(), rights=rights)
    assert scored["shortlist_ownable"] is False
    assert scored["commercial_gate"]["verdict"] == "FAIL"
    assert scored["score"] <= 10
