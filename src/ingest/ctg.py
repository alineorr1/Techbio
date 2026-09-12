"""ClinicalTrials.gov v2 client.

Verified 2026-09-12 against https://clinicaltrials.gov/api/oas/v2 (OpenAPI 3.0.3, API 2.0.5):

- Base: https://clinicaltrials.gov/api/v2/studies
- query.cond: Essie expression (ConditionSearch)
- filter.overallStatus: comma-separated enum (TERMINATED, WITHDRAWN, SUSPENDED, UNKNOWN, COMPLETED, ...)
- filter.advanced: Essie (used here for StudyType + InterventionType)
- filter.ids: comma-separated NCT IDs
- countTotal, pageSize, pageToken, nextPageToken
- There is no filter.studyType parameter; study type is AREA[StudyType] in filter.advanced
- Full study JSON: protocolSection, derivedSection, hasResults

Store the complete raw JSON. Never discard the original.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator

from src.config import indication_synonym_query, indications_config
from src.http import HttpClient

CTG_STUDIES = "https://clinicaltrials.gov/api/v2/studies"
CTG_STUDY = "https://clinicaltrials.gov/api/v2/studies/{nct_id}"

STOPPED_STATUSES = frozenset({"TERMINATED", "WITHDRAWN", "SUSPENDED", "UNKNOWN"})


def _advanced_filter(cfg: dict[str, Any]) -> str:
    study_type = cfg.get("study_type") or "INTERVENTIONAL"
    types = cfg.get("intervention_types") or ["DRUG"]
    type_clause = " OR ".join(f"AREA[InterventionType]{t}" for t in types)
    return f"AREA[StudyType]{study_type} AND ({type_clause})"


def nested(d: dict[str, Any] | None, *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def nct_id_of(study: dict[str, Any]) -> str:
    return nested(study, "protocolSection", "identificationModule", "nctId") or ""


def last_update_of(study: dict[str, Any]) -> str | None:
    return nested(study, "protocolSection", "statusModule", "lastUpdatePostDateStruct", "date")


def overall_status_of(study: dict[str, Any]) -> str:
    return nested(study, "protocolSection", "statusModule", "overallStatus") or ""


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(value[: len(fmt) + 2] if fmt != "%Y-%m-%d" else value, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def years_since(value: str | None, today: date | None = None) -> float | None:
    dt = parse_date(value)
    if not dt:
        return None
    today = today or date.today()
    return (today - dt).days / 365.25


def in_stopped_universe(study: dict[str, Any], cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or indications_config()
    sex = (nested(study, "protocolSection", "eligibilityModule", "sex") or "").upper()
    if sex == "MALE":
        return False
    status = overall_status_of(study)
    nct = nct_id_of(study)
    always = set(cfg.get("always_include_ncts") or [])
    if nct in always:
        return True
    stopped = set(cfg.get("stopped_statuses") or STOPPED_STATUSES)
    if status in stopped:
        return True
    completed_cfg = cfg.get("completed_no_results") or {}
    if status == (completed_cfg.get("status") or "COMPLETED"):
        has_results = bool(study.get("hasResults"))
        min_years = float(completed_cfg.get("min_years_since_primary_completion") or 2)
        pcd = nested(study, "protocolSection", "statusModule", "primaryCompletionDateStruct", "date")
        age = years_since(pcd)
        if (not has_results) and age is not None and age >= min_years:
            return True
        # also use completion date if primary is missing
        if (not has_results) and age is None:
            cd = nested(study, "protocolSection", "statusModule", "completionDateStruct", "date")
            age2 = years_since(cd)
            if age2 is not None and age2 >= min_years:
                return True
    return False


class ClinicalTrialsClient:
    def __init__(self, http: HttpClient, cfg: dict[str, Any] | None = None) -> None:
        self.http = http
        self.cfg = cfg or indications_config()

    async def fetch_universe(
        self,
        *,
        since: str | None = None,
        max_records: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield full study records matching the config-driven query.

        `since` is a YYYY-MM-DD last-update lower bound (weekly incremental).
        """
        page_size = int(self.cfg.get("ingest", {}).get("page_size") or 100)
        cap = max_records if max_records is not None else int(self.cfg.get("ingest", {}).get("max_records") or 800)
        cond = indication_synonym_query(self.cfg)
        advanced = _advanced_filter(self.cfg)
        if since:
            advanced = f"({advanced}) AND AREA[LastUpdatePostDate]RANGE[{since}, MAX]"

        params: dict[str, Any] = {
            "query.cond": cond,
            "filter.advanced": advanced,
            "pageSize": page_size,
            "countTotal": "true",
        }
        yielded = 0
        total = None
        page_token = None
        while yielded < cap:
            if page_token:
                params["pageToken"] = page_token
            data = await self.http.get_json(CTG_STUDIES, params=params)
            if total is None:
                total = data.get("totalCount")
                print(f"[ingest] ClinicalTrials.gov v2 total matching query: {total}")
            studies = data.get("studies") or []
            if not studies:
                break
            for study in studies:
                if yielded >= cap:
                    break
                yield study
                yielded += 1
            page_token = data.get("nextPageToken")
            if not page_token:
                break
            params.pop("countTotal", None)

        # Sentinel NCT IDs (Organon guard counterexample etc.) plus golden-set IDs.
        seen_need = set(self.cfg.get("always_include_ncts") or [])
        from src.paths import GOLDEN_DIR

        labels = GOLDEN_DIR / "labels.jsonl"
        if labels.exists():
            import json as _json

            for line in labels.read_text().splitlines():
                if line.strip():
                    seen_need.add(_json.loads(line)["nct_id"])
        if seen_need:
            async for study in self.fetch_ids(sorted(seen_need)):
                yield study

    async def fetch_ids(self, nct_ids: list[str]) -> AsyncIterator[dict[str, Any]]:
        if not nct_ids:
            return
        # API: filter.ids is a comma-separated list, pageSize up to 1000
        chunk_size = 50
        for i in range(0, len(nct_ids), chunk_size):
            chunk = nct_ids[i : i + chunk_size]
            params = {
                "filter.ids": ",".join(chunk),
                "pageSize": len(chunk),
            }
            data = await self.http.get_json(CTG_STUDIES, params=params)
            got = {nct_id_of(s): s for s in (data.get("studies") or [])}
            missing = [n for n in chunk if n not in got]
            for s in got.values():
                yield s
            # fallback per-id
            for nct in missing:
                try:
                    one = await self.http.get_json(CTG_STUDY.format(nct_id=nct))
                    if isinstance(one, dict) and nested(one, "protocolSection"):
                        yield one
                    elif isinstance(one, dict) and one.get("studies"):
                        yield one["studies"][0]
                except Exception as exc:  # noqa: BLE001
                    print(f"[ingest] failed to fetch {nct}: {exc}")


