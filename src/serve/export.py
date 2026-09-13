"""Serve stage: export a versioned JSON snapshot the dashboard can load with no backend."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import indications_config, scoring_config
from src.db import connect, dump_json, load_json
from src.extract.schema import POPULATION_BOOLEAN_FIELDS
from src.ingest.ctg import nested
from src.paths import (
    CHANGE_REPORT_DIR,
    CLASSIFY_DIR,
    ENRICH_DIR,
    EXTRACT_DIR,
    FEEDBACK_PATH,
    RAW_CTG_DIR,
    SCORE_DIR,
    SNAPSHOT_DIR,
    ensure_dirs,
)
from src.identity.programme import identifiers_from_nct, programme_id_for
from src.rights.query import ownability_query
from src.rights.schema import cmc_of, empty_rights, pathway_505b2_of
from src.rights.store import load_rights, rights_for_nct


import re

def _indication(study: dict[str, Any]) -> str:
    cfg = indications_config()
    conds = " ".join(nested(study, "protocolSection", "conditionsModule", "conditions") or []).lower()
    title = (
        (nested(study, "protocolSection", "identificationModule", "briefTitle") or "")
        + " "
        + (nested(study, "protocolSection", "identificationModule", "officialTitle") or "")
    ).lower()
    blob = f"{conds} {title}"
    for key, ind in cfg["indications"].items():
        for syn in ind.get("synonyms") or []:
            syn_l = syn.lower().strip()
            if len(syn_l) < 4:
                continue
            if re.search(rf"\b{re.escape(syn_l)}\b", blob):
                return key
    return "other"


def _male_only(study: dict[str, Any]) -> bool:
    sex = (nested(study, "protocolSection", "eligibilityModule", "sex") or "").upper()
    return sex == "MALE"


def _links(nct: str, enrich: dict[str, Any]) -> list[dict[str, str]]:
    links = [
        {"label": "ClinicalTrials.gov record", "url": f"https://clinicaltrials.gov/study/{nct}"},
        {"label": "ClinicalTrials.gov API (verbatim JSON)", "url": f"https://clinicaltrials.gov/api/v2/studies/{nct}"},
    ]
    for s in ((enrich.get("open_targets") or {}).get("sources") or []):
        if s.get("url"):
            links.append({"label": s.get("label") or "Open Targets", "url": s["url"]})
    epmc = enrich.get("europepmc") or {}
    if epmc.get("source_url"):
        links.append({"label": "Europe PMC search (NCT ID)", "url": epmc["source_url"]})
    for p in epmc.get("papers") or []:
        if p.get("url"):
            links.append({"label": p.get("title") or "Publication", "url": p["url"]})
    sp = enrich.get("sponsor") or {}
    if sp.get("source_url"):
        links.append({"label": f"Sponsor status source ({sp.get('status')})", "url": sp["source_url"]})
    return links


def build_asset(nct: str) -> dict[str, Any] | None:
    raw_path = RAW_CTG_DIR / f"{nct}.json"
    ext_path = EXTRACT_DIR / f"{nct}.json"
    clf_path = CLASSIFY_DIR / f"{nct}.json"
    score_path = SCORE_DIR / f"{nct}.json"
    if not (raw_path.exists() and ext_path.exists() and clf_path.exists() and score_path.exists()):
        return None
    study = load_json(raw_path)
    extraction = load_json(ext_path)
    clf = load_json(clf_path)
    scored = load_json(score_path)
    enrich = load_json(ENRICH_DIR / f"{nct}.json") if (ENRICH_DIR / f"{nct}.json").exists() else {}
    if _male_only(study):
        return None
    ident = nested(study, "protocolSection", "identificationModule") or {}
    status = nested(study, "protocolSection", "statusModule") or {}
    design = nested(study, "protocolSection", "designModule") or {}
    sponsor = nested(study, "protocolSection", "sponsorCollaboratorsModule", "leadSponsor") or {}
    conds = nested(study, "protocolSection", "conditionsModule", "conditions") or []
    ints = nested(study, "protocolSection", "armsInterventionsModule", "interventions") or []
    pop = extraction.get("population") or {}
    indication = _indication(study)
    ind_label = (indications_config()["indications"].get(indication) or {}).get("label") or indication
    pid = (enrich.get("programme_id") or programme_id_for(identifiers_from_nct(nct)))
    rights = enrich.get("rights_record") or load_rights(nct_id=nct, programme_id=pid) or rights_for_nct(nct)
    if not rights:
        rights = empty_rights(pid, nct_id=nct)
    return {
        "nct_id": nct,
        "programme_id": pid,
        "brief_title": ident.get("briefTitle"),
        "official_title": ident.get("officialTitle"),
        "indication": indication,
        "indication_label": ind_label,
        "conditions": conds,
        "phase": design.get("phases") or ["NA"],
        "overall_status": status.get("overallStatus"),
        "why_stopped": status.get("whyStopped"),
        "start_date": nested(status, "startDateStruct", "date"),
        "primary_completion_date": nested(status, "primaryCompletionDateStruct", "date"),
        "completion_date": nested(status, "completionDateStruct", "date"),
        "last_update_date": nested(status, "lastUpdatePostDateStruct", "date"),
        "year_stopped": (nested(status, "completionDateStruct", "date") or nested(status, "primaryCompletionDateStruct", "date") or "")[:4],
        "sponsor_name": sponsor.get("name"),
        "sponsor_class": sponsor.get("class"),
        "sponsor_status": (enrich.get("sponsor") or {}).get("status") or "unknown",
        "enrolment": nested(study, "protocolSection", "designModule", "enrollmentInfo"),
        "has_results": study.get("hasResults"),
        "interventions": [{"name": i.get("name"), "type": i.get("type")} for i in ints],
        "targets": extraction.get("targets") or [],
        "mechanism_summary": extraction.get("mechanism_summary"),
        "extraction": extraction,
        "classification": clf,
        "score": scored,
        "enrichment": {
            "open_targets": enrich.get("open_targets") or {},
            "europepmc": {
                "has_results_publication": (enrich.get("europepmc") or {}).get("has_results_publication"),
                "silence_after_completion": (enrich.get("europepmc") or {}).get("silence_after_completion"),
                "papers": (enrich.get("europepmc") or {}).get("papers") or [],
                "source_url": (enrich.get("europepmc") or {}).get("source_url"),
            },
            "sponsor": enrich.get("sponsor") or {},
            "rights": enrich.get("rights") or {
                "schema_version": rights.get("schema_version"),
                "nct_id": nct,
                "programme_id": pid,
                "confidence": rights.get("confidence") or "empty_stub",
            },
        },
        "rights": rights,
        "ownability": ownability_query(rights),
        "cmc": cmc_of(rights) if isinstance(rights, dict) else cmc_of({}),
        "pathway_505b2": pathway_505b2_of(rights) if isinstance(rights, dict) else pathway_505b2_of({}),
        "population_checklist": [
            {"field": f, "captured": bool(pop.get(f)), "source": "extraction.population"}
            for f in POPULATION_BOOLEAN_FIELDS
        ],
        "links": _links(nct, enrich),
        "sources": {
            "registry_json": f"data/raw/ctg/{nct}.json",
            "extraction_json": f"data/derived/extract/{nct}.json",
            "classification_json": f"data/derived/classify/{nct}.json",
            "score_json": f"data/derived/score/{nct}.json",
            "rights_json": f"data/derived/rights/{nct}.json",
        },
    }


def landscape(assets: list[dict[str, Any]]) -> dict[str, Any]:
    by_ind_mode: dict[str, dict[str, int]] = {}
    scores = []
    capture = {f: 0 for f in POPULATION_BOOLEAN_FIELDS}
    by_year: dict[str, int] = {}
    for a in assets:
        ind = a.get("indication") or "other"
        mode = (a.get("classification") or {}).get("failure_mode") or "unclear"
        by_ind_mode.setdefault(ind, {})
        by_ind_mode[ind][mode] = by_ind_mode[ind].get(mode, 0) + 1
        sc = (a.get("score") or {}).get("score")
        if sc is not None:
            scores.append(sc)
        for item in a.get("population_checklist") or []:
            if item.get("captured"):
                capture[item["field"]] = capture.get(item["field"], 0) + 1
        y = a.get("year_stopped") or "unknown"
        by_year[y] = by_year.get(y, 0) + 1
    n = len(assets) or 1
    return {
        "n_assets": len(assets),
        "failure_modes_by_indication": by_ind_mode,
        "score_histogram": _histogram(scores),
        "population_capture_rates": {
            f: {"captured": capture[f], "n": len(assets), "rate": round(capture[f] / n, 4)}
            for f in POPULATION_BOOLEAN_FIELDS
        },
        "assets_by_year_stopped": dict(sorted(by_year.items())),
        "mean_female_specific_capture": round(
            (sum(capture.values()) / (len(POPULATION_BOOLEAN_FIELDS) * n)) if assets else 0.0,
            4,
        ),
    }


def _histogram(values: list[float], bins: int = 10) -> list[dict[str, Any]]:
    if not values:
        return []
    lo, hi = 0.0, 100.0
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, int((v - lo) / width))
        counts[idx] += 1
    out = []
    for i, c in enumerate(counts):
        out.append({"bin_start": round(lo + i * width, 1), "bin_end": round(lo + (i + 1) * width, 1), "count": c})
    return out


def weekly_changes(current: list[dict[str, Any]], previous_path: Path | None) -> dict[str, Any]:
    if not previous_path or not previous_path.exists():
        return {"previous_snapshot": None, "new_in_top20": [], "moved_over_10pts": [], "note": "No previous snapshot; this is the baseline."}
    prev = load_json(previous_path)
    prev_assets = {a["nct_id"]: a for a in prev.get("assets") or []}
    curr_sorted = sorted(current, key=lambda a: -((a.get("score") or {}).get("score") or 0))
    prev_sorted = sorted(prev_assets.values(), key=lambda a: -((a.get("score") or {}).get("score") or 0))
    prev_top = {a["nct_id"] for a in prev_sorted[:20]}
    new_in_top20 = []
    for a in curr_sorted[:20]:
        if a["nct_id"] not in prev_top:
            new_in_top20.append(
                {
                    "nct_id": a["nct_id"],
                    "title": a.get("brief_title"),
                    "score": (a.get("score") or {}).get("score"),
                    "failure_mode": (a.get("classification") or {}).get("failure_mode"),
                    "why": (a.get("score") or {}).get("arithmetic"),
                }
            )
    moved = []
    for a in current:
        old = prev_assets.get(a["nct_id"])
        if not old:
            continue
        ds = ((a.get("score") or {}).get("score") or 0) - ((old.get("score") or {}).get("score") or 0)
        if abs(ds) > 10:
            moved.append(
                {
                    "nct_id": a["nct_id"],
                    "title": a.get("brief_title"),
                    "delta": round(ds, 1),
                    "from": (old.get("score") or {}).get("score"),
                    "to": (a.get("score") or {}).get("score"),
                    "why": (a.get("score") or {}).get("caps_applied") or (a.get("classification") or {}).get("rule_fired"),
                }
            )
    return {
        "previous_snapshot": str(previous_path),
        "new_in_top20": new_in_top20,
        "moved_over_10pts": sorted(moved, key=lambda x: -abs(x["delta"])),
    }


def load_feedback() -> list[dict[str, Any]]:
    if not FEEDBACK_PATH.exists():
        return []
    rows = []
    for line in FEEDBACK_PATH.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def export_snapshot(*, dest: Path | None = None) -> Path:
    ensure_dirs()
    assets = []
    for path in sorted(SCORE_DIR.glob("*.json")):
        a = build_asset(path.stem)
        if a:
            assets.append(a)
    assets.sort(key=lambda a: -((a.get("score") or {}).get("score") or 0))
    prev = None
    existing = sorted(SNAPSHOT_DIR.glob("snapshot_*.json"))
    if existing:
        prev = existing[-1]
    snap_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "snapshot_id": snap_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scoring": scoring_config(),
        "indications": {
            k: {"label": v.get("label"), "efo_ids": v.get("efo_ids"), "mondo_ids": v.get("mondo_ids")}
            for k, v in indications_config()["indications"].items()
        },
        "assets": assets,
        "landscape": landscape(assets),
        "weekly": weekly_changes(assets, prev),
        "feedback": load_feedback(),
        "counts": {"n_assets": len(assets), "n_raw": len(list(RAW_CTG_DIR.glob("*.json")))},
    }
    out = dest or (SNAPSHOT_DIR / f"snapshot_{snap_id}.json")
    dump_json(out, payload)
    # Stable pointer for the dashboard
    latest = SNAPSHOT_DIR / "latest.json"
    dump_json(latest, payload)
    dashboard_public = Path(__file__).resolve().parents[2] / "dashboard" / "public" / "data" / "snapshot.json"
    dashboard_public.parent.mkdir(parents=True, exist_ok=True)
    dump_json(dashboard_public, payload)
    con = connect()
    try:
        con.execute(
            "INSERT INTO snapshots (snapshot_id, created_at, n_assets, path) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (snapshot_id) DO UPDATE SET n_assets = excluded.n_assets, path = excluded.path",
            [snap_id, datetime.now(timezone.utc).replace(tzinfo=None), len(assets), str(out)],
        )
        con.commit()
    finally:
        con.close()
    report = {
        "snapshot_id": snap_id,
        "n_assets": len(assets),
        "top20": [
            {
                "nct_id": a["nct_id"],
                "score": (a.get("score") or {}).get("score"),
                "failure_mode": (a.get("classification") or {}).get("failure_mode"),
                "title": a.get("brief_title"),
            }
            for a in assets[:20]
        ],
        "weekly": payload["weekly"],
        "landscape_headline": payload["landscape"]["mean_female_specific_capture"],
    }
    dump_json(CHANGE_REPORT_DIR / f"change_{snap_id}.json", report)
    print(f"[serve] snapshot {snap_id} n_assets={len(assets)} -> {out}")
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", type=Path, default=None)
    args = parser.parse_args(argv)
    export_snapshot(dest=args.dest)


if __name__ == "__main__":
    main()
