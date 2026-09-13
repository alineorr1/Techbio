"""K4 Intermezzo commercial gate: sex-diff alone ≠ PASS; cheap generic ≠ PASS."""

from __future__ import annotations

from src.classify.rules import classify_record
from src.extract.schema import Classification, Extraction, Population, EndpointQuality, Target
from src.rights.gates import K4_INTERMEZZO, SEX_DIFF_ALONE, evaluate_commercial_gate
from src.rights.schema import empty_rights
from src.score.compute import score_asset


def _study(title="Test", intervention="DrugX"):
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000000", "briefTitle": title},
            "statusModule": {
                "overallStatus": "TERMINATED",
                "startDateStruct": {"date": "2018-01-01"},
                "completionDateStruct": {"date": "2018-07-20"},
            },
            "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": 80, "type": "ACTUAL"}},
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


def _clf():
    return Classification(
        nct_id="NCT00000000",
        failure_mode="funding_or_sponsor",
        confidence="high",
        signals={},
        rule_fired="test",
    )


def test_empty_rights_never_pass():
    gate = evaluate_commercial_gate(study=_study(), rights=empty_rights("p_empty"))
    assert gate["verdict"] != "PASS"
    assert gate["empty_stub"] is True
    assert "EMPTY_RIGHTS_NOT_OWNABLE" in gate["reason_codes"]


def test_sex_dose_alone_is_not_pass():
    rights = empty_rights("p_sexonly")
    rights["commercial_shape"] = {
        "sex_dose_differentiation": True,
        "sex_diff_labeling": True,
        "generic_available": None,
        "pricing_power": "unknown",
    }
    gate = evaluate_commercial_gate(study=_study(), rights=rights)
    assert gate["verdict"] != "PASS"
    assert SEX_DIFF_ALONE in gate["reason_codes"]
    assert K4_INTERMEZZO not in gate["reason_codes"]


def test_k4_intermezzo_named_cheap_generic_is_fail():
    rights = empty_rights("p_intermezzo")
    rights["commercial_shape"] = {
        "sex_dose_differentiation": True,
        "generic_available": True,
        "pricing_power": "none",
    }
    gate = evaluate_commercial_gate(study=_study(title="Intermezzo MOTN", intervention="Intermezzo"), rights=rights)
    assert gate["verdict"] == "FAIL"
    assert K4_INTERMEZZO in gate["reason_codes"]
    assert gate["intermezzo"]["shaped"] is True


def test_k4_zolpidem_no_exclusivity_is_not_pass():
    gate = evaluate_commercial_gate(
        study=_study(title="Zolpidem sublingual", intervention="zolpidem tartrate"),
        rights=empty_rights("p_zolpidem"),
    )
    assert gate["verdict"] != "PASS"
    assert K4_INTERMEZZO in gate["reason_codes"]
    assert gate["verdict"] == "FAIL"


def test_resolved_right_can_pass_without_sex_diff():
    rights = empty_rights("p_realright")
    rights["confidence"] = "high"
    rights["ip"]["right_class"] = "option"
    rights["ip"]["listed_drug_ref"] = "NDA021007"
    rights["ip"]["docket_empty"] = False
    rights["commercial_shape"] = {"pricing_power": "present", "generic_available": False}
    rights["ind_regulatory"]["pathway_505b2"] = {
        "pathway": "505(b)(2)",
        "rld_ref": "NDA021007",
        "listed_drug_name": None,
        "listed_drug_ref": "NDA021007",
        "exclusivity_windows": [{"exclusivity_type": "NCE", "start": None, "end": None, "status": "active"}],
        "orange_book_url": None,
        "orange_book_hook": "orange_book",
        "confidence": "high",
    }
    gate = evaluate_commercial_gate(study=_study(), rights=rights)
    assert gate["verdict"] == "PASS"


def test_classify_and_score_apply_intermezzo_gate():
    study = _study(title="Intermezzo", intervention="Intermezzo")
    rights = empty_rights("p_gate")
    rights["commercial_shape"] = {"sex_dose_differentiation": True, "generic_available": True, "pricing_power": "none"}
    clf = classify_record(study, _ext("Intermezzo"), rights=rights)
    assert clf.commercial_gate["verdict"] == "FAIL"
    assert K4_INTERMEZZO in clf.disqualifier_codes
    assert "K_COM_ELSEWHERE" in clf.signals["kill_codes"]
    assert "K_VALUE_NOT_CAPTURED" in clf.signals["kill_codes"]
    assert clf.signals["kill_triggered"] is True

    enrich = {
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
    scored = score_asset(study, _ext("Intermezzo"), _clf(), enrich, rights=rights)
    assert scored["commercial_gate"]["verdict"] == "FAIL"
    assert scored["score"] <= 20
    assert any("Intermezzo" in c or "K4" in c for c in scored["caps_applied"])
