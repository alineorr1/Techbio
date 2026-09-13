"""LLM extraction with cache. Falls back to PromptAwareExtractor when no API key is set."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from src.api_cost import (
    BudgetKillError,
    acquire_runner_lock,
    append_ledger,
    preflight_paid_call,
    provider_for_model,
    release_runner_lock,
)
from src.extract.deterministic import PromptAwareExtractor, extract_json_from_llm_text
from src.extract.schema import Extraction
from src.extract.validate import ExtractionError, parse_extraction
from src.ingest.ctg import nct_id_of
from src import llm_cache
from src.paths import PROMPTS_DIR

PROMPT_VERSION = "extraction_v1"
PROMPT_PATH = PROMPTS_DIR / f"{PROMPT_VERSION}.md"
PAID_MAX_TOKENS = 2000


def load_prompt() -> str:
    return PROMPT_PATH.read_text()


def current_model_name() -> str:
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-5-20250929"
    return "mock-prompt-aware-v1"


def _nct_from_study(study: dict[str, Any] | None) -> str | None:
    if not study:
        return None
    return nct_id_of(study) or None


async def complete_llm(
    prompt: str,
    source_text: str,
    model: str,
    *,
    nct_id: str | None = None,
) -> str:
    if model.startswith("mock"):
        raise RuntimeError("complete_llm called for mock model")
    provider = provider_for_model(model)
    try:
        preflight_paid_call(model=model, provider=provider)
    except BudgetKillError as exc:
        append_ledger(
            {
                "event": "refuse",
                "provider": provider,
                "model": model,
                "nct_id": nct_id,
                "purpose": "extract",
                "reason": str(exc),
            }
        )
        raise
    append_ledger(
        {
            "event": "paid_attempt",
            "provider": provider,
            "model": model,
            "nct_id": nct_id,
            "purpose": "extract",
            "estimated_usd": 0.05,
        }
    )
    system_plus = prompt
    user = "REGISTRY RECORD:\n" + source_text
    if os.environ.get("OPENAI_API_KEY") and not model.startswith("claude"):
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                json={
                    "model": model,
                    "temperature": 0,
                    "max_tokens": PAID_MAX_TOKENS,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_plus},
                        {"role": "user", "content": user},
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    if os.environ.get("ANTHROPIC_API_KEY"):
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": PAID_MAX_TOKENS,
                    "temperature": 0,
                    "system": system_plus,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            resp.raise_for_status()
            parts = resp.json()["content"]
            return "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    raise RuntimeError("no LLM credentials")


class Extractor:
    def __init__(self, *, force_mock: bool = False) -> None:
        self.prompt = load_prompt()
        self.model = current_model_name()
        self.force_mock = force_mock or self.model.startswith("mock")
        self.mock = PromptAwareExtractor(PROMPT_PATH)
        self._lock_held = False
        if not self.force_mock:
            acquire_runner_lock()
            self._lock_held = True

    def close(self) -> None:
        if self._lock_held:
            release_runner_lock()
            self._lock_held = False

    def __enter__(self) -> Extractor:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    async def extract(self, study: dict[str, Any], source_text: str) -> Extraction:
        nct_id = _nct_from_study(study)
        if self.force_mock:
            return self.mock.extract(study, source_text)

        key = llm_cache.cache_key(self.prompt, source_text, self.model)
        cached = llm_cache.load(key)
        if cached is not None:
            append_ledger(
                {
                    "event": "cache_hit",
                    "provider": provider_for_model(self.model),
                    "model": self.model,
                    "nct_id": nct_id,
                    "purpose": "extract",
                }
            )
            return parse_extraction(cached["extraction"], source_text)

        last_error: str | None = None
        payload: Any = None
        for attempt in range(2):
            user_text = source_text
            if last_error:
                user_text = source_text + "\n\nVALIDATION ERROR ON PREVIOUS ATTEMPT:\n" + last_error
            try:
                raw = await complete_llm(self.prompt, user_text, self.model, nct_id=nct_id)
                payload = extract_json_from_llm_text(raw)
                ext = parse_extraction(payload, source_text)
                llm_cache.store(
                    key,
                    {"extraction": ext.model_dump(), "model": self.model, "prompt_version": PROMPT_VERSION},
                )
                return ext
            except BudgetKillError:
                raise
            except (ExtractionError, json.JSONDecodeError, httpx.HTTPError) as exc:
                last_error = str(exc)
                if attempt == 0:
                    continue
                raise ExtractionError(last_error, payload) from exc
        raise ExtractionError("unreachable")
