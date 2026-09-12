"""Golden-set eval harness. Human labels only. Per-field reporting, confusion, failures, regression guard."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.db import dump_json
from src.extract.deterministic import PromptAwareExtractor
from src.extract.llm import PROMPT_VERSION
from src.extract.schema import POPULATION_BOOLEAN_FIELDS, Extraction
from src.ingest.ctg import flatten_study_text
from src.paths import EVAL_RUNS_DIR, GOLDEN_DIR, RAW_CTG_DIR, ensure_dirs

LABELS_PATH = GOLDEN_DIR / "labels.jsonl"
REQUIRED_LABEL_FIELDS = ("nct_id", "labelled_by", "rationale")

EVAL_FIELDS = [
    "stop_reason_category",
    "targets",
    *POPULATION_BOOLEAN_FIELDS,
    "endpoint_appropriate_for_indication",
]


class LabelError(SystemExit):
    pass


def load_labels(path: Path = LABELS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        raise LabelError(f"golden labels not found: {path}")
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        for key in REQUIRED_LABEL_FIELDS:
            if not row.get(key):
                raise LabelError(
                    f"Refusing to run: row {i} (nct_id={row.get('nct_id')!r}) "
                    f"missing required human-provenance field `{key}`. "
                    "Golden labels must be human authored."
                )
        if str(row.get("labelled_by", "")).lower() in {"model", "llm", "gpt", "claude", "auto"}:
            raise LabelError(
                f"Refusing to run: row {i} labelled_by={row.get('labelled_by')!r} looks machine-authored."
            )
        rows.append(row)
    if not rows:
        raise LabelError("golden labels file is empty")
    return rows


def _target_set(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                names.add(item.strip().lower())
            elif isinstance(item, dict):
                n = (item.get("name") or item.get("gene_symbol") or "").strip().lower()
                if n:
                    names.add(n)
                g = (item.get("gene_symbol") or "").strip().lower()
                if g:
                    names.add(g)
    return names


def field_equal(field: str, predicted: Any, labelled: Any) -> bool:
    if field == "targets":
        p = _target_set(predicted)
        h = _target_set(labelled)
        if not h and not p:
            return True
        if not h:
            return not p
        return len(p & h) / len(h | p) >= 0.5 if (h | p) else True
    return predicted == labelled


def target_overlap(predicted: Any, labelled: Any) -> float:
    p = _target_set(predicted)
    h = _target_set(labelled)
    if not h and not p:
        return 1.0
    union = h | p
    if not union:
        return 1.0
    return len(p & h) / len(union)


def predict_one(nct_id: str, extractor: PromptAwareExtractor) -> Extraction:
    raw_path = RAW_CTG_DIR / f"{nct_id}.json"
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Missing cached registry record for golden NCT {nct_id} at {raw_path}. "
            "Run `python -m src.ingest` first."
        )
    study = json.loads(raw_path.read_text())
    source = flatten_study_text(study)
    return extractor.extract(study, source)


def _predicted_value(ext: Extraction, field: str) -> Any:
    if field == "stop_reason_category":
        return ext.stop_reason_category
    if field == "targets":
        return [t.model_dump() for t in ext.targets]
    if field == "endpoint_appropriate_for_indication":
        return ext.endpoint_quality.endpoint_appropriate_for_indication
    if field in POPULATION_BOOLEAN_FIELDS:
        return getattr(ext.population, field)
    raise KeyError(field)


def _labelled_value(row: dict[str, Any], field: str) -> Any:
    if field == "stop_reason_category":
        return row["stop_reason_category"]
    if field == "targets":
        return row.get("targets") or []
    if field == "endpoint_appropriate_for_indication":
        return row["endpoint_appropriate_for_indication"]
    if field in POPULATION_BOOLEAN_FIELDS:
        return (row.get("population") or {})[field]
    raise KeyError(field)


def evaluate(
    labels: list[dict[str, Any]] | None = None,
    extractor: PromptAwareExtractor | None = None,
) -> dict[str, Any]:
    ensure_dirs()
    labels = labels if labels is not None else load_labels()
    extractor = extractor or PromptAwareExtractor()
    per_field_correct: dict[str, int] = {f: 0 for f in EVAL_FIELDS}
    per_field_total: dict[str, int] = {f: 0 for f in EVAL_FIELDS}
    confusion: dict[str, Counter] = defaultdict(Counter)
    failures: list[dict[str, Any]] = []
    biology_split = Counter()

    for row in labels:
        nct = row["nct_id"]
        pred = predict_one(nct, extractor)
        gold_cat = row["stop_reason_category"]
        pred_cat = pred.stop_reason_category
        confusion[gold_cat][pred_cat] += 1
        if row.get("biology_failed") is True:
            biology_split["biology_failed"] += 1
        elif row.get("biology_failed") is False:
            biology_split["something_else"] += 1

        row_mismatch = False
        mismatch_fields: list[str] = []
        for field in EVAL_FIELDS:
            labelled = _labelled_value(row, field)
            predicted = _predicted_value(pred, field)
            per_field_total[field] += 1
            ok = field_equal(field, predicted, labelled)
            if field == "targets":
                # store overlap as well
                pass
            if ok:
                per_field_correct[field] += 1
            else:
                row_mismatch = True
                mismatch_fields.append(field)
        if row_mismatch:
            failures.append(
                {
                    "nct_id": nct,
                    "human_stop_reason_category": gold_cat,
                    "predicted_stop_reason_category": pred_cat,
                    "stop_reason_evidence": pred.stop_reason_evidence,
                    "human_rationale": row.get("rationale"),
                    "mismatch_fields": mismatch_fields,
                    "predicted_targets": [t.name for t in pred.targets],
                    "labelled_targets": row.get("targets"),
                }
            )

    field_rows = []
    for field in EVAL_FIELDS:
        tot = per_field_total[field] or 1
        acc = per_field_correct[field] / tot
        field_rows.append(
            {
                "field": field,
                "correct": per_field_correct[field],
                "n": per_field_total[field],
                "accuracy": round(acc, 4),
            }
        )
    aggregate = (
        sum(per_field_correct[f] for f in EVAL_FIELDS) / sum(per_field_total[f] for f in EVAL_FIELDS)
        if EVAL_FIELDS
        else 0.0
    )
    # Decisive confusion cells
    discard_good = confusion.get("funding_or_sponsor", Counter()).get("efficacy", 0)
    surface_dead = confusion.get("efficacy", Counter()).get("funding_or_sponsor", 0)

    result = {
        "prompt_version": PROMPT_VERSION,
        "n_labels": len(labels),
        "biology_split": dict(biology_split),
        "fields": field_rows,
        "aggregate_accuracy": round(aggregate, 4),
        "confusion_stop_reason_category": {k: dict(v) for k, v in confusion.items()},
        "callouts": {
            "labelled_funding_or_sponsor_predicted_efficacy": discard_good,
            "labelled_efficacy_predicted_funding_or_sponsor": surface_dead,
        },
        "failures": failures,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def print_report(result: dict[str, Any]) -> None:
    print(f"prompt_version: {result['prompt_version']}")
    print(f"n_labels: {result['n_labels']}  split={result.get('biology_split')}")
    print()
    print(f"{'field':42} {'correct':>8} {'n':>6} {'acc':>8}")
    print("-" * 70)
    for row in result["fields"]:
        print(f"{row['field']:42} {row['correct']:8d} {row['n']:6d} {row['accuracy']:8.1%}")
    print("-" * 70)
    print(f"{'AGGREGATE (not a substitute for per-field)':42} {'':>8} {'':>6} {result['aggregate_accuracy']:8.1%}")
    print()
    print("Confusion matrix: stop_reason_category (rows = human label, cols = predicted)")
    labels = sorted({*result["confusion_stop_reason_category"].keys()} | {
        c for row in result["confusion_stop_reason_category"].values() for c in row
    })
    print(f"{'human\\pred':22}" + "".join(f"{c[:10]:>12}" for c in labels))
    for h in labels:
        cells = result["confusion_stop_reason_category"].get(h, {})
        print(f"{h:22}" + "".join(f"{cells.get(c, 0):12d}" for c in labels))
    print()
    print("Decisive cells (opposite ranking consequences):")
    print(
        "  labelled funding_or_sponsor, predicted efficacy "
        f"(discards a good asset): {result['callouts']['labelled_funding_or_sponsor_predicted_efficacy']}"
    )
    print(
        "  labelled efficacy, predicted funding_or_sponsor "
        f"(surfaces a dead one): {result['callouts']['labelled_efficacy_predicted_funding_or_sponsor']}"
    )
    print()
    print(f"Failures ({len(result['failures'])}):")
    if not result["failures"]:
        print("  none")
    for f in result["failures"]:
        print(
            f"  {f['nct_id']}: human={f['human_stop_reason_category']} "
            f"pred={f['predicted_stop_reason_category']} "
            f"fields={','.join(f['mismatch_fields'])}"
        )
        print(f"      evidence: {f['stop_reason_evidence'][:180]!r}")


def previous_run(prompt_version: str, runs_dir: Path = EVAL_RUNS_DIR) -> dict[str, Any] | None:
    if not runs_dir.exists():
        return None
    files = sorted(runs_dir.glob("*.json"))
    if not files:
        return None
    # Compare against the most recent run of a *different* snapshot; same-version
    # re-runs still compare so a silent prompt edit is caught.
    latest = json.loads(files[-1].read_text())
    return latest


def regression_guard(current: dict[str, Any], previous: dict[str, Any] | None) -> list[str]:
    if previous is None:
        return []
    prev_fields = {r["field"]: r["accuracy"] for r in previous.get("fields") or []}
    regressions = []
    for row in current["fields"]:
        old = prev_fields.get(row["field"])
        if old is None:
            continue
        if old - row["accuracy"] > 0.03:
            regressions.append(
                f"{row['field']}: {old:.1%} -> {row['accuracy']:.1%} (drop {(old - row['accuracy']):.1%} > 3pp)"
            )
    return regressions


def persist_run(result: dict[str, Any]) -> Path:
    ensure_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = EVAL_RUNS_DIR / f"{ts}_{result['prompt_version']}.json"
    dump_json(path, result)
    return path
