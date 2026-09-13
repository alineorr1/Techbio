"""Serve export drops indication==other unless the NCT is always_include."""

from src.config import indications_config
from src.serve.export import _indication, _keep_for_export


def _study(*, nct: str, conditions: list[str], title: str = "A trial") -> dict:
    return {
        "protocolSection": {
            "identificationModule": {
                "nctId": nct,
                "briefTitle": title,
                "officialTitle": title,
            },
            "conditionsModule": {"conditions": conditions},
        }
    }


def test_keep_endo_and_pcos():
    assert _keep_for_export("NCT08888888", "endometriosis")
    assert _keep_for_export("NCT08888888", "pcos")


def test_drop_other_unless_always_include():
    always = set(indications_config()["always_include_ncts"])
    assert "NCT05560646" in always
    assert not _keep_for_export("NCT08888888", "other")
    assert _keep_for_export("NCT05560646", "other")
    assert _keep_for_export("NCT03709420", "other")
    assert _keep_for_export("NCT00001848", "other")


def test_indication_endo_pcos_or_other():
    assert _indication(_study(nct="NCT1", conditions=["Endometriosis"])) == "endometriosis"
    assert _indication(_study(nct="NCT2", conditions=["Polycystic Ovary Syndrome"])) == "pcos"
    assert _indication(_study(nct="NCT3", conditions=["Uterine Fibroids"], title="Leiomyoma")) == "other"
