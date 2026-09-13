"""Pydantic extraction schema. One LLM call per trial; output validated against this model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Modality = Literal["small molecule", "biologic", "peptide", "device", "hormone", "other", "unknown"]
Confidence = Literal["high", "medium", "low"]
StopCategory = Literal[
    "efficacy",
    "safety",
    "recruitment",
    "funding_or_sponsor",
    "strategic",
    "regulatory",
    "design",
    "not_stated",
    "other",
]
EndpointType = Literal["objective", "patient_reported", "composite", "surrogate", "unclear"]
EndpointAppropriate = Literal["yes", "no", "uncertain"]
FailureMode = Literal[
    "funding_or_sponsor",
    "recruitment",
    "efficacy_uninterpretable",
    "efficacy",
    "safety",
    "unclear",
]


class Target(BaseModel):
    name: str
    gene_symbol: str | None = None
    modality: Modality = "unknown"
    confidence: Confidence = "low"

    @field_validator("gene_symbol", mode="before")
    @classmethod
    def empty_gene_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v


class Population(BaseModel):
    diagnosis_method_stated: bool = False
    diagnosis_method: str | None = None
    disease_severity_stratified: bool = False
    age_range_specified: bool = False
    menopausal_status_specified: bool = False
    menstrual_cycle_phase_controlled: bool = False
    hormonal_contraceptive_use_addressed: bool = False
    prior_treatment_history_specified: bool = False
    biomarker_or_molecular_subtype_used: bool = False

    @field_validator("diagnosis_method", mode="before")
    @classmethod
    def empty_diag_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v


class EndpointQuality(BaseModel):
    primary_endpoint: str
    endpoint_type: EndpointType = "unclear"
    endpoint_appropriate_for_indication: EndpointAppropriate = "uncertain"
    reasoning: str = Field(default="", max_length=400)


class Extraction(BaseModel):
    nct_id: str
    targets: list[Target] = Field(default_factory=list)
    mechanism_summary: str = Field(default="", max_length=500)
    population: Population = Field(default_factory=Population)
    stop_reason_raw: str | None = None
    stop_reason_category: StopCategory = "not_stated"
    stop_reason_evidence: str = ""
    endpoint_quality: EndpointQuality
    extraction_confidence: Confidence = "low"
    unresolved: list[str] = Field(default_factory=list)

    @field_validator("stop_reason_raw", mode="before")
    @classmethod
    def empty_raw_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v


class Classification(BaseModel):
    nct_id: str
    failure_mode: FailureMode
    confidence: Confidence
    signals: dict[str, object]
    rule_fired: str
    notes: str = ""
    commercial_gate: dict[str, object] | None = None
    disqualifier_codes: list[str] = Field(default_factory=list)


POPULATION_BOOLEAN_FIELDS = [
    "diagnosis_method_stated",
    "disease_severity_stratified",
    "age_range_specified",
    "menopausal_status_specified",
    "menstrual_cycle_phase_controlled",
    "hormonal_contraceptive_use_addressed",
    "prior_treatment_history_specified",
    "biomarker_or_molecular_subtype_used",
]
