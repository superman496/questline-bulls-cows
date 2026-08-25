"""Evaluate QuestLine recommendations against the world-line model.

This benchmark measures observability only. It does not change recommendation
scoring or claim that the human opening heuristic is universally optimal.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import time
from typing import Any, Dict, List, Tuple


HUMAN_GROUPS = ("01", "23", "45", "67", "89")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate QuestLine world-line behavior.")
    parser.add_argument("--limit", type=int, default=None, help="Only evaluate the first N answers.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many answers before evaluating.")
    parser.add_argument("--progress-every", type=int, default=100, help="Print progress every N answers; 0 disables output.")
    parser.add_argument("--output", default="benchmark_worldline_results.json", help="JSON output path.")
    parser.add_argument("--markdown", default="benchmark_worldline_report.md", help="Markdown report path.")
    parser.add_argument("--no-cache", action="store_true", help="Disable feedback matrix cache.")
    return parser.parse_args()


def groups_for_guess(guess: str) -> List[str]:
    return [group for group in HUMAN_GROUPS if any(digit in group for digit in guess)]


def group_coverage(guess: str, groups: Tuple[str, ...]) -> int:
    return sum(any(digit in group for digit in guess) for group in groups)


def world_snapshot(solver: Any, history: List[Tuple[str, Tuple[int, int]]]) -> Dict[str, Any]:
    import questline

    candidates = solver.filter_candidates(history)
    if not candidates:
        return {"confidence": None, "groups": [], "support": 0.0}
    worlds = Counter(solver.fixed_signature(questline.ALL_CODES[index]) for index in candidates)
    ranked = sorted(worlds.items(), key=lambda item: (-item[1], item[0]))
    signature, count = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    support = count / len(candidates)
    lead = (count - runner_up) / len(candidates)
    return {
        "confidence": "tied" if sum(value == count for value in worlds.values()) > 1 else ("weak" if lead < 0.05 else "clear"),
        "groups": [name for name, amount in zip(questline.FIXED_GROUPS, signature) if amount],
        "support": support,
    }


def evaluate_route(questline: Any, solver: Any, answer: str) -> Dict[str, Any]:
    route = solver.play_answer(answer)
    history: List[Tuple[str, Tuple[int, int]]] = []
    rounds: List[Dict[str, Any]] = []
    for round_number, (guess, feedback, remaining) in enumerate(route, 1):
        history.append((guess, feedback))
        main = world_snapshot(solver, history)
        main_groups = tuple(main.get("groups", []))
        guess_groups = groups_for_guess(guess)
        rounds.append({
            "round": round_number,
            "guess": guess,
            "feedback": questline.fb_to_str(feedback),
            "remaining": remaining,
            "groups": guess_groups,
            "main_world_confidence": main.get("confidence"),
            "main_world_groups": list(main_groups),
            "main_world_support": main.get("support"),
            "main_world_aligned": bool(main_groups) and group_coverage(guess, main_groups) > 0,
            "introduces_45": "45" in guess_groups,
            "introduces_67": "67" in guess_groups,
            "opening_pattern_round_3": round_number == 3 and "67" in guess_groups and group_coverage(guess, ("01", "23", "45")) >= 2,
            "is_68_heavy": "6" in guess and "8" in guess,
        })
    return {"answer": answer, "steps": len(route), "rounds": rounds}


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    all_rounds = [row for result in results for row in result["rounds"]]
    by_round: Dict[str, Dict[str, Any]] = {}
    for round_number in range(1, max((row["round"] for row in all_rounds), default=0) + 1):
        rows = [row for row in all_rounds if row["round"] == round_number]
        by_round[str(round_number)] = {
            "games_reaching_round": len(rows),
            "introduces_45_rate": sum(row["introduces_45"] for row in rows) / len(rows) if rows else 0.0,
            "introduces_67_rate": sum(row["introduces_67"] for row in rows) / len(rows) if rows else 0.0,
            "human_round_3_pattern_rate": sum(row["opening_pattern_round_3"] for row in rows) / len(rows) if rows else 0.0,
            "main_world_alignment_rate": sum(row["main_world_aligned"] for row in rows) / len(rows) if rows else 0.0,
            "68_heavy_count": sum(row["is_68_heavy"] for row in rows),
            "68_heavy_rate": sum(row["is_68_heavy"] for row in rows) / len(rows) if rows else 0.0,
            "confidence": dict(Counter(row["main_world_confidence"] for row in rows)),
        }

    steps = [result["steps"] for result in results]
    all_guesses = [row["guess"] for row in all_rounds]
    group_counts = Counter(group for row in all_rounds for group in row["groups"])
    return {
        "total_answers": len(results),
        "average_steps": sum(steps) / len(steps) if steps else 0.0,
        "max_steps": max(steps) if steps else None,
        "total_guesses": len(all_rounds),
        "unique_guesses": len(set(all_guesses)),
        "group_frequency": dict(sorted(group_counts.items())),
        "68_heavy_total": sum("6" in guess and "8" in guess for guess in all_guesses),
        "68_heavy_rate": sum("6" in guess and "8" in guess for guess in all_guesses) / len(all_guesses) if all_guesses else 0.0,
        "by_round": by_round,
    }


def render_markdown(output: Dict[str, Any]) -> str:
    summary = output["summary"]
    lines = [
        "# QuestLine World-Line Evaluation",
        "",
        "> Observability benchmark only; recommendation scoring was not changed.",
        "",
        "## Overall",
        "",
        f"- Answers evaluated: **{summary['total_answers']}**",
        f"- Average steps: **{summary['average_steps']:.4f}**",
        f"- Maximum steps: **{summary['max_steps']}**",
        f"- Total guesses: **{summary['total_guesses']}**",
        f"- Unique guesses: **{summary['unique_guesses']}**",
        f"- 68-heavy guesses: **{summary['68_heavy_total']} ({summary['68_heavy_rate']:.2%})**",
        "",
        "## Group frequency",
        "",
        "| Group | Count |",
        "|---|---:|",
    ]
    for group, count in summary["group_frequency"].items():
        lines.append(f"| {group} | {count} |")
    lines += ["", "## By round", "", "| Round | Games | 45 rate | 67 rate | Human r3 pattern | Main-world aligned | 68-heavy |", "|---:|---:|---:|---:|---:|---:|---:|"]
    for round_number, row in summary["by_round"].items():
        lines.append(
            f"| {round_number} | {row['games_reaching_round']} | {row['introduces_45_rate']:.1%} | "
            f"{row['introduces_67_rate']:.1%} | {row['human_round_3_pattern_rate']:.1%} | "
            f"{row['main_world_alignment_rate']:.1%} | {row['68_heavy_rate']:.1%} |"
        )
    lines += ["", "## Interpretation", "", "- `45 rate` measures whether a guess uses at least one digit from group `45`.", "- `67 rate` measures whether a guess uses at least one digit from group `67`.", "- The human round-3 pattern requires group `67` plus coverage of at least two of `01`, `23`, and `45`.", "- Main-world alignment means the guess uses at least one digit from a currently strongest fixed group; it is not a quality judgment.", "- 68-heavy is a descriptive count, not evidence by itself that the strategy is wrong.", ""]
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    import questline

    solver = questline.QuestLineSolver(use_cache=not args.no_cache, verbose=True)
    all_answers = list(questline.ALL_CODES)
    start = max(0, args.offset)
    end = start + args.limit if args.limit is not None else len(all_answers)
    answers = all_answers[start:end]
    started = time.time()
    results: List[Dict[str, Any]] = []
    for index, answer in enumerate(answers, 1):
        results.append(evaluate_route(questline, solver, answer))
        if args.progress_every and (index % args.progress_every == 0 or index == len(answers)):
            print(f"{index}/{len(answers)} evaluated in {time.time() - started:.1f}s")

    output = {
        "project": "QuestLine",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation": "world-line observability",
        "offset": args.offset,
        "summary": summarize(results),
        "results": results,
    }
    Path(args.output).write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.markdown).write_text(render_markdown(output), encoding="utf-8")
    print(render_markdown(output))
    print(f"\nJSON saved to: {args.output}")
    print(f"Markdown saved to: {args.markdown}")


if __name__ == "__main__":
    main()
