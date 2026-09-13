# Women's Health Failed Asset Triage Engine

A pipeline and dashboard that finds **clinical-stage endometriosis and PCOS drug programmes that stopped for reasons other than the biology being wrong**, and ranks them as re-acquisition / re-development candidates.

The motivating problem: capital in women's health has clustered in academia and in late-stage de-risked commercial assets. A large number of clinically advanced programmes were shelved because a sponsor ran out of money, a trial under-recruited, a corporate strategy shifted, or a study was designed with a population so poorly defined that a real effect could not have been detected. Those failures are separable from "the mechanism does not work," and they are separable in public data.

The counterexample the scoring rules exist to catch: Organon acquired Forendo Pharma for an endometriosis HSD17B1 programme; that asset, **OG-6219, failed Phase 2 and was discontinued in 2025**. Acquiring overlooked science does not automatically create value. Rule B (the Organon guard) refuses to score an asset above 60 unless independent mechanism evidence **predates** the trial start date.

**Success criterion.** A domain expert opens the dashboard, clicks the top-ranked asset, and can trace every input that produced the score back to a primary source in under thirty seconds.

## Findings (population capture)

From a live ClinicalTrials.gov v2 ingest of **interventional DRUG/BIOLOGICAL** trials in endometriosis and PCOS (stopped, unknown, or completed with no results and primary completion more than two years ago):

- **551** scored assets in the dashboard snapshot (558 cached registry records; male-only studies are dropped at export). The query matched 870 interventional drug/biologic records; 248 active or recently-completed-with-results rows were excluded by the quiet-failure filter.
- Mean capture of the eight female-specific population variables: **42%**.
- Almost universal: age range (99%).
- Usually present: diagnosis method (72%).
- The holes that matter: disease severity / stage (**8%**), prior treatment history (**8%**), biomarker or molecular subtype (21%), menopausal status (42%), cycle-phase control (42%), hormonal contraception addressed (46%).

A trial that does not say whether it enrolled rASRM I or IV, or whether patients had failed a GnRH analogue, cannot have told you the biology failed. That is why stated efficacy plus two or fewer of these variables classifies as `efficacy_uninterpretable`.

See `notebooks/findings.ipynb` and `landscape.population_capture_rates` in the snapshot.

## Method

Six stages. No stage calls another stage. Each writes to disk and is independently re-runnable and idempotent.

```
ingest  →  extract  →  enrich  →  classify  →  score  →  serve
```

| Stage | What it does |
|---|---|
| **ingest** | ClinicalTrials.gov v2 (`/api/v2/studies`). Interventional DRUG/BIOLOGICAL. Indication synonyms from `config/indications.yaml`. Status in terminated/withdrawn/suspended/unknown, **or completed with no results and primary completion > 2 years ago**. Complete raw JSON cached under `data/raw/ctg/`. |
| **extract** | One call per record against `prompts/extraction_v1.md`. Output validated by Pydantic. `stop_reason_evidence` must be a **verbatim substring** of the input or the record is quarantined. No unnamed targets. If no LLM key is set, a deterministic extractor runs — still schema-valid, still verbatim-checked, still prompt-aware for eval. |
| **enrich** | Open Targets GraphQL (association, genetic evidence, known drugs, tractability; dates marked pre- vs post-trial) and Europe PMC (NCT ID + intervention name). Sponsor status from the curated CSV, each row with a source URL. |
| **classify** | Spec section 6 rules, **in order**: sponsor ceased while enrolling → recruitment <50% anticipated with no safety signal → stated efficacy + ≤2 female-specific variables (`efficacy_uninterpretable`) → stated efficacy with adequate stratification → any safety signal → unclear (surface for review). |
| **score** | 0–100 with four visible components (weights in `config/scoring.yaml`): mechanism 35, failure-mode 30, population (inverted) 20, accessibility 15. **Rule A:** safety failures capped at 25. **Rule B:** no score above 60 without pre-trial independent mechanism evidence. |
| **serve** | Versioned JSON snapshot. Dashboard reads it. No server required for the hosted preview. |

Weekly refresh (Monday 06:00 UTC when GitHub Actions is enabled, or `scripts/weekly.sh` locally) fetches registry records changed in the last ten days, extracts only NCT IDs whose derived JSON is stale, re-scores the universe, and writes `dashboard/public/data/snapshot.json` plus a change report (new entries in the top 20; score moves >10 points).

## How to run

Python 3.11+. Copy `.env.example` to `.env` if you have an `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. Without a key the corpus still runs on the deterministic extractor.

```bash
python -m pip install -e ".[dev]"

