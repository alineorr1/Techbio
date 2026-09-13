# Pilot pack (Ali D1 + Pharma Exec bar)

Unpaid mock extract only. No paid LLM. No public marketing. No MD-LIVE dashboard banner.
Desk vocabulary: TRIAGE / RIGHTS_QUEUE / OPP.

## Commands

```bash
python -m src.pilot.export --ncts NCT03481842,NCT04372121,NCT03411980 --out data/pilot/exports/
python -m src.pilot.export --ncts 2023-599001-99-00 --out data/pilot/ctis-eu-example/
python -m src.pilot.export --pack
```

## Filter rules (rights queue)

Source of truth: `config/rights-queue.json`.

1. **Locked WALK_AWAY** (Asset IP desk / kill-book) — not a fill item.
2. **Withdrawn** or **0-enrolment** — E3 walk-away stays locked.
3. **Modality / RLD disregard** — generic SOC (metformin, OCP, naltrexone, …), nutraceutical (fiber / inositol / vitamin), marketed class (Lunabell / Caronositol / Nexplanon / elagolix brands), imaging-only, blood-product / PRP.
4. Remaining **empty-stub / NOT OPTIONABLE** rows that survived those hard kills are sorted: industry single-grantor → thin biotech → TT named-asset → other.
5. **Cap ≤50** (floor 30 / ceiling 50) of RIGHTS_QUEUE before anything is handed to human fill. Overflow stays **RIGHTS_QUEUE** (never OPP); it is not the handoff set.

Auto-WALK does **not** loosen: empty→NOT OPTIONABLE; CONTINGENT needs citable IP; Intermezzo; REMS; Rule B.

Desk vocabulary: **TRIAGE** / **RIGHTS_QUEUE** / **OPP**. Empty-rights survivors (~514 on this corpus) are **RIGHTS_QUEUE**, never OPP. OPP is not invented from score.

## E7 CTIS EU example

See `data/pilot/ctis-eu-example/`. Regenerate scores (ephemeral derived files) with `python -m src.score.ctis --force-mock` then re-export the EU CT id. Snapshot.json is not rewritten.

## Kill-book

`data/pilot/kill-book.json` — locked WALK_AWAYs (BioGene, linzagolix, Viramal, BOL, …). Negative labels are product.

## D2 IC / D3 rollup

IC half-page branches by label + desk. Filled WALK_AWAY does **not** reuse empty-rights boilerplate. `data/pilot/d3-rollup.json` counts by T2 label and desk.
