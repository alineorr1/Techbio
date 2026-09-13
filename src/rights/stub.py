"""Shared stub helper. No network. Missing keys → NotConfigured or empty_stub."""

from __future__ import annotations

import os
from typing import Any

from src.rights.exceptions import NotConfigured


def env_set(name: str) -> bool:
    return bool((os.environ.get(name) or "").strip())


def module_stub(name: str, env_var: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "module": name,
        "status": "empty_stub",
        "confidence": "empty_stub",
        "env_var": env_var,
        "note": f"{name} stub; {env_var} not used. No live call.",
    }
    if extra:
        payload.update(extra)
    return payload


def fetch_stub(
    name: str,
    env_var: str,
    *,
    live: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not live:
        return module_stub(name, env_var, extra)
    if not env_set(env_var):
        raise NotConfigured(name, env_var)
    raise NotConfigured(name, env_var, reason="live client not wired (no network call)")
