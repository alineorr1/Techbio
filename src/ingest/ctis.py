"""CTIS public-API ingest (Wave-1, feature-flagged).

Opt-in only: ``python -m src.ingest.ctis --condition endometriosis --max 50``.
Do not import this module from ``src.pipeline`` or the weekly cron.

Search is POST /search only (GET returns 403). Retrieve is GET /retrieve/{ctNumber}.
Raw records are written as RawEnvelope JSON under ``data/raw/ctis/``.
Public status comes from ``ctPublicStatusCode`` (retrieve) or the numeric
``search.ctStatus`` code — never from the retrieve ``ctStatus`` string.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

from src.config import indications_config
from src.db import dump_json
from src.http import HttpClient
from src.identity.programme import (
    IdentityStore,
    identifiers_from_ctis_retrieve,
    nested,
)
from src.paths import (
    CTIS_STATUS_MAP_PATH,
    RAW_CTIS_DIR,
    RAW_CTIS_SEARCH_DIR,
    IDENTITY_DIR,
    ensure_dirs,
)

# Wave-1 feature flag: this module is the only entry point. Pipeline wiring is off.
WIRED_INTO_PIPELINE = False
FEATURE_ENV = "WH_CTIS_INGEST"

CTIS_BASE = "https://euclinicaltrials.eu/ctis-public-api"
CTIS_SEARCH = f"{CTIS_BASE}/search"
CTIS_RETRIEVE = f"{CTIS_BASE}/retrieve/{{ct_number}}"
CTIS_USER_AGENT = "we.are Techbio/0.1 (CTIS ingest; +https://github.com/alineorr1/Techbio)"
CTIS_REQUESTS_PER_SECOND = 2.0
RAW_SCHEMA_VERSION = "wave1.raw.v1"
SOURCE = "ctis"

# GET /search is rejected by the portal; never call it.
SEARCH_GET_RETURNS = 403


def feature_enabled(env: dict[str, str] | None = None) -> bool:
    raw = (env or os.environ).get(FEATURE_ENV, "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_status_map(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CTIS_STATUS_MAP_PATH).read_text())


def lookup_public_status_code(code: Any, *, field: str) -> dict[str, Any]:
    """Map a public status *code*. Strings (including retrieve.ctStatus) are unmapped."""
    spec = load_status_map()
    if not isinstance(code, int):
        return {
            "code": None,
            "field": field,
            "label": None,
            "universe": spec["unmapped_policy"],
            "mapped_status": None,
            "unmapped": True,
        }
    entry = spec["codes"].get(str(code))
    if not entry:
        return {
            "code": code,
            "field": field,
            "label": None,
            "universe": spec["unmapped_policy"],
            "mapped_status": None,
            "unmapped": True,
        }
    return {
        "code": code,
        "field": field,
        "label": entry["label"],
        "universe": entry["universe"],
        "mapped_status": entry.get("mapped_status"),
        "unmapped": False,
    }


def public_status_from_retrieve(payload: dict[str, Any]) -> dict[str, Any]:
    """W1-K2: use retrieve.ctPublicStatusCode only. Never the application-status string."""
    return lookup_public_status_code(payload.get("ctPublicStatusCode"), field="ctPublicStatusCode")


def public_status_from_search(row: dict[str, Any]) -> dict[str, Any]:
    """Search public status is the numeric ``ctStatus`` code, not a label string."""
    code = row.get("ctStatus")
    if not isinstance(code, int):
        code = None
    return lookup_public_status_code(code, field="search.ctStatus")


def make_raw_envelope(
    *,
    url: str,
    status: int,
    cached: bool,
    native_id: str,
    payload: dict[str, Any],
    fetched_at: str | None = None,
    match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "schema_version": RAW_SCHEMA_VERSION,
        "source": SOURCE,
        "fetched_at": fetched_at or utc_now(),
        "http": {"url": url, "status": status, "cached": cached},
        "native_id": native_id,
        "payload": payload,
        "public_status": public_status_from_retrieve(payload),
    }
    if match is not None:
        envelope["match"] = match
    return envelope


def search_query_hash(medical_condition: str) -> str:
    blob = json.dumps(
        {
            "medicalCondition": medical_condition,
            "sort": {"property": "decisionDate", "direction": "DESC"},
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _post_cache_body(json_body: dict[str, Any]) -> str:
    return json.dumps(json_body, sort_keys=True, separators=(",", ":"))


def write_search_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def condition_text_from_retrieve(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in nested(payload, "authorizedApplication", "authorizedPartI", "medicalConditions") or []:
        if isinstance(item, dict) and item.get("medicalCondition"):
            parts.append(str(item["medicalCondition"]))
    for item in (
        nested(
            payload,
            "authorizedApplication",
            "authorizedPartI",
            "trialDetails",
            "trialInformation",
            "medicalCondition",
            "partIMedicalConditions",
        )
        or []
    ):
        if isinstance(item, dict) and item.get("medicalCondition"):
            parts.append(str(item["medicalCondition"]))
    return " | ".join(parts)


def condition_text_from_search(row: dict[str, Any]) -> str:
    return str(row.get("conditions") or "")


def indication_entries(cfg: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    return (cfg or indications_config()).get("indications") or {}


def resolve_indication(condition: str, cfg: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    """Map a CLI --condition to (indication_key, synonym search terms). No YAML writes."""
    entries = indication_entries(cfg)
    needle = condition.strip().lower()
    for key, entry in entries.items():
        synonyms = [str(s) for s in (entry.get("synonyms") or [])]
        label = str(entry.get("label") or key)
        names = {key.lower(), label.lower(), *(s.lower() for s in synonyms)}
        if needle in names:
            return key, synonyms or [key]
    return condition.strip(), [condition.strip()]


def search_term_plan(
    condition: str | None,
    cfg: dict[str, Any] | None = None,
) -> list[tuple[str, str, list[str]]]:
    """Yield (indication_key, search_term, synonyms) from existing indications.yaml only."""
    entries = indication_entries(cfg)
    if condition:
        key, synonyms = resolve_indication(condition, cfg)
        return [(key, term, synonyms) for term in synonyms]
    plan: list[tuple[str, str, list[str]]] = []
    for key, entry in entries.items():
        synonyms = [str(s) for s in (entry.get("synonyms") or [])] or [key]
        for term in synonyms:
            plan.append((key, term, synonyms))
    return plan


def is_secondary_only_match(
    *,
    indication_key: str,
    synonyms: list[str],
    condition_text: str,
    hitting_terms: Iterable[str],
) -> bool:
    """True when the hit is only via a non-primary synonym (quarantine flag)."""
    primary = (synonyms[0] if synonyms else indication_key).lower()
    text = (condition_text or "").lower()
    if primary and primary in text:
        return False
    non_primary = {s.lower() for s in synonyms[1:]}
    hits = {t.lower() for t in hitting_terms}
    if non_primary & hits:
        return True
    return any(term in text for term in non_primary if term)


def make_ctis_http(*, cache_dir: Path | None = None) -> HttpClient:
    return HttpClient(
        requests_per_second=CTIS_REQUESTS_PER_SECOND,
        max_concurrency=2,
        cache_dir=cache_dir,
        user_agent=CTIS_USER_AGENT,
    )


class CtisClient:
    """CTIS search (POST) + retrieve (GET) via the shared rate-limited HttpClient."""

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def search_body(self, medical_condition: str, *, page: int, size: int) -> dict[str, Any]:
        return {
            "pagination": {"page": page, "size": size},
            "searchCriteria": {"medicalCondition": medical_condition},
            "sort": {"property": "decisionDate", "direction": "DESC"},
        }

    async def search_page(self, medical_condition: str, *, page: int = 1, size: int = 100) -> dict[str, Any]:
        body = self.search_body(medical_condition, page=page, size=size)
        return await self.http.post_json(CTIS_SEARCH, json_body=body)

    async def iter_search(
        self,
        medical_condition: str,
        *,
        page_size: int = 100,
        max_records: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        page = 1
        yielded = 0
        while True:
            body = self.search_body(medical_condition, page=page, size=page_size)
            cached = self.http.cache_get("POST", CTIS_SEARCH, _post_cache_body(body)) is not None
            data = await self.http.post_json(CTIS_SEARCH, json_body=body)
            rows = data.get("data") or []
            for row in rows:
                if max_records is not None and yielded >= max_records:
                    return
                item = dict(row)
                item["_http"] = {"url": CTIS_SEARCH, "status": 200, "cached": cached}
                yield item
                yielded += 1
            if max_records is not None and yielded >= max_records:
                return
            pagination = data.get("pagination") or {}
            if not rows or not pagination.get("nextPage"):
                return
            page += 1

    async def retrieve(self, ct_number: str) -> tuple[dict[str, Any], dict[str, Any]]:
        url = CTIS_RETRIEVE.format(ct_number=ct_number)
        cached = self.http.cache_get("GET", url) is not None
        payload = await self.http.get_json(url)
        meta = {"url": url, "status": 200, "cached": cached}
        return payload, meta


async def run_async(
    *,
    condition: str | None = None,
    max_records: int = 50,
    page_size: int = 100,
    write_identity: bool = True,
    raw_dir: Path | None = None,
    search_dir: Path | None = None,
    identity_dir: Path | None = None,
    http: HttpClient | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not feature_enabled():
        raise RuntimeError(f"CTIS ingest disabled ({FEATURE_ENV}=0). Feature-flagged; not in pipeline.")
    if WIRED_INTO_PIPELINE:
        raise RuntimeError("CTIS ingest must not be wired into src.pipeline")

    ensure_dirs()
    raw_dir = raw_dir or RAW_CTIS_DIR
    search_dir = search_dir or RAW_CTIS_SEARCH_DIR
    identity_dir = identity_dir or IDENTITY_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    search_dir.mkdir(parents=True, exist_ok=True)

    cfg = cfg or indications_config()
    plan = search_term_plan(condition, cfg)
    store = IdentityStore(identity_dir) if write_identity else None

    owns_http = http is None
    client_http = http or make_ctis_http()

    searched_terms: list[str] = []
    hits_by_ct: dict[str, dict[str, Any]] = {}
    secondary_only = 0
    retrieved = 0

    async def _run(active_http: HttpClient) -> None:
        nonlocal retrieved, secondary_only
        client = CtisClient(active_http)
        remaining = max_records
        for indication_key, term, synonyms in plan:
            if remaining is not None and remaining <= 0:
                break
            searched_terms.append(term)
            term_rows: list[dict[str, Any]] = []
            async for row in client.iter_search(term, page_size=page_size, max_records=remaining):
                ct_number = row.get("ctNumber")
                if not ct_number:
                    continue
                term_rows.append({k: v for k, v in row.items() if k != "_http"})
                bucket = hits_by_ct.setdefault(
                    ct_number,
                    {
                        "ct_number": ct_number,
                        "indication_key": indication_key,
                        "synonyms": synonyms,
                        "hitting_terms": [],
                        "search_row": row,
                    },
                )
                if term not in bucket["hitting_terms"]:
                    bucket["hitting_terms"].append(term)
            write_search_jsonl(search_dir / f"{search_query_hash(term)}.jsonl", term_rows)
            remaining = max_records - len(hits_by_ct)

        for ct_number, bucket in hits_by_ct.items():
            payload, meta = await client.retrieve(ct_number)
            retrieved += 1
            condition_text = condition_text_from_retrieve(payload) or condition_text_from_search(
                bucket["search_row"]
            )
            secondary = is_secondary_only_match(
                indication_key=bucket["indication_key"],
                synonyms=bucket["synonyms"],
                condition_text=condition_text,
                hitting_terms=bucket["hitting_terms"],
            )
            if secondary:
                secondary_only += 1
            match = {
                "indication_key": bucket["indication_key"],
                "search_terms": bucket["hitting_terms"],
                "secondary_only_match": secondary,
            }
            envelope = make_raw_envelope(
                url=meta["url"],
                status=int(meta["status"]),
                cached=bool(meta["cached"]),
                native_id=ct_number,
                payload=payload,
                match=match,
            )
            dump_json(raw_dir / f"{ct_number}.json", envelope)
            if store is not None:
                store.upsert(
                    identifiers_from_ctis_retrieve(payload),
                    source=SOURCE,
                    native_id=ct_number,
                    secondary_only_match=secondary,
                )

    if owns_http:
        async with client_http as active:
            await _run(active)
    else:
        await _run(client_http)

    summary = {
        "feature": "ctis_ingest",
        "wired_into_pipeline": WIRED_INTO_PIPELINE,
        "condition": condition,
        "searched_terms": searched_terms,
        "search_hits": len(hits_by_ct),
        "retrieved": retrieved,
        "envelopes": retrieved,
        "programmes": len(store.all()) if store is not None else 0,
        "secondary_only": secondary_only,
        "raw_dir": str(raw_dir),
        "identity_dir": str(identity_dir) if write_identity else None,
        "user_agent": CTIS_USER_AGENT,
        "requests_per_second": CTIS_REQUESTS_PER_SECOND,
    }
    print(
        f"[ctis] terms={len(searched_terms)} hits={len(hits_by_ct)} "
        f"retrieved={retrieved} secondary_only={secondary_only} "
        f"programmes={summary['programmes']}"
    )
    print(f"[ctis] envelopes at {raw_dir}")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wave-1 CTIS ingest (feature-flagged; not wired into src.pipeline)"
    )
    parser.add_argument(
        "--condition",
        help="Indication key, label, or synonym from config/indications.yaml (search terms only)",
    )
    parser.add_argument("--max", dest="max_records", type=int, default=50)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--no-identity", action="store_true", help="Skip programme_id writes")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = build_parser().parse_args(argv)
    return asyncio.run(
        run_async(
            condition=args.condition,
            max_records=args.max_records,
            page_size=args.page_size,
            write_identity=not args.no_identity,
        )
    )


if __name__ == "__main__":
    main()
