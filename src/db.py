"""DuckDB warehouse helpers. Single file, no server. Idempotent upserts by nct_id."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import duckdb

from src.paths import WAREHOUSE_PATH, ensure_dirs

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_studies (
  nct_id VARCHAR PRIMARY KEY,
  fetched_at TIMESTAMP,
  last_update_date VARCHAR,
  overall_status VARCHAR,
  payload_json JSON
);

CREATE TABLE IF NOT EXISTS extractions (
  nct_id VARCHAR PRIMARY KEY,
  extracted_at TIMESTAMP,
  prompt_version VARCHAR,
  payload_json JSON,
  extraction_confidence VARCHAR
);

CREATE TABLE IF NOT EXISTS quarantine (
  nct_id VARCHAR PRIMARY KEY,
  quarantined_at TIMESTAMP,
  reason VARCHAR,
  payload_json JSON
);

CREATE TABLE IF NOT EXISTS enrichments (
  nct_id VARCHAR PRIMARY KEY,
  enriched_at TIMESTAMP,
  payload_json JSON
);

CREATE TABLE IF NOT EXISTS classifications (
  nct_id VARCHAR PRIMARY KEY,
  classified_at TIMESTAMP,
  failure_mode VARCHAR,
  confidence VARCHAR,
  payload_json JSON
);

CREATE TABLE IF NOT EXISTS scores (
  nct_id VARCHAR PRIMARY KEY,
  scored_at TIMESTAMP,
  score DOUBLE,
  payload_json JSON
);

CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_id VARCHAR PRIMARY KEY,
  created_at TIMESTAMP,
  n_assets INTEGER,
  path VARCHAR
);

CREATE TABLE IF NOT EXISTS feedback (
  feedback_id VARCHAR PRIMARY KEY,
  nct_id VARCHAR,
  created_at TIMESTAMP,
  reason VARCHAR,
  payload_json JSON
);

CREATE TABLE IF NOT EXISTS eval_runs (
  run_id VARCHAR PRIMARY KEY,
  created_at TIMESTAMP,
  prompt_version VARCHAR,
  payload_json JSON
);
"""


def connect(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    ensure_dirs()
    db_path = path or WAREHOUSE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(SCHEMA_SQL)
    return con


def upsert(con: duckdb.DuckDBPyConnection, table: str, nct_id: str, **fields: Any) -> None:
    cols = ["nct_id", *fields.keys()]
    placeholders = ", ".join(["?"] * len(cols))
    assignments = ", ".join(f"{c} = excluded.{c}" for c in fields)
    values: list[Any] = [nct_id]
    for v in fields.values():
        if isinstance(v, (dict, list)):
            values.append(json.dumps(v, ensure_ascii=False, default=str))
        else:
            values.append(v)
    con.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (nct_id) DO UPDATE SET {assignments}",
        values,
    )


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def iter_json_dir(directory: Path) -> Iterable[tuple[str, Any]]:
    if not directory.exists():
        return
    for path in sorted(directory.glob("*.json")):
        yield path.stem, load_json(path)
