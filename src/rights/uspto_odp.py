"""USPTO Open Data Portal stub (patent families). No live calls in Wave-1b.

Named uspto_odp (not usppto). Enable later with USPTO_ODP_API_KEY + a wired client.
"""

from __future__ import annotations

from typing import Any

from src.rights.stub import fetch_stub, module_stub

NAME = "uspto_odp"
ENV_VAR = "USPTO_ODP_API_KEY"


def stub_section() -> dict[str, Any]:
    return module_stub(NAME, ENV_VAR, extra={"patent_families": []})


def fetch(*, live: bool = False) -> dict[str, Any]:
    return fetch_stub(NAME, ENV_VAR, live=live, extra={"patent_families": []})
