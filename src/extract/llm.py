"""LLM extraction with cache. Falls back to PromptAwareExtractor when no API key is set."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from src.extract.deterministic import PromptAwareExtractor, extract_json_from_llm_text
from src.extract.schema import Extraction
from src.extract.validate import ExtractionError, parse_extraction
from src import llm_cache
from src.paths import PROMPTS_DIR

PROMPT_VERSION = "extraction_v1"
PROMPT_PATH = PROMPTS_DIR / f"{PROMPT_VERSION}.md"


def load_prompt() -> str:
    return PROMPT_PATH.read_text()


def current_model_name() -> str:
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-5-20250929"
    return "mock-prompt-aware-v1"


async def complete_llm(prompt: str, source_text: str, model: str) -> str:
    if model.startswith("mock"):
        raise RuntimeError("complete_llm called for mock model")
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
                    "max_tokens": 2000,
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

    async def extract(self, study: dict[str, Any], source_text: str) -> Extraction:
        if self.force_mock:
            return self.mock.extract(study, source_text)

        key = llm_cache.cache_key(self.prompt, source_text, self.model)
        cached = llm_cache.load(key)
        if cached is not None:
            return parse_extraction(cached["extraction"], source_text)

        last_error: str | None = None
        payload: Any = None
        for attempt in range(2):
            user_text = source_text
            if last_error:
                user_text = source_text + "\n\nVALIDATION ERROR ON PREVIOUS ATTEMPT:\n" + last_error
            try:
                raw = await complete_llm(self.prompt, user_text, self.model)
                payload = extract_json_from_llm_text(raw)
                ext = parse_extraction(payload, source_text)
                llm_cache.store(
                    key,
                    {"extraction": ext.model_dump(), "model": self.model, "prompt_version": PROMPT_VERSION},
                )
                return ext
            except (ExtractionError, json.JSONDecodeError, httpx.HTTPError) as exc:
                last_error = str(exc)
                if attempt == 0:
                    continue
                raise ExtractionError(last_error, payload) from exc
        raise ExtractionError("unreachable")
