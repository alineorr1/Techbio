"""FDA Orange Book hook stub (RLD / exclusivity). No live calls in Wave-1b.

Public data later; ORANGE_BOOK_LIVE must be set and a client wired before fetch(live=True).
"""

from __future__ import annotations

from typing import Any

from src.rights.schema import empty_pathway_505b2
from src.rights.stub import fetch_stub, module_stub

NAME = "orange_book"
ENV_VAR = "ORANGE_BOOK_LIVE"


def stub_section() -> dict[str, Any]:
    path = empty_pathway_505b2()
    return module_stub(
        NAME,
        ENV_VAR,
        extra={
            "rld_ref": path["rld_ref"],
            "listed_drug_ref": path["listed_drug_ref"],
            "exclusivity_windows": path["exclusivity_windows"],
            "orange_book_url": path["orange_book_url"],
        },
    )


def fetch(*, live: bool = False) -> dict[str, Any]:
    extra = stub_section()
    extra.pop("module", None)
    extra.pop("status", None)
    extra.pop("confidence", None)
    extra.pop("env_var", None)
    extra.pop("note", None)
    return fetch_stub(NAME, ENV_VAR, live=live, extra=extra)
