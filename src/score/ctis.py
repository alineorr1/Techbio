"""Phase-2 CTIS score wire (opt-in, unpaid mock extract only).

Reads ``data/raw/ctis/`` envelopes written by Phase-1 ingest, attaches
programme identity, and runs extract → enrich → classify → score for
EU shelved / failed-asset-universe rows.

NCT-linked rows whose NCT is already in the CTG corpus are merged into
that programme (additional source) and are **not** scored a second time.

Not imported by ``src.pipeline`` or weekly cron. Disable with
``WH_CTIS_SCORE=0``. Always uses ``extract --force-mock`` — no paid LLM.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.classify.rules import classify_record
from src.db import connect, dump_json, load_json, upsert
from src.enrich.sponsors import enrich_sponsor
from src.extract.llm import PROMPT_VERSION, Extractor
from src.extract.schema import Extraction
from src.extract.validate import ExtractionError
from src.identity.programme import IdentityStore, identifiers_from_ctis_retrieve
from src.ingest.ctis import FEATURE_ENV as INGEST_FEATURE_ENV
from src.ingest.ctis import WIRED_INTO_PIPELINE as INGEST_WIRED
from src.ingest.ctis_study import (
    ctis_to_study,
    eu_ct_of,
    flatten_ctis_text,
    in_failed_asset_universe,
    is_drug_or_biologic_programme,
    nct_ids_of,
    primary_display_id_of,
    public_status_of,
)
from src.paths import (
    CLASSIFY_DIR,
    ENRICH_DIR,
    EXTRACT_DIR,
    IDENTITY_DIR,
    QUARANTINE_DIR,
    RAW_CTG_DIR,
    RAW_CTIS_DIR,
    SCORE_DIR,
    ensure_dirs,
)
from src.rights.store import attach_empty_rights, load_rights
from src.score.compute import score_asset

# Phase-2 feature flag. Dedicated module only — pipeline / weekly stay off.
WIRED_INTO_PIPELINE = False
FEATURE_ENV = "WH_CTIS_SCORE"
SOURCE = "ctis"


def feature_enabled(env: dict[str, str] | None = None) -> bool:
    raw = (env or os.environ).get(FEATURE_ENV, "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def nct_in_ctg_corpus(nct: str, raw_ctg_dir: Path | None = None) -> bool:
    if not nct:
        return False
    return (raw_ctg_dir or RAW_CTG_DIR).joinpath(f"{nct}.json").is_file()


def linked_ncts_in_ctg(envelope: dict[str, Any], raw_ctg_dir: Path | None = None) -> list[str]:
    return [nct for nct in nct_ids_of(envelope) if nct_in_ctg_corpus(nct, raw_ctg_dir)]


def iter_ctis_envelopes(raw_dir: Path | None = None) -> list[tuple[Path, dict[str, Any]]]:
    directory = raw_dir or RAW_CTIS_DIR
    if not directory.exists():
        return []
    rows: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("_"):
            continue
        rec = load_json(path)
        if not isinstance(rec, dict):
            continue
        rows.append((path, rec))
    return rows


def _empty_enrich(
    *,
    study: dict[str, Any],
    programme_id: str,
    nct_id: str | None,
    eu_ct: str,
    display_id: str,
) -> dict[str, Any]:
    sponsor = enrich_sponsor(study)
    return {
        "nct_id": nct_id or "",
        "programme_id": programme_id,
        "primary_display_id": display_id,
        "source": SOURCE,
        "eu_ct": eu_ct,
        "open_targets": {},
        "europepmc": {},
        "sponsor": sponsor,
        "rights": {
            "schema_version": "wave-1b.rights-stub.v1",
            "nct_id": nct_id,
            "programme_id": programme_id,
            "confidence": "empty_stub",
            "path": f"data/derived/rights/{nct_id or programme_id}.json",
        },
    }


def _annotate_extraction(
    ext: Extraction,
    *,
    programme_id: str,
    display_id: str,
    eu_ct: str,
    nct_id: str,
) -> dict[str, Any]:
    payload = ext.model_dump()
    payload["nct_id"] = nct_id or payload.get("nct_id") or ""
    payload["programme_id"] = programme_id
    payload["primary_display_id"] = display_id
    payload["eu_ct"] = eu_ct
    payload["source"] = SOURCE
    return payload


async def extract_ctis_one(
    extractor: Extractor,
    envelope: dict[str, Any],
    *,
    programme_id: str,
    display_id: str,
    eu_ct: str,
    nct_id: str,
    quarantine_dir: Path,
) -> tuple[str, dict[str, Any] | None]:
    study = ctis_to_study(envelope)
    source = flatten_ctis_text(envelope)
    try:
        ext = await extractor.extract(study, source)
    except ExtractionError as exc:
        dump_json(
            quarantine_dir / f"{programme_id}.json",
            {
                "programme_id": programme_id,
                "primary_display_id": display_id,
                "eu_ct": eu_ct,
                "reason": str(exc),
                "payload": exc.payload,
                "source": SOURCE,
            },
        )
        return "quarantine", None
    payload = _annotate_extraction(
        ext,
        programme_id=programme_id,
        display_id=display_id,
        eu_ct=eu_ct,
        nct_id=nct_id or ext.nct_id or "",
    )
    return "ok", payload


def decide_disposition(
    envelope: dict[str, Any],
    *,
    raw_ctg_dir: Path | None = None,
) -> str:
    """merge_nct | exclude | quarantine | score."""
    linked = linked_ncts_in_ctg(envelope, raw_ctg_dir)
    if linked:
        return "merge_nct"
    status = public_status_of(envelope)
    if status.get("unmapped"):
        return "quarantine"
    if in_failed_asset_universe(envelope) and is_drug_or_biologic_programme(envelope):
        return "score"
    return "exclude"


async def run_async(
    *,
    force_mock: bool = True,
    raw_dir: Path | None = None,
    raw_ctg_dir: Path | None = None,
    identity_dir: Path | None = None,
    extract_dir: Path | None = None,
    enrich_dir: Path | None = None,
    classify_dir: Path | None = None,
    score_dir: Path | None = None,
    quarantine_dir: Path | None = None,
    write_identity: bool = True,
) -> dict[str, Any]:
    if not feature_enabled():
        raise RuntimeError(f"CTIS score wire disabled ({FEATURE_ENV}=0). Feature-flagged; not in pipeline.")
    if WIRED_INTO_PIPELINE or INGEST_WIRED:
        raise RuntimeError("CTIS must not be wired into src.pipeline")
    if not force_mock:
        raise RuntimeError("CTIS score wire is unpaid-only; pass --force-mock (no OpenAI / paid LLM).")

    ensure_dirs()
    raw_dir = raw_dir or RAW_CTIS_DIR
    raw_ctg_dir = raw_ctg_dir or RAW_CTG_DIR
    identity_dir = identity_dir or IDENTITY_DIR
    extract_dir = extract_dir or EXTRACT_DIR
    enrich_dir = enrich_dir or ENRICH_DIR
    classify_dir = classify_dir or CLASSIFY_DIR
    score_dir = score_dir or SCORE_DIR
    quarantine_dir = quarantine_dir or QUARANTINE_DIR
    for path in (extract_dir, enrich_dir, classify_dir, score_dir, quarantine_dir, identity_dir):
        path.mkdir(parents=True, exist_ok=True)

    store = IdentityStore(identity_dir) if write_identity else None
    envelopes = iter_ctis_envelopes(raw_dir)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    counts = {
        "n_ctis_raw": len(envelopes),
        "n_scored_eu_shelved": 0,
        "n_merged_to_nct": 0,
        "n_excluded_active": 0,
        "n_quarantine": 0,
        "n_optionable": 0,
        "ok": 0,
        "skipped": 0,
    }
    scored_ids: list[str] = []
    merged_ids: list[str] = []

    extractor = Extractor(force_mock=True)
    try:
        con = connect()
        try:
            for path, envelope in envelopes:
                payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else envelope
                ids = identifiers_from_ctis_retrieve(payload)
                eu_ct = eu_ct_of(envelope)
                ncts = nct_ids_of(envelope)
                display = primary_display_id_of(envelope)
                nct_id = ncts[0] if ncts else ""

                if store is not None:
                    programme = store.upsert(
                        ids,
                        source=SOURCE,
                        native_id=eu_ct or path.stem,
                        secondary_only_match=bool((envelope.get("match") or {}).get("secondary_only_match")),
                    )
                else:
                    from src.identity.programme import make_identity

                    programme = make_identity(ids, sources=[SOURCE])
                    eudracts = (programme.get("ids") or {}).get("eudract") or [None]
                    attach_empty_rights(
                        programme["programme_id"],
                        nct_id=nct_id or None,
                        eu_ct=eu_ct,
                        eudract=eudracts[0],
                    )
                pid = programme["programme_id"]

                disposition = decide_disposition(envelope, raw_ctg_dir=raw_ctg_dir)
                if disposition == "merge_nct":
                    counts["n_merged_to_nct"] += 1
                    merged_ids.append(eu_ct)
                    continue
                if disposition == "exclude":
                    counts["n_excluded_active"] += 1
                    continue
                if disposition == "quarantine":
                    counts["n_quarantine"] += 1
                    dump_json(
                        quarantine_dir / f"{pid}.json",
                        {
                            "programme_id": pid,
                            "primary_display_id": display,
                            "reason": "unmapped_public_status",
                            "public_status": public_status_of(envelope),
                            "source": SOURCE,
                        },
                    )
                    continue

                status, ext_payload = await extract_ctis_one(
                    extractor,
                    envelope,
                    programme_id=pid,
                    display_id=display,
                    eu_ct=eu_ct,
                    nct_id=nct_id,
                    quarantine_dir=quarantine_dir,
                )
                if status != "ok" or ext_payload is None:
                    counts["n_quarantine"] += 1
                    continue

                dump_json(extract_dir / f"{pid}.json", ext_payload)
                upsert(
                    con,
                    "extractions",
                    pid,
                    extracted_at=now,
                    prompt_version=PROMPT_VERSION,
                    payload_json=ext_payload,
                    extraction_confidence=ext_payload.get("extraction_confidence"),
                )

                study = ctis_to_study(envelope)
                extraction = Extraction.model_validate(
                    {k: v for k, v in ext_payload.items() if k in Extraction.model_fields}
                )
                enrich = _empty_enrich(
                    study=study,
                    programme_id=pid,
                    nct_id=nct_id or None,
                    eu_ct=eu_ct,
                    display_id=display,
                )
                dump_json(enrich_dir / f"{pid}.json", enrich)
                upsert(con, "enrichments", pid, enriched_at=now, payload_json=enrich)

                rights = load_rights(nct_id=nct_id or None, programme_id=pid)
                clf = classify_record(study, extraction, enrich, rights=rights)
                clf_payload = clf.model_dump()
                clf_payload["programme_id"] = pid
                clf_payload["primary_display_id"] = display
                clf_payload["source"] = SOURCE
                dump_json(classify_dir / f"{pid}.json", clf_payload)
                upsert(
                    con,
                    "classifications",
                    pid,
                    classified_at=now,
                    failure_mode=clf.failure_mode,
                    confidence=clf.confidence,
                    payload_json=clf_payload,
                )

                scored = score_asset(study, extraction, clf, enrich, rights=rights)
                scored["programme_id"] = pid
                scored["primary_display_id"] = display
                scored["eu_ct"] = eu_ct
                scored["source"] = SOURCE
                scored["nct_id"] = nct_id or scored.get("nct_id") or ""
                dump_json(score_dir / f"{pid}.json", scored)
                upsert(con, "scores", pid, scored_at=now, score=scored["score"], payload_json=scored)

                counts["n_scored_eu_shelved"] += 1
                counts["ok"] += 1
                scored_ids.append(pid)
                if scored.get("optionable"):
                    counts["n_optionable"] += 1
            con.commit()
        finally:
            con.close()
    finally:
        extractor.close()

    summary = {
        "feature": "ctis_score",
        "wired_into_pipeline": WIRED_INTO_PIPELINE,
        "ingest_wired_into_pipeline": INGEST_WIRED,
        "ingest_flag": INGEST_FEATURE_ENV,
        "force_mock": True,
        "n_ctis_raw": counts["n_ctis_raw"],
        "n_scored_eu_shelved": counts["n_scored_eu_shelved"],
        "n_merged_to_nct": counts["n_merged_to_nct"],
        "n_excluded_active": counts["n_excluded_active"],
        "n_quarantine": counts["n_quarantine"],
        "optionable": counts["n_optionable"],
        "scored_programme_ids": scored_ids,
        "merged_eu_ct": merged_ids,
        "raw_dir": str(raw_dir),
    }
    print(
        f"[ctis-score] raw={counts['n_ctis_raw']} scored_eu_shelved={counts['n_scored_eu_shelved']} "
        f"merged_to_nct={counts['n_merged_to_nct']} excluded_active={counts['n_excluded_active']} "
        f"quarantine={counts['n_quarantine']} optionable={counts['n_optionable']}"
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase-2 CTIS score wire (feature-flagged; unpaid mock extract; not in src.pipeline)"
    )
    parser.add_argument(
        "--force-mock",
        action="store_true",
        default=True,
        help="Required unpaid path (default). Paid LLM is refused.",
    )
    parser.add_argument("--no-identity", action="store_true", help="Skip programme_id writes")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = build_parser().parse_args(argv)
    return asyncio.run(
        run_async(
            force_mock=True if args.force_mock else True,
            write_identity=not args.no_identity,
        )
    )


if __name__ == "__main__":
    main()
