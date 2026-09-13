"""Offline CTIS ingest tests (fixtures only; no live network)."""

from __future__ import annotations

import asyncio
import inspect
import json

from src.ingest.ctis import (
    CTIS_REQUESTS_PER_SECOND,
    CTIS_SEARCH,
    CTIS_USER_AGENT,
    RAW_SCHEMA_VERSION,
    WIRED_INTO_PIPELINE,
    CtisClient,
    build_parser,
    condition_text_from_retrieve,
    is_secondary_only_match,
    lookup_public_status_code,
    make_raw_envelope,
    public_status_from_retrieve,
    public_status_from_search,
    resolve_indication,
    run_async,
    search_term_plan,
)
from src.paths import CTIS_STATUS_MAP_PATH, ROOT

FIXTURES = ROOT / "tests" / "fixtures" / "ctis"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


class FakeHttp:
    """HttpClient stand-in. Records POST vs GET so tests can enforce search=POST."""

    def __init__(self, search: dict[str, dict], retrieve: dict[str, dict]) -> None:
        self.search = search
        self.retrieve = retrieve
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []

    def cache_get(self, method: str, url: str, body: str | None = None):
        return None

    async def post_json(self, url: str, *, json_body: dict, skip_cache: bool = False):
        self.posts.append((url, json_body))
        assert url == CTIS_SEARCH
        term = (json_body.get("searchCriteria") or {}).get("medicalCondition")
        page = (json_body.get("pagination") or {}).get("page", 1)
        payload = self.search.get(term) or {
            "pagination": {
                "totalRecords": 0,
                "currentPage": page,
                "totalPages": 0,
                "nextPage": False,
                "prevPage": False,
            },
            "data": [],
        }
        if page > 1:
            return {
                "pagination": {
                    "totalRecords": payload.get("pagination", {}).get("totalRecords", 0),
                    "currentPage": page,
                    "totalPages": 1,
                    "nextPage": False,
                    "prevPage": True,
                },
                "data": [],
            }
        return payload

    async def get_json(self, url: str, *, params=None, skip_cache: bool = False):
        self.gets.append(url)
        assert "/retrieve/" in url
        ct_number = url.rstrip("/").split("/")[-1]
        if ct_number in self.retrieve:
            return self.retrieve[ct_number]
        return {"ctNumber": ct_number, "ctStatus": "Authorised", "ctPublicStatusCode": 2}


def test_user_agent_identifies_we_are_techbio():
    assert "we.are" in CTIS_USER_AGENT
    assert "Techbio" in CTIS_USER_AGENT


def test_rate_limit_is_two_rps():
    assert CTIS_REQUESTS_PER_SECOND == 2.0


def test_not_wired_into_pipeline():
    assert WIRED_INTO_PIPELINE is False


def test_cli_parses_condition_and_max():
    args = build_parser().parse_args(["--condition", "endometriosis", "--max", "50"])
    assert args.condition == "endometriosis"
    assert args.max_records == 50


def test_envelope_contract_from_live_smoke_fixture():
    payload = load_fixture("retrieve_2024-518143-38-00.json")
    url = "https://euclinicaltrials.eu/ctis-public-api/retrieve/2024-518143-38-00"
    envelope = make_raw_envelope(
        url=url,
        status=200,
        cached=False,
        native_id="2024-518143-38-00",
        payload=payload,
        fetched_at="2026-09-12T22:40:00Z",
    )
    assert envelope["schema_version"] == RAW_SCHEMA_VERSION == "wave1.raw.v1"
    assert envelope["source"] == "ctis"
    assert envelope["fetched_at"] == "2026-09-12T22:40:00Z"
    assert envelope["http"] == {"url": url, "status": 200, "cached": False}
    assert envelope["native_id"] == "2024-518143-38-00"
    assert envelope["payload"]["ctPublicStatusCode"] == 3
    assert envelope["public_status"]["code"] == 3
    assert envelope["public_status"]["field"] == "ctPublicStatusCode"


def test_w1_k2_retrieve_uses_public_status_code_not_ctstatus_string():
    payload = load_fixture("retrieve_2024-518143-38-00.json")
    assert payload["ctStatus"] == "Authorised"
    assert payload["ctPublicStatusCode"] == 3
    mapped = public_status_from_retrieve(payload)
    assert mapped["code"] == 3
    assert mapped["label"] == "Authorised, recruiting"
    assert mapped["universe"] == "exclude"
    assert mapped["field"] == "ctPublicStatusCode"

    trap = {"ctStatus": "Ended", "ctPublicStatusCode": 3}
    trapped = public_status_from_retrieve(trap)
    assert trapped["code"] == 3
    assert trapped["mapped_status"] is None
    assert trapped["label"] != "Ended"

    missing = public_status_from_retrieve({"ctStatus": "Ended"})
    assert missing["code"] is None
    assert missing["unmapped"] is True
    assert missing["universe"] == "quarantine_until_mapped"

    source = inspect.getsource(public_status_from_retrieve)
    assert "ctPublicStatusCode" in source
    assert "ctStatus" not in source


def test_w1_k2_search_uses_numeric_status_code():
    row = load_fixture("search_2024-518143-38-00.json")["data"][0]
    assert row["ctStatus"] == 3
    mapped = public_status_from_search(row)
    assert mapped["code"] == 3
    assert mapped["field"] == "search.ctStatus"
    assert public_status_from_search({"ctStatus": "Ended"})["unmapped"] is True


