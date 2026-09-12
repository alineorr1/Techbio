"""Scoring Rule A (safety cap) and Rule B (Organon guard)."""

from src.extract.schema import Classification, Extraction, Population, EndpointQuality, Target
from src.score.compute import score_asset


def _ext(unresolved=None, conf="high"):
    return Extraction(
        nct_id="NCT00000001",
        targets=[Target(name="OG-6219", gene_symbol="HSD17B1", confidence="high")],
        mechanism_summary="HSD17B1 inhibitor tested for endometriosis pain.",
        population=Population(age_range_specified=True),
        stop_reason_raw=None,
        stop_reason_category="not_stated",
        stop_reason_evidence="Overall status: COMPLETED",
        endpoint_quality=EndpointQuality(
            primary_endpoint="pelvic pain",
            endpoint_type="patient_reported",
            endpoint_appropriate_for_indication="yes",
            reasoning="pain",
        ),
        extraction_confidence=conf,
        unresolved=unresolved or [],
    )


def _study(start="2022-10-25"):
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000001", "briefTitle": "OG-6219"},
            "statusModule": {
                "overallStatus": "COMPLETED",
                "startDateStruct": {"date": start},
                "completionDateStruct": {"date": "2025-05-28"},
            },
            "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": 354, "type": "ACTUAL"}},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Organon and Co"}},
        }
    }


def _clf(mode="unclear"):
    return Classification(
        nct_id="NCT00000001",
        failure_mode=mode,
        confidence="high",
        signals={},
        rule_fired="test",
    )


def test_rule_a_safety_capped_at_25():
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
            "sources": [],
        },
        "sponsor": {"status": "ceased", "source_url": "https://example.com"},
    }
    scored = score_asset(_study(), _ext(), _clf("safety"), enrich)
    assert scored["score"] <= 25
    assert scored["rule_a_safety_cap"] is True
    assert any("Rule A" in c for c in scored["caps_applied"])


def test_rule_b_organon_guard_without_pretrial_evidence():
    enrich = {
        "open_targets": {
            "overall_association_score": 0.9,
            "genetic_association_score": 0.5,
            "known_drugs": [],
            "literature_only": True,
            "evidence_items": [
                {
                    "publication_year": 2024,
                    "publication_date": "2024-01-01",
                    "datasource_id": "europepmc",
                    "datatype_id": "literature",
                }
            ],
            "sources": [],
        },
        "sponsor": {"status": "operating"},
    }
    # Use a favourable failure mode so the raw score would otherwise exceed 60
    scored = score_asset(_study(start="2022-10-25"), _ext(), _clf("funding_or_sponsor"), enrich)
    assert scored["rule_b_organon_guard"] is True
    assert scored["score"] <= 60
    assert any("Organon" in c for c in scored["caps_applied"])


def test_rule_b_not_applied_when_pretrial_evidence_exists():
    enrich = {
        "open_targets": {
            "overall_association_score": 0.5,
            "genetic_association_score": 0.4,
            "known_drugs": [{"drug": "x"}],
            "literature_only": False,
            "evidence_items": [
                {
                    "publication_year": 2015,
                    "publication_date": "2015-06-01",
                    "datasource_id": "ot_genetics_portal",
                    "datatype_id": "genetic_association",
                }
            ],
            "sources": [],
        },
        "sponsor": {"status": "ceased"},
    }
    scored = score_asset(_study(start="2022-10-25"), _ext(), _clf("funding_or_sponsor"), enrich)
    assert scored["pretrial_mechanism"]["has_pretrial_evidence"] is True
    # May or may not exceed 60 depending on weights, but Organon cap must not fire
    assert not any("Organon" in c for c in scored["caps_applied"])


def test_four_components_and_arithmetic_present():
    scored = score_asset(_study(), _ext(), _clf("unclear"), {"sponsor": {"status": "unknown"}})
    comps = scored["components"]
    assert set(comps) == {
        "mechanism_evidence",
        "failure_mode",
        "population_definition",
        "asset_accessibility",
    }
    assert "×" in scored["arithmetic"] or "x" in scored["arithmetic"].lower() or "+" in scored["arithmetic"]
    assert 0 <= scored["score"] <= 100
    assert scored["weights"]["mechanism_evidence"] == 35
