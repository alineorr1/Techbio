"""0-100 score with four visible components. Rule A (safety cap) and Rule B (Organon guard)."""

from __future__ import annotations

from datetime import date
from typing import Any

from src.config import scoring_config
from src.extract.schema import POPULATION_BOOLEAN_FIELDS, Classification, Extraction
from src.ingest.ctg import nested, parse_date, years_since
from src.rights.gates import apply_score_caps, evaluate_commercial_gate
from src.rights.query import apply_gate_to_rights, ownability_query


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def mechanism_component(enrich: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    mech = cfg.get("mechanism") or {}
    ot = (enrich or {}).get("open_targets") or {}
    overall = ot.get("overall_association_score")
    genetic = ot.get("genetic_association_score") or 0.0
    known_drug = bool(ot.get("known_drugs"))
    literature_only = bool(ot.get("literature_only"))
    scale = float(mech.get("overall_association_scale") or 100)
    gscale = float(mech.get("genetic_bonus_scale") or 40)
    kbonus = float(mech.get("known_drug_bonus") or 15)
    lit_pen = float(mech.get("literature_only_penalty") or 0.45)

    if overall is None:
        raw = 18.0  # thin independent evidence
        note = "No Open Targets association for a named gene; mechanism component is a floor, not a pass."
    else:
        raw = float(overall) * scale + float(genetic) * gscale
        if known_drug:
            raw += kbonus
        note = "Open Targets overall association scaled to 0-100, plus genetic bonus."
        if literature_only:
            raw *= lit_pen
            note += " Literature-only evidence penalised (Organon-relevant: papers after a failed trial are not independent)."
    value = _clip(raw)
    return {
        "value": round(value, 2),
        "overall_association_score": overall,
        "genetic_association_score": genetic,
        "known_drug": known_drug,
        "literature_only": literature_only,
        "note": note,
        "sources": ot.get("sources") or [],
    }


def failure_mode_component(clf: Classification, cfg: dict[str, Any]) -> dict[str, Any]:
    table = cfg.get("failure_mode_scores") or {}
    value = float(table.get(clf.failure_mode, table.get("unclear", 40)))
    return {
        "value": round(value, 2),
        "failure_mode": clf.failure_mode,
        "rule_fired": clf.rule_fired,
        "note": f"Lookup of {clf.failure_mode} in config/scoring.yaml failure_mode_scores.",
    }


def population_component(extraction: Extraction, cfg: dict[str, Any]) -> dict[str, Any]:
    fields = cfg.get("population_booleans") or POPULATION_BOOLEAN_FIELDS
    captured = []
    missing = []
    for f in fields:
        on = bool(getattr(extraction.population, f))
        (captured if on else missing).append(f)
    n = len(fields) or 1
    # Inverted: fewer captured variables => higher score (trial could not have falsified biology)
    value = 100.0 * (1.0 - len(captured) / n)
    return {
        "value": round(value, 2),
        "captured": captured,
        "missing": missing,
        "n_captured": len(captured),
        "n_fields": n,
        "note": "Inverted capture rate of female-specific population variables from the extraction.",
    }


def accessibility_component(
    study: dict[str, Any],
    enrich: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    acc = cfg.get("accessibility") or {}
    sponsor = (enrich or {}).get("sponsor") or {}
    status = sponsor.get("status") or "unknown"
    sp_pts = float((acc.get("sponsor_status_points") or {}).get(status, 42))
    phases = nested(study, "protocolSection", "designModule", "phases") or ["UNKNOWN"]
    phase_table = acc.get("phase_points") or {}
    phase_pts = max(float(phase_table.get(p, 34)) for p in phases)
    stop = nested(study, "protocolSection", "statusModule", "completionDateStruct", "date") or nested(
        study, "protocolSection", "statusModule", "primaryCompletionDateStruct", "date"
    )
    years = years_since(stop) or years_since(
        nested(study, "protocolSection", "statusModule", "lastUpdatePostDateStruct", "date")
    )
    ycfg = acc.get("years_since_stop") or {}
    peak_lo = float(ycfg.get("peak_low") or 2)
    peak_hi = float(ycfg.get("peak_high") or 8)
    ymax = float(ycfg.get("max_points") or 100)
    if years is None:
        year_pts = 50.0
    elif years < peak_lo:
        year_pts = ymax * (years / peak_lo) if peak_lo else ymax
    elif years <= peak_hi:
        year_pts = ymax
    else:
        year_pts = ymax * max(0.25, 1.0 - (years - peak_hi) / 12.0)
    # Weighted blend of the three accessibility sub-parts (equal).
    value = (sp_pts + phase_pts + year_pts) / 3.0
    return {
        "value": round(_clip(value), 2),
        "sponsor_status": status,
        "sponsor_points": sp_pts,
        "phase": phases,
        "phase_points": phase_pts,
        "years_since_stop": None if years is None else round(years, 2),
        "years_points": round(year_pts, 2),
        "sponsor_source_url": sponsor.get("source_url"),
        "note": "Mean of sponsor-status, phase-reached, and years-since-stop sub-scores from config/scoring.yaml.",
    }


def pretrial_mechanism_evidence(enrich: dict[str, Any], study: dict[str, Any]) -> dict[str, Any]:
    start = parse_date(nested(study, "protocolSection", "statusModule", "startDateStruct", "date"))
    items = ((enrich or {}).get("open_targets") or {}).get("evidence_items") or []
    pre = []
    post = []
    for ev in items:
        year = ev.get("publication_year") or ev.get("evidence_year")
        ev_date = parse_date(ev.get("publication_date") or ev.get("evidence_date"))
        marker = None
        if ev_date and start:
            marker = "pre_trial" if ev_date < start else "post_trial"
        elif year and start:
            marker = "pre_trial" if int(year) < start.year else "post_trial"
        rec = {**ev, "timing": marker}
        if marker == "pre_trial":
            pre.append(rec)
        else:
            post.append(rec)
    return {
        "trial_start": None if not start else start.isoformat(),
        "has_pretrial_evidence": bool(pre),
        "pretrial_count": len(pre),
        "posttrial_count": len(post),
        "pretrial": pre[:8],
        "posttrial": post[:8],
    }


def uncertainty(extraction: Extraction, cfg: dict[str, Any]) -> dict[str, Any]:
    conf = cfg.get("confidence") or {}
    rank = conf.get("extraction_confidence_rank") or {"high": 1.0, "medium": 0.75, "low": 0.45}
    flag_n = int(conf.get("unresolved_high_flag") or 4)
    n_unresolved = len(extraction.unresolved)
    factor = float(rank.get(extraction.extraction_confidence, 0.5))
    high_uncertainty = n_unresolved >= flag_n or extraction.extraction_confidence == "low"
    # Display interval: +/- 15 points when high uncertainty, +/- 6 otherwise, scaled.
    half = 15.0 if high_uncertainty else 6.0
    half = half * (1.5 - 0.5 * factor)
    return {
        "extraction_confidence": extraction.extraction_confidence,
        "n_unresolved": n_unresolved,
        "unresolved": extraction.unresolved,
        "high_uncertainty": high_uncertainty,
        "interval_halfwidth": round(half, 1),
        "flag": "HIGH_UNCERTAINTY" if high_uncertainty else "OK",
    }


def score_asset(
    study: dict[str, Any],
    extraction: Extraction,
    classification: Classification,
    enrich: dict[str, Any] | None = None,
    rights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = scoring_config()
    weights = cfg["weights"]
    enrich = enrich or {}
    named_genes = {t.gene_symbol for t in extraction.targets if t.gene_symbol}
    ot = dict((enrich.get("open_targets") or {}))
    if not named_genes:
        # Never score Open Targets evidence for a gene the record did not name.
        ot = {
            **ot,
            "overall_association_score": None,
            "genetic_association_score": 0.0,
            "evidence_items": [],
            "literature_only": True,
            "known_drugs": [],
            "note": "No named gene symbol in the extraction; Open Targets is not queried.",
        }
        enrich = {**enrich, "open_targets": ot}
    mech = mechanism_component(enrich, cfg)
    fail = failure_mode_component(classification, cfg)
    pop = population_component(extraction, cfg)
    acc = accessibility_component(study, enrich, cfg)
    timing = pretrial_mechanism_evidence(enrich, study)

    w_m, w_f, w_p, w_a = (
        float(weights["mechanism_evidence"]),
        float(weights["failure_mode"]),
        float(weights["population_definition"]),
        float(weights["asset_accessibility"]),
    )
    wsum = w_m + w_f + w_p + w_a
    raw = (
        mech["value"] * w_m + fail["value"] * w_f + pop["value"] * w_p + acc["value"] * w_a
    ) / wsum

    caps: list[str] = []
    capped = raw
    # Rule A
    safety_cap = float((cfg.get("rules") or {}).get("safety_score_cap") or 25)
    if classification.failure_mode == "safety":
        if capped > safety_cap:
            caps.append(f"Rule A: safety failure cap {safety_cap}")
            capped = safety_cap
    # Rule B Organon guard
    organon = float((cfg.get("rules") or {}).get("organon_guard_max_without_pretrial_evidence") or 60)
    if not timing["has_pretrial_evidence"] and capped > organon:
        caps.append(
            f"Rule B (Organon guard): no pre-trial independent mechanism evidence; cap {organon}"
        )
        capped = organon

    extra_names = [t.name for t in extraction.targets] + [t.gene_symbol for t in extraction.targets if t.gene_symbol]
    rights_rec = rights if rights is not None else (enrich or {}).get("rights_record")
    if rights_rec:
        rights_rec = dict(rights_rec)
    gate = evaluate_commercial_gate(
        study=study,
        rights=rights_rec,
        intervention_names=extra_names,
        scoring_cfg=cfg,
    )
    if rights_rec:
        apply_gate_to_rights(rights_rec, gate)
    capped, gate_caps = apply_score_caps(capped, gate)
    caps.extend(gate_caps)
    ownability = ownability_query(rights_rec)

    unc = uncertainty(extraction, cfg)
    lo = _clip(capped - unc["interval_halfwidth"])
    hi = _clip(capped + unc["interval_halfwidth"])

    arithmetic = (
        f"({mech['value']:.1f}×{w_m:.0f} + {fail['value']:.1f}×{w_f:.0f} + "
        f"{pop['value']:.1f}×{w_p:.0f} + {acc['value']:.1f}×{w_a:.0f}) / {wsum:.0f} "
        f"= {raw:.1f}"
    )
    if caps:
        arithmetic += " then " + "; ".join(caps) + f" → {capped:.1f}"

    return {
        "nct_id": extraction.nct_id,
        "score": round(capped, 1),
        "raw_weighted_sum": round(raw, 1),
        "arithmetic": arithmetic,
        "weights": {"mechanism_evidence": w_m, "failure_mode": w_f, "population_definition": w_p, "asset_accessibility": w_a},
        "components": {
            "mechanism_evidence": mech,
            "failure_mode": fail,
            "population_definition": pop,
            "asset_accessibility": acc,
        },
        "caps_applied": caps,
        "rule_a_safety_cap": classification.failure_mode == "safety",
        "rule_b_organon_guard": (not timing["has_pretrial_evidence"]),
        "commercial_gate": gate,
        "ownability": ownability,
        "pretrial_mechanism": timing,
        "uncertainty": unc,
        "confidence_interval": [round(lo, 1), round(hi, 1)],
        "failure_mode": classification.failure_mode,
        "classification_rule": classification.rule_fired,
    }
