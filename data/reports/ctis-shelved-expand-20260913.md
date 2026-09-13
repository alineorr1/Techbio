# CTIS shelved expand — status memo (unpaid)

For Eng coordinator → CoS. Do **not** merge without CoS GO.

PR: https://github.com/alineorr1/Techbio/pull/13  
Base: `main` @ `f3bd534` (CTIS Phase-2 already merged).  
Run: 2026-09-13, unpaid public API + mock extract only.

## Counts (this checkout, `python -m src.score.ctis --force-mock`)

| metric | n |
| --- | --- |
| `n_raw` | 16 |
| `n_search_hits` (endo + PCOS synonyms) | 20 |
| `n_shelved_candidates` (include / include_review) | 4 |
| `n_shelved_scored` | 3 |
| `n_merged_to_nct` | 1 |
| `optionable` | 0 |

Search bound was `--max 400` (200 endo / 200 PCOS). CTIS returned **20 unique hits** — the public corpus for these synonyms is smaller than the 200–500 cap. Every hit was taken; recruiting / pending / not-authorised / recruitment-ended were **not** retrieved.

## Score wire dispositions

| EU CT | public status | disposition | note |
| --- | --- | --- | --- |
| `2022-501310-57-00` | Ended (8) | **merge_nct** | OG-6219 → `NCT05560646` (in committed CTG slice). Not second-scored. |
| `2023-599001-99-00` | Suspended (7) | score | EU-only fixture. Empty rights → **NOT OPTIONABLE**. |
| `2024-519126-20-00` | Ended (8) | score | `NCT04356664` not in committed CTG smoke slice; scored once. Empty rights → **NOT OPTIONABLE**. |
| `2024-518527-29-00` | Ended (8) | score | **New.** SPIOMET4HEALTH PCOS; `NCT05394142`. Empty rights → **NOT OPTIONABLE**. |
| `2024-520423-88-00` | Ended (8) | exclude | Imaging-only PET. |

No Temporarily halted / Expired / Revoked / Suspended rows in the live endo/PCOS search (fixture Suspended only). `optionable=0`.

## NCT merge / no double-score

- Merge key is `programme_id` union when the NCT is on disk under `data/raw/ctg/`.
- OG-6219 merges here.
- `NCT05394142` (SPIOMET) **is** in the private 578-asset snapshot, but the committed CTG smoke slice does not include `data/raw/ctg/NCT05394142.json`. On a full-corpus machine the same envelope **merges** and is not second-scored. This checkout scores it once as CTIS. Snapshot was **not** rewritten.

## What landed in git

- Sanitized new retrieve: `data/raw/ctis/2024-518527-29-00.json`
- Search JSONL + `data/raw/ctis/_search/expand_index.json` (20-hit reproduce set)
- Ingest flags: `--universe shelved`, sanitize, skip-existing, skip-unpaired, indication split
- This memo

**Not committed (ephemeral):** `data/derived/{extract,enrich,classify,score,identity}/`, empty rights stub for `NCT05394142`, `data/warehouse.duckdb`. Re-run `python -m src.score.ctis --force-mock` to regenerate.

## Untouched

- No OpenAI / paid LLM; spend-gate kill stays
- No MD banner
- No `dashboard/public/data/snapshot.json` rewrite (578 CTG corpus)
- No CT.gov industry mining
- No ICTRP commercial
- Pipeline / weekly still have no `ctis` string

## CoS ping line

CTIS shelved expand (unpaid): `n_raw=16` (was 15) / `n_search_hits=20` (API exhausted; bound 400) / `n_shelved_scored=3` / `n_merged_to_nct=1` / `optionable=0`. New PCOS Ended row `2024-518527-29-00` (SPIOMET). Awaiting CoS merge GO.
