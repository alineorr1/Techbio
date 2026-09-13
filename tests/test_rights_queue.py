"""T1/T3: disregard generics/marketed; cap active queue at ≤50."""

from __future__ import annotations

import json

from src.paths import RIGHTS_QUEUE_RULES_PATH, ROOT
from src.pilot.labels import LABEL_RIGHTS_QUEUE, is_empty_stub
from src.pilot.queue import build_rights_queue, disregard_hit, label_assets
from src.pilot.snapshot import snapshot_assets
from src.rights.codes import BIOGENE_ELTA_NCT, LINZAGOLIX_NCT


def test_queue_rules_match_dashboard_copy():
    src = json.loads(RIGHTS_QUEUE_RULES_PATH.read_text())
    dest = json.loads((ROOT / "dashboard" / "src" / "lib" / "rightsQueueRules.json").read_text())
    assert src == dest


def test_disregard_metformin_fiber_imaging():
    assert disregard_hit({"nct_id": "NCT1", "brief_title": "Metformin in PCOS", "interventions": [{"name": "Metformin"}]})
    assert disregard_hit({"nct_id": "NCT2", "brief_title": "Dietary fiber", "interventions": [{"name": "Fiber-Stat"}]})
    assert disregard_hit({"nct_id": "NCT3", "brief_title": "Evaluating with F-18 fluoroestradiol", "interventions": []})
    assert disregard_hit({"nct_id": "NCT4", "overall_status": "WITHDRAWN", "brief_title": "Novel"})
    assert disregard_hit({"nct_id": "NCT5", "enrolment": {"count": 0}, "brief_title": "Novel"})


def test_live_snapshot_queue_is_capped_and_not_opp():
    assets = snapshot_assets()
    built = build_rights_queue(assets)
    assert 1 <= built["n_queue"] <= 50
    assert built["n_queue"] <= built["cap"] <= 50
    assert built["n_empty_stub"] >= 500
    assert built["n_disregarded"] >= 100
    assert built["n_opp"] == 0
    ncts = [row["nct_id"] for row in built["queue"]]
    assert BIOGENE_ELTA_NCT not in ncts
    assert LINZAGOLIX_NCT not in ncts
    assert all(row["empty_stub"] for row in built["queue"])
    assert all(row["optionable"] is False for row in built["queue"])
    assert all(row["label"] == "RIGHTS_QUEUE" for row in built["queue"])
    assert all(row["label"] == "RIGHTS_QUEUE" for row in built["overflow"])
    assert "industry_single_grantor" in built["sort_order"]

    tagged = label_assets(assets)
    empty_ids = [
        str(a.get("nct_id") or "")
        for a in assets
        if is_empty_stub(a) and a.get("nct_id")
    ]
    assert len(empty_ids) >= 500
    assert all(tagged[nct]["label"] == LABEL_RIGHTS_QUEUE for nct in empty_ids)
    assert all(tagged[nct]["label"] != "OPP" for nct in empty_ids)
    assert sum(1 for row in tagged.values() if row.get("human_fill")) <= 50
    assert tagged[BIOGENE_ELTA_NCT]["label"] != LABEL_RIGHTS_QUEUE
    assert tagged[LINZAGOLIX_NCT]["label"] != LABEL_RIGHTS_QUEUE
