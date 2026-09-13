"""Teratogen/REMS table: hard disqualify or strong downrank with reason codes."""

from __future__ import annotations

from src.classify.rules import classify_record
from src.config import disqualifiers_config
from src.extract.schema import Classification, Extraction, Population, EndpointQuality, Target
from src.rights.gates import apply_teratogen_rems, evaluate_commercial_gate
from src.rights.schema import empty_rights
from src.score.compute import score_asset


def _study(intervention: str):
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000000", "briefTitle": f"{intervention} study"},
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


def test_disqualifier_table_is_structured():
    cfg = disqualifiers_config()
    table = cfg["teratogen_rems"]
    assert table["entries"]
    for entry in table["entries"]:
        assert entry["substance"]
        assert entry["reason_code"]
        assert entry["action"] in {"hard_disqualify", "strong_downrank"}
        assert entry.get("note")
        assert "biology-failure" in (entry.get("note") or "").lower() or "not a biology" in (entry.get("note") or "").lower()


def test_rems_hard_disqualify_thalidomide():
    result = apply_teratogen_rems(study=_study("thalidomide"))
    assert result["matched"] is True
    assert result["hard_disqualify"] is True
    assert "REMS_TERATOGEN" in result["reason_codes"]
    assert result["matches"][0]["substance"] == "thalidomide"
    gate = evaluate_commercial_gate(study=_study("thalidomide"), rights=empty_rights("p_thal"))
    assert gate["verdict"] == "FAIL"
    assert "REMS_TERATOGEN" in gate["reason_codes"]


def test_labeled_teratogen_strong_downrank_valproate():
    result = apply_teratogen_rems(study=_study("valproate"))
    assert result["matched"] is True
    assert result["hard_disqualify"] is False
    assert result["strong_downrank"] is True
    assert "TERATOGEN_LABELED" in result["reason_codes"]


def test_unlisted_drug_does_not_match():
    result = apply_teratogen_rems(study=_study("linzagolix"))
    assert result["matched"] is False
    assert result["reason_codes"] == []


def test_classify_surfaces_rems_reason_codes():
    clf = classify_record(_study("lenalidomide"), _ext("lenalidomide"), rights=empty_rights("p_len"))
    assert "REMS_TERATOGEN" in clf.disqualifier_codes
    assert clf.commercial_gate["teratogen_rems"]["hard_disqualify"] is True
    # Failure mode is unchanged — REMS is not a biology/safety invention.
    assert clf.failure_mode == "unclear"
    assert clf.rule_fired != "5_safety_signal"


def test_score_applies_rems_hard_cap():
    scored = score_asset(_study("thalidomide"), _ext("thalidomide"), _clf(), _rich_enrich(), rights=empty_rights("p_thal"))
    assert scored["score"] <= 10
    assert any("REMS" in c or "teratogen" in c for c in scored["caps_applied"])
    assert scored["commercial_gate"]["verdict"] == "FAIL"


def test_score_applies_teratogen_downrank_cap():
    scored = score_asset(_study("methotrexate"), _ext("methotrexate"), _clf(), _rich_enrich(), rights=empty_rights("p_mtx"))
    assert scored["score"] <= 25
    assert any("downrank" in c.lower() or "TERATOGEN" in c for c in scored["caps_applied"])


def test_organon_rule_b_still_independent():
    """REMS/Intermezzo sit beside Rule B; they do not invent mechanism evidence."""
    study = _study("DrugX")
    scored = score_asset(study, _ext(), _clf(), {"sponsor": {"status": "operating"}, "open_targets": {}}, rights=empty_rights("p_x"))
    assert scored["rule_b_organon_guard"] is True
    assert scored["commercial_gate"]["verdict"] != "PASS"
