"""CTIS public-API ingest (Wave-1, feature-flagged).

Opt-in only: ``python -m src.ingest.ctis --condition endometriosis --max 50``.
Shelved expand: ``python -m src.ingest.ctis --max 400 --universe shelved``.
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

# Wave-1 feature flag: this module is ingest-only. Pipeline wiring is off.
# Phase-2 score wiring is a separate opt-in module (WH_CTIS_SCORE).
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

SHELVED_UNIVERSES = frozenset({"include", "include_review"})
UNIVERSE_MODES = frozenset({"all", "shelved"})
# Search-row fields that are public trial metadata (no contacts / sites).
SEARCH_ROW_KEEP = (
    "ctNumber",
    "ctStatus",
    "ctTitle",
    "shortTitle",
    "conditions",
    "trialPhase",
    "sponsor",
    "sponsorType",
    "product",
    "gender",
    "ageGroup",
    "totalNumberEnrolled",
    "primaryEndPoint",
    "resultsFirstReceived",
    "startDateEU",
    "endDateEU",
    "decisionDateOverall",
    "therapeuticAreas",
)
_PRODUCT_NAME_KEYS = (
    "productName",
    "inventedName",
    "tradeName",
    "substanceName",
    "activeSubstance",
)
_PII_KEY_FRAGMENTS = (
    "email",
    "phone",
    "telephone",
    "fax",
    "address",
    "street",
    "postal",
    "zipcode",
    "contact",
    "investigator",
    "firstname",
    "lastname",
    "fullname",
    "orcid",
)


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


def in_shelved_universe(status: dict[str, Any]) -> bool:
    return (not status.get("unmapped")) and status.get("universe") in SHELVED_UNIVERSES


def search_row_is_shelved(row: dict[str, Any]) -> bool:
    """True when search.ctStatus maps to include / include_review."""
    return in_shelved_universe(public_status_from_search(row))


def should_retrieve_search_row(row: dict[str, Any], universe: str) -> bool:
    if universe == "all":
        return True
    if universe == "shelved":
        return search_row_is_shelved(row)
    raise ValueError(f"unknown universe mode: {universe}")


def sanitize_search_row(row: dict[str, Any]) -> dict[str, Any]:
    """Keep public trial metadata only. Drop contacts / sites / country lists."""
    return {key: row[key] for key in SEARCH_ROW_KEEP if key in row and row[key] not in (None, "")}


def _looks_like_pii_key(key: str) -> bool:
    lowered = key.lower().replace("_", "")
    return any(frag in lowered for frag in _PII_KEY_FRAGMENTS)


def _collect_named_products(node: Any, found: list[str] | None = None) -> list[str]:
    out = found if found is not None else []
    if isinstance(node, dict):
        for key, val in node.items():
            if _looks_like_pii_key(str(key)):
                continue
            if key in _PRODUCT_NAME_KEYS and isinstance(val, str) and val.strip():
                out.append(val.strip())
            else:
                _collect_named_products(val, out)
    elif isinstance(node, list):
        for item in node:
            _collect_named_products(item, out)
    return out


def _condition_items(items: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return out
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or not item.get("medicalCondition"):
            continue
        label = str(item["medicalCondition"])
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "medicalCondition": label,
                "isConditionRareDisease": bool(item.get("isConditionRareDisease")),
            }
        )
    return out


def _sponsor_items(payload: dict[str, Any]) -> list[dict[str, str]]:
    part_i = nested(payload, "authorizedApplication", "authorizedPartI") or {}
    names: list[str] = []
    for item in part_i.get("sponsors") or []:
        if isinstance(item, dict):
            for key in ("sponsorName", "organisationName", "commercialName", "legalName"):
                if item.get(key):
                    names.append(str(item[key]))
                    break
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"sponsorName": name})
    return out


def sanitize_retrieve_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip contacts, sites, investigators, events, documents. Keep identity + status."""
    part_i = nested(payload, "authorizedApplication", "authorizedPartI") or {}
    ident = (
        nested(
            part_i,
            "trialDetails",
            "clinicalTrialIdentifiers",
        )
        or {}
    )
    secondary = ident.get("secondaryIdentifyingNumbers") or {}
    nct_obj = secondary.get("nctNumber")
    nct_out: dict[str, Any] | None
    if isinstance(nct_obj, dict) and nct_obj.get("number"):
        nct_out = {"number": nct_obj.get("number")}
    elif isinstance(nct_obj, str) and nct_obj.strip():
        nct_out = {"number": nct_obj.strip()}
    else:
        nct_out = None

    additional: list[dict[str, Any]] = []
    extra = secondary.get("additionalRegistries") or []
    if isinstance(extra, dict):
        extra = [extra]
    for item in extra:
        if not isinstance(item, dict):
            continue
        kept = {
            key: item[key]
            for key in ("number", "registry", "name", "type", "label")
            if item.get(key)
        }
        if kept:
            additional.append(kept)

    conditions = _condition_items(part_i.get("medicalConditions"))
    if not conditions:
        conditions = _condition_items(
            nested(
                part_i,
                "trialDetails",
                "trialInformation",
                "medicalCondition",
                "partIMedicalConditions",
            )
        )
    products = [{"productName": name} for name in _collect_named_products(part_i)]
    eudra = nested(payload, "authorizedApplication", "eudraCt") or {}
    return {
        "ctNumber": payload.get("ctNumber"),
        "ctPublicStatusCode": payload.get("ctPublicStatusCode"),
        "startDateEU": payload.get("startDateEU"),
        "endDateEU": payload.get("endDateEU"),
        "decisionDate": payload.get("decisionDate"),
        "publishDate": payload.get("publishDate"),
        "trialPhase": payload.get("trialPhase"),
        "totalNumberEnrolled": payload.get("totalNumberEnrolled"),
        "authorizedApplication": {
            "eudraCt": {
                "eudraCtCode": eudra.get("eudraCtCode"),
                "isTransitioned": eudra.get("isTransitioned"),
            },
            "authorizedPartI": {
                "trialDetails": {
                    "clinicalTrialIdentifiers": {
                        "fullTitle": ident.get("fullTitle"),
                        "publicTitle": ident.get("publicTitle"),
                        "shortTitle": ident.get("shortTitle"),
                        "secondaryIdentifyingNumbers": {
                            "nctNumber": nct_out,
                            "additionalRegistries": additional,
                        },
                    },
                    "trialInformation": {
                        "medicalCondition": {"partIMedicalConditions": conditions}
                    },
                },
                "medicalConditions": conditions,
                "products": products,
                "sponsors": _sponsor_items(payload),
            },
        },
    }


