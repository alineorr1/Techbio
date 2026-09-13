"""CTIS retrieve → CTG-shaped study + flatten (Phase-2 score wire).

Public status comes only from ``envelope.public_status`` or
``ctPublicStatusCode`` via ``public_status_from_retrieve``. Never read the
retrieve ``ctStatus`` application-status string.

Ingest/identity only. Does not import classify, score, or serve.
"""

from __future__ import annotations

import re
from typing import Any

from src.identity.programme import identifiers_from_ctis_retrieve, nested
from src.ingest.ctis import public_status_from_retrieve

INCLUDE_UNIVERSES = frozenset({"include", "include_review"})
EXCLUDE_UNIVERSES = frozenset({"exclude", "exclude_pending_end"})

_PHASE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"phase\s*1\s*/\s*2|phase\s*i/?ii\b|phase1_phase2", re.I), "PHASE1_PHASE2"),
    (re.compile(r"phase\s*2\s*/\s*3|phase\s*ii/?iii\b|phase2_phase3", re.I), "PHASE2_PHASE3"),
    (re.compile(r"early\s*phase\s*1|phase\s*0", re.I), "EARLY_PHASE1"),
    (re.compile(r"phase\s*iv\b|phase\s*4\b|therapeutic use", re.I), "PHASE4"),
    (re.compile(r"phase\s*iii\b|phase\s*3\b|therapeutic confirmatory", re.I), "PHASE3"),
    (re.compile(r"phase\s*ii\b|phase\s*2\b|therapeutic exploratory", re.I), "PHASE2"),
    (re.compile(r"phase\s*i\b|phase\s*1\b", re.I), "PHASE1"),
]


def envelope_payload(envelope: dict[str, Any]) -> dict[str, Any]:
    payload = envelope.get("payload")
    if isinstance(payload, dict) and payload.get("ctNumber"):
        return payload
    if envelope.get("ctNumber") and "authorizedApplication" in envelope:
        return envelope
    return payload if isinstance(payload, dict) else envelope


def public_status_of(envelope: dict[str, Any]) -> dict[str, Any]:
    """Prefer the ingest-time public_status block; else retrieve code only."""
    stored = envelope.get("public_status")
    if isinstance(stored, dict) and stored.get("field") in {"ctPublicStatusCode", "search.ctStatus"}:
        return stored
    return public_status_from_retrieve(envelope_payload(envelope))


def in_failed_asset_universe(envelope: dict[str, Any]) -> bool:
    """True for include / include_review public-status codes (shelved universe)."""
    status = public_status_of(envelope)
    if status.get("unmapped"):
        return False
    return status.get("universe") in INCLUDE_UNIVERSES


def is_recruiting_or_active_exclude(envelope: dict[str, Any]) -> bool:
    status = public_status_of(envelope)
    return status.get("universe") in EXCLUDE_UNIVERSES


def mapped_overall_status(envelope: dict[str, Any]) -> str:
    status = public_status_of(envelope)
    mapped = status.get("mapped_status")
    if isinstance(mapped, str) and mapped:
        return mapped
    return "UNKNOWN"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _collect_strings(node: Any, keys: set[str], *, found: list[str] | None = None) -> list[str]:
    out = found if found is not None else []
    if isinstance(node, dict):
        for key, val in node.items():
            if key in keys:
                if isinstance(val, str) and val.strip():
                    out.append(val.strip())
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, str) and item.strip():
                            out.append(item.strip())
            _collect_strings(val, keys, found=out)
    elif isinstance(node, list):
        for item in node:
            _collect_strings(item, keys, found=out)
    return out


