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

# Asset IP public-only desk writeback (Wave-1b).
BIOGENE_ELTA_NCT = "NCT03481842"
BOL_NCT = "NCT04174911"
LINZAGOLIX_NCT = "NCT04372121"
VIRAMAL_NCT = "NCT03352076"
# Empty: Viramal + BOL closed WALK_AWAY after public patent-number pass (null / adjacent-only).
# Re-adding an NCT here is the one-line hold if Asset IP ever needs a provisional CONTINGENT.
PROVISIONAL_CONTINGENT_NCTS: frozenset[str] = frozenset()
DESK_WRITEBACK_NCTS = (
    "NCT02669238",
    "NCT04554693",
    "NCT05670353",
    "NCT04641273",
    LINZAGOLIX_NCT,
    "NCT03380091",
    "NCT03970330",
    "NCT00703092",
    "NCT01631981",
    VIRAMAL_NCT,
    "NCT05370521",
    "NCT03201601",
    "NCT03340324",
    "NCT00212277",
    "NCT00865488",
    "NCT00758953",
    BIOGENE_ELTA_NCT,
    BOL_NCT,
)
