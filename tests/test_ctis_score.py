"""Phase-2 CTIS score wire: status trap, universe, dedup, unpaid mock extract."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

from src.ingest.ctis import make_raw_envelope
from src.ingest.ctis_study import (
    ctis_to_study,
    flatten_ctis_text,
    in_failed_asset_universe,
    is_drug_or_biologic_programme,
    is_recruiting_or_active_exclude,
    mapped_overall_status,
    public_status_of,
)
from src.paths import RAW_CTG_DIR, ROOT
from src.rights.gates import NOT_OPTIONABLE
from src.score.ctis import (
    WIRED_INTO_PIPELINE,
    decide_disposition,
    feature_enabled,
    run_async,
)
from src.serve.export import _keep_for_export, build_ctis_asset

FIXTURES = ROOT / "tests" / "fixtures" / "ctis"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def envelope_from_retrieve(name: str, **match) -> dict:
    payload = load_fixture(name)
    env = make_raw_envelope(
        url=f"https://euclinicaltrials.eu/ctis-public-api/retrieve/{payload['ctNumber']}",
        status=200,
        cached=True,
        native_id=payload["ctNumber"],
        payload=payload,
        fetched_at="2026-09-13T00:00:00Z",
        match=match or None,
    )
    return env


def test_score_wire_not_in_pipeline():
    assert WIRED_INTO_PIPELINE is False
    pipeline = (ROOT / "src" / "pipeline.py").read_text().lower()
    weekly = (ROOT / "scripts" / "weekly.sh").read_text().lower()
    yml = (ROOT / ".github" / "workflows" / "weekly.yml").read_text().lower()
    assert "ctis" not in pipeline
    assert "ctis" not in weekly
    assert "ctis" not in yml


def test_feature_flag_defaults_on_for_module():
    assert feature_enabled({}) is True
    assert feature_enabled({"WH_CTIS_SCORE": "0"}) is False
    assert feature_enabled({"WH_CTIS_SCORE": "off"}) is False


def test_public_status_trap_never_uses_retrieve_ctstatus_string():
    payload = load_fixture("retrieve_2023-599001-99-00.json")
    assert payload["ctStatus"] == "Ended"
    assert payload["ctPublicStatusCode"] == 7
    env = envelope_from_retrieve("retrieve_2023-599001-99-00.json")
    mapped = public_status_of(env)
    assert mapped["code"] == 7
    assert mapped["label"] == "Suspended"
    assert mapped["universe"] == "include"
    assert mapped["mapped_status"] == "SUSPENDED"
    assert mapped["field"] == "ctPublicStatusCode"
    assert mapped["label"] != "Ended"

    study = ctis_to_study(env)
    assert study["protocolSection"]["statusModule"]["overallStatus"] == "SUSPENDED"
    text = flatten_ctis_text(env)
    assert "Overall status: SUSPENDED" in text
    assert "Why stopped: Suspended" in text
    # Application-status string must not drive overall status.
    assert "Overall status: Ended" not in text

    study_src = (ROOT / "src" / "ingest" / "ctis_study.py").read_text()
    assert "ctPublicStatusCode" in inspect.getsource(public_status_of)
    assert 'payload.get("ctStatus")' not in study_src
    assert "payload['ctStatus']" not in study_src
    assert "retrieve.ctStatus" not in inspect.getsource(flatten_ctis_text)


def test_shelved_include_vs_recruiting_exclude():
    shelved = envelope_from_retrieve("retrieve_2023-599001-99-00.json")
    recruiting = envelope_from_retrieve("retrieve_2024-518143-38-00.json")
    ended = envelope_from_retrieve("retrieve_2024-519126-20-00.json")
    ongoing = envelope_from_retrieve("retrieve_2025-523076-23-00.json")

    assert in_failed_asset_universe(shelved)
    assert not is_recruiting_or_active_exclude(shelved)
    assert mapped_overall_status(shelved) == "SUSPENDED"

    assert not in_failed_asset_universe(recruiting)
    assert is_recruiting_or_active_exclude(recruiting)

    assert in_failed_asset_universe(ended)
    assert mapped_overall_status(ended) == "COMPLETED_OR_TERMINATED"

    assert not in_failed_asset_universe(ongoing)
    assert is_recruiting_or_active_exclude(ongoing)


def test_disposition_merge_when_nct_in_ctg_corpus():
    merge = envelope_from_retrieve("retrieve_nct05560646_merge.json")
    assert decide_disposition(merge, raw_ctg_dir=RAW_CTG_DIR) == "merge_nct"
    recruiting = envelope_from_retrieve("retrieve_2024-518143-38-00.json")
    # NCT03693677 is not in the committed CTG smoke slice → recruiting exclude, not merge.
    assert decide_disposition(recruiting, raw_ctg_dir=RAW_CTG_DIR) == "exclude"
    eu_only = envelope_from_retrieve("retrieve_2023-599001-99-00.json")
    assert decide_disposition(eu_only, raw_ctg_dir=RAW_CTG_DIR) == "score"
    assert is_drug_or_biologic_programme(eu_only)
    gnrh = envelope_from_retrieve(
        "retrieve_2024-519126-20-00.json",
    )
    gnrh["search_row"] = {"product": "DECAPEPTYL L.P. 11,25 mg", "ctTitle": gnrh["payload"]["authorizedApplication"]["authorizedPartI"]["trialDetails"]["clinicalTrialIdentifiers"]["publicTitle"]}
    assert is_drug_or_biologic_programme(gnrh)
    pet = make_raw_envelope(
        url="https://euclinicaltrials.eu/ctis-public-api/retrieve/2024-520423-88-00",
        status=200,
        cached=True,
        native_id="2024-520423-88-00",
        payload={
            "ctNumber": "2024-520423-88-00",
            "ctPublicStatusCode": 8,
            "authorizedApplication": {
                "authorizedPartI": {
                    "trialDetails": {
                        "clinicalTrialIdentifiers": {
                            "fullTitle": "Contribution of PET (positron emission tomography) scans for endometriosis",
                            "publicTitle": "PET scans for endometriosis",
                            "secondaryIdentifyingNumbers": {"nctNumber": None},
                        },
                        "trialInformation": {
                            "medicalCondition": {
                                "partIMedicalConditions": [{"medicalCondition": "Endometriosis"}]
                            }
                        },
                    },
                    "medicalConditions": [{"medicalCondition": "Endometriosis"}],
                    "products": [{"productName": "Furosemide"}],
                }
            },
        },
    )
    assert not is_drug_or_biologic_programme(pet)
    assert decide_disposition(pet, raw_ctg_dir=RAW_CTG_DIR) == "exclude"


def test_mock_extract_score_eu_only_and_dedup(tmp_path: Path):
    raw_dir = tmp_path / "raw_ctis"
    raw_ctg = tmp_path / "raw_ctg"
    raw_dir.mkdir()
    raw_ctg.mkdir()
    # Existing CTG programme for OG-6219 — CTIS mirror must merge, not double-score.
    (raw_ctg / "NCT05560646.json").write_text("{}", encoding="utf-8")

    eu_only = envelope_from_retrieve("retrieve_2023-599001-99-00.json")
    merge = envelope_from_retrieve("retrieve_nct05560646_merge.json")
    recruiting = envelope_from_retrieve("retrieve_2024-518143-38-00.json")
    (raw_dir / "2023-599001-99-00.json").write_text(json.dumps(eu_only), encoding="utf-8")
    (raw_dir / "2024-555606-46-00.json").write_text(json.dumps(merge), encoding="utf-8")
    (raw_dir / "2024-518143-38-00.json").write_text(json.dumps(recruiting), encoding="utf-8")

    summary = asyncio.run(
        run_async(
            force_mock=True,
            raw_dir=raw_dir,
            raw_ctg_dir=raw_ctg,
            identity_dir=tmp_path / "identity",
            extract_dir=tmp_path / "extract",
            enrich_dir=tmp_path / "enrich",
            classify_dir=tmp_path / "classify",
            score_dir=tmp_path / "score",
            quarantine_dir=tmp_path / "quarantine",
        )
    )
    assert summary["n_ctis_raw"] == 3
    assert summary["n_scored_eu_shelved"] == 1
    assert summary["n_merged_to_nct"] == 1
    assert summary["n_excluded_active"] == 1
    assert summary["optionable"] == 0
    assert len(summary["scored_programme_ids"]) == 1

    pid = summary["scored_programme_ids"][0]
    scored = json.loads((tmp_path / "score" / f"{pid}.json").read_text())
    assert scored["programme_id"] == pid
    assert scored["primary_display_id"] == "2023-599001-99-00"
    assert scored["source"] == "ctis"
    assert scored.get("optionable") is False
    assert scored["pre_pass"]["surface"] == NOT_OPTIONABLE
    assert scored["pre_pass"]["optionable"] is False
    # No second score file for the NCT-linked mirror.
    score_files = list((tmp_path / "score").glob("*.json"))
    assert len(score_files) == 1

    ext = json.loads((tmp_path / "extract" / f"{pid}.json").read_text())
    assert ext["primary_display_id"] == "2023-599001-99-00"
    assert ext["source"] == "ctis"


def test_eu_only_empty_rights_not_optionable_in_serve(tmp_path: Path, monkeypatch):
    raw_dir = tmp_path / "raw_ctis"
    raw_dir.mkdir()
    eu_only = envelope_from_retrieve("retrieve_2023-599001-99-00.json")
    (raw_dir / "2023-599001-99-00.json").write_text(json.dumps(eu_only), encoding="utf-8")

    extract_dir = tmp_path / "extract"
    enrich_dir = tmp_path / "enrich"
    classify_dir = tmp_path / "classify"
    score_dir = tmp_path / "score"
    identity_dir = tmp_path / "identity"

    summary = asyncio.run(
        run_async(
            force_mock=True,
            raw_dir=raw_dir,
            raw_ctg_dir=tmp_path / "raw_ctg",
            identity_dir=identity_dir,
            extract_dir=extract_dir,
            enrich_dir=enrich_dir,
            classify_dir=classify_dir,
            score_dir=score_dir,
            quarantine_dir=tmp_path / "quarantine",
        )
    )
    pid = summary["scored_programme_ids"][0]

    import src.serve.export as export

    monkeypatch.setattr(export, "RAW_CTIS_DIR", raw_dir)
    monkeypatch.setattr(export, "EXTRACT_DIR", extract_dir)
    monkeypatch.setattr(export, "ENRICH_DIR", enrich_dir)
    monkeypatch.setattr(export, "CLASSIFY_DIR", classify_dir)
    monkeypatch.setattr(export, "SCORE_DIR", score_dir)
    monkeypatch.setattr(export, "IDENTITY_DIR", identity_dir)

    from src.rights import store as rights_store

    monkeypatch.setattr(rights_store, "RIGHTS_DIR", identity_dir.parent / "rights")

    asset = build_ctis_asset(pid)
    assert asset is not None
    assert asset["primary_display_id"] == "2023-599001-99-00"
    assert asset["source"] == "ctis"
    assert asset["indication"] == "endometriosis"
    assert asset["optionable"] is False
    assert asset["gate_surface"] == NOT_OPTIONABLE
    assert asset["ownability"]["optionable"] is False
    assert _keep_for_export(asset["primary_display_id"], asset["indication"])


def test_indication_other_stays_out_of_ranked_export():
    assert not _keep_for_export("2023-000000-00-00", "other")
    assert _keep_for_export("2023-000000-00-00", "endometriosis")


def test_force_mock_required(tmp_path: Path):
    try:
        asyncio.run(
            run_async(
                force_mock=False,
                raw_dir=tmp_path,
                raw_ctg_dir=tmp_path,
                identity_dir=tmp_path / "id",
                extract_dir=tmp_path / "x",
                enrich_dir=tmp_path / "e",
                classify_dir=tmp_path / "c",
                score_dir=tmp_path / "s",
                quarantine_dir=tmp_path / "q",
            )
        )
    except RuntimeError as exc:
        assert "unpaid-only" in str(exc)
        assert "force-mock" in str(exc)
    else:
        raise AssertionError("paid path must be refused")
