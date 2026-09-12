"""Verbatim evidence assertion. Hallucinated stop_reason_evidence is quarantined."""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from src.extract.schema import Extraction


class ExtractionError(Exception):
    def __init__(self, message: str, payload: Any | None = None) -> None:
        super().__init__(message)
        self.payload = payload


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_verbatim_substring(evidence: str, source_text: str) -> bool:
    """True iff evidence is a contiguous substring of the extractor input.

    Allows only whitespace-flexibility: we also accept the evidence if the
    whitespace-normalized form is a substring of the whitespace-normalized source.
    We do NOT accept paraphrases.
    """
    if evidence == "":
        return True
    if evidence in source_text:
        return True
    ev = normalize_ws(evidence)
    src = normalize_ws(source_text)
    return ev in src and ev != ""


def assert_verbatim(extraction: Extraction, source_text: str) -> None:
    if not is_verbatim_substring(extraction.stop_reason_evidence, source_text):
        raise ExtractionError(
            "stop_reason_evidence is not a verbatim substring of the input",
            extraction.model_dump(),
        )
    if extraction.stop_reason_raw:
        if extraction.stop_reason_raw not in source_text and normalize_ws(
            extraction.stop_reason_raw
        ) not in normalize_ws(source_text):
            raise ExtractionError(
                "stop_reason_raw is not a verbatim substring of the input",
                extraction.model_dump(),
            )


def parse_extraction(payload: Any, source_text: str) -> Extraction:
    try:
        ext = Extraction.model_validate(payload)
    except ValidationError as exc:
        raise ExtractionError(f"schema validation failed: {exc}", payload) from exc
    assert_verbatim(ext, source_text)
    return ext
