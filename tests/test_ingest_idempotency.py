"""Ingest is idempotent: re-running does not duplicate NCT rows."""

from datetime import datetime

from src.db import connect, upsert
from src.ingest.ctg import in_stopped_universe, nct_id_of


def _terminated_study(nct="NCT11111111"):
    return {
        "hasResults": False,
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": "X"},
            "statusModule": {
                "overallStatus": "TERMINATED",
                "whyStopped": "Lack of recruitment",
                "lastUpdatePostDateStruct": {"date": "2020-01-01"},
                "primaryCompletionDateStruct": {"date": "2019-01-01"},
            },
            "designModule": {"studyType": "INTERVENTIONAL", "phases": ["PHASE2"]},
            "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": "Metformin"}]},
            "conditionsModule": {"conditions": ["Polycystic Ovary Syndrome"]},
        },
    }


def test_in_stopped_universe_terminated():
    assert in_stopped_universe(_terminated_study())


def test_completed_with_results_recent_excluded():
    study = _terminated_study("NCT05560646")
    # OG-6219 is in always_include so it stays
    study["protocolSection"]["statusModule"]["overallStatus"] = "COMPLETED"
    study["hasResults"] = True
    study["protocolSection"]["statusModule"]["primaryCompletionDateStruct"] = {"date": "2025-05-28"}
    assert in_stopped_universe(study)


def test_completed_no_results_old_included():
    study = _terminated_study("NCT00999999")
    study["protocolSection"]["statusModule"]["overallStatus"] = "COMPLETED"
    study["hasResults"] = False
    study["protocolSection"]["statusModule"]["primaryCompletionDateStruct"] = {"date": "2015-01-01"}
    assert in_stopped_universe(study)


def test_completed_recent_with_results_not_in_always_include_excluded():
    study = _terminated_study("NCT08888888")
    study["protocolSection"]["statusModule"]["overallStatus"] = "COMPLETED"
    study["hasResults"] = True
    study["protocolSection"]["statusModule"]["primaryCompletionDateStruct"] = {"date": "2025-01-01"}
    assert not in_stopped_universe(study)


def test_upsert_does_not_duplicate(tmp_path):
    db = tmp_path / "t.duckdb"
    con = connect(db)
    study = _terminated_study()
    nct = nct_id_of(study)
    now = datetime(2026, 1, 1)
    upsert(con, "raw_studies", nct, fetched_at=now, last_update_date="2020-01-01", overall_status="TERMINATED", payload_json=study)
    upsert(con, "raw_studies", nct, fetched_at=now, last_update_date="2020-01-01", overall_status="TERMINATED", payload_json=study)
    n = con.execute("SELECT count(*) FROM raw_studies").fetchone()[0]
    assert n == 1
    con.close()