def make_raw_envelope(
    *,
    url: str,
    status: int,
    cached: bool,
    native_id: str,
    payload: dict[str, Any],
    fetched_at: str | None = None,
    match: dict[str, Any] | None = None,
    search_row: dict[str, Any] | None = None,
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
    if search_row is not None:
        envelope["search_row"] = search_row
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


def unpaired_synonyms(entry: dict[str, Any]) -> set[str]:
    """Synonyms that require a paired term (CTG Essie only — skip for CTIS search)."""
    required = entry.get("require_paired_terms") or {}
    return {str(term) for term in required}


def search_term_plan(
    condition: str | None,
    cfg: dict[str, Any] | None = None,
    *,
    skip_unpaired: bool = False,
) -> list[tuple[str, str, list[str]]]:
    """Yield (indication_key, search_term, synonyms) from existing indications.yaml only."""
    entries = indication_entries(cfg)
    if condition:
        key, synonyms = resolve_indication(condition, cfg)
        skip = unpaired_synonyms(entries.get(key) or {}) if skip_unpaired else set()
        return [(key, term, synonyms) for term in synonyms if term not in skip]
    plan: list[tuple[str, str, list[str]]] = []
    for key, entry in entries.items():
        synonyms = [str(s) for s in (entry.get("synonyms") or [])] or [key]
        skip = unpaired_synonyms(entry) if skip_unpaired else set()
        for term in synonyms:
            if term in skip:
                continue
            plan.append((key, term, synonyms))
    return plan


def indication_search_budgets(
    plan: list[tuple[str, str, list[str]]],
    max_records: int,
) -> dict[str, int]:
    """Split the unique-hit cap across indication keys so PCOS is not starved."""
    keys: list[str] = []
    for key, _, _ in plan:
        if key not in keys:
            keys.append(key)
    if not keys:
        return {}
    if len(keys) == 1:
        return {keys[0]: max_records}
    base, extra = divmod(max_records, len(keys))
    return {key: base + (1 if i < extra else 0) for i, key in enumerate(keys)}


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
    universe: str = "all",
    sanitize: bool = True,
    skip_existing: bool = True,
    skip_unpaired: bool = False,
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
    if universe not in UNIVERSE_MODES:
        raise ValueError(f"universe must be one of {sorted(UNIVERSE_MODES)}")

    ensure_dirs()
    raw_dir = raw_dir or RAW_CTIS_DIR
    search_dir = search_dir or RAW_CTIS_SEARCH_DIR
    identity_dir = identity_dir or IDENTITY_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    search_dir.mkdir(parents=True, exist_ok=True)

    cfg = cfg or indications_config()
    plan = search_term_plan(condition, cfg, skip_unpaired=skip_unpaired)
    budgets = indication_search_budgets(plan, max_records)
    store = IdentityStore(identity_dir) if write_identity else None

    owns_http = http is None
    client_http = http or make_ctis_http()

    searched_terms: list[str] = []
    hits_by_ct: dict[str, dict[str, Any]] = {}
    new_hits_by_indication: dict[str, int] = {key: 0 for key in budgets}
    secondary_only = 0
    retrieved = 0
    skipped_existing = 0
    skipped_universe = 0

    async def _run(active_http: HttpClient) -> None:
        nonlocal retrieved, secondary_only, skipped_existing, skipped_universe
        client = CtisClient(active_http)
        for indication_key, term, synonyms in plan:
            remaining_for_ind = budgets.get(indication_key, 0) - new_hits_by_indication.get(
                indication_key, 0
            )
            if remaining_for_ind <= 0:
                continue
            searched_terms.append(term)
            term_rows: list[dict[str, Any]] = []
            async for row in client.iter_search(
                term, page_size=page_size, max_records=remaining_for_ind
            ):
                ct_number = row.get("ctNumber")
                if not ct_number:
                    continue
                clean_row = sanitize_search_row({k: v for k, v in row.items() if k != "_http"})
                if "ctStatus" in row and "ctStatus" not in clean_row:
                    clean_row["ctStatus"] = row["ctStatus"]
                term_rows.append(clean_row)
                if ct_number in hits_by_ct:
                    if term not in hits_by_ct[ct_number]["hitting_terms"]:
                        hits_by_ct[ct_number]["hitting_terms"].append(term)
                    continue
                hits_by_ct[ct_number] = {
                    "ct_number": ct_number,
                    "indication_key": indication_key,
                    "synonyms": synonyms,
                    "hitting_terms": [term],
                    "search_row": {**row, **clean_row},
                }
                new_hits_by_indication[indication_key] = new_hits_by_indication.get(indication_key, 0) + 1
                if new_hits_by_indication[indication_key] >= budgets.get(indication_key, 0):
                    break
            write_search_jsonl(search_dir / f"{search_query_hash(term)}.jsonl", term_rows)

        for ct_number, bucket in hits_by_ct.items():
            search_row = bucket["search_row"]
            if not should_retrieve_search_row(search_row, universe):
                skipped_universe += 1
                continue
            dest = raw_dir / f"{ct_number}.json"
            if skip_existing and dest.exists():
                skipped_existing += 1
                continue
            payload, meta = await client.retrieve(ct_number)
            if sanitize:
                payload = sanitize_retrieve_payload(payload)
            retrieved += 1
            condition_text = condition_text_from_retrieve(payload) or condition_text_from_search(
                search_row
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
                search_row=sanitize_search_row(search_row),
            )
            dump_json(dest, envelope)
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

    n_raw_on_disk = len([p for p in raw_dir.glob("*.json") if not p.name.startswith("_")])
    summary = {
        "feature": "ctis_ingest",
        "wired_into_pipeline": WIRED_INTO_PIPELINE,
        "condition": condition,
        "universe": universe,
        "sanitize": sanitize,
        "skip_existing": skip_existing,
        "skip_unpaired": skip_unpaired,
        "searched_terms": searched_terms,
        "indication_budgets": budgets,
        "search_hits": len(hits_by_ct),
        "search_hits_by_indication": dict(new_hits_by_indication),
        "n_shelved_candidates": len(hits_by_ct) - skipped_universe,
        "skipped_universe": skipped_universe,
        "skipped_existing": skipped_existing,
        "retrieved": retrieved,
        "envelopes": retrieved,
        "n_raw_on_disk": n_raw_on_disk,
        "programmes": len(store.all()) if store is not None else 0,
        "secondary_only": secondary_only,
        "raw_dir": str(raw_dir),
        "identity_dir": str(identity_dir) if write_identity else None,
        "user_agent": CTIS_USER_AGENT,
        "requests_per_second": CTIS_REQUESTS_PER_SECOND,
    }
    print(
        f"[ctis] terms={len(searched_terms)} hits={len(hits_by_ct)} "
        f"universe={universe} skipped_universe={skipped_universe} "
        f"retrieved={retrieved} skipped_existing={skipped_existing} "
        f"secondary_only={secondary_only} programmes={summary['programmes']}"
    )
    print(f"[ctis] envelopes at {raw_dir} n_raw_on_disk={n_raw_on_disk}")
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
    parser.add_argument(
        "--universe",
        choices=sorted(UNIVERSE_MODES),
        default="all",
        help="all=retrieve every search hit; shelved=include/include_review only",
    )
    parser.add_argument(
        "--no-sanitize",
        action="store_true",
        help="Write full retrieve payloads (default strips contacts/sites/PII)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-retrieve even when data/raw/ctis/{ctNumber}.json already exists",
    )
    parser.add_argument(
        "--skip-unpaired",
        action="store_true",
        help="Skip require_paired_terms synonyms (e.g. hyperandrogenism without anovulation)",
    )
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
            universe=args.universe,
            sanitize=not args.no_sanitize,
            skip_existing=not args.overwrite,
            skip_unpaired=args.skip_unpaired,
        )
    )


if __name__ == "__main__":
    main()
