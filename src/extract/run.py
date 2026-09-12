"""Extract stage: LLM (or deterministic mock) over cached registry records.

Writes data/derived/extract/{nct}.json. Quarantines schema/verbatim failures.
Does not call ingest, enrich, classify, or score.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from src.db import connect, dump_json, load_json, upsert
from src.extract.llm import PROMPT_VERSION, Extractor
from src.extract.validate import ExtractionError
from src.ingest.ctg import flatten_study_text, nct_id_of
from src.paths import EXTRACT_DIR, QUARANTINE_DIR, RAW_CTG_DIR, ensure_dirs


async def extract_one(extractor: Extractor, study: dict, raw_path: Path) -> str:
    nct = nct_id_of(study) or raw_path.stem
    source = flatten_study_text(study)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        ext = await extractor.extract(study, source)
    except ExtractionError as exc:
        dump_json(
            QUARANTINE_DIR / f"{nct}.json",
            {"nct_id": nct, "reason": str(exc), "payload": exc.payload, "source_path": str(raw_path)},
        )
        con = connect()
        try:
            upsert(con, "quarantine", nct, quarantined_at=now, reason=str(exc)[:500], payload_json=exc.payload or {})
            con.commit()
        finally:
            con.close()
        return "quarantine"
    dump_json(EXTRACT_DIR / f"{nct}.json", ext.model_dump())
    con = connect()
    try:
        upsert(
            con,
            "extractions",
            nct,
            extracted_at=now,
            prompt_version=PROMPT_VERSION,
            payload_json=ext.model_dump(),
            extraction_confidence=ext.extraction_confidence,
        )
        con.commit()
    finally:
        con.close()
    return "ok"


def _extract_is_fresh(raw_path: Path) -> bool:
    """True when derived extract is at least as new as the cached registry JSON."""
    out = EXTRACT_DIR / f"{raw_path.stem}.json"
    if not out.exists():
        return False
    return out.stat().st_mtime >= raw_path.stat().st_mtime


async def run_async(
    *,
    nct_ids: list[str] | None = None,
    force_mock: bool = False,
    skip_existing: bool = False,
) -> dict[str, int]:
    ensure_dirs()
    extractor = Extractor(force_mock=force_mock)
    paths = sorted(RAW_CTG_DIR.glob("*.json"))
    if nct_ids:
        want = set(nct_ids)
        paths = [p for p in paths if p.stem in want]
    counts = {"ok": 0, "quarantine": 0, "missing": 0, "skipped": 0}
    sem = asyncio.Semaphore(8)

    async def one(path: Path) -> None:
        async with sem:
            if skip_existing and _extract_is_fresh(path):
                counts["skipped"] = counts.get("skipped", 0) + 1
                return
            study = load_json(path)
            status = await extract_one(extractor, study, path)
            counts[status] = counts.get(status, 0) + 1

    await asyncio.gather(*(one(p) for p in paths))
    print(f"[extract] prompt={PROMPT_VERSION} model={extractor.model} {counts} n={len(paths)}")
    return counts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract structured records from cached CTG JSON")
    parser.add_argument("--nct", action="append", dest="nct_ids")
    parser.add_argument("--force-mock", action="store_true")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip NCT IDs whose extract JSON is newer than the cached registry record (weekly / no-new-data).",
    )
    args = parser.parse_args(argv)
    asyncio.run(run_async(nct_ids=args.nct_ids, force_mock=args.force_mock, skip_existing=args.skip_existing))


if __name__ == "__main__":
    main()
