"""Wave-1b contract: rights stubs, no paid LLM, K4 Intermezzo named in source."""

from __future__ import annotations

from pathlib import Path

from src.paths import ROOT

RIGHTS = ROOT / "src" / "rights"
SCORE = ROOT / "src" / "score" / "compute.py"
CLASSIFY = ROOT / "src" / "classify" / "rules.py"
EXTRACT_LLM = ROOT / "src" / "extract" / "llm.py"
SCORING = ROOT / "config" / "scoring.yaml"


def test_w1b_rights_modules_exist():
    for name in ("uspto_odp.py", "epo_ops.py", "opencorporates.py", "orange_book.py", "schema.py", "gates.py"):
        assert (RIGHTS / name).is_file()
    assert not (RIGHTS / "usppto_odp.py").exists()
    assert "wave-1b.rights-stub.v1" in (RIGHTS / "schema.py").read_text()
    assert (RIGHTS / "wave-1b.rights-stub.v1.json").is_file()
    text = (RIGHTS / "schema.py").read_text()
    for block in (
        "identity",
        "counterparty",
        "ind_regulatory",
        "fto_lite",
        "coi",
        "ownership",
        "thesis_mismatch",
    ):
        assert block in text
    codes = (RIGHTS / "codes.py").read_text()
    for code in (
        "K_THESIS_MISMATCH",
        "K_NO_COUNTERPARTY",
        "K_NO_IP_EMPTY_DOCKET",
        "K_COM_ELSEWHERE",
        "K_VALUE_NOT_CAPTURED",
        "K_REG_CAPTURE_DESTROY",
        "K_FAILED_PIVOTAL",
        "S_PRIVATE_IP_ONLY",
        "S_LICENSE_MAP_MISSING",
        "S_ORANGE_BOOK_BLOCK",
        "S_COI_UNCLEAR",
        "S_TAXONOMY_FIX",
    ):
        assert code in codes


def test_w1b_no_openai_or_paid_llm_in_rights():
    blob = "\n".join(p.read_text() for p in RIGHTS.glob("*.py")).lower()
    assert "openai" not in blob
    assert "anthropic" not in blob
    assert "api.openai.com" not in blob


def test_w1b_extract_llm_not_enabled():
    text = EXTRACT_LLM.read_text()
    assert "force_mock" in text
    # This PR must not flip extract to a paid default.
    assert "OPENAI_API_KEY" in text


def test_w1b_k4_and_organon_rule_b_still_present():
    gates = (RIGHTS / "gates.py").read_text()
    assert "K4_INTERMEZZO" in gates
    assert "SEX_DIFF_ALONE" in gates
    scoring = SCORING.read_text()
    assert "organon_guard_max_without_pretrial_evidence" in scoring
    assert "intermezzo_score_cap" in scoring
    assert "src.rights.gates" in CLASSIFY.read_text()
    assert "evaluate_commercial_gate" in SCORE.read_text()