def condition_list(payload: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    for item in nested(payload, "authorizedApplication", "authorizedPartI", "medicalConditions") or []:
        if isinstance(item, dict) and item.get("medicalCondition"):
            parts.append(str(item["medicalCondition"]))
    for item in (
        nested(
            payload,
            "authorizedApplication",
            "authorizedPartI",
            "trialDetails",
            "trialInformation",
            "medicalCondition",
            "partIMedicalConditions",
        )
        or []
    ):
        if isinstance(item, dict) and item.get("medicalCondition"):
            parts.append(str(item["medicalCondition"]))
    # de-dupe, preserve order
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        key = part.lower()
        if key not in seen:
            seen.add(key)
            unique.append(part)
    return unique


def titles_of(payload: dict[str, Any]) -> dict[str, str | None]:
    ident = nested(
        payload,
        "authorizedApplication",
        "authorizedPartI",
        "trialDetails",
        "clinicalTrialIdentifiers",
    ) or {}
    return {
        "full": _text(ident.get("fullTitle")),
        "public": _text(ident.get("publicTitle")),
        "short": _text(ident.get("shortTitle")),
    }


_PRODUCT_LIST_KEYS = {
    "products",
    "investigationalMedicinalProducts",
    "medicinalProducts",
    "productList",
    "impList",
}
_PRODUCT_NAME_KEYS = {
    "productName",
    "inventedName",
    "tradeName",
    "substanceName",
    "activeSubstance",
}
_JUNK_PRODUCTS = {
    "patients",
    "number",
    "id",
    "code",
    "value",
    "placebo",
    "matching placebo",
}
_IMAGING_ONLY = re.compile(
    r"\b(pet|positron emission|glucotrace|omnipaque|fdg|fapi|tracer|contrast media)\b",
    re.I,
)
_IMAGING_ADJUNCT = re.compile(
    r"\b(furosemide|omnipaque|buscopan|saline|contrast)\b",
    re.I,
)


def product_names(payload: dict[str, Any], extra: dict[str, Any] | None = None) -> list[str]:
    """Named IMPs only — do not scrape hospital / MeSH / 'Patients' strings."""
    names: list[str] = []
    part_i = nested(payload, "authorizedApplication", "authorizedPartI") or {}
    for key, val in part_i.items():
        if key not in _PRODUCT_LIST_KEYS:
            continue
        names.extend(_collect_strings(val, _PRODUCT_NAME_KEYS))
    if extra and extra.get("product"):
        raw = extra["product"]
        if isinstance(raw, str):
            for chunk in re.split(r",(?![^()]*\))", raw):
                piece = chunk.strip()
                if piece:
                    names.append(piece)
        elif isinstance(raw, list):
            names.extend(str(x).strip() for x in raw if str(x).strip())
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        key = name.lower()
        if key in _JUNK_PRODUCTS or len(name) < 3:
            continue
        if "diseases [c]" in key or "techniques and equipment" in key:
            continue
        if key not in seen:
            seen.add(key)
            out.append(name)
    return out


def is_drug_or_biologic_programme(envelope: dict[str, Any]) -> bool:
    """CTG-equivalent: score drug/biologic programmes, not imaging-only diagnostics."""
    payload = envelope_payload(envelope)
    extra = {}
    if isinstance(envelope.get("match"), dict):
        extra.update(envelope["match"])
    if isinstance(envelope.get("search_row"), dict):
        extra.update(envelope["search_row"])
    names = product_names(payload, extra)
    title = " ".join(
        str(v or "")
        for v in (
            extra.get("ctTitle"),
            extra.get("shortTitle"),
            *(titles_of(payload).values()),
        )
    )
    if _IMAGING_ONLY.search(title):
        return False
    drugs = [
        n
        for n in names
        if not _IMAGING_ONLY.search(n)
        and not _IMAGING_ADJUNCT.search(n)
        and "hospital" not in n.lower()
        and "centre hospitalier" not in n.lower()
    ]
    return bool(drugs)


def sponsor_name(payload: dict[str, Any], extra: dict[str, Any] | None = None) -> str | None:
    if extra and extra.get("sponsor"):
        return _text(extra.get("sponsor"))
    names = _collect_strings(
        nested(payload, "authorizedApplication") or {},
        {"sponsorName", "organisationName", "commercialName", "legalName"},
    )
    return names[0] if names else None


def _parse_enrolment(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _phase_of(text: str | None) -> str:
    if not text:
        return "NA"
    for pat, label in _PHASE_PATTERNS:
        if pat.search(text):
            return label
    return "NA"


def _iso_date(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    match = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", text)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    return text[:10] if len(text) >= 10 else text


def _sex_of(value: Any) -> str | None:
    text = (str(value) if value is not None else "").strip().lower()
    if text in {"f", "female", "women", "woman"}:
        return "FEMALE"
    if text in {"m", "male", "men", "man"}:
        return "MALE"
    if text in {"all", "both", "male and female"}:
        return "ALL"
    return _text(value).upper() if _text(value) else None


def flatten_ctis_text(envelope: dict[str, Any]) -> str:
    """Canonical extractor input. stop_reason_evidence must be a substring of this."""
    payload = envelope_payload(envelope)
    status = public_status_of(envelope)
    titles = titles_of(payload)
    extra = envelope.get("match") if isinstance(envelope.get("match"), dict) else {}
    search = envelope.get("search_row") if isinstance(envelope.get("search_row"), dict) else {}
    meta = {**search, **extra}
    ids = identifiers_from_ctis_retrieve(payload)
    eu_ct = (ids.get("eu_ct") or [payload.get("ctNumber")])[0]
    ncts = ids.get("nct") or []
    lines: list[str] = []

    def add(label: str, value: Any) -> None:
        if value is None or value == "" or value == []:
            return
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value if v not in (None, ""))
            if not value:
                return
        lines.append(f"{label}: {value}")

    add("EU CT", eu_ct)
    if ncts:
        add("NCT ID", ncts[0] if len(ncts) == 1 else ncts)
    add("Brief title", titles["public"] or titles["full"] or titles["short"] or meta.get("ctTitle"))
    add("Official title", titles["full"] or titles["public"])
    add("Acronym", titles["short"] or meta.get("shortTitle"))
    add("Overall status", status.get("mapped_status") or "UNKNOWN")
    add("Public status label", status.get("label"))
    add("Public status code", status.get("code"))
    add("Public status field", status.get("field"))
    add("Why stopped", status.get("label"))
    add("Start date", _iso_date(payload.get("startDateEU") or meta.get("startDateEU")))
    add("Completion date", _iso_date(payload.get("endDateEU") or meta.get("endDateEU")))
    add("Decision date", _iso_date(payload.get("decisionDate") or meta.get("decisionDateOverall")))
    add("Has results", meta.get("resultsFirstReceived"))
    add("Phase", meta.get("trialPhase") or payload.get("trialPhase"))
    add("Lead sponsor", sponsor_name(payload, meta))
    add("Conditions", condition_list(payload) or _text(meta.get("conditions")))
    add("Sex", meta.get("gender") or meta.get("sex"))
    add("Age group", meta.get("ageGroup"))
    add("Enrollment count", meta.get("totalNumberEnrolled") or payload.get("totalNumberEnrolled"))
    for i, name in enumerate(product_names(payload, meta), 1):
        add(f"Intervention {i} type", "DRUG")
        add(f"Intervention {i} name", name)
    add("Primary outcome 1 measure", meta.get("primaryEndPoint") or meta.get("endPoint"))
    add("Eligibility criteria", meta.get("endPoint"))
    if extra.get("secondary_only_match"):
        add("Secondary only match", True)
    return "\n".join(lines)


def ctis_to_study(envelope: dict[str, Any]) -> dict[str, Any]:
    """Project a CTIS envelope onto the CTG-shaped dict extract/classify/score read."""
    payload = envelope_payload(envelope)
    status = public_status_of(envelope)
    titles = titles_of(payload)
    extra = envelope.get("match") if isinstance(envelope.get("match"), dict) else {}
    search = envelope.get("search_row") if isinstance(envelope.get("search_row"), dict) else {}
    meta = {**search, **extra}
    ids = identifiers_from_ctis_retrieve(payload)
    eu_ct = (ids.get("eu_ct") or [str(payload.get("ctNumber") or envelope.get("native_id") or "")])[0]
    ncts = list(ids.get("nct") or [])
    nct = ncts[0] if ncts else ""
    conditions = condition_list(payload)
    if not conditions and meta.get("conditions"):
        conditions = [c.strip() for c in str(meta["conditions"]).split(",") if c.strip()]
    products = product_names(payload, meta)
    start = _iso_date(payload.get("startDateEU") or meta.get("startDateEU"))
    end = _iso_date(payload.get("endDateEU") or meta.get("endDateEU"))
    decision = _iso_date(payload.get("decisionDate") or meta.get("decisionDateOverall"))
    enrol = _parse_enrolment(meta.get("totalNumberEnrolled") or payload.get("totalNumberEnrolled"))
    phase = _phase_of(str(meta.get("trialPhase") or payload.get("trialPhase") or ""))
    sponsor = sponsor_name(payload, meta)
    primary = _text(meta.get("primaryEndPoint") or meta.get("endPoint"))
    why = _text(status.get("label"))
    overall = mapped_overall_status(envelope)

    study = {
        "protocolSection": {
            "identificationModule": {
                "nctId": nct,
                "orgStudyIdInfo": {"id": eu_ct},
                "briefTitle": titles["public"] or titles["full"] or titles["short"] or meta.get("ctTitle") or eu_ct,
                "officialTitle": titles["full"] or titles["public"] or meta.get("ctTitle"),
                "acronym": titles["short"] or meta.get("shortTitle"),
            },
            "statusModule": {
                "overallStatus": overall,
                "whyStopped": why,
                "startDateStruct": {"date": start} if start else {},
                "primaryCompletionDateStruct": {"date": end or decision} if (end or decision) else {},
                "completionDateStruct": {"date": end or decision} if (end or decision) else {},
                "lastUpdatePostDateStruct": {"date": decision} if decision else {},
            },
            "descriptionModule": {
                "briefSummary": titles["public"] or titles["full"] or "",
                "detailedDescription": titles["full"] or "",
            },
            "conditionsModule": {"conditions": conditions},
            "designModule": {
                "studyType": "INTERVENTIONAL",
                "phases": [phase],
                "enrollmentInfo": {
                    "count": enrol,
                    "type": "ACTUAL" if enrol is not None else None,
                },
            },
            "armsInterventionsModule": {
                "interventions": [{"type": "DRUG", "name": name} for name in products],
            },
            "outcomesModule": {
                "primaryOutcomes": [{"measure": primary, "description": primary}] if primary else [],
            },
            "eligibilityModule": {
                "sex": _sex_of(meta.get("gender") or meta.get("sex")),
                "stdAges": [meta.get("ageGroup")] if meta.get("ageGroup") else [],
                "eligibilityCriteria": primary or "",
            },
            "sponsorCollaboratorsModule": {
                "leadSponsor": {
                    "name": sponsor,
                    "class": meta.get("sponsorType") or "OTHER",
                }
            },
        },
        "hasResults": str(meta.get("resultsFirstReceived") or "").strip().lower() in {"yes", "true", "1"},
        "ctis": {
            "eu_ct": eu_ct,
            "nct_ids": ncts,
            "public_status": status,
            "native_id": envelope.get("native_id") or eu_ct,
        },
    }
    return study


def primary_display_id_of(envelope: dict[str, Any]) -> str:
    payload = envelope_payload(envelope)
    ids = identifiers_from_ctis_retrieve(payload)
    ncts = ids.get("nct") or []
    if ncts:
        return ncts[0]
    eu = ids.get("eu_ct") or [payload.get("ctNumber") or envelope.get("native_id")]
    return str(eu[0])


def nct_ids_of(envelope: dict[str, Any]) -> list[str]:
    return list(identifiers_from_ctis_retrieve(envelope_payload(envelope)).get("nct") or [])


def eu_ct_of(envelope: dict[str, Any]) -> str:
    payload = envelope_payload(envelope)
    ids = identifiers_from_ctis_retrieve(payload)
    eu = ids.get("eu_ct") or []
    if eu:
        return eu[0]
    return str(payload.get("ctNumber") or envelope.get("native_id") or "")
