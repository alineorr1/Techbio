"""Run stages in order. Stages still only communicate via disk."""

from __future__ import annotations

import argparse
import asyncio

from src.classify.run import run as classify_run
from src.enrich.run import run_async as enrich_run
from src.extract.run import run_async as extract_run
from src.ingest.run import run_async as ingest_run
from src.score.run import run as score_run
from src.serve.export import export_snapshot


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the WH failed-asset pipeline")
    parser.add_argument("--since", default=None)
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--skip-enrich", action="store_true")
    args = parser.parse_args(argv)
    if not args.skip_ingest:
        asyncio.run(ingest_run(since=args.since, max_records=args.max_records))
    asyncio.run(extract_run(force_mock=True))
    if not args.skip_enrich:
        asyncio.run(enrich_run())
    classify_run()
    score_run()
    export_snapshot()


if __name__ == "__main__":
    main()
