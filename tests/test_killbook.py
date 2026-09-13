"""A6: locked WALK_AWAYs are a first-class negative product."""

from src.pilot.killbook import build_kill_book
from src.rights.codes import BIOGENE_ELTA_NCT, BOL_NCT, DESK_WRITEBACK_NCTS, LINZAGOLIX_NCT, VIRAMAL_NCT


def test_kill_book_covers_locked_desk_closes():
    book = build_kill_book()
    assert book["n"] == len(DESK_WRITEBACK_NCTS) == 18
    assert book["n_optionable"] == 0
    assert book["n_opp"] == 0
    by_nct = {row["nct_id"]: row for row in book["rows"]}
    for nct in (BIOGENE_ELTA_NCT, LINZAGOLIX_NCT, VIRAMAL_NCT, BOL_NCT):
        row = by_nct[nct]
        assert row["classification"] == "WALK_AWAY"
        assert row["ownable"] is False
        assert row["optionable"] is False
        assert row["opp"] is False
        assert row["kill_codes"]
        assert row["rationale"]
    assert by_nct[BIOGENE_ELTA_NCT]["citations"] == []
    assert any("WO2007" in c or "WO2014" in c for c in by_nct[LINZAGOLIX_NCT]["citations"])
