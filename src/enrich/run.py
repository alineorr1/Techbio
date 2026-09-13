"""Enrich stage: Open Targets + Europe PMC + curated sponsor CSV. Writes per-NCT JSON.

Wave-1b: also ensures programme identity and attaches empty rights (fill is stub).
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from src.config import indications_config
from src.db import connect, dump_json, load_json, upsert
from src.enrich.europepmc import enrich_publications
from src.enrich.opentargets import enrich_targets
from src.enrich.sponsors import enrich_sponsor
from src.extract.schema import Extraction
from src.http import HttpClient
from src.identity.programme import IdentityStore, identifiers_from_nct
from src.ingest.ctg import nested
from src.paths import ENRICH_DIR, EXTRACT_DIR, RAW_CTG_DIR, ensure_dirs
from src.rights.fill import fill_rights
from src.rights.store import attach_empty_rights, merge_sponsor_entity


def _interventions(study: dict) -> list[str]:
    ints = nested(study, "protocolSection", "armsInterventionsModule", "interventions") or []
    return [i.get("name") for i in ints if i.get("name")]


def _completion_year(study: dict) -> int | None:
    raw = nested(study, "protocolSection", "statusModule", "primaryCompletionDateStruct", "date") or nested(
        study, "protocolSection", "statusModule", "completionDateStruct", "date"
    )
    if not raw:
        return None
    try:
        return int(str(raw)[:4])
    except ValueError:
        return None


async def enrich_one(http: HttpClient, nct: str, study: dict, extraction: Extraction | None) -> dict:
    targets = [t.model_dump() for t in extraction.targets] if extraction else []
    start = nested(study, "protocolSection", "statusModule", "startDateStruct", "date")
    ot = await enrich_targets(http, targets, trial_start=start)
    epmc = await enrich_publications(
        http,
        nct,
        _interventions(study),
        _completion_year(study),
        nested(study, "protocolSection", "sponsorCollaboratorsModule", "leadSponsor", "name"),
    )
    sponsor = enrich_sponsor(study)
    identity = IdentityStore()
    programme = identity.upsert(identifiers_from_nct(nct), source="ctg", native_id=nct)
    pid = programme["programme_id"]
    attach_empty_rights(pid)
    fill_rights(pid, live=False)
    entity = (sponsor.get("sponsor_entity") or {})
    if entity:
        merge_sponsor_entity(pid, entity)
    return {
        "nct_id": nct,
        "programme_id": pid,
        "open_targets": ot,
        "europepmc": epmc,
        "sponsor": sponsor,
        "rights": {
            "schema_version": "wave1.rights.v0",
            "programme_id": pid,
            "confidence": "empty_stub",
            "path": f"data/derived/rights/{pid}.json",
        },
    }


def _enrich_is_fresh(nct: str, raw_path: Path) -> bool:
    """True when enrich JSON is at least as new as raw + extract inputs."""
    out = ENRICH_DIR / f"{nct}.json"
    if not out.exists():
        return False
    newest_in = raw_path.stat().st_mtime
    ext = EXTRACT_DIR / f"{nct}.json"
    if ext.exists():
        newest_in = max(newest_in, ext.stat().st_mtime)
    return out.stat().st_mtime >= newest_in


async def run_async(*, nct_ids: list[str] | None = None, skip_existing: bool = False) -> dict[str, int]:
    ensure_dirs()
    cfg = indications_config()
    ingest_cfg = cfg.get("ingest") or {}
    want = set(nct_ids) if nct_ids else None
    paths = [p for p in sorted(RAW_CTG_DIR.glob("*.json")) if (not want or p.stem in want)]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    n_ok = 0
    n_skip = 0
    async with HttpClient(
        requests_per_second=float(ingest_cfg.get("requests_per_second") or 2.0),
        max_concurrency=int(ingest_cfg.get("max_concurrency") or 3),
    ) as http:
        con = connect()
        try:
            for path in paths:
                nct = path.stem
                if skip_existing and _enrich_is_fresh(nct, path):
                    n_skip += 1
                    continue
                study = load_json(path)
                ext = None
                if (EXTRACT_DIR / f"{nct}.json").exists():
                    ext = Extraction.model_validate(load_json(EXTRACT_DIR / f"{nct}.json"))
                payload = await enrich_one(http, nct, study, ext)
                dump_json(ENRICH_DIR / f"{nct}.json", payload)
                upsert(con, "enrichments", nct, enriched_at=now, payload_json=payload)
                n_ok += 1
            con.commit()
        finally:
            con.close()
    print(f"[enrich] wrote={n_ok} skipped={n_skip}")
    return {"ok": n_ok, "skipped": n_skip}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nct", action="append", dest="nct_ids")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip NCT IDs whose enrich JSON is newer than raw + extract (weekly / no-new-data).",
    )
    args = parser.parse_args(argv)
    asyncio.run(run_async(nct_ids=args.nct_ids, skip_existing=args.skip_existing))


if __name__ == "__main__":
    main()
