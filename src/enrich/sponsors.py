"""Sponsor-status lookup against the curated CSV (source URL per row)."""

from __future__ import annotations

from typing import Any

from src.classify.rules import match_sponsor


def enrich_sponsor(study: dict[str, Any]) -> dict[str, Any]:
    row = match_sponsor(study)
    if not row:
        lead = (
            ((study.get("protocolSection") or {}).get("sponsorCollaboratorsModule") or {})
            .get("leadSponsor") or {}
        )
        return {
            "status": "unknown",
            "sponsor_name": lead.get("name"),
            "source_url": None,
            "notes": "Lead sponsor not in the curated CSV; do not infer solvency.",
        }
    return {
        "status": row.get("status") or "unknown",
        "sponsor_name": row.get("sponsor_name"),
        "matched_lead": row.get("matched_lead"),
        "as_of": row.get("as_of"),
        "source_url": row.get("source_url"),
        "notes": row.get("notes"),
    }
