"""Eval harness provenance checks and regression helper."""

import json
from pathlib import Path

import pytest

from src.eval.harness import LabelError, load_labels, regression_guard


def test_load_labels_has_human_provenance():
    rows = load_labels()
    assert len(rows) == 40
    bio = sum(1 for r in rows if r.get("biology_failed") is True)
    other = sum(1 for r in rows if r.get("biology_failed") is False)
    assert bio == 20 and other == 20
    for r in rows:
        assert r["labelled_by"]
        assert r["rationale"]
        assert r["nct_id"].startswith("NCT")


def test_refuses_missing_labelled_by(tmp_path: Path):
    p = tmp_path / "labels.jsonl"
    p.write_text(json.dumps({"nct_id": "NCT1", "rationale": "x", "stop_reason_category": "safety"}) + "\n")
    with pytest.raises(LabelError):
        load_labels(p)


def test_refuses_model_labelled_by(tmp_path: Path):
    p = tmp_path / "labels.jsonl"
    p.write_text(
        json.dumps(
            {
                "nct_id": "NCT1",
                "labelled_by": "llm",
                "rationale": "x",
                "stop_reason_category": "safety",
            }
        )
        + "\n"
    )
    with pytest.raises(LabelError):
        load_labels(p)


def test_regression_guard_trips_over_3pp():
    prev = {"fields": [{"field": "stop_reason_category", "accuracy": 0.80}]}
    cur = {"fields": [{"field": "stop_reason_category", "accuracy": 0.76}]}
    assert regression_guard(cur, prev)  # 4pp drop
    cur2 = {"fields": [{"field": "stop_reason_category", "accuracy": 0.78}]}
    assert regression_guard(cur2, prev) == []  # 2pp, allowed
