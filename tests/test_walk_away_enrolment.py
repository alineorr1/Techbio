"""WITHDRAWN / enrollment=0 is walk-away, not a high-value recruitment win."""

from __future__ import annotations

from src.classify.rules import classify_record, walk_away_reason_codes
from src.db import load_json
from src.extract.schema import Classification, Extraction, Population, EndpointQuality, Target
from src.paths import RAW_CTG_DIR
from src.rights.gates import WALK_AWAY_WITHDRAWN, WALK_AWAY_ZERO_ENROLMENT
from src.rights.schema import empty_rights
from src.score.compute import score_asset


def _ext(nct_id="NCT00000000", category="not_stated", evidence="Overall status: WITHDRAWN"):
    return Extraction(
        nct_id=nct_id,
        targets=[Target(name="DrugX")],
        mechanism_summary="A named drug was tested.",
        population=Population(),
        stop_reason_category=category,
        stop_reason_evidence=evidence,
        endpoint_quality=EndpointQuality(
            primary_endpoint="pain VAS",
            endpoint_type="patient_reported",
            endpoint_appropriate_for_indication="yes",
            reasoning="pain scale",
        ),
        extraction_confidence="medium",
    )


def _study(status="WITHDRAWN", actual=0, enroll_type="ACTUAL", why=None):
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000000", "briefTitle": "Walk-away fixture"},
            "statusModule": {
                "overallStatus": status,
                "whyStopped": why,
                "startDateStruct": {"date": "2018-01-01"},
                "completionDateStruct": {"date": "2018-07-20"},
            },
            "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": actual, "type": enroll_type}},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Bayer"}},
        }
    }


def _clf_recruitment():
    return Classification(
        nct_id="NCT00000000",
        failure_mode="recruitment",
        confidence="high",
        signals={},
        rule_fired="2_enrolment_below_half_no_safety",
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


def test_withdrawn_classifies_as_never_started_not_recruitment():
    study = _study(status="WITHDRAWN", actual=0)
    clf = classify_record(study, _ext())
    assert clf.failure_mode == "never_started"
    assert clf.failure_mode != "recruitment"
    assert clf.rule_fired == "walk_away_withdrawn_or_zero_enrolment"
    assert WALK_AWAY_WITHDRAWN in clf.walk_away_codes
    assert WALK_AWAY_ZERO_ENROLMENT in clf.walk_away_codes


def test_zero_enrolment_terminated_is_walk_away_not_recruitment():
    study = _study(status="TERMINATED", actual=0)
    clf = classify_record(study, _ext(category="recruitment", evidence="Overall status: TERMINATED"))
    assert clf.failure_mode == "never_started"
    assert clf.failure_mode != "recruitment"
    assert WALK_AWAY_ZERO_ENROLMENT in clf.walk_away_codes


def test_nct03481842_biogene_not_recruitment_win():
    path = RAW_CTG_DIR / "NCT03481842.json"
    study = load_json(path)
    assert study["protocolSection"]["statusModule"]["overallStatus"] == "WITHDRAWN"
    assert study["protocolSection"]["designModule"]["enrollmentInfo"]["count"] == 0
    codes = walk_away_reason_codes(study)
    assert WALK_AWAY_WITHDRAWN in codes
    assert WALK_AWAY_ZERO_ENROLMENT in codes
    clf = classify_record(study, _ext(nct_id="NCT03481842", category="strategic"))
    assert clf.failure_mode == "never_started"
    scored = score_asset(study, _ext(nct_id="NCT03481842"), clf, _rich_enrich(), rights=empty_rights("p_bio"))
    assert scored["failure_mode"] != "recruitment"
    assert scored["components"]["failure_mode"]["value"] < 86
    assert scored["score"] <= 20
    assert scored["shortlist_ownable"] is False


def test_nct04174911_withdrawn_zero_not_recruitment_win():
    path = RAW_CTG_DIR / "NCT04174911.json"
    study = load_json(path)
    assert study["protocolSection"]["statusModule"]["overallStatus"] == "WITHDRAWN"
    assert study["protocolSection"]["designModule"]["enrollmentInfo"]["count"] == 0
    clf = classify_record(study, _ext(nct_id="NCT04174911", category="other"))
    assert clf.failure_mode != "recruitment"
    assert clf.failure_mode == "never_started"
    scored = score_asset(study, _ext(nct_id="NCT04174911"), clf, _rich_enrich(), rights=empty_rights("p_bol"))
    assert scored["components"]["failure_mode"]["value"] < 86
    assert scored["score"] <= 20


def test_stale_recruitment_classify_does_not_inflate_withdrawn_score():
    """Score must not treat a mis-tagged recruitment classify as a win."""
    study = _study(status="WITHDRAWN", actual=0)
    scored = score_asset(study, _ext(), _clf_recruitment(), _rich_enrich(), rights=empty_rights("p_stale"))
    assert scored["failure_mode"] == "never_started"
    assert scored["components"]["failure_mode"]["overridden_from"] == "recruitment"
    assert scored["components"]["failure_mode"]["value"] < 86
    assert scored["score"] <= 20
    assert any("Walk-away" in c or "walk-away" in c.lower() for c in scored["caps_applied"])


def test_genuine_under_enrolment_still_recruitment():
    study = _study(status="TERMINATED", actual=100, enroll_type="ESTIMATED")
    study["resultsSection"] = {
        "participantFlowModule": {
            "periods": [{"milestones": [{"type": "STARTED", "achievements": [{"numSubjects": 12}]}]}]
        }
    }
    clf = classify_record(study, _ext(category="not_stated", evidence="Overall status: TERMINATED"))
    assert clf.failure_mode == "recruitment"
    assert clf.walk_away_codes == []
    scored = score_asset(study, _ext(), clf, {"sponsor": {"status": "unknown"}}, rights=empty_rights("p_rec"))
    assert scored["failure_mode"] == "recruitment"
    assert scored["components"]["failure_mode"]["value"] == 86