def test_status_enum_pin_has_codes_1_to_12():
    spec = json.loads(CTIS_STATUS_MAP_PATH.read_text())
    assert spec["source_of_truth"]["retrieve"] == "ctPublicStatusCode"
    assert "retrieve.ctStatus" in spec["do_not_use"]
    for code in range(1, 13):
        assert str(code) in spec["codes"]
    assert spec["codes"]["6"]["mapped_status"] == "SUSPENDED"
    assert spec["codes"]["8"]["mapped_status"] == "COMPLETED_OR_TERMINATED"
    assert spec["codes"]["12"]["label"] == "Cancelled"
    assert lookup_public_status_code(99, field="ctPublicStatusCode")["unmapped"] is True


def test_synonym_loop_reads_existing_yaml_only():
    key, synonyms = resolve_indication("endometriosis")
    assert key == "endometriosis"
    assert "endometriosis" in synonyms
    assert "adenomyosis" in synonyms
    plan = search_term_plan("endometriosis")
    assert [term for _, term, _ in plan] == synonyms
    key2, syn2 = resolve_indication("adenomyosis")
    assert key2 == "endometriosis"
    assert syn2 == synonyms


def test_secondary_only_quarantine_flag():
    synonyms = ["endometriosis", "adenomyosis", "endometrioma"]
    adeno = load_fixture("retrieve_2025-523076-23-00.json")
    both = load_fixture("retrieve_2024-519126-20-00.json")
    assert is_secondary_only_match(
        indication_key="endometriosis",
        synonyms=synonyms,
        condition_text=condition_text_from_retrieve(adeno),
        hitting_terms=["adenomyosis"],
    )
    assert not is_secondary_only_match(
        indication_key="endometriosis",
        synonyms=synonyms,
        condition_text=condition_text_from_retrieve(both),
        hitting_terms=["adenomyosis"],
    )


def test_search_is_post_and_paginates():
    page1 = load_fixture("search_endometriosis_page1.json")
    http = FakeHttp({"endometriosis": page1}, {})
    client = CtisClient(http)

    async def _collect() -> list[dict]:
        rows = []
        async for row in client.iter_search("endometriosis", page_size=5, max_records=5):
            rows.append(row)
        return rows

    rows = asyncio.run(_collect())
    assert len(rows) == 5
    assert http.posts
    assert all(url == CTIS_SEARCH for url, _ in http.posts)
    assert http.posts[0][1]["searchCriteria"]["medicalCondition"] == "endometriosis"
    assert http.posts[0][1]["pagination"] == {"page": 1, "size": 5}
    assert http.posts[0][1]["sort"] == {"property": "decisionDate", "direction": "DESC"}
    assert not http.gets
    assert all(body["pagination"]["page"] == 1 for _, body in http.posts)


def test_search_pagination_follows_next_page():
    class PagedHttp(FakeHttp):
        async def post_json(self, url: str, *, json_body: dict, skip_cache: bool = False):
            self.posts.append((url, json_body))
            page = json_body["pagination"]["page"]
            if page == 1:
                return {
                    "pagination": {"totalRecords": 2, "currentPage": 1, "totalPages": 2, "nextPage": True, "prevPage": False},
                    "data": [{"ctNumber": "2024-000001-00-00", "ctStatus": 8}],
                }
            return {
                "pagination": {"totalRecords": 2, "currentPage": 2, "totalPages": 2, "nextPage": False, "prevPage": True},
                "data": [{"ctNumber": "2024-000002-00-00", "ctStatus": 7}],
            }

    http = PagedHttp({}, {})
    client = CtisClient(http)

    async def _collect() -> list[str]:
        return [row["ctNumber"] async for row in client.iter_search("endometriosis", page_size=1)]

    numbers = asyncio.run(_collect())
    assert numbers == ["2024-000001-00-00", "2024-000002-00-00"]
    assert [body["pagination"]["page"] for _, body in http.posts] == [1, 2]


def test_run_async_writes_envelopes_offline(tmp_path):
    smoke = load_fixture("retrieve_2024-518143-38-00.json")
    search = load_fixture("search_2024-518143-38-00.json")
    http = FakeHttp({"endometriosis": search}, {"2024-518143-38-00": smoke})
    raw_dir = tmp_path / "raw"
    identity_dir = tmp_path / "identity"
    summary = asyncio.run(
        run_async(
            condition="endometriosis",
            max_records=1,
            page_size=5,
            raw_dir=raw_dir,
            search_dir=tmp_path / "search",
            identity_dir=identity_dir,
            http=http,
            cfg={
                "indications": {
                    "endometriosis": {"label": "Endometriosis", "synonyms": ["endometriosis"]}
                }
            },
        )
    )
    assert summary["retrieved"] == 1
    assert summary["wired_into_pipeline"] is False
    envelope = json.loads((raw_dir / "2024-518143-38-00.json").read_text())
    assert envelope["schema_version"] == "wave1.raw.v1"
    assert envelope["payload"]["ctPublicStatusCode"] == 3
    assert envelope["public_status"]["field"] == "ctPublicStatusCode"
    assert list(identity_dir.glob("p_*.json"))
    assert all("/search" in url for url, _ in http.posts)
    assert all("/retrieve/" in url for url in http.gets)