def flatten_study_text(study: dict[str, Any]) -> str:
    """Canonical text the extractor sees. stop_reason_evidence must be a substring of this."""
    p = study.get("protocolSection") or {}
    ident = p.get("identificationModule") or {}
    status = p.get("statusModule") or {}
    desc = p.get("descriptionModule") or {}
    cond = p.get("conditionsModule") or {}
    design = p.get("designModule") or {}
    arms = p.get("armsInterventionsModule") or {}
    outcomes = p.get("outcomesModule") or {}
    elig = p.get("eligibilityModule") or {}
    sponsor = p.get("sponsorCollaboratorsModule") or {}
    lines: list[str] = []

    def add(label: str, value: Any) -> None:
        if value is None or value == "" or value == []:
            return
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value)
        lines.append(f"{label}: {value}")

    add("NCT ID", ident.get("nctId"))
    add("Brief title", ident.get("briefTitle"))
    add("Official title", ident.get("officialTitle"))
    add("Acronym", ident.get("acronym"))
    add("Overall status", status.get("overallStatus"))
    add("Why stopped", status.get("whyStopped"))
    add("Last known status", status.get("lastKnownStatus"))
    add("Start date", nested(status, "startDateStruct", "date"))
    add("Primary completion date", nested(status, "primaryCompletionDateStruct", "date"))
    add("Completion date", nested(status, "completionDateStruct", "date"))
    add("Last update", nested(status, "lastUpdatePostDateStruct", "date"))
    add("Has results", study.get("hasResults"))
    add("Phase", (design.get("phases") or ["NA"]))
    add("Study type", design.get("studyType"))
    add("Enrollment count", nested(design, "enrollmentInfo", "count"))
    add("Enrollment type", nested(design, "enrollmentInfo", "type"))
    add("Lead sponsor", nested(sponsor, "leadSponsor", "name"))
    add("Lead sponsor class", nested(sponsor, "leadSponsor", "class"))
    collabs = [c.get("name") for c in (sponsor.get("collaborators") or []) if c.get("name")]
    add("Collaborators", collabs)
    add("Conditions", cond.get("conditions"))
    add("Keywords", cond.get("keywords"))
    add("Brief summary", desc.get("briefSummary"))
    add("Detailed description", desc.get("detailedDescription"))
    for i, arm in enumerate(arms.get("armGroups") or [], 1):
        add(f"Arm {i} label", arm.get("label"))
        add(f"Arm {i} type", arm.get("type"))
        add(f"Arm {i} description", arm.get("description"))
    for i, inter in enumerate(arms.get("interventions") or [], 1):
        add(f"Intervention {i} type", inter.get("type"))
        add(f"Intervention {i} name", inter.get("name"))
        add(f"Intervention {i} description", inter.get("description"))
        add(f"Intervention {i} other names", inter.get("otherNames"))
        add(f"Intervention {i} arm group labels", inter.get("armGroupLabels"))
    add("Sex", elig.get("sex"))
    add("Minimum age", elig.get("minimumAge"))
    add("Maximum age", elig.get("maximumAge"))
    add("Std ages", elig.get("stdAges"))
    add("Healthy volunteers", elig.get("healthyVolunteers"))
    add("Eligibility criteria", elig.get("eligibilityCriteria"))
    for i, oc in enumerate(outcomes.get("primaryOutcomes") or [], 1):
        add(f"Primary outcome {i} measure", oc.get("measure"))
        add(f"Primary outcome {i} description", oc.get("description"))
        add(f"Primary outcome {i} time frame", oc.get("timeFrame"))
    for i, oc in enumerate(outcomes.get("secondaryOutcomes") or [], 1):
        add(f"Secondary outcome {i} measure", oc.get("measure"))
        add(f"Secondary outcome {i} description", oc.get("description"))
    # Results module if present (OG-6219 etc.)
    results = study.get("resultsSection") or {}
    if results:
        lines.append("RESULTS SECTION PRESENT: true")
        for drop in (results.get("moreInfoModule") or {}).get("limitationsAndCaveats") or []:
            if isinstance(drop, dict):
                add("Limitations and caveats", drop.get("description") or drop)
            else:
                add("Limitations and caveats", drop)
        lac = nested(results, "moreInfoModule", "limitationsAndCaveats", "description")
        add("Limitations and caveats", lac)
    return "\n".join(lines)


async def _unused_asyncio_marker() -> None:
    await asyncio.sleep(0)
