"""Score stage: rank the entire universe. Re-runnable; writes per-asset JSON + warehouse."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from src.db import connect, dump_json, load_json, upsert
from src.extract.schema import Classification, Extraction
from src.paths import CLASSIFY_DIR, ENRICH_DIR, EXTRACT_DIR, RAW_CTG_DIR, SCORE_DIR, ensure_dirs
from src.rights.store import rights_for_nct
from src.score.compute import score_asset


def run(*, nct_ids: list[str] | None = None) -> dict[str, int]:
    ensure_dirs()
    want = set(nct_ids) if nct_ids else None
    n_ok = n_skip = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    con = connect()
    try:
        for path in sorted(RAW_CTG_DIR.glob("*.json")):
            nct = path.stem
            if want and nct not in want:
                continue
            if not (EXTRACT_DIR / f"{nct}.json").exists() or not (CLASSIFY_DIR / f"{nct}.json").exists():
                n_skip += 1
                continue
            study = load_json(path)
            extraction = Extraction.model_validate(load_json(EXTRACT_DIR / f"{nct}.json"))
            clf = Classification.model_validate(load_json(CLASSIFY_DIR / f"{nct}.json"))
            enrich = load_json(ENRICH_DIR / f"{nct}.json") if (ENRICH_DIR / f"{nct}.json").exists() else {}
            rights = enrich.get("rights_record") or rights_for_nct(nct)
            scored = score_asset(study, extraction, clf, enrich, rights=rights)
            dump_json(SCORE_DIR / f"{nct}.json", scored)
            upsert(con, "scores", nct, scored_at=now, score=scored["score"], payload_json=scored)
            n_ok += 1
        con.commit()
    finally:
        con.close()
    print(f"[score] wrote={n_ok} skipped={n_skip}")
    return {"ok": n_ok, "skipped": n_skip}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nct", action="append", dest="nct_ids")
    args = parser.parse_args(argv)
    run(nct_ids=args.nct_ids)


if __name__ == "__main__":
    main()
