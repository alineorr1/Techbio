"""Ingest stage: pull ClinicalTrials.gov v2 records, cache verbatim, upsert warehouse.

Independently re-runnable. Idempotent (one JSON file and one DuckDB row per NCT ID).
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Any

from src.config import indications_config
from src.db import connect, dump_json, upsert
from src.http import HttpClient
from src.ingest.ctg import (
    ClinicalTrialsClient,
    in_stopped_universe,
    last_update_of,
    nct_id_of,
    overall_status_of,
)
from src.paths import RAW_CTG_DIR, ensure_dirs


async def run_async(*, since: str | None = None, max_records: int | None = None) -> dict[str, Any]:
    ensure_dirs()
    cfg = indications_config()
    ingest_cfg = cfg.get("ingest") or {}
    rps = float(ingest_cfg.get("requests_per_second") or 3.0)
    conc = int(ingest_cfg.get("max_concurrency") or 4)
    fetched = 0
    kept = 0
    skipped_status = 0
    seen: set[str] = set()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with HttpClient(requests_per_second=rps, max_concurrency=conc) as http:
        client = ClinicalTrialsClient(http, cfg)
        con = connect()
        try:
            async for study in client.fetch_universe(since=since, max_records=max_records):
                nct = nct_id_of(study)
                fetched += 1
                if not nct or nct in seen:
                    continue
                seen.add(nct)
                if not in_stopped_universe(study, cfg):
                    skipped_status += 1
                    continue
                dump_json(RAW_CTG_DIR / f"{nct}.json", study)
                upsert(
                    con,
                    "raw_studies",
                    nct,
                    fetched_at=now,
                    last_update_date=last_update_of(study),
                    overall_status=overall_status_of(study),
                    payload_json=study,
                )
                kept += 1
            con.commit()
        finally:
            con.close()

    summary = {
        "fetched": fetched,
        "unique": len(seen),
        "kept_in_universe": kept,
        "skipped_status": skipped_status,
        "raw_dir": str(RAW_CTG_DIR),
    }
    print(
        f"[ingest] fetched={fetched} unique={len(seen)} "
        f"kept_in_universe={kept} skipped_other_status={skipped_status}"
    )
    print(f"[ingest] cached at {RAW_CTG_DIR}")
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ingest ClinicalTrials.gov v2 records")
    parser.add_argument("--since", help="Only records with lastUpdatePostDate on/after YYYY-MM-DD")
    parser.add_argument("--max-records", type=int, default=None)
    args = parser.parse_args(argv)
    asyncio.run(run_async(since=args.since, max_records=args.max_records))


if __name__ == "__main__":
    main()
