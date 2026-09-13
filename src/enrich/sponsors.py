"""Sponsor-status lookup against the curated CSV (source URL per row).

Wave-1b: also emit structured sponsor_entity so enrich is not stuck on an
unstructured unknown name. Resolution is unknown | not_yet_fetched | resolved.
"""

from __future__ import annotations

from typing import Any

from src.classify.rules import match_sponsor
from src.rights.schema import SponsorEntity


def _lead_name(study: dict[str, Any]) -> str | None:
    lead = (
        ((study.get("protocolSection") or {}).get("sponsorCollaboratorsModule") or {})
        .get("leadSponsor") or {}
    )
    name = lead.get("name")
    return str(name) if name else None


def sponsor_entity_from_row(row: dict[str, Any] | None, *, lead_name: str | None) -> dict[str, Any]:
    """unknown = name but no legal match; resolved = CSV (or later OC) hit."""
    if not row:
        entity = SponsorEntity(
            name=lead_name,
            legal_name=None,
            resolution_status="unknown" if lead_name else "not_yet_fetched",
            source="unstructured_registry" if lead_name else "none",
        )
        return entity.model_dump()
    entity = SponsorEntity(
        name=row.get("matched_lead") or row.get("sponsor_name") or lead_name,
        legal_name=row.get("sponsor_name"),
        resolution_status="resolved",
        source="curated_csv",
    )
    return entity.model_dump()


def enrich_sponsor(study: dict[str, Any]) -> dict[str, Any]:
    row = match_sponsor(study)
    lead = _lead_name(study)
    entity = sponsor_entity_from_row(row, lead_name=lead)
    if not row:
        return {
            "status": "unknown",
            "sponsor_name": lead,
            "source_url": None,
            "notes": "Lead sponsor not in the curated CSV; do not infer solvency.",
            "sponsor_entity": entity,
        }
    return {
        "status": row.get("status") or "unknown",
        "sponsor_name": row.get("sponsor_name"),
        "matched_lead": row.get("matched_lead"),
        "as_of": row.get("as_of"),
        "source_url": row.get("source_url"),
        "notes": row.get("notes"),
        "sponsor_entity": entity,
    }
