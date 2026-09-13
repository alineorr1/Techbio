"""Load the committed rights-queue / disregard rule table."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.paths import RIGHTS_QUEUE_RULES_PATH

SCHEMA_VERSION = "pilot.rights-queue.v1"
DEFAULT_CAP = 50
CAP_MIN = 30
CAP_MAX = 50


@lru_cache(maxsize=4)
def load_queue_rules(path: Path | None = None) -> dict[str, Any]:
    dest = path or RIGHTS_QUEUE_RULES_PATH
    payload = json.loads(dest.read_text())
    cap = int(payload.get("cap") or DEFAULT_CAP)
    payload["cap"] = max(CAP_MIN, min(CAP_MAX, cap))
    return payload
