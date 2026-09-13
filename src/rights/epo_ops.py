"""EPO OPS stub (European patent families). No live calls in Wave-1b.

Enable later with EPO_OPS_KEY / EPO_OPS_SECRET + a wired client.
"""

from __future__ import annotations

from typing import Any

from src.rights.stub import fetch_stub, module_stub

NAME = "epo_ops"
ENV_VAR = "EPO_OPS_KEY"


def stub_section() -> dict[str, Any]:
    return module_stub(NAME, ENV_VAR, extra={"patent_families": []})


def fetch(*, live: bool = False) -> dict[str, Any]:
    return fetch_stub(NAME, ENV_VAR, live=live, extra={"patent_families": []})
