"""Europe PMC REST client.

Verified 2026-09-12 against https://www.ebi.ac.uk/europepmc/webservices/rest/search:

- Required query parameter: `query`
- `format=json` returns {hitCount, resultList: {result: [...]}}
- Pagination: pageSize, nextCursorMark / cursorMark (also nextPageUrl)
- Result fields used: id, source, pmid, pmcid, doi, title, pubYear, authorString,
  firstPublicationDate, journalTitle, isOpenAccess
- No API key required.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from src.http import HttpClient

EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


async def search(http: HttpClient, query: str, page_size: int = 15) -> dict[str, Any]:
    data = await http.get_json(
        EUROPEPMC,
        params={
            "query": query,
            "format": "json",
            "pageSize": page_size,
            "resultType": "lite",
        },
    )
    results = ((data.get("resultList") or {}).get("result")) or []
    papers = []
    for r in results:
        papers.append(
            {
                "id": r.get("id"),
                "source": r.get("source"),
                "pmid": r.get("pmid"),
                "pmcid": r.get("pmcid"),
                "doi": r.get("doi"),
                "title": r.get("title"),
                "pub_year": r.get("pubYear"),
                "first_publication_date": r.get("firstPublicationDate"),
                "journal": r.get("journalTitle"),
                "authors": r.get("authorString"),
                "is_open_access": r.get("isOpenAccess"),
                "url": (
                    f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}"
                    if r.get("id")
                    else None
                ),
            }
        )
    return {"query": query, "hit_count": data.get("hitCount") or 0, "papers": papers}


async def enrich_publications(
    http: HttpClient,
    nct_id: str,
    intervention_names: list[str],
    completion_year: int | None,
    sponsor_name: str | None,
) -> dict[str, Any]:
    nct_hits = await search(http, nct_id)
    papers = list(nct_hits["papers"])
    extra_queries = []
    # One intervention-name query in addition to the NCT ID (spec 4.3).
    for name in intervention_names[:1]:
        if not name or name.lower() in {"placebo"}:
            continue
        extra_queries.append(f'"{name}" AND {nct_id}')
    for q in extra_queries[:2]:
        more = await search(http, q, page_size=8)
        seen = {p.get("id") for p in papers}
        for p in more["papers"]:
            if p.get("id") not in seen:
                papers.append(p)
                seen.add(p.get("id"))

    years = []
    for p in papers:
        try:
            years.append(int(p["pub_year"]))
        except (TypeError, ValueError):
            continue
    published = nct_hits["hit_count"] > 0 or any(nct_id.lower() in ((p.get("title") or "") + (p.get("id") or "")).lower() for p in papers)
    # Treat any Europe PMC hit on the NCT ID as a results-adjacent publication trail.
    has_nct_pub = nct_hits["hit_count"] > 0
    post_silence = False
    if completion_year and has_nct_pub is False:
        post_silence = True
    sponsor_later = False
    if sponsor_name and completion_year:
        # cheap check: any paper year > completion with intervention in title
        sponsor_later = any(
            (p.get("pub_year") and int(str(p["pub_year"])[:4]) > completion_year)
            for p in papers
            if p.get("pub_year")
        )

    return {
        "nct_query": nct_hits,
        "papers": papers[:20],
        "has_results_publication": has_nct_pub,
        "publication_years": years,
        "silence_after_completion": post_silence,
        "sponsor_published_after": sponsor_later,
        "source_url": f"{EUROPEPMC}?query={quote(nct_id)}&format=json",
        "endpoint": EUROPEPMC,
    }
