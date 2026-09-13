"""Schema wave-1b.rights-stub.v1 — Asset IP lock (Eng buy-in).

Content primary key is nct_id when an NCT exists. programme_id is clustering
only (existing identity graph). Always create the stub, even if taxonomy is
empty (FOR-6219). confidence=empty_stub never implies ownability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.rights.codes import HARD_KILL_CODES, SOFT_CODES

SCHEMA_VERSION = "wave-1b.rights-stub.v1"
REQUIRED_BLOCKS = (
    "identity",
    "counterparty",
    "ind_regulatory",
    "ip",
    "fto_lite",
    "coi",
    "ownership",
    "kill",
    "process",
)

RightClass = Literal["option", "505(b)(2)", "method_of_use", "unknown"]
RightsConfidence = Literal["empty_stub", "low", "medium", "high"]
DeskClassification = Literal["WALK_AWAY", "CONTINGENT", "NEEDS_COUNSEL", "PASS"]
OwnershipRecommendation = Literal["walk_away", "contingent", "hold", "needs_counsel", "unknown"]
DeskBool = Literal["yes", "no", "unknown"]
ResolutionStatus = Literal["unknown", "not_yet_fetched", "resolved"]
GateVerdict = Literal["PASS", "FAIL", "HOLD", "empty_stub"]
PricingPower = Literal["none", "unknown", "present"]
ComparabilityRisk = Literal["low", "medium", "high", "unknown"]
PathwayKind = Literal["505(b)(2)", "505(j)", "505(b)(1)", "unknown"]
ExclusivityStatus = Literal["unknown", "active", "expired", "not_applicable"]
PatentStatus = Literal["unknown", "pending", "granted", "expired", "lapsed"]
SponsorSource = Literal["unstructured_registry", "curated_csv", "opencorporates", "none"]
Outreach = Literal["none"]
IndStatus = Literal["unknown", "active", "inactive", "withdrawn"]
AssignStatus = Literal["unknown", "not_yet_fetched", "recorded", "gap"]
FtoStatus = Literal["empty_stub", "clear", "blocked", "unknown"]
CoiStatus = Literal["unclear", "clear", "flagged"]
HardKillCode = Literal[
    "K_THESIS_MISMATCH",
    "K_NO_COUNTERPARTY",
    "K_NO_IP_EMPTY_DOCKET",
    "K_COM_ELSEWHERE",
    "K_VALUE_NOT_CAPTURED",
    "K_REG_CAPTURE_DESTROY",
    "K_FAILED_PIVOTAL",
]
SoftCode = Literal[
    "S_PRIVATE_IP_ONLY",
    "S_LICENSE_MAP_MISSING",
    "S_ORANGE_BOOK_BLOCK",
    "S_COI_UNCLEAR",
    "S_TAXONOMY_FIX",
]


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


class Taxonomy(BaseModel):
    indication: str | None = None
    target: str | None = None
    modality: str | None = None
    empty: bool = True


class IdentityBlock(BaseModel):
    nct_id: str | None = None
    programme_id: str
    eu_ct: str | None = None
    eudract: str | None = None
    asset_name: str | None = None
    taxonomy: Taxonomy = Field(default_factory=Taxonomy)
    thesis_mismatch: bool = False
    thesis_mismatch_reason: str | None = None


class CounterpartyBlock(BaseModel):
    present: bool = False
    holder_name: str | None = None
    holder_status: ResolutionStatus = "not_yet_fetched"
    sponsor_entity: SponsorEntity = Field(default_factory=SponsorEntity)


class IndRegulatoryBlock(BaseModel):
    ind_number: str | None = None
    ind_holder: str | None = None
    status: IndStatus = "unknown"
    pathway: PathwayKind = "unknown"
    cmc: CmcChecklist = Field(default_factory=CmcChecklist)
    pathway_505b2: Pathway505b2 = Field(default_factory=Pathway505b2)


class Assignment(BaseModel):
    status: AssignStatus = "not_yet_fetched"
    assignee: str | None = None
    chain_of_title: list[dict[str, Any]] = Field(default_factory=list)


class OrangeBookStub(BaseModel):
    rld_ref: str | None = None
    listed_drug_ref: str | None = None
    exclusivity_windows: list[ExclusivityWindow] = Field(default_factory=list)
    url: str | None = None
    hook: str = "orange_book"
    confidence: RightsConfidence = "empty_stub"


class IpBlock(BaseModel):
    right_class: RightClass = "unknown"
    assignment: Assignment = Field(default_factory=Assignment)
    patent_families: list[PatentFamily] = Field(default_factory=list)
    orange_book: OrangeBookStub = Field(default_factory=OrangeBookStub)
    listed_drug_ref: str | None = None
    docket_empty: bool = True


class FtoLiteBlock(BaseModel):
    status: FtoStatus = "empty_stub"
    blocking_refs: list[str] = Field(default_factory=list)
    note: str = ""
    confidence: RightsConfidence = "empty_stub"


class CoiBlock(BaseModel):
    status: CoiStatus = "unclear"
    flags: list[str] = Field(default_factory=list)
    note: str = ""


class OwnershipBlock(BaseModel):
    """Required. Empty stub is never ownable."""

    status: ResolutionStatus = "not_yet_fetched"
    holder: str | None = None
    ownable: bool = False
    confidence: RightsConfidence = "empty_stub"
    recommendation: OwnershipRecommendation | None = None
    note: str = "Empty stub. Does not imply ownability."


class KillBlock(BaseModel):
    triggered: bool = False
    codes: list[str] = Field(default_factory=list)
    hard: list[str] = Field(default_factory=list)
    soft: list[str] = Field(default_factory=list)
    notes: str = ""


class ProcessBlock(BaseModel):
    outreach: Outreach = "none"
    updated_by: str | None = None
    updated_at: str | None = None
    note: str | None = None


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
    schema_version: Literal["wave-1b.rights-stub.v1"] = SCHEMA_VERSION
    nct_id: str | None = None
    programme_id: str
    confidence: RightsConfidence = "empty_stub"
    desk_classification: DeskClassification | None = None
    shortlist_ownable: bool = False
    optionable_candidate: bool = False
    identity: IdentityBlock
    counterparty: CounterpartyBlock = Field(default_factory=CounterpartyBlock)
    ind_regulatory: IndRegulatoryBlock = Field(default_factory=IndRegulatoryBlock)
    ip: IpBlock = Field(default_factory=IpBlock)
    fto_lite: FtoLiteBlock = Field(default_factory=FtoLiteBlock)
    coi: CoiBlock = Field(default_factory=CoiBlock)
    ownership: OwnershipBlock = Field(default_factory=OwnershipBlock)
    kill: KillBlock = Field(default_factory=KillBlock)
    process: ProcessBlock = Field(default_factory=ProcessBlock)
    commercial_shape: CommercialShape = Field(default_factory=CommercialShape)
    commercial_gate: CommercialGate = Field(default_factory=CommercialGate)
    modules: dict[str, dict[str, Any]] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=utc_now)
    notes: str = "Empty rights stub. Does not imply ownability."

    @model_validator(mode="after")
    def _lock_empty_stub(self) -> "RightsRecord":
        if self.confidence == "empty_stub":
            self.ownership.ownable = False
            self.ownership.confidence = "empty_stub"
            self.desk_classification = None
            if self.commercial_gate.verdict == "PASS":
                self.commercial_gate.verdict = "empty_stub"
            if self.process.outreach != "none":
                self.process.outreach = "none"
        if self.desk_classification in {"WALK_AWAY", "CONTINGENT", "NEEDS_COUNSEL"}:
            self.ownership.ownable = False
            if self.commercial_gate.verdict == "PASS":
                self.commercial_gate.verdict = "FAIL" if self.desk_classification == "WALK_AWAY" else "HOLD"
        if self.process.outreach != "none":
            self.process.outreach = "none"
        # Empty / unfilled / killed / not-ownable is never optionable.
        self.shortlist_ownable = False
        self.optionable_candidate = False
        self.identity.programme_id = self.programme_id
        if self.nct_id:
            self.identity.nct_id = self.nct_id
        self.identity.taxonomy.empty = not any(
            [self.identity.taxonomy.indication, self.identity.taxonomy.target, self.identity.taxonomy.modality]
        )
        return self


def empty_cmc() -> dict[str, Any]:
    return CmcChecklist().model_dump()


def empty_pathway_505b2() -> dict[str, Any]:
    return Pathway505b2().model_dump()


def empty_sponsor_entity(*, name: str | None = None, resolution_status: ResolutionStatus = "not_yet_fetched") -> dict[str, Any]:
    return SponsorEntity(name=name, resolution_status=resolution_status).model_dump()


def content_key(*, nct_id: str | None, programme_id: str) -> str:
    """nct_id is the content PK when present; otherwise programme_id (EU-only)."""
    return nct_id or programme_id


def empty_rights(programme_id: str, nct_id: str | None = None, **overrides: Any) -> dict[str, Any]:
    """Empty attach. Always created, even with empty taxonomy. Never ownable."""
    identity = overrides.pop("identity", None)
    record = RightsRecord(
        programme_id=programme_id,
        nct_id=nct_id,
        identity=identity
        or IdentityBlock(
            programme_id=programme_id,
            nct_id=nct_id,
            taxonomy=Taxonomy(empty=True),
        ),
    )
    payload = record.model_dump()
    payload.update(overrides)
    payload["schema_version"] = SCHEMA_VERSION
    payload["programme_id"] = programme_id
    if nct_id:
        payload["nct_id"] = nct_id
        payload.setdefault("identity", {})["nct_id"] = nct_id
        payload["identity"]["programme_id"] = programme_id
    payload["process"] = {"outreach": "none"}
    payload["ownership"] = {
        **(payload.get("ownership") or {}),
        "ownable": False,
        "confidence": "empty_stub",
        "recommendation": None,
        "note": "Empty stub. Does not imply ownability.",
    }
    payload["confidence"] = "empty_stub"
    payload["desk_classification"] = None
    payload["shortlist_ownable"] = False
    payload["optionable_candidate"] = False
    payload.setdefault("commercial_gate", {})
    if payload["commercial_gate"].get("verdict") == "PASS":
        payload["commercial_gate"]["verdict"] = "empty_stub"
    payload["notes"] = "Empty rights stub. Does not imply ownability."
    _seed_soft_codes(payload)
    return RightsRecord.model_validate(payload).model_dump()


def _seed_soft_codes(payload: dict[str, Any]) -> None:
    """Queryable soft flags on an empty stub. Do not set kill.triggered."""
    soft: list[str] = []
    taxonomy = (payload.get("identity") or {}).get("taxonomy") or {}
    if taxonomy.get("empty", True):
        soft.append("S_TAXONOMY_FIX")
    if (payload.get("coi") or {}).get("status", "unclear") == "unclear":
        soft.append("S_COI_UNCLEAR")
    if (payload.get("ip") or {}).get("docket_empty", True):
        soft.append("S_LICENSE_MAP_MISSING")
    kill = payload.setdefault("kill", {})
    existing = list(kill.get("soft") or [])
    for code in soft:
        if code not in existing:
            existing.append(code)
    kill["soft"] = existing
    hard = list(kill.get("hard") or [])
    kill["hard"] = hard
    codes = list(dict.fromkeys([*hard, *existing, *(kill.get("codes") or [])]))
    kill["codes"] = codes
    kill["triggered"] = bool(hard)


def assert_empty_stub_not_ownable(payload: dict[str, Any]) -> None:
    if payload.get("confidence") == "empty_stub":
        if payload.get("commercial_gate", {}).get("verdict") == "PASS":
            raise ValueError("empty_stub confidence must not imply ownability (commercial_gate=PASS)")
        if (payload.get("ownership") or {}).get("ownable"):
            raise ValueError("empty_stub confidence must not imply ownability (ownership.ownable)")


def cmc_of(payload: dict[str, Any]) -> dict[str, Any]:
    return ((payload.get("ind_regulatory") or {}).get("cmc")) or empty_cmc()


def pathway_505b2_of(payload: dict[str, Any]) -> dict[str, Any]:
    return ((payload.get("ind_regulatory") or {}).get("pathway_505b2")) or empty_pathway_505b2()


def sponsor_entity_of(payload: dict[str, Any]) -> dict[str, Any]:
    return ((payload.get("counterparty") or {}).get("sponsor_entity")) or empty_sponsor_entity()


# Re-export catalogs for tests / Decision Required.
HARD_KILL_CODE_SET = set(HARD_KILL_CODES)
SOFT_CODE_SET = set(SOFT_CODES)
