"""Classify decision rules, applied in order (spec section 6)."""

from src.classify.rules import classify_record
from src.extract.schema import Classification, Extraction, Population, EndpointQuality, Target


def _ext(**kwargs) -> Extraction:
    pop = kwargs.pop("population", None) or Population()
    return Extraction(
        nct_id=kwargs.get("nct_id", "NCT00000000"),
        targets=kwargs.get("targets") or [Target(name="DrugX")],
        mechanism_summary="A named drug was tested.",
        population=pop,
        stop_reason_raw=kwargs.get("stop_reason_raw"),
        stop_reason_category=kwargs.get("stop_reason_category", "not_stated"),
        stop_reason_evidence=kwargs.get("stop_reason_evidence", "Overall status: TERMINATED"),
        endpoint_quality=EndpointQuality(primary_endpoint="pain VAS", endpoint_type="patient_reported", endpoint_appropriate_for_indication="yes", reasoning="pain scale"),
        extraction_confidence="medium",
        unresolved=[],
    )


def _study(status="TERMINATED", why=None, actual=40, anticipated=None, enroll_type="ACTUAL", sponsor="Bayer", start="2018-01-01", stop="2018-07-20"):
    enrollment = {"count": actual, "type": enroll_type}
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000000", "briefTitle": "Test"},
            "statusModule": {
                "overallStatus": status,
                "whyStopped": why,
                "startDateStruct": {"date": start},
                "completionDateStruct": {"date": stop},
            },
            "designModule": {"phases": ["PHASE2"], "enrollmentInfo": enrollment},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor, "class": "INDUSTRY"}},
        }
    }


def test_rule1_sponsor_ceased_while_enrolling():
    # Millendo ceased; enrolment proceeding
    study = _study(sponsor="Millendo Therapeutics US, Inc.", actual=80, enroll_type="ACTUAL", stop="2021-06-01")
    ext = _ext(stop_reason_category="strategic", stop_reason_raw="sponsor decision")
    clf = classify_record(study, ext)
    assert clf.failure_mode == "funding_or_sponsor"
    assert clf.rule_fired.startswith("1_")


def _study_under_enrolled(actual=10, anticipated=100, status="TERMINATED"):
    """Genuine under-enrolment: ESTIMATED planned + results-flow STARTED actual."""
    study = _study(status=status, actual=anticipated, enroll_type="ESTIMATED")
    study["resultsSection"] = {
        "participantFlowModule": {
            "periods": [
                {
                    "milestones": [
                        {"type": "STARTED", "achievements": [{"numSubjects": actual}]},
                    ]
                }
            ]
        }
    }
    return study


def test_rule2_enrolment_below_half_no_safety():
    study = _study_under_enrolled(actual=10, anticipated=100)
    ext = _ext(stop_reason_category="not_stated")
    clf = classify_record(study, ext)
    assert clf.failure_mode == "recruitment"
    assert clf.rule_fired.startswith("2_")
    assert clf.walk_away_codes == []


def test_rule2_does_not_fire_on_safety():
    study = _study(actual=0, why="Clinical hold for safety")
    ext = _ext(stop_reason_category="safety", stop_reason_raw="Clinical hold for safety", stop_reason_evidence="Clinical hold for safety")
    clf = classify_record(study, ext)
    assert clf.failure_mode == "safety"


def test_rule3_efficacy_uninterpretable():
    study = _study(actual=100, enroll_type="ACTUAL")
    ext = _ext(
        stop_reason_category="efficacy",
        stop_reason_raw="interim analysis showed no effect",
        population=Population(),  # zero female-specific vars
    )
    clf = classify_record(study, ext)
    assert clf.failure_mode == "efficacy_uninterpretable"
    assert clf.rule_fired.startswith("3_")


def test_rule4_efficacy_with_stratification():
    study = _study(actual=100)
    pop = Population(
        diagnosis_method_stated=True,
        disease_severity_stratified=True,
        age_range_specified=True,
        menopausal_status_specified=True,
    )
    ext = _ext(stop_reason_category="efficacy", population=pop)
    clf = classify_record(study, ext)
    assert clf.failure_mode == "efficacy"
    assert clf.rule_fired.startswith("4_")


def test_rule5_safety():
    study = _study(actual=121, why="terminated due to hepatotoxicity")
    ext = _ext(stop_reason_category="safety", stop_reason_raw="hepatotoxicity", stop_reason_evidence="hepatotoxicity")
    clf = classify_record(study, ext)
    assert clf.failure_mode == "safety"
    assert clf.rule_fired.startswith("5_")


def test_rule6_unclear():
    study = _study(actual=80, why=None, sponsor="Bayer")
    ext = _ext(stop_reason_category="not_stated")
    clf = classify_record(study, ext)
    assert clf.failure_mode == "unclear"
    assert isinstance(clf, Classification)
