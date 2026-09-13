"""Locked Asset IP kill / soft codes. Queryable; do not rename."""

from __future__ import annotations

HARD_KILL_CODES = (
    "K_THESIS_MISMATCH",
    "K_NO_COUNTERPARTY",
    "K_NO_IP_EMPTY_DOCKET",
    "K_COM_ELSEWHERE",
    "K_VALUE_NOT_CAPTURED",
    "K_REG_CAPTURE_DESTROY",
    "K_FAILED_PIVOTAL",
)

SOFT_CODES = (
    "S_PRIVATE_IP_ONLY",
    "S_LICENSE_MAP_MISSING",
    "S_ORANGE_BOOK_BLOCK",
    "S_COI_UNCLEAR",
    "S_TAXONOMY_FIX",
)

# FOR-6219 / OG-6219: always attach a stub even when taxonomy is empty.
FOR_6219_NCT = "NCT03709420"
OG_6219_NCT = "NCT05560646"
