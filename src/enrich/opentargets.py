"""Open Targets Platform GraphQL client.

Verified 2026-09-12 against https://api.platform.opentargets.org/api/v4/graphql:

- Query.disease(efoId) accepts MONDO_ and EFO_ ids (EFO_0001065 resolves via Disease.dbXRefs;
  live disease records use MONDO_0005133 for endometriosis, MONDO_0008487 for PCOS).
- Disease.associatedTargets(BFilter, page) → rows { score, datatypeScores, datasourceScores, target }
- Target.evidences(efoIds, datasourceIds, size) includes publicationYear, publicationDate,
  evidenceDate, studyStartDate, drugFromSource, clinicalStage, datasourceId, datatypeId, score.
- Target.tractability { label, modality, value }
- Search entityNames: disease | target | drug
"""

from __future__ import annotations

from typing import Any

from src.config import indications_config
from src.http import HttpClient

OT_GQL = "https://api.platform.opentargets.org/api/v4/graphql"

ASSOC_Q = """
query Assoc($efoId: String!, $symbol: String) {
  disease(efoId: $efoId) {
    id
    name
    associatedTargets(BFilter: $symbol, page: {index: 0, size: 5}) {
      count
      rows {
        score
        datatypeScores { id score }
        datasourceScores { id score }
        target { id approvedSymbol }
      }
    }
  }
}
"""

TARGET_Q = """
query TargetEv($id: String!, $efoIds: [String!]!) {
  target(ensemblId: $id) {
    id
    approvedSymbol
    tractability { label modality value }
    associatedDiseases(page: {index: 0, size: 15}) {
      count
      rows {
        score
        datatypeScores { id score }
        disease { id name }
      }
    }
    evidences(efoIds: $efoIds, size: 25) {
      count
      rows {
        datasourceId
        datatypeId
        score
        publicationYear
        publicationDate
        evidenceDate
        studyStartDate
        drugFromSource
        clinicalStage
      }
    }
  }
}
"""

SEARCH_TARGET_Q = """
query SearchTarget($q: String!) {
  search(queryString: $q, entityNames: ["target"], page: {index: 0, size: 3}) {
    hits { id name entity }
  }
}
"""

KNOWN_DRUG_Q = """
query Known($id: String!, $efoIds: [String!]!) {
  target(ensemblId: $id) {
    id
    approvedSymbol
    evidences(efoIds: $efoIds, datasourceIds: ["known_drug", "chembl"], size: 20) {
      count
      rows {
        datasourceId
        datatypeId
        score
        drugFromSource
        clinicalStage
        publicationYear
      }
    }
  }
}
"""


def indication_ids() -> list[str]:
    cfg = indications_config()
    ids: list[str] = []
    for ind in cfg["indications"].values():
        ids.extend(ind.get("mondo_ids") or [])
        ids.extend(ind.get("related_mondo_ids") or [])
        ids.extend(ind.get("efo_ids") or [])
    # unique, MONDO first
    seen = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    return seen


