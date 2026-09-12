"""Wave-1 kill conditions. A contract break must fail CI."""

from __future__ import annotations

from pathlib import Path

from src.paths import ROOT

INGEST = ROOT / "src" / "ingest" / "ctis.py"
IDENTITY = ROOT / "src" / "identity" / "programme.py"
PIPELINE = ROOT / "src" / "pipeline.py"
WEEKLY_SH = ROOT / "scripts" / "weekly.sh"
WEEKLY_YML = ROOT / ".github" / "workflows" / "weekly.yml"
INDICATIONS = ROOT / "config" / "indications.yaml"


def _read(*paths: Path) -> str:
    return "\n".join(path.read_text() for path in paths)


def test_w1_k1_contract_files_exist():
    assert INGEST.is_file()
    assert IDENTITY.is_file()
    assert (ROOT / "data" / "smoke" / "ctis_status_map.json").is_file()
    assert (ROOT / "tests" / "fixtures" / "ctis" / "retrieve_2024-518143-38-00.json").is_file()
    assert (ROOT / "tests" / "fixtures" / "ctis" / "search_2024-518143-38-00.json").is_file()
    text = INGEST.read_text()
    assert "wave1.raw.v1" in text
    assert "POST" in text or "post_json" in text
    assert "ctPublicStatusCode" in text
    assert "WE.are".lower() in text.lower() or "we.are" in text


def test_w1_k2_source_never_maps_retrieve_ctstatus_string():
    text = INGEST.read_text()
    assert "ctPublicStatusCode" in text
    # retrieve mapper must not fall back to the application-status string
    assert "Never retrieve.ctStatus" in text or "Never from the retrieve" in text or "never from the retrieve" in text.lower()
    assert "payload.get(\"ctStatus\")" not in text
    assert "payload['ctStatus']" not in text


def test_w1_k3_no_ictrp():
    blob = _read(INGEST, IDENTITY).lower()
    assert "ictrp" not in blob
    assert "chictr" not in blob
    assert "who.int" not in blob


def test_w1_k4_one_programme_id_contract():
    text = IDENTITY.read_text()
    assert 'programme_id = "p_"' in text or 'return f"p_{digest}"' in text
    assert "UnionFind" in text
    assert "sha256" in text


def test_w1_k6_no_classify_score_serve_or_indications_expand():
    blob = _read(INGEST, IDENTITY)
    assert "src.classify" not in blob
    assert "src.score" not in blob
    assert "src.serve" not in blob
    assert "openai" not in blob.lower()
    assert "yaml.dump" not in blob
    assert "safe_dump" not in blob
    assert "ctis" not in PIPELINE.read_text().lower()
    assert "ctis" not in WEEKLY_SH.read_text().lower()
    assert "ctis" not in WEEKLY_YML.read_text().lower()
    # This PR must not expand indications.yaml; synonyms stay search terms only.
    yaml_text = INDICATIONS.read_text()
    assert yaml_text.count("endometriosis") >= 1
    assert "chocolate cyst" in yaml_text
    assert "Stein-Leventhal" in yaml_text
