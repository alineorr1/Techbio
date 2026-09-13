"""Rights stubs: no network keys → NotConfigured or empty_stub."""

from __future__ import annotations

import pytest

from src.rights import epo_ops, opencorporates, orange_book, uspto_odp
from src.rights.exceptions import NotConfigured
from src.rights.fill import fill_rights
from src.rights.schema import empty_rights


MODULES = (uspto_odp, epo_ops, opencorporates, orange_book)


@pytest.fixture(autouse=True)
def _no_rights_keys(monkeypatch):
    for key in (
        "USPTO_ODP_API_KEY",
        "EPO_OPS_KEY",
        "EPO_OPS_SECRET",
        "OPENCORPORATES_API_KEY",
        "ORANGE_BOOK_LIVE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_no_usppto_typo_module():
    import src.rights as pkg
    from pathlib import Path

    rights_dir = Path(pkg.__file__).parent
    names = {p.name for p in rights_dir.glob("*.py")}
    assert "usppto_odp.py" not in names
    assert "uspto_odp.py" in names


@pytest.mark.parametrize("mod", MODULES, ids=[m.NAME for m in MODULES])
def test_stub_returns_empty_stub(mod):
    section = mod.fetch(live=False)
    assert section["status"] == "empty_stub"
    assert section["confidence"] == "empty_stub"
    assert section["module"] == mod.NAME


@pytest.mark.parametrize("mod", MODULES, ids=[m.NAME for m in MODULES])
def test_live_without_key_raises_not_configured(mod):
    with pytest.raises(NotConfigured) as exc:
        mod.fetch(live=True)
    assert exc.value.module == mod.NAME
    assert exc.value.env_var == mod.ENV_VAR


def test_fill_without_keys_writes_empty_stub(tmp_path):
    rec = fill_rights("p_2222222222222222", live=False, root=tmp_path)
    assert rec["confidence"] == "empty_stub"
    assert rec["commercial_gate"]["verdict"] != "PASS"
    for name in ("uspto_odp", "epo_ops", "opencorporates", "orange_book"):
        assert rec["modules"][name]["status"] == "empty_stub"
        assert rec["modules"][name]["confidence"] == "empty_stub"


def test_fill_live_raises_not_configured(tmp_path):
    attach = empty_rights("p_3333333333333333")
    from src.rights.store import write_rights

    write_rights(attach, root=tmp_path)
    with pytest.raises(NotConfigured):
        fill_rights("p_3333333333333333", live=True, root=tmp_path)
