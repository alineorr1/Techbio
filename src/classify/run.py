"""Classify stage: assign failure mode from extraction + enrichment + registry fields."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.classify.rules import classify_record, _stop_date
from src.db import connect, dump_json, load_json, upsert
from src.extract.schema import Extraction
from src.ingest.ctg import nct_id_of
from src.paths import CLASSIFY_DIR, ENRICH_DIR, EXTRACT_DIR, RAW_CTG_DIR, ensure_dirs
from src.rights.store import rights_for_nct


def _peer_stops(studies: dict[str, dict], window_days: int = 180) -> dict[str, int]:
    by_sponsor: dict[str, list[tuple[str, object]]] = defaultdict(list)
    for nct, study in studies.items():
        lead = (
            ((study.get("protocolSection") or {}).get("sponsorCollaboratorsModule") or {})
            .get("leadSponsor") or {}
        ).get("name") or ""
        dt = _stop_date(study)
        if lead and dt:
            by_sponsor[lead.lower()].append((nct, dt))
    counts = {nct: 0 for nct in studies}
    for items in by_sponsor.values():
        for nct, dt in items:
            peers = sum(1 for other, odt in items if other != nct and abs((odt - dt).days) <= window_days)
            counts[nct] = peers
    return counts


def run(*, nct_ids: list[str] | None = None) -> dict[str, int]:
    ensure_dirs()
    want = set(nct_ids) if nct_ids else None
    studies = {}
    for path in RAW_CTG_DIR.glob("*.json"):
        if want and path.stem not in want:
            continue
        studies[path.stem] = load_json(path)
    peers = _peer_stops(studies)
    n_ok = 0
    n_skip = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    con = connect()
    try:
        for nct, study in studies.items():
            ext_path = EXTRACT_DIR / f"{nct}.json"
            if not ext_path.exists():
                n_skip += 1
                continue
            extraction = Extraction.model_validate(load_json(ext_path))
            enrich = load_json(ENRICH_DIR / f"{nct}.json") if (ENRICH_DIR / f"{nct}.json").exists() else {}
            rights = enrich.get("rights_record") or rights_for_nct(nct)
            clf = classify_record(study, extraction, enrich, peer_stops=peers.get(nct, 0), rights=rights)
            payload = clf.model_dump()
            dump_json(CLASSIFY_DIR / f"{nct}.json", payload)
            upsert(
                con,
                "classifications",
                nct,
                classified_at=now,
                failure_mode=clf.failure_mode,
                confidence=clf.confidence,
                payload_json=payload,
            )
            n_ok += 1
        con.commit()
    finally:
        con.close()
    print(f"[classify] wrote={n_ok} skipped_no_extraction={n_skip}")
    return {"ok": n_ok, "skipped": n_skip}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nct", action="append", dest="nct_ids")
    args = parser.parse_args(argv)
    run(nct_ids=args.nct_ids)


if __name__ == "__main__":
    main()