async def ot_graphql(http: HttpClient, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = await http.post_json(OT_GQL, json_body={"query": query, "variables": variables})
    if payload.get("errors"):
        return {"data": None, "errors": payload["errors"]}
    return payload


async def resolve_target_id(http: HttpClient, gene_or_name: str) -> dict[str, str] | None:
    data = await ot_graphql(http, SEARCH_TARGET_Q, {"q": gene_or_name})
    hits = (((data.get("data") or {}).get("search") or {}).get("hits")) or []
    for h in hits:
        if h.get("entity") == "target" and h.get("id"):
            return {"id": h["id"], "name": h.get("name") or gene_or_name}
    return None


async def enrich_targets(
    http: HttpClient,
    targets: list[dict[str, Any]],
    trial_start: str | None = None,
) -> dict[str, Any]:
    efo_ids = indication_ids()
    per_target: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []
    best_overall = None
    best_genetic = 0.0
    literature_only = True
    known_drugs: list[dict[str, Any]] = []
    advanced_elsewhere = False
    sources: list[dict[str, str]] = []

    # Never query Open Targets with an inferred gene. Only named gene symbols
    # from the record (extraction refuses to invent these) are resolved.
    symbols = []
    for t in targets:
        if t.get("gene_symbol"):
            symbols.append(t["gene_symbol"])

    for symbol in symbols[:5]:
        resolved = await resolve_target_id(http, symbol)
        assoc_rows = []
        for efo in efo_ids[:4]:
            assoc = await ot_graphql(http, ASSOC_Q, {"efoId": efo, "symbol": (resolved or {}).get("name") or symbol})
            disease = ((assoc.get("data") or {}).get("disease")) or {}
            rows = ((disease.get("associatedTargets") or {}).get("rows")) or []
            if rows:
                assoc_rows = rows
                sources.append(
                    {
                        "label": f"Open Targets association {disease.get('name')}–{symbol}",
                        "url": f"https://platform.opentargets.org/disease/{disease.get('id')}",
                    }
                )
                break
        overall = assoc_rows[0]["score"] if assoc_rows else None
        genetic = 0.0
        dts = (assoc_rows[0].get("datatypeScores") if assoc_rows else None) or []
        ds_ids = {d.get("id"): d.get("score") for d in dts}
        genetic = float(ds_ids.get("genetic_association") or ds_ids.get("somatic_mutation") or 0.0)
        if ds_ids and set(ds_ids) - {"literature", "text_mining"}:
            literature_only = False
        if overall is not None:
            best_overall = overall if best_overall is None else max(best_overall, overall)
        best_genetic = max(best_genetic, genetic)

        ensembl = (resolved or {}).get("id") or (assoc_rows[0]["target"]["id"] if assoc_rows else None)
        tractability = []
        safety = []
        if ensembl:
            td = await ot_graphql(http, TARGET_Q, {"id": ensembl, "efoIds": efo_ids[:3]})
            tgt = ((td.get("data") or {}).get("target")) or {}
            tractability = tgt.get("tractability") or []
            ev_rows = ((tgt.get("evidences") or {}).get("rows")) or []
            for ev in ev_rows:
                item = {
                    "target": tgt.get("approvedSymbol") or symbol,
                    "datasource_id": ev.get("datasourceId"),
                    "datatype_id": ev.get("datatypeId"),
                    "score": ev.get("score"),
                    "publication_year": ev.get("publicationYear"),
                    "publication_date": ev.get("publicationDate"),
                    "evidence_date": ev.get("evidenceDate"),
                    "study_start_date": ev.get("studyStartDate"),
                    "drug_from_source": ev.get("drugFromSource"),
                    "clinical_stage": ev.get("clinicalStage"),
                    "source_url": f"https://platform.opentargets.org/target/{ensembl}",
                }
                evidence_items.append(item)
                if ev.get("datatypeId") not in {None, "literature"}:
                    literature_only = False
            for row in ((tgt.get("associatedDiseases") or {}).get("rows")) or []:
                phasey = row.get("score") or 0
                name = ((row.get("disease") or {}).get("name") or "").lower()
                if phasey and phasey >= 0.2 and "endometri" not in name and "polycystic" not in name and "pcos" not in name:
                    advanced_elsewhere = True
            kd = await ot_graphql(http, KNOWN_DRUG_Q, {"id": ensembl, "efoIds": efo_ids[:3]})
            krows = ((((kd.get("data") or {}).get("target") or {}).get("evidences") or {}).get("rows")) or []
            for kr in krows:
                known_drugs.append(
                    {
                        "drug": kr.get("drugFromSource"),
                        "max_phase": kr.get("clinicalStage"),
                        "score": kr.get("score"),
                        "target": symbol,
                    }
                )
            sources.append(
                {
                    "label": f"Open Targets target {(resolved or {}).get('name') or symbol}",
                    "url": f"https://platform.opentargets.org/target/{ensembl}",
                }
            )
        per_target.append(
            {
                "query_symbol": symbol,
                "ensembl_id": ensembl,
                "overall_association_score": overall,
                "datatype_scores": ds_ids,
                "tractability": tractability,
                "safety_liabilities": safety,
            }
        )

    if not symbols:
        literature_only = False  # no named target: Organon guard still applies via empty evidence_items

    return {
        "overall_association_score": best_overall,
        "genetic_association_score": best_genetic,
        "literature_only": literature_only if evidence_items or best_overall else True,
        "known_drugs": known_drugs,
        "target_advanced_elsewhere": advanced_elsewhere,
        "per_target": per_target,
        "evidence_items": evidence_items,
        "sources": sources,
        "graphql_endpoint": OT_GQL,
        "disease_ids_queried": efo_ids,
    }
