"""E7: cheap EU CTIS shelved example (no 578-snapshot rewrite, unpaid mock only)."""

from __future__ import annotations

from typing import Any

from src.classify.rules import classify_record
from src.extract.llm import Extractor
from src.extract.schema import Extraction
from src.identity.programme import identifiers_from_ctis_retrieve, make_identity
from src.ingest.ctis_study import (
    ctis_to_study,
    envelope_payload,
    eu_ct_of,
    flatten_ctis_text,
    nct_ids_of,
    primary_display_id_of,
    public_status_of,
)
from src.db import load_json
from src.paths import RAW_CTIS_DIR
from src.rights.gates import NOT_OPTIONABLE, evaluate_pre_pass
from src.rights.schema import cmc_of, empty_rights, pathway_505b2_of
from src.rights.store import load_rights
from src.score.compute import score_asset

DEFAULT_EU_CT = "2023-599001-99-00"
REGEN_CMD = "python -m src.score.ctis --force-mock"


def load_ctis_envelope(eu_ct: str = DEFAULT_EU_CT) -> dict[str, Any]:
    path = RAW_CTIS_DIR / f"{eu_ct}.json"
    if not path.is_file():
        raise FileNotFoundError(f"CTIS raw envelope missing: {path}. Re-run `{REGEN_CMD}` if needed.")
    return load_json(path)


async def build_ctis_asset_in_memory(eu_ct: str = DEFAULT_EU_CT) -> dict[str, Any]:
    """Mock-extract + score one EU-only envelope. Does not write data/derived or snapshot.json."""
    envelope = load_ctis_envelope(eu_ct)
    payload = envelope_payload(envelope)
    ids = identifiers_from_ctis_retrieve(payload)
    identity = make_identity(ids, sources=["ctis"])
    pid = identity["programme_id"]
    display = primary_display_id_of(envelope) or eu_ct
    ncts = nct_ids_of(envelope)
    nct = ncts[0] if ncts else None
    study = ctis_to_study(envelope)
    extractor = Extractor(force_mock=True)
    try:
        ext = await extractor.extract(study, flatten_ctis_text(envelope))
    finally:
        extractor.close()
    ext_payload = ext.model_dump()
    ext_payload.update(
        {
            "nct_id": nct or ext_payload.get("nct_id") or "",
            "programme_id": pid,
            "primary_display_id": display,
            "eu_ct": eu_ct,
            "source": "ctis",
        }
    )
    extraction = Extraction.model_validate({k: v for k, v in ext_payload.items() if k in Extraction.model_fields})
    rights = load_rights(nct_id=nct, programme_id=pid) or empty_rights(pid, nct_id=nct, identity={
        "programme_id": pid,
        "nct_id": nct,
        "eu_ct": eu_ct,
    })
    enrich = {
        "nct_id": nct or "",
        "programme_id": pid,
        "primary_display_id": display,
        "source": "ctis",
        "eu_ct": eu_ct,
        "open_targets": {},
        "europepmc": {},
        "sponsor": {"status": "unknown"},
        "rights": {
            "schema_version": rights.get("schema_version"),
            "nct_id": nct,
            "programme_id": pid,
            "confidence": rights.get("confidence") or "empty_stub",
        },
    }
    clf = classify_record(study, extraction, enrich, rights=rights)
    scored = score_asset(study, extraction, clf, enrich, rights=rights)
    walk = list(clf.walk_away_codes or [])
    pre = scored.get("pre_pass") or evaluate_pre_pass(study=study, rights=rights, walk_away_codes=walk)
    ident = (study.get("protocolSection") or {}).get("identificationModule") or {}
    status = (study.get("protocolSection") or {}).get("statusModule") or {}
    public = public_status_of(envelope)
    return {
        "nct_id": nct or display,
        "programme_id": pid,
        "primary_display_id": display,
        "eu_ct": eu_ct,
        "source": "ctis",
        "brief_title": ident.get("briefTitle"),
        "official_title": ident.get("officialTitle"),
        "indication": "endometriosis",
        "indication_label": "Endometriosis",
        "overall_status": status.get("overallStatus") or public.get("mapped_status"),
        "why_stopped": status.get("whyStopped") or public.get("label"),
        "sponsor_name": ((study.get("protocolSection") or {}).get("sponsorCollaboratorsModule") or {}).get(
            "leadSponsor", {}
        ).get("name"),
        "sponsor_class": "OTHER",
        "sponsor_status": "unknown",
        "enrolment": ((study.get("protocolSection") or {}).get("designModule") or {}).get("enrollmentInfo"),
        "phase": ((study.get("protocolSection") or {}).get("designModule") or {}).get("phases") or ["PHASE2"],
        "interventions": [
            {"name": i.get("name"), "type": i.get("type")}
            for i in ((study.get("protocolSection") or {}).get("armsInterventionsModule") or {}).get("interventions")
            or []
        ],
        "extraction": ext_payload,
        "classification": clf.model_dump(),
        "score": scored,
        "rights": rights,
        "pre_pass": pre,
        "optionable": False,
        "shortlist_ownable": False,
        "gate_surface": pre.get("surface") or NOT_OPTIONABLE,
        "desk_classification": rights.get("desk_classification"),
        "cmc": cmc_of(rights),
        "pathway_505b2": pathway_505b2_of(rights),
        "ownability": {"surface": NOT_OPTIONABLE, "optionable": False, "md_status": pre.get("md_status")},
        "sources": {
            "registry_json": f"data/raw/ctis/{eu_ct}.json",
            "regen": REGEN_CMD,
        },
        "links": [
            {
                "label": "CTIS public record",
                "url": f"https://euclinicaltrials.eu/ctis-public-api/retrieve/{eu_ct}",
            }
        ],
    }


def regeneration_readme(eu_ct: str = DEFAULT_EU_CT) -> str:
    return (
        f"# CTIS EU pilot example (`{eu_ct}`)\n"
        "\n"
        "Cheap E7 path: one EU-only shelved CTIS programme as JSON+MD. "
        "Does **not** rewrite `dashboard/public/data/snapshot.json` (578 CTG assets).\n"
        "\n"
        "## Regenerate derived score (optional)\n"
        "\n"
        "Unpaid mock only — no OpenAI:\n"
        "\n"
        "```bash\n"
        f"{REGEN_CMD}\n"
        "python -m src.pilot.export --ncts "
        f"{eu_ct} --out data/pilot/ctis-eu-example/\n"
        "```\n"
        "\n"
        "Phase-2 score wire writes ephemeral `data/derived/{extract,enrich,classify,score,identity}/` "
        "and is **not** committed. The dossier in this folder is the committed proof.\n"
        "\n"
        "Empty rights → **NOT OPTIONABLE**. Not an OPP. High score ≠ buy.\n"
    )