# Full pipeline (ClinicalTrials.gov + extract + enrich + classify + score + snapshot)
python -m src.pipeline

# Or stage by stage (each is independently re-runnable)
python -m src.ingest
python -m src.extract          # --force-mock to skip paid LLMs; --skip-existing for weekly
python -m src.enrich
python -m src.classify
python -m src.score
python -m src.serve

# Pilot pack (D2 IC half-page + D1 dossiers, capped rights queue, kill-book, D3 rollup). Unpaid; no snapshot rewrite.
python -m src.pilot.export --pack
python -m src.pilot.export --ncts NCT03481842,NCT04372121,NCT03411980 --out data/pilot/exports/

# Eval harness (no arguments; clean checkout)
python -m src.eval.run
python -m src.eval.selftest    # corrupts the prompt and asserts accuracy drops

pytest
```

Dashboard (local):

```bash
cd dashboard
npm install
npm run dev -- --host 0.0.0.0 --port 4177
```

The UI loads `dashboard/public/data/snapshot.json` (static; no API). Re-export after a pipeline run with `python -m src.serve`.

See **Operations** below for secrets, GitHub Actions, Vercel, and the weekly loop.

## Eval

Golden labels live in `data/golden/labels.jsonl`. Forty trials, twenty where a human (A. Rao, MD) judged the biology/drug failed and twenty where something else failed. Every row has `labelled_by` and a one-line `rationale`. The harness **refuses to run** if provenance is missing. Labels are not model-generated.

`python -m src.eval.run` prints per-field accuracy (stop reason, target overlap, each population boolean, endpoint appropriateness), a confusion matrix on `stop_reason_category` with the two decisive cells called out, a failure list with NCT ID + evidence string, and a regression guard against `data/eval/runs/`.

## Limitations

- **Registry data is self-reported and incomplete.** Why-stopped is frequently absent, euphemistic, or written by a sponsor with an interest in the wording. "Business reasons" can hide a scientific failure; "strategic" can hide insolvency. Classification combines the extracted reason with enrolment, sponsor status, and publication silence rather than trusting the field, but it cannot see inside a board deck.
- **A completed trial that never posted results is a quiet abandonment, not proof of either biology or operations.** We include those records because they are the ones most systems miss; the dashboard marks them as high-uncertainty when extraction fields are unresolved.
- **Open Targets association scores are not a measure of clinical viability.** They are an independent, pre-registered-style prior on target–disease linkage. Literature-only evidence is penalised because papers published after a failed trial are not independent of that trial.
- **This system ranks hypotheses for human review. It does not make investment recommendations.** A high score means "the public record is compatible with a non-biological failure and the mechanism had some independent support," not "buy this asset."
- **Sponsor status is a 20+ row curated CSV**, not a company-intelligence pipeline. Academic sponsors are listed as operating; that does not mean the PI still holds the IND.
- **The mock extractor used when no LLM key is present only copies text in the record.** It will miss pharmacology a reviewer would see in a paper. Re-run `src.extract` with a key to replace those rows; the cache is keyed on prompt+input+model so a real model does not collide with the mock.
- **Indication scope is endometriosis and PCOS only**, by design. Adding a third indication is a change to `config/indications.yaml`, not a refactor. Do not expand the query to "improve coverage."

## Operations

What you need for the system to **function**, **update every 7 days**, and **show the dashboard**. This repo's `origin` remote is currently Origin (`origin.cursor.com`), not GitHub. GitHub Actions cron will not fire until the same workflows exist on a GitHub remote with Actions enabled.

### What is already wired

| Piece | Status |
|---|---|
| Python pipeline (ingest → extract → enrich → classify → score → serve) | In the repo. Stages talk only via disk. |
| Deterministic mock extractor | Runs when no LLM key is set. Corpus already scored with it. |
| ClinicalTrials.gov v2, Open Targets, Europe PMC | No API keys. |
| Dashboard | Static Vite app. Reads `dashboard/public/data/snapshot.json`. |
| Snapshot export | `python -m src.serve` writes `data/snapshots/latest.json`, a versioned snapshot, a change report, **and** `dashboard/public/data/snapshot.json`. |
| Weekly workflow | `.github/workflows/weekly.yml` — Monday 06:00 UTC + `workflow_dispatch`. Incremental ingest (`--since` 10 days), `extract --skip-existing`, `enrich --skip-existing`, full classify + score, serve, artifact upload, bot commit of generated files. |
| Local weekly | `scripts/weekly.sh` (same stages). |
| CI | `.github/workflows/ci.yml` — pytest + eval + selftest on push. Same GitHub-remote caveat. |
| Vercel | Root `vercel.json` builds `dashboard/` (`npm run build --prefix dashboard`, output `dashboard/dist`). |

### Checklist — one-time setup (ordered)

1. **Python 3.11+.** `python -m pip install -e ".[dev]"`. Copy `.env.example` to `.env`.
2. **LLM key (optional for a first look, required for quality on new records).**
   - Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in `.env`.
   - Without a key, `python -m src.extract` uses the mock. Already-scored assets in git stay as they are.
   - With a key, re-run extract (no `--skip-existing`) to replace mock rows; the LLM cache is keyed on prompt + input + model so mock and paid calls do not collide.
3. **Dashboard locally.** `cd dashboard && npm i && npm run dev -- --host 0.0.0.0 --port 4177`. Open `http://127.0.0.1:4177`. You should see the ranked list from the committed snapshot — no extra secrets.
4. **See it on the web (Vercel).** Click **Publish** (or import the GitHub repo in Vercel). Framework: Vite. Root `vercel.json` already points at `dashboard/`. No Vercel env vars are required — the snapshot is static JSON. After deploy, the live URL is the dashboard.
5. **Weekly updates on a schedule — pick one:**
   - **GitHub Actions (automatic):** push this repo to GitHub (or add a GitHub remote), enable Actions, allow the default `GITHUB_TOKEN` to write to `main` (Settings → Actions → General → Workflow permissions → Read and write). Optionally add repo secrets `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`. The workflow is `.github/workflows/weekly.yml` (`cron: "0 6 * * 1"` plus Run workflow). On success it **commits** `dashboard/public/data/snapshot.json`, `data/snapshots/`, `data/reports/`, and any new/updated `data/raw/ctg` + `data/derived/{extract,enrich,classify,score}` files. It does **not** commit `.env`, `data/cache/`, or secrets. A Vercel project hooked to that GitHub repo rebuilds on the bot commit — that is how the hosted dashboard updates every Monday.
   - **Local cron (works on Origin-only remotes):** `chmod +x scripts/weekly.sh && ./scripts/weekly.sh`, then commit the generated snapshot (and derived files if new trials appeared) and push. Schedule it with cron/launchd if you want every 7 days without GitHub.
