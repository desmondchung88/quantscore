"""Run the whole pipeline: schema -> relational -> documents -> mirrors -> seed.

    python etl/run_all.py              # everything
    python etl/run_all.py --from 3     # resume at step 3
    python etl/run_all.py --only 2 4   # just those steps
"""
from __future__ import annotations

import argparse
import time

from common import banner

import step1_schema
import step2_relational
import step3_documents
import step4_benchmark
import step5_seed

STEPS = {
    1: ("Relational schema", step1_schema.main),
    2: ("Relational data load", step2_relational.main),
    3: ("Document store load", step3_documents.main),
    4: ("Benchmark mirrors", step4_benchmark.main),
    5: ("Demo seed", step5_seed.main),
}


def main() -> None:
    ap = argparse.ArgumentParser(description="QuantScore ETL")
    ap.add_argument("--from", dest="start", type=int, default=1,
                    help="first step to run (1-5)")
    ap.add_argument("--only", nargs="*", type=int, help="run only these steps")
    args = ap.parse_args()

    chosen = sorted(args.only) if args.only else [
        n for n in sorted(STEPS) if n >= args.start
    ]

    t0 = time.perf_counter()
    for n in chosen:
        if n not in STEPS:
            raise SystemExit(f"No such step: {n}")
        STEPS[n][1]()

    banner(f"PIPELINE COMPLETE in {time.perf_counter() - t0:.1f}s")
    print("  Start the API with:   python backend/run.py")
    print("  Start the UI with:    cd frontend && npm run dev")
    print()


if __name__ == "__main__":
    main()
