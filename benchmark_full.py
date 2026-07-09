"""Full exhaustive benchmark for QuestLine.

This script evaluates QuestLine against every valid 4-digit Bulls & Cows answer.

Rules assumed by QuestLine
--------------------------
- 4 distinct digits from 0-9
- leading zero allowed
- total answer space: 10P4 = 5040

Usage
-----
Run a fast smoke test first:

    python benchmark_full.py --limit 200

Run the full exhaustive benchmark:

    python benchmark_full.py

Show more frequent progress:

    python benchmark_full.py --progress-every 50

Save every solving route as well:

    python benchmark_full.py --routes

Output
------
By default, writes:

    benchmark_full_results.json

This file is meant to be local benchmark output. It is safe to keep it ignored
by .gitignore.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import time
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run QuestLine full exhaustive benchmark.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only test the first N answers. Useful for smoke tests.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="Print progress every N answers. Use 0 to disable progress output.",
    )
    parser.add_argument(
        "--output",
        default="benchmark_full_results.json",
        help="Output JSON file path.",
    )
    parser.add_argument(
        "--routes",
        action="store_true",
        help="Store every solving route in the JSON output. This makes the output larger.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable QuestLine feedback matrix cache. Mostly useful for debugging.",
    )
    return parser.parse_args()


def summarize(step_counts: list[int]) -> dict[str, Any]:
    total = len(step_counts)
    distribution = dict(sorted(Counter(step_counts).items()))
    return {
        "total_codes": total,
        "total_steps": sum(step_counts),
        "average_steps": sum(step_counts) / total if total else 0.0,
        "min_steps": min(step_counts) if step_counts else None,
        "max_steps": max(step_counts) if step_counts else None,
        "distribution": distribution,
        "le_2": sum(s <= 2 for s in step_counts),
        "le_3": sum(s <= 3 for s in step_counts),
        "le_4": sum(s <= 4 for s in step_counts),
        "le_5": sum(s <= 5 for s in step_counts),
        "le_6": sum(s <= 6 for s in step_counts),
        "ge_7": sum(s >= 7 for s in step_counts),
        "ge_8": sum(s >= 8 for s in step_counts),
    }


def fmt_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remain = seconds - minutes * 60
    return f"{minutes}m{remain:.0f}s"


def main() -> None:
    args = parse_args()

    print("Importing QuestLine...")
    import questline

    print("Starting QuestLine solver...")
    solver = questline.QuestLineSolver(use_cache=not args.no_cache, verbose=True)

    all_answers = list(questline.ALL_CODES)
    answers = all_answers[: args.limit] if args.limit is not None else all_answers

    expected_total = len(all_answers)
    print(f"Answer space: {expected_total} valid codes")
    print(f"Benchmark size: {len(answers)} codes")

    if args.limit is None:
        print("Mode: full exhaustive benchmark")
    else:
        print(f"Mode: limited smoke test, first {args.limit} codes")

    print()
    print("Running benchmark...")

    started = time.time()
    step_counts: list[int] = []
    results: list[dict[str, Any]] = []

    for index, answer in enumerate(answers, 1):
        route = solver.play_answer(answer)
        steps = len(route)
        step_counts.append(steps)

        row: dict[str, Any] = {
            "answer": answer,
            "steps": steps,
        }
        if args.routes:
            row["route"] = [
                {
                    "guess": guess,
                    "feedback": questline.fb_to_str(feedback),
                    "remaining": remaining,
                }
                for guess, feedback, remaining in route
            ]
        results.append(row)

        if args.progress_every and (index % args.progress_every == 0 or index == len(answers)):
            elapsed = time.time() - started
            rate = index / elapsed if elapsed > 0 else 0.0
            remaining_count = len(answers) - index
            eta = remaining_count / rate if rate > 0 else 0.0
            current = summarize(step_counts)
            print(
                f"{index:5d}/{len(answers)}  "
                f"avg={current['average_steps']:.4f}  "
                f"max={current['max_steps']}  "
                f"7+={current['ge_7']}  "
                f"elapsed={fmt_seconds(elapsed)}  "
                f"eta={fmt_seconds(eta)}"
            )

    elapsed = time.time() - started
    summary = summarize(step_counts)

    output = {
        "project": "QuestLine",
        "description": "A narrative-driven Bulls & Cows solver.",
        "variant": "4 digits, no repeated digits, leading zero allowed",
        "answer_space": "10P4 = 5040",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "summary": summary,
        "results": results,
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("Final summary")
    print("-------------")
    print(f"total_codes   : {summary['total_codes']}")
    print(f"total_steps   : {summary['total_steps']}")
    print(f"average_steps : {summary['average_steps']:.6f}")
    print(f"min_steps     : {summary['min_steps']}")
    print(f"max_steps     : {summary['max_steps']}")
    print(f"distribution  : {summary['distribution']}")
    print(f"<=2           : {summary['le_2']}")
    print(f"<=3           : {summary['le_3']}")
    print(f"<=4           : {summary['le_4']}")
    print(f"<=5           : {summary['le_5']}")
    print(f"<=6           : {summary['le_6']}")
    print(f"7+            : {summary['ge_7']}")
    print(f"8+            : {summary['ge_8']}")
    print(f"elapsed       : {fmt_seconds(elapsed)}")
    print(f"saved_to      : {output_path}")

    if summary["ge_8"] == 0:
        print()
        print("No 8+ step games found in this benchmark.")


if __name__ == "__main__":
    main()
