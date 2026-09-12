#!/usr/bin/env bash
# Local equivalent of .github/workflows/weekly.yml.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SINCE="${SINCE:-$(python -c "from datetime import datetime, timedelta, timezone; print((datetime.now(timezone.utc)-timedelta(days=10)).strftime('%Y-%m-%d'))")}"
echo "[weekly] ingest since ${SINCE}"
python -m src.ingest --since "$SINCE"
python -m src.extract --skip-existing
python -m src.enrich --skip-existing
python -m src.classify
python -m src.score
python -m src.serve
echo "[weekly] wrote dashboard/public/data/snapshot.json"
