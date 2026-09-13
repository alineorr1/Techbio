"""Schema wave1.rights.v0 — economic right attached by programme_id.

Empty attach is the default. confidence=empty_stub never implies ownability.
Desk-grade CMC / 505(b)(2) fields are structured booleans and enums, not prose.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "wave1.rights.v0"

RightClass = Literal["option", "505(b)(2)", "method_of_use", "unknown"]
RightsConfidence = Literal["empty_stub", "low", "medium", "high"]
DeskBool = Literal["yes", "no", "unknown"]
ResolutionStatus = Literal["unknown", "not_yet_fetched", "resolved"]
GateVerdict = Literal["PASS", "FAIL", "HOLD", "empty_stub"]
PricingPower = Literal["none", "unknown", "present"]
ComparabilityRisk = Literal["low", "medium", "high", "unknown"]
PathwayKind = Literal["505(b)(2)", "505(j)", "505(b)(1)", "unknown"]
ExclusivityStatus = Literal["unknown", "active", "expired", "not_applicable"]
PatentStatus = Literal["unknown", "pending", "granted", "expired", "lapsed"]
SponsorSource = Literal["unstructured_registry", "curated_csv", "opencorporates", "none"]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PatentFamily(BaseModel):
    family_id: str | None = None
    jurisdiction: str | None = None
    publication_numbers: list[str] = Field(default_factory=list)
    status: PatentStatus = "unknown"
    title: str | None = None


class SponsorEntity(BaseModel):
    """Structured sponsor vs unstructured registry name.

    unknown          — name present, no legal-entity match
    not_yet_fetched  — live lookup not attempted (empty stub default)
    resolved         — curated CSV or OpenCorporates match
    """

    name: str | None = None
    legal_name: str | None = None
    resolution_status: ResolutionStatus = "not_yet_fetched"
    jurisdiction: str | None = None
    opencorporates_id: str | None = None
    company_number: str | None = None
    source: SponsorSource = "none"


class CmcChecklist(BaseModel):
    """Desk-grade CMC checklist. No LLM poetry — enums / notes only."""

    api_source_identified: DeskBool = "unknown"
    formulation_described: DeskBool = "unknown"
    impurity_profile_available: DeskBool = "unknown"
    stability_data_available: DeskBool = "unknown"
    manufacturing_site_known: DeskBool = "unknown"
    spec_available: DeskBool = "unknown"
    ctd_module_3_available: DeskBool = "unknown"
    comparability_risk: ComparabilityRisk = "unknown"
    notes: str = ""
    confidence: RightsConfidence = "empty_stub"


class ExclusivityWindow(BaseModel):
    exclusivity_type: str | None = None
    start: str | None = None
    end: str | None = None
    status: ExclusivityStatus = "unknown"


class Pathway505b2(BaseModel):
    """505(b)(2) RLD / exclusivity stub. Orange Book hook only until live fill."""

    pathway: PathwayKind = "unknown"
    rld_ref: str | None = None
    listed_drug_name: str | None = None
    listed_drug_ref: str | None = None
    exclusivity_windows: list[ExclusivityWindow] = Field(default_factory=list)
    orange_book_url: str | None = None
    orange_book_hook: str = "orange_book"
    confidence: RightsConfidence = "empty_stub"


class CommercialShape(BaseModel):
    sex_dose_differentiation: bool | None = None
    sex_diff_labeling: bool | None = None
    generic_available: bool | None = None
    pricing_power: PricingPower = "unknown"


class CommercialGate(BaseModel):
    verdict: GateVerdict = "empty_stub"
    reason_codes: list[str] = Field(default_factory=list)
    notes: str = ""


class RightsRecord(BaseModel):
    schema_version: Literal["wave1.rights.v0"] = SCHEMA_VERSION
    programme_id: str
    right_class: RightClass = "unknown"
    patent_families: list[PatentFamily] = Field(default_factory=list)
    listed_drug_ref: str | None = None
    sponsor_entity: SponsorEntity = Field(default_factory=SponsorEntity)
    cmc: CmcChecklist = Field(default_factory=CmcChecklist)
    pathway_505b2: Pathway505b2 = Field(default_factory=Pathway505b2)
    commercial_shape: CommercialShape = Field(default_factory=CommercialShape)
    commercial_gate: CommercialGate = Field(default_factory=CommercialGate)
    modules: dict[str, dict[str, Any]] = Field(default_factory=dict)
    confidence: RightsConfidence = "empty_stub"
    updated_at: str = Field(default_factory=utc_now)
    notes: str = "Empty rights stub. Does not imply ownability."


def empty_cmc() -> dict[str, Any]:
    return CmcChecklist().model_dump()


def empty_pathway_505b2() -> dict[str, Any]:
    return Pathway505b2().model_dump()


def empty_sponsor_entity(*, name: str | None = None, resolution_status: ResolutionStatus = "not_yet_fetched") -> dict[str, Any]:
    return SponsorEntity(name=name, resolution_status=resolution_status).model_dump()


def empty_rights(programme_id: str, **overrides: Any) -> dict[str, Any]:
    """Empty attach. confidence is always empty_stub unless caller filled rights."""
    record = RightsRecord(programme_id=programme_id)
    payload = record.model_dump()
    payload.update(overrides)
    if not _has_filled_right(payload):
        payload["confidence"] = "empty_stub"
        payload.setdefault("commercial_gate", {})
        if payload["commercial_gate"].get("verdict") == "PASS":
            payload["commercial_gate"]["verdict"] = "empty_stub"
        payload["notes"] = "Empty rights stub. Does not imply ownability."
    return payload


def _has_filled_right(payload: dict[str, Any]) -> bool:
    if payload.get("patent_families"):
        return True
    if payload.get("listed_drug_ref"):
        return True
    if payload.get("right_class") in {"option", "505(b)(2)", "method_of_use"}:
        return True
    path = payload.get("pathway_505b2") or {}
    if path.get("rld_ref") or path.get("listed_drug_ref") or path.get("exclusivity_windows"):
        return True
    return False


def assert_empty_stub_not_ownable(payload: dict[str, Any]) -> None:
    if payload.get("confidence") == "empty_stub" and payload.get("commercial_gate", {}).get("verdict") == "PASS":
        raise ValueError("empty_stub confidence must not imply ownability (commercial_gate=PASS)")
