"""stop_reason_evidence must be a verbatim substring; hallucinations quarantine."""

import pytest

from src.extract.deterministic import DeterministicExtractor
from src.extract.schema import Extraction, EndpointQuality, Population
from src.extract.validate import ExtractionError, assert_verbatim, is_verbatim_substring, parse_extraction


SOURCE = """NCT ID: NCT03373422
Brief title: AKR1C3 inhibitor in endometriosis
Overall status: TERMINATED
Why stopped: Study BAY1128688/17472 (AKRENDO 1) was terminated early on 20 July 2018 due to hepatotoxicity
Intervention 1 type: DRUG
Intervention 1 name: BAY1128688
Eligibility criteria: Women of at least 18 years of age. Premenopausal.
"""


def test_verbatim_accepts_exact_why_stopped():
    assert is_verbatim_substring(
        "Study BAY1128688/17472 (AKRENDO 1) was terminated early on 20 July 2018 due to hepatotoxicity",
        SOURCE,
    )


def test_verbatim_rejects_paraphrase():
    assert not is_verbatim_substring("the trial stopped because of liver toxicity", SOURCE)


def test_assert_verbatim_quarantines_hallucination():
    ext = Extraction(
        nct_id="NCT03373422",
        targets=[],
        mechanism_summary="An AKR1C3 inhibitor.",
        population=Population(),
        stop_reason_raw="Study BAY1128688/17472 (AKRENDO 1) was terminated early on 20 July 2018 due to hepatotoxicity",
        stop_reason_category="safety",
        stop_reason_evidence="the drug caused drug-induced liver injury in multiple patients",
        endpoint_quality=EndpointQuality(primary_endpoint="pain", reasoning="x"),
    )
    with pytest.raises(ExtractionError):
        assert_verbatim(ext, SOURCE)


def test_parse_extraction_ok():
    payload = {
        "nct_id": "NCT03373422",
        "targets": [{"name": "BAY1128688", "gene_symbol": None, "modality": "small molecule", "confidence": "high"}],
        "mechanism_summary": "BAY1128688 was tested for endometriosis pain.",
        "population": {"diagnosis_method_stated": False, "age_range_specified": True},
        "stop_reason_raw": "Study BAY1128688/17472 (AKRENDO 1) was terminated early on 20 July 2018 due to hepatotoxicity",
        "stop_reason_category": "safety",
        "stop_reason_evidence": "due to hepatotoxicity",
        "endpoint_quality": {
            "primary_endpoint": "pain",
            "endpoint_type": "patient_reported",
            "endpoint_appropriate_for_indication": "yes",
            "reasoning": "pain scale",
        },
        "extraction_confidence": "high",
        "unresolved": [],
    }
    ext = parse_extraction(payload, SOURCE)
    assert ext.stop_reason_category == "safety"


def test_deterministic_extractor_never_invents_unnamed_gene():
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT03373422", "briefTitle": "BAY1128688 endometriosis"},
            "statusModule": {
                "overallStatus": "TERMINATED",
                "whyStopped": "Study BAY1128688/17472 (AKRENDO 1) was terminated early on 20 July 2018 due to hepatotoxicity",
            },
            "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": 121, "type": "ACTUAL"}},
            "armsInterventionsModule": {
                "interventions": [{"type": "DRUG", "name": "BAY1128688"}, {"type": "DRUG", "name": "Placebo"}]
            },
            "conditionsModule": {"conditions": ["Endometriosis"]},
            "eligibilityModule": {"minimumAge": "18 Years", "eligibilityCriteria": "Women 18+"},
            "outcomesModule": {"primaryOutcomes": [{"measure": "Endometriosis associated pelvic pain VAS"}]},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Bayer"}},
        }
    }
    ext = DeterministicExtractor().extract(study)
    from src.ingest.ctg import flatten_study_text

    source = flatten_study_text(study)
    assert ext.stop_reason_evidence in source or ext.stop_reason_raw in source
    assert all(t.gene_symbol is None for t in ext.targets), "must not infer AKR1C3; it is not named"
    assert any(t.name == "BAY1128688" for t in ext.targets)
    assert not any(t.name.lower() == "placebo" for t in ext.targets)
    assert ext.stop_reason_category == "safety"
