"""Resolved paths for the repository. All stages read/write under these."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.environ.get("WH_DATA_DIR") or (ROOT / "data")).resolve()
CONFIG_DIR = ROOT / "config"
PROMPTS_DIR = ROOT / "prompts"

RAW_DIR = DATA_DIR / "raw"
RAW_CTG_DIR = RAW_DIR / "ctg"
RAW_CTIS_DIR = RAW_DIR / "ctis"
RAW_CTIS_SEARCH_DIR = RAW_CTIS_DIR / "_search"
DERIVED_DIR = DATA_DIR / "derived"
IDENTITY_DIR = DERIVED_DIR / "identity"
RIGHTS_DIR = DERIVED_DIR / "rights"
EXTRACT_DIR = DERIVED_DIR / "extract"
ENRICH_DIR = DERIVED_DIR / "enrich"
CLASSIFY_DIR = DERIVED_DIR / "classify"
SCORE_DIR = DERIVED_DIR / "score"
QUARANTINE_DIR = DERIVED_DIR / "quarantine"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
CACHE_DIR = DATA_DIR / "cache"
LLM_CACHE_DIR = CACHE_DIR / "llm"
HTTP_CACHE_DIR = CACHE_DIR / "http"
GOLDEN_DIR = DATA_DIR / "golden"
EVAL_RUNS_DIR = DATA_DIR / "eval" / "runs"
WAREHOUSE_PATH = DATA_DIR / "warehouse.duckdb"
FEEDBACK_PATH = DATA_DIR / "feedback.jsonl"
CHANGE_REPORT_DIR = DATA_DIR / "reports"

INDICATIONS_PATH = CONFIG_DIR / "indications.yaml"
SCORING_PATH = CONFIG_DIR / "scoring.yaml"
SPONSORS_PATH = CONFIG_DIR / "sponsors.csv"
DISQUALIFIERS_PATH = CONFIG_DIR / "disqualifiers.yaml"

# Committed Wave-1 pins (not relocated when WH_DATA_DIR is overridden).
SMOKE_DIR = ROOT / "data" / "smoke"
CTIS_STATUS_MAP_PATH = SMOKE_DIR / "ctis_status_map.json"


def ensure_dirs() -> None:
    for path in (
        RAW_CTG_DIR,
        RAW_CTIS_DIR,
        RAW_CTIS_SEARCH_DIR,
        IDENTITY_DIR,
        RIGHTS_DIR,
        EXTRACT_DIR,
        ENRICH_DIR,
        CLASSIFY_DIR,
        SCORE_DIR,
        QUARANTINE_DIR,
        SNAPSHOT_DIR,
        LLM_CACHE_DIR,
        HTTP_CACHE_DIR,
        GOLDEN_DIR,
        EVAL_RUNS_DIR,
        CHANGE_REPORT_DIR,
        DATA_DIR / "eval",
    ):
        path.mkdir(parents=True, exist_ok=True)
