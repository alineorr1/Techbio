"""OpenAI/Anthropic spend gate + JSONL ledger helpers.

Stage-1: the only paid extract runner is VL. The kill switch lives in the
budget JSON. Missing or unreadable budget fails closed (treat as kill).

Resolution order for the budget file:
1. ``WH_API_COST_BUDGET`` (explicit override; used in tests)
2. ``/workspace/api-cost-budget.json`` (LIVE proven path)
3. ``config/api-cost-budget.json`` (repo-relative CI default)
"""

from __future__ import annotations

import atexit
import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.paths import CONFIG_DIR, ROOT

LIVE_BUDGET_PATH = Path("/workspace/api-cost-budget.json")
REPO_BUDGET_PATH = CONFIG_DIR / "api-cost-budget.json"
HARD_ALLOWLIST = frozenset({"gpt-4o-mini"})
HARD_CEILING_USD = 50.0
DEFAULT_ESTIMATE_USD = 0.05

_lock_fd: int | None = None


class BudgetKillError(RuntimeError):
    """Paid LLM call refused by the spend gate."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _data_dir() -> Path:
    return Path(os.environ.get("WH_DATA_DIR") or (ROOT / "data")).resolve()


def budget_path() -> Path:
    env = (os.environ.get("WH_API_COST_BUDGET") or "").strip()
    if env:
        return Path(env)
    if LIVE_BUDGET_PATH.is_file():
        return LIVE_BUDGET_PATH
    return REPO_BUDGET_PATH


def ledger_path() -> Path:
    return _data_dir() / "reports" / "api_call_ledger.jsonl"


def runner_lock_path() -> Path:
    return _data_dir() / "locks" / "extract_runner.lock"


def load_budget() -> dict[str, Any]:
    path = budget_path()
    if not path.is_file():
        return {
            "kill": True,
            "allowlist": sorted(HARD_ALLOWLIST),
            "ceiling_usd": HARD_CEILING_USD,
        }
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {
            "kill": True,
            "allowlist": sorted(HARD_ALLOWLIST),
            "ceiling_usd": HARD_CEILING_USD,
        }
    if not isinstance(payload, dict):
        return {
            "kill": True,
            "allowlist": sorted(HARD_ALLOWLIST),
            "ceiling_usd": HARD_CEILING_USD,
        }
    return payload


def allowed_models(budget: dict[str, Any] | None = None) -> frozenset[str]:
    budget = budget if budget is not None else load_budget()
    raw = budget.get("allowlist")
    if not isinstance(raw, list):
        raw = ["gpt-4o-mini"]
    return frozenset(str(m) for m in raw) & HARD_ALLOWLIST


def effective_ceiling_usd(budget: dict[str, Any] | None = None) -> float:
    budget = budget if budget is not None else load_budget()
    raw = budget.get("ceiling_usd", HARD_CEILING_USD)
    try:
        return min(float(raw), HARD_CEILING_USD)
    except (TypeError, ValueError):
        return HARD_CEILING_USD


def ledger_spent_usd(path: Path | None = None) -> float:
    target = path or ledger_path()
    if not target.is_file():
        return 0.0
    total = 0.0
    for line in target.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("event") not in {"paid_attempt", None}:
            # Cache hits and refuses do not consume budget. Historical rows
            # without an event field still count if they carry a cost.
            if row.get("event") in {"refuse", "cache_hit"}:
                continue
        raw = row.get("cost_usd", row.get("estimated_usd", 0.0))
        try:
            total += float(raw or 0.0)
        except (TypeError, ValueError):
            continue
    return total


def current_spent_usd(budget: dict[str, Any] | None = None) -> float:
    budget = budget if budget is not None else load_budget()
    raw = budget.get("spent_usd", 0.0)
    try:
        manual = float(raw or 0.0)
    except (TypeError, ValueError):
        manual = 0.0
    return manual + ledger_spent_usd()


def append_ledger(row: dict[str, Any]) -> Path:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": _utc_now(), **row}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def provider_for_model(model: str) -> str:
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("mock"):
        return "mock"
    return "openai"


def preflight_paid_call(
    *,
    model: str,
    provider: str | None = None,
    estimated_usd: float = DEFAULT_ESTIMATE_USD,
) -> dict[str, Any]:
    """Refuse a paid OpenAI/Anthropic call when kill, allowlist, or ceiling trip.

    Does not write the ledger; the caller appends ``refuse`` / ``paid_attempt``.
    """
    budget = load_budget()
    provider = provider or provider_for_model(model)
    if bool(budget.get("kill", True)):
        raise BudgetKillError(
            f"spend gate kill is on (budget={budget_path()}); refused {provider}/{model}"
        )
    if model not in allowed_models(budget):
        raise BudgetKillError(
            f"model {model!r} is not allowlisted (hard allowlist={sorted(HARD_ALLOWLIST)})"
        )
    ceiling = effective_ceiling_usd(budget)
    spent = current_spent_usd(budget)
    try:
        estimate = max(float(estimated_usd), 0.0)
    except (TypeError, ValueError):
        estimate = DEFAULT_ESTIMATE_USD
    if spent + estimate > ceiling:
        raise BudgetKillError(
            f"spend ceiling ${ceiling:.2f} would be exceeded (spent=${spent:.4f} + est=${estimate:.4f})"
        )
    return budget


def acquire_runner_lock() -> Path:
    """Exclusive single-runner lock at data/locks/extract_runner.lock."""
    global _lock_fd
    if _lock_fd is not None:
        raise RuntimeError("extract runner lock already held in this process")
    path = runner_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise RuntimeError(f"extract runner lock held: {path}") from exc
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    _lock_fd = fd
    return path


def release_runner_lock() -> None:
    global _lock_fd
    if _lock_fd is None:
        return
    fd = _lock_fd
    _lock_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


atexit.register(release_runner_lock)
