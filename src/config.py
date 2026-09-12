"""YAML/CSV config loaders. Indications are never hardcoded in pipeline logic."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.paths import INDICATIONS_PATH, SCORING_PATH, SPONSORS_PATH


@lru_cache(maxsize=1)
def indications_config(path: Path | None = None) -> dict[str, Any]:
    with (path or INDICATIONS_PATH).open() as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def scoring_config(path: Path | None = None) -> dict[str, Any]:
    with (path or SCORING_PATH).open() as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def sponsor_rows(path: Path | None = None) -> list[dict[str, str]]:
    with (path or SPONSORS_PATH).open(newline="") as fh:
        return list(csv.DictReader(fh))


def indication_synonym_query(cfg: dict[str, Any] | None = None) -> str:
    """Essie OR-query from config synonym lists, including paired-term rules."""
    cfg = cfg or indications_config()
    clauses: list[str] = []
    for ind in cfg["indications"].values():
        for syn in ind.get("synonyms") or []:
            paired = (ind.get("require_paired_terms") or {}).get(syn)
            if paired:
                inner = " OR ".join(_essie_quote(p) for p in paired)
                clauses.append(f"({_essie_quote(syn)} AND ({inner}))")
            else:
                clauses.append(_essie_quote(syn))
    return " OR ".join(clauses)


def _essie_quote(term: str) -> str:
    if " " in term or "-" in term:
        return f'"{term}"'
    return term


def efo_and_mondo_for(indication_key: str) -> list[str]:
    cfg = indications_config()
    ind = cfg["indications"][indication_key]
    ids = list(ind.get("mondo_ids") or []) + list(ind.get("efo_ids") or [])
    ids.extend(ind.get("related_mondo_ids") or [])
    return ids
