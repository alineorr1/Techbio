"""505(b)(2) RLD / exclusivity stubs with Orange Book hook placeholders."""

from __future__ import annotations

from typing import Any

from src.rights.orange_book import stub_section as orange_book_stub
from src.rights.schema import Pathway505b2, empty_pathway_505b2


def default_pathway() -> dict[str, Any]:
    return empty_pathway_505b2()


def attach_pathway(record: dict[str, Any], pathway: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(record)
    raw = pathway if pathway is not None else default_pathway()
    payload.setdefault("ind_regulatory", {})["pathway_505b2"] = Pathway505b2.model_validate(raw).model_dump()
    if raw.get("listed_drug_ref"):
        payload.setdefault("ip", {})["listed_drug_ref"] = raw["listed_drug_ref"]
        payload.setdefault("ip", {}).setdefault("orange_book", {})["listed_drug_ref"] = raw["listed_drug_ref"]
    return payload


def orange_book_hook() -> dict[str, Any]:
    """Placeholder link hook for a later Orange Book client."""
    return orange_book_stub()