6. **Do not add keys for** ClinicalTrials.gov, Open Targets, or Europe PMC. They are public.

### Weekly loop (what actually runs)

```
ingest --since (today − 10 days)
  → extract --skip-existing     # only new/updated NCT JSON
  → enrich --skip-existing      # Open Targets + Europe PMC for those rows
  → classify                    # whole universe, local, cheap
  → score                       # whole universe, local, cheap
  → serve                       # snapshot JSON + change report → dashboard/public/data/
```

Without an LLM secret, extract of **new** records still runs the mock. Classify/score/serve do not need a key. Enrich does not need a key but hits the public APIs for cache misses only.

### How to view the dashboard

| Where | What you do |
|---|---|
| Local | `cd dashboard && npm i && npm run dev -- --host 0.0.0.0 --port 4177` → `http://127.0.0.1:4177` |
| After a pipeline run | `python -m src.serve` then refresh; Vite serves `public/data/snapshot.json` |
| Vercel | Publish / import; wait for the build. Ranked list, asset detail, landscape, weekly changes are hash routes (`#/ranked`, `#/asset/NCT…`, `#/landscape`, `#/weekly`). |
| After weekly | Bot commit (GitHub) or your commit (local script) of `dashboard/public/data/snapshot.json` → Vercel rebuild → ranks update. |

### Honest gaps

- **This Origin remote does not run GitHub Actions.** Cron is dormant until the workflow lives on GitHub with Actions enabled, or you run `scripts/weekly.sh` yourself.
- **Mock extract is not a pharmacologist.** New trials ingested without a key will have verbatim-only targets and weaker scores until you re-extract with a key.
- **Sponsor status is a curated CSV**, not live company intelligence.
- **Feedback** on asset detail is localStorage + clipboard JSONL; it does not POST to a server.
- **Vercel hosts the dashboard only.** It does not run the Python pipeline.

## Repository layout

See the tree in the spec: `config/`, `src/{ingest,extract,enrich,classify,score,eval,serve}/`, `prompts/`, `data/`, `dashboard/`, `.github/workflows/weekly.yml`, `scripts/weekly.sh`.
