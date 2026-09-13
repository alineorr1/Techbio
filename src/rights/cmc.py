"""Desk-grade CMC checklist defaults. Structured only — no LLM poetry."""

from __future__ import annotations

from typing import Any

from src.rights.schema import CmcChecklist, empty_cmc


def default_checklist() -> dict[str, Any]:
    return empty_cmc()


def attach_cmc(record: dict[str, Any], checklist: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(record)
    raw = checklist if checklist is not None else default_checklist()
    payload.setdefault("ind_regulatory", {})["cmc"] = CmcChecklist.model_validate(raw).model_dump()
    return payload
