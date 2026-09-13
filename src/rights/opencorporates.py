"""OpenCorporates stub (sponsor legal entity). No live calls in Wave-1b.

Enable later with OPENCORPORATES_API_KEY + a wired client.
"""

from __future__ import annotations

from typing import Any

from src.rights.schema import empty_sponsor_entity
from src.rights.stub import fetch_stub, module_stub

NAME = "opencorporates"
ENV_VAR = "OPENCORPORATES_API_KEY"


def stub_section() -> dict[str, Any]:
    return module_stub(
        NAME,
        ENV_VAR,
        extra={"sponsor_entity": empty_sponsor_entity(resolution_status="not_yet_fetched")},
    )


def fetch(*, live: bool = False) -> dict[str, Any]:
    return fetch_stub(
        NAME,
        ENV_VAR,
        live=live,
        extra={"sponsor_entity": empty_sponsor_entity(resolution_status="not_yet_fetched")},
    )
