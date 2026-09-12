"""LLM call cache keyed by sha256(prompt + model + input). A no-new-data rerun costs nothing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.paths import LLM_CACHE_DIR, ensure_dirs


def cache_key(prompt: str, source_text: str, model: str) -> str:
    blob = f"{model}\n---PROMPT---\n{prompt}\n---INPUT---\n{source_text}".encode()
    return hashlib.sha256(blob).hexdigest()


def load(key: str, cache_dir: Path | None = None) -> dict[str, Any] | None:
    ensure_dirs()
    path = (cache_dir or LLM_CACHE_DIR) / f"{key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def store(key: str, payload: dict[str, Any], cache_dir: Path | None = None) -> None:
    ensure_dirs()
    path = (cache_dir or LLM_CACHE_DIR) / f"{key}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
