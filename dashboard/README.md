# Dashboard

Static Vite + React + Tailwind + Recharts app. It has no backend.

It reads `public/data/snapshot.json`, which `python -m src.serve` writes from the scored corpus.

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 4177
```

Deploy: repo-root `vercel.json` builds this directory. See the Operations section in the project README for secrets, weekly updates, and Vercel.
