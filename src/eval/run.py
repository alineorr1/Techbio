"""Entry point: python -m src.eval.run  (no arguments, clean checkout)."""

from __future__ import annotations

import sys

from src.eval.harness import evaluate, persist_run, previous_run, print_report, regression_guard


def main(argv: list[str] | None = None) -> int:
    result = evaluate()
    print_report(result)
    prev = previous_run(result["prompt_version"])
    regressions = regression_guard(result, prev)
    path = persist_run(result)
    print(f"\nwrote {path}")
    if regressions:
        print("REGRESSION: field accuracy dropped by more than 3 percentage points vs previous run:")
        for line in regressions:
            print(f"  {line}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
