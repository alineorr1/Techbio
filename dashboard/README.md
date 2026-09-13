# Dashboard

Static Vite + React + Tailwind + Recharts app. It has no backend.

It reads `public/data/snapshot.json`, which `python -m src.serve` writes from the scored corpus.

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 4177
```

Hash routes (no server router):

| Route | View |
|---|---|
| `#/ranked` | Ranked asset list (default) |
| `#/asset/NCT…` | Asset detail: score breakdown, Rule A/B, population checklist, links |
| `#/landscape` | Corpus charts when `snapshot.landscape` is present |
| `#/weekly` | Top-20 / ±10pt moves when `snapshot.weekly` is present |

A smoke snapshot from the committed ClinicalTrials.gov cache is checked in at `public/data/snapshot.json` so Vercel has data without OpenAI. To regenerate after extract/classify/score:

```bash
python -m src.extract --force-mock   # or a real key; not required for the dashboard
python -m src.classify
python -m src.score
python -m src.serve
```

Chrome is the Oxman B&W lock: white ground, ink type, `we.are` wordmark, typographic diligence banner (`non-buy · rights-unknown · honest`). No wine/maroon header.

Deploy: repo-root `vercel.json` builds this directory. See the Operations section in the project README for secrets, weekly updates, and Vercel.
