"""Failure-mode classification. Decision rules from spec section 6, applied in order.

Does not call ingest/extract/enrich/score. Reads their on-disk outputs.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from src.config import scoring_config, sponsor_rows
from src.extract.schema import POPULATION_BOOLEAN_FIELDS, Classification, Extraction
from src.ingest.ctg import nested, parse_date


def _enrolment(study: dict[str, Any]) -> tuple[int | None, int | None, str | None]:
    info = nested(study, "protocolSection", "designModule", "enrollmentInfo") or {}
    count = info.get("count")
    etype = info.get("type")
    # CTG v2 typically has one count + type ACTUAL|ESTIMATED. Anticipated is often lost
    # after completion; we also look at derived/results participant flow.
    actual = count if etype == "ACTUAL" else None
    anticipated = count if etype == "ESTIMATED" else None
    flow = nested(study, "resultsSection", "participantFlowModule")
    if isinstance(flow, dict):
        groups = flow.get("groups") or flow.get("periodGroups") or []
        # periods -> milestones STARTED
        periods = flow.get("periods") or []
        started = None
        for period in periods:
            for ms in period.get("milestones") or []:
                if str(ms.get("type") or ms.get("title") or "").upper() in {"STARTED", "START"}:
                    nums = []
                    for ach in ms.get("achievements") or []:
                        if ach.get("numSubjects") is not None:
                            nums.append(int(ach["numSubjects"]))
                    if nums:
                        started = sum(nums)
        if started is not None:
            actual = started
    return actual, anticipated, etype


def _stop_date(study: dict[str, Any]) -> date | None:
    status = nested(study, "protocolSection", "statusModule") or {}
    for key in (
        "completionDateStruct",
        "primaryCompletionDateStruct",
        "lastUpdatePostDateStruct",
    ):
        dt = parse_date((status.get(key) or {}).get("date"))
        if dt:
            return dt
    return None


def _start_date(study: dict[str, Any]) -> date | None:
    return parse_date(
        nested(study, "protocolSection", "statusModule", "startDateStruct", "date")
    )


def _normalize(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else " " for ch in name).split()[0] if name else ""


def match_sponsor(study: dict[str, Any]) -> dict[str, Any] | None:
    lead = nested(study, "protocolSection", "sponsorCollaboratorsModule", "leadSponsor", "name") or ""
    lead_l = lead.lower()
    best = None
    for row in sponsor_rows():
        needle = (row.get("normalized_name") or "").lower()
        raw = (row.get("sponsor_name") or "").lower()
        if needle and needle in lead_l:
            best = {**row, "matched_lead": lead}
            break
        if raw and (raw in lead_l or lead_l in raw):
            best = {**row, "matched_lead": lead}
            break
    return best


def sponsor_ceased_near_stop(study: dict[str, Any], window_quarters: int = 2) -> bool:
    row = match_sponsor(study)
    if not row:
        return False
    if row.get("status") not in {"ceased", "restructured"}:
        return False
    stop = _stop_date(study)
    as_of = parse_date(row.get("as_of"))
    if not stop or not as_of:
        # ceased/restructured with unknown timing: still a strong funding signal
        return True
    window = timedelta(days=int(window_quarters) * 91)
    return abs((as_of - stop).days) <= window.days or as_of <= stop


def female_specific_capture_count(extraction: Extraction) -> int:
    return sum(1 for f in POPULATION_BOOLEAN_FIELDS if getattr(extraction.population, f))


def _safety_signal(extraction: Extraction, study: dict[str, Any]) -> bool:
    if extraction.stop_reason_category == "safety":
        return True
    why = (nested(study, "protocolSection", "statusModule", "whyStopped") or "").lower()
    if any(
        tok in why
        for tok in (
            "not for safety",
            "not due to any safety",
            "not due to safety",
            "not attributed to safety",
            "no safety concerns",
        )
    ):
        return False
    return any(
        tok in why
        for tok in (
            "safety",
            "hepatotox",
            "clinical hold",
            "adverse",
            "toxicity",
            "fda put the study on hold",
            "risk/benefit",
        )
    )


def classify_record(
    study: dict[str, Any],
    extraction: Extraction,
    enrich: dict[str, Any] | None = None,
    peer_stops: int = 0,
) -> Classification:
    cfg = scoring_config()
    cl = cfg.get("classify") or {}
    threshold = float(cl.get("enrolment_recruitment_threshold") or 0.5)
    quarters = int(cl.get("sponsor_window_quarters") or 2)
    min_vars = int(cl.get("female_specific_vars_for_interpretable_efficacy") or 3)

    actual, anticipated, etype = _enrolment(study)
    ratio = None
    if actual is not None and anticipated and anticipated > 0:
        ratio = actual / anticipated
    # If only actual is known and is 0, treat as below threshold.
    if ratio is None and actual == 0:
        ratio = 0.0

    enrolment_proceeding = False
    if anticipated and actual is not None:
        enrolment_proceeding = actual >= 0.25 * anticipated and actual > 0
    elif actual is not None and actual > 0 and etype == "ACTUAL":
        enrolment_proceeding = True

    ceased = sponsor_ceased_near_stop(study, quarters)
    captured = female_specific_capture_count(extraction)
    safety = _safety_signal(extraction, study)
    stated = extraction.stop_reason_category
    published = bool((enrich or {}).get("europepmc", {}).get("has_results_publication"))
    target_advanced = bool((enrich or {}).get("open_targets", {}).get("target_advanced_elsewhere"))

    signals: dict[str, Any] = {
        "extracted_category": stated,
        "enrolment_actual": actual,
        "enrolment_anticipated": anticipated,
        "enrolment_type": etype,
        "enrolment_ratio": ratio,
        "enrolment_proceeding": enrolment_proceeding,
        "sponsor_match": match_sponsor(study),
        "sponsor_ceased_near_stop": ceased,
        "peer_trials_stopped_same_window": peer_stops,
        "female_specific_vars_captured": captured,
        "safety_signal": safety,
        "results_published": published,
        "target_advanced_elsewhere": target_advanced,
        "stop_reason_evidence": extraction.stop_reason_evidence,
        "stop_reason_raw": extraction.stop_reason_raw,
    }

    # Rule 1
    if ceased and enrolment_proceeding:
        return Classification(
            nct_id=extraction.nct_id,
            failure_mode="funding_or_sponsor",
            confidence="high",
            signals=signals,
            rule_fired="1_sponsor_ceased_while_enrolling",
            notes="Sponsor ceased/restructured within two quarters of stop and enrolment was proceeding.",
        )
    # Rule 2
    if ratio is not None and ratio < threshold and not safety:
        return Classification(
            nct_id=extraction.nct_id,
            failure_mode="recruitment",
            confidence="high" if ratio < 0.25 else "medium",
            signals=signals,
            rule_fired="2_enrolment_below_half_no_safety",
            notes=f"Actual enrolment {actual} vs anticipated {anticipated} (ratio={ratio:.2f}) with no safety signal.",
        )
    # Rule 3 / 4
    if stated == "efficacy":
        if captured <= (min_vars - 1):
            return Classification(
                nct_id=extraction.nct_id,
                failure_mode="efficacy_uninterpretable",
                confidence="medium",
                signals=signals,
                rule_fired="3_efficacy_but_population_underspecified",
                notes=f"Stated efficacy failure but only {captured} female-specific population variables captured.",
            )
        return Classification(
            nct_id=extraction.nct_id,
            failure_mode="efficacy",
            confidence="high",
            signals=signals,
            rule_fired="4_efficacy_with_adequate_stratification",
            notes=f"Stated efficacy failure with {captured} population variables captured.",
        )
    # Rule 5
    if safety:
        return Classification(
            nct_id=extraction.nct_id,
            failure_mode="safety",
            confidence="high",
            signals=signals,
            rule_fired="5_safety_signal",
            notes="Safety signal present; ranked down hard. No cleverness.",
        )
    # Mapped extracted categories that are operational
    if stated == "funding_or_sponsor":
        return Classification(
            nct_id=extraction.nct_id,
            failure_mode="funding_or_sponsor",
            confidence="medium",
            signals=signals,
            rule_fired="6_extracted_funding",
            notes="Extracted stop category is funding/sponsor; no earlier rule fired.",
        )
    if stated == "recruitment":
        return Classification(
            nct_id=extraction.nct_id,
            failure_mode="recruitment",
            confidence="medium",
            signals=signals,
            rule_fired="6_extracted_recruitment",
            notes="Extracted stop category is recruitment; enrolment ratio unavailable or above threshold.",
        )
    # Rule 6
    return Classification(
        nct_id=extraction.nct_id,
        failure_mode="unclear",
        confidence="low",
        signals=signals,
        rule_fired="6_unclear_surface_for_review",
        notes="No earlier rule fired. Surface for human review rather than guessing.",
    )
