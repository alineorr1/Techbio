"""Spend gate: dry refuse under kill, no live OpenAI/Anthropic spend."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.api_cost import (
    HARD_ALLOWLIST,
    HARD_CEILING_USD,
    BudgetKillError,
    acquire_runner_lock,
    append_ledger,
    budget_path,
    current_spent_usd,
    effective_ceiling_usd,
    ledger_path,
    preflight_paid_call,
    release_runner_lock,
)
from src.extract.llm import complete_llm
from src.paths import API_COST_BUDGET_PATH, P1_FROZEN_NCTS_PATH, ROOT

FROZEN_NCTS = [
    "NCT05670353",
    "NCT04641273",
    "NCT03481842",
    "NCT04347135",
    "NCT03970330",
    "NCT00703092",
    "NCT04118777",
    "NCT01028781",
    "NCT02728245",
    "NCT00729560",
    "NCT00159575",
    "NCT00203996",
    "NCT00682890",
    "NCT04174911",
    "NCT04184323",
    "NCT03905941",
    "NCT05370521",
    "NCT03343067",
    "NCT00001848",
    "NCT05560646",
]


def _write_budget(path: Path, **fields: object) -> Path:
    payload = {
        "kill": False,
        "allowlist": ["gpt-4o-mini"],
        "ceiling_usd": 50,
        **fields,
    }
    path.write_text(json.dumps(payload))
    return path


def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **budget_fields: object) -> Path:
    data = tmp_path / "data"
    budget = _write_budget(tmp_path / "budget.json", **budget_fields)
    monkeypatch.setenv("WH_DATA_DIR", str(data))
    monkeypatch.setenv("WH_API_COST_BUDGET", str(budget))
    return budget


def test_committed_budget_is_killed_for_ci():
    payload = json.loads(API_COST_BUDGET_PATH.read_text())
    assert payload["kill"] is True
    assert payload["allowlist"] == ["gpt-4o-mini"]
    assert float(payload["ceiling_usd"]) == HARD_CEILING_USD
    assert HARD_ALLOWLIST == frozenset({"gpt-4o-mini"})


def test_budget_path_prefers_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    budget = _write_budget(tmp_path / "override.json", kill=True)
    monkeypatch.setenv("WH_API_COST_BUDGET", str(budget))
    assert budget_path() == budget


def test_preflight_refuses_when_kill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate(tmp_path, monkeypatch, kill=True)
    with pytest.raises(BudgetKillError, match="kill"):
        preflight_paid_call(model="gpt-4o-mini", provider="openai")


def test_preflight_refuses_non_allowlisted_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate(tmp_path, monkeypatch, kill=False)
    with pytest.raises(BudgetKillError, match="not allowlisted"):
        preflight_paid_call(model="gpt-4o", provider="openai")
    with pytest.raises(BudgetKillError, match="not allowlisted"):
        preflight_paid_call(model="claude-sonnet-4-5-20250929", provider="anthropic")


def test_preflight_refuses_over_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate(tmp_path, monkeypatch, kill=False, spent_usd=49.99)
    with pytest.raises(BudgetKillError, match="ceiling"):
        preflight_paid_call(model="gpt-4o-mini", provider="openai", estimated_usd=0.05)


def test_preflight_caps_ceiling_at_50(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate(tmp_path, monkeypatch, kill=False, ceiling_usd=500)
    assert effective_ceiling_usd() == HARD_CEILING_USD


def test_preflight_allows_gpt4o_mini_when_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate(tmp_path, monkeypatch, kill=False, spent_usd=0)
    snapshot = preflight_paid_call(model="gpt-4o-mini", provider="openai")
    assert snapshot["kill"] is False


def test_complete_llm_refuses_under_kill_without_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate(tmp_path, monkeypatch, kill=True)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-no-spend")
    called = {"post": False}

    class BoomClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> BoomClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> None:
            called["post"] = True
            raise AssertionError("paid HTTP must not run under kill")

    monkeypatch.setattr("httpx.AsyncClient", BoomClient)

    async def _run() -> None:
        with pytest.raises(BudgetKillError):
            await complete_llm("prompt", "source", "gpt-4o-mini", nct_id="NCT00000000")

    asyncio.run(_run())
    assert called["post"] is False
    rows = [json.loads(line) for line in ledger_path().read_text().splitlines()]
    assert rows[-1]["event"] == "refuse"
    assert rows[-1]["nct_id"] == "NCT00000000"
    assert current_spent_usd() == 0.0


def test_complete_llm_openai_payload_sets_max_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate(tmp_path, monkeypatch, kill=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-no-spend")
    captured: dict[str, object] = {}

    class FakeResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "{}"}}]}

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, headers: dict | None = None, json: dict | None = None):
            captured["url"] = url
            captured["json"] = json
            return FakeResp()

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)

    async def _run() -> str:
        return await complete_llm("prompt", "source", "gpt-4o-mini", nct_id="NCT00000000")

    assert asyncio.run(_run()) == "{}"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["json"]["max_tokens"] == 2000
    rows = [json.loads(line) for line in ledger_path().read_text().splitlines()]
    assert rows[-1]["event"] == "paid_attempt"


def test_runner_lock_is_single_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate(tmp_path, monkeypatch)
    path = acquire_runner_lock()
    assert path.exists()
    with pytest.raises(RuntimeError, match="already held"):
        acquire_runner_lock()
    release_runner_lock()
    acquire_runner_lock()
    release_runner_lock()


def test_append_ledger_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate(tmp_path, monkeypatch)
    append_ledger({"event": "cache_hit", "model": "gpt-4o-mini", "nct_id": "NCT00000000"})
    lines = ledger_path().read_text().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["event"] == "cache_hit"
    assert "ts" in row


def test_p1_frozen_ncts_exact_order():
    assert P1_FROZEN_NCTS_PATH.is_relative_to(ROOT / "data" / "smoke")
    lines = P1_FROZEN_NCTS_PATH.read_text().splitlines()
    assert lines == FROZEN_NCTS
    assert len(lines) == 20
    assert len(set(lines)) == 20
