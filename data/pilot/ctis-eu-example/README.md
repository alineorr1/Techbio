# CTIS EU pilot example (`2023-599001-99-00`)

Cheap E7 path: one EU-only shelved CTIS programme as JSON+MD. Does **not** rewrite `dashboard/public/data/snapshot.json` (578 CTG assets).

## Regenerate derived score (optional)

Unpaid mock only — no OpenAI:

```bash
python -m src.score.ctis --force-mock
python -m src.pilot.export --ncts 2023-599001-99-00 --out data/pilot/ctis-eu-example/
```

Phase-2 score wire writes ephemeral `data/derived/{extract,enrich,classify,score,identity}/` and is **not** committed. The dossier in this folder is the committed proof.

Empty rights → **NOT OPTIONABLE**. Not an OPP. High score ≠ buy.
