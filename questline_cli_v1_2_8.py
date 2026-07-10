"""QuestLine CLI v1.2.8

Final v1.2 lightweight-loading polish.

This file is a thin patched wrapper over `questline_cli_v1_2_7.py`.
Keep `questline_cli_v1_2_7.py` in the same project directory.

v1.2.8 fixes two unnecessary feedback-matrix loading cases:

1. Round 2 / opening display no longer calls `unique_answer()` unless the
   remaining possible answer count is already 1.
2. Saving a jackpot or solved replay no longer calls `unique_answer()` and does
   not load the feedback matrix just to compute replay metadata.

All v1.2.7 behavior is preserved:
- strict 2/3/6 digit input grammar
- duplicate guess conflict checks
- consistency check before accepting any input, including 4b0c
- logical-solved state
- post-logic probing
- replay JSON fields
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import questline_cli_v1_2_7 as base
except ModuleNotFoundError as exc:
    raise SystemExit(
        "questline_cli_v1_2_8.py requires questline_cli_v1_2_7.py in the same directory. "
        "Please upload both files together."
    ) from exc

History = List[Tuple[str, Tuple[int, int]]]
ReplayRows = List[Dict[str, Any]]


def _logic_answer_for_replay(history: History, replay: ReplayRows, solved: bool, final_answer: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    """Compute logical_answer/logical_solved_at_round without loading the matrix.

    For saved replays, the game is normally solved. If a row has remaining_after == 1,
    the logical answer must be the final answer. This avoids calling filter_candidates()
    during replay saving, which is the source of the unwanted cache load in v1.2.7.
    """
    if not replay:
        return None, None

    for row in replay:
        if row.get("remaining_after") == 1:
            logical_round = int(row.get("round", 0)) or None
            # If the row itself is 4b0c, the row's guess is directly the answer.
            if row.get("feedback") == "4b0c":
                return str(row.get("guess")), logical_round
            # In solved replay saving, the final answer is already known.
            if solved and final_answer:
                return final_answer, logical_round
            return None, logical_round
    return None, None


def save_replay(history: History, replay: ReplayRows, solver: Any, jackpot: bool, lang: str) -> Path:
    """Patched replay saver that avoids unnecessary matrix loading.

    Unlike v1.2.7, this function does not call base.unique_answer() while saving.
    This prevents a one-guess jackpot replay from loading the feedback matrix just
    to write logical metadata.
    """
    path = Path(f"questline_replay_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    solved = bool(history and history[-1][1] == (4, 0))
    final_answer = history[-1][0] if solved else None
    logical_answer, logical_round = _logic_answer_for_replay(history, replay, solved, final_answer)
    verified_round = len(history) if solved else None
    verification_delay = max(0, verified_round - logical_round) if verified_round and logical_round else 0
    probe_count = sum(1 for row in replay if row.get("post_logic_probe"))

    data = {
        "project": "QuestLine",
        "saved_at": datetime.now().isoformat(),
        "ui_language": lang,
        "solved": solved,
        "jackpot": jackpot,
        "final_answer": final_answer,
        "rounds": len(history),
        "logical_answer": logical_answer,
        "logical_solved_at_round": logical_round,
        "verified_at_round": verified_round,
        "verification_delay_rounds": verification_delay,
        "post_logic_probe_count": probe_count,
        "history": replay,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_turn(solver: Any, history: History, result: Dict[str, Any], menu: List[Dict[str, Any]], lang: str) -> None:
    """Patched turn printer: only query unique answer when remaining == 1."""
    round_number = len(history) + 1
    rem = base.candidate_count(solver, history)
    print()
    print(base.tr(lang, "round", n=round_number))
    print(f"{base.tr(lang, 'next')}: {menu[0]['guess']}")
    if rem is not None:
        print(f"{base.tr(lang, 'remaining')}: {rem}")
        print(f"{base.tr(lang, 'direct_hit')}: {base.direct_hit(rem)}")
        if len(history) == 1:
            read = base.opening_read(rem, history[0][1], lang)
            if read:
                print(f"{base.tr(lang, 'opening_read')}: {read}")
        elif round_number >= 3:
            print(f"{base.tr(lang, 'pace')}: {base.pace(round_number, rem, lang)}")
    else:
        print(f"{base.tr(lang, 'remaining')}: {base.tr(lang, 'unknown')}")

    ans = base.unique_answer(solver, history) if rem == 1 else None
    if ans and not (history and history[-1][1] == (4, 0)):
        print(base.tr(lang, "logic_solved", answer=ans))
    print(f"{base.tr(lang, 'strategy')}: {base.strategy_state(result, lang)}")
    base.print_menu(menu, lang, round_number)


def print_report(solver: Any, history: History, lang: str, state: Any) -> None:
    """Patched report printer: only query unique answer when remaining == 1."""
    result = base.get_result(solver, history, lang, state, top_k=12)
    if result is None:
        return
    print(f"\n[{base.tr(lang, 'report_title')}]")
    base.print_history(history, lang)
    rem = base.candidate_count(solver, history)
    if rem is not None:
        print(f"{base.tr(lang, 'remaining')}: {rem}")
        print(f"{base.tr(lang, 'direct_hit')}: {base.direct_hit(rem)}")
    ans = base.unique_answer(solver, history) if rem == 1 else None
    if ans:
        print(base.tr(lang, "logic_solved", answer=ans))
    anchor = result.get("avg_anchor")
    if anchor:
        print(f"AVG: {anchor['guess']} exp={anchor['exp']:.3f} max={anchor['max']} buckets={anchor['bucket_count']}")
    menu = base.build_menu(solver, result, history)
    base.print_menu(menu, lang, len(history) + 1)
    candidates = result.get("candidates") or []
    if candidates and len(candidates) <= 20:
        print(f"\n{base.tr(lang, 'candidates')}")
        for code in candidates:
            print(f"  {code}")


def main(argv: Optional[Sequence[str]] = None) -> None:
    # Monkey-patch the v1.2.7 module so game_loop/solved_flow use the fixed functions.
    base.save_replay = save_replay
    base.print_turn = print_turn
    base.print_report = print_report

    parser = argparse.ArgumentParser(description="QuestLine interactive CLI v1.2.8")
    parser.add_argument("--lang", choices=["zh", "en"], default=None)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    lang = args.lang or base.choose_language("zh")
    base.print_welcome(lang)
    solver = base.questline.QuestLineSolver(verbose=True)

    keep = True
    while keep:
        keep = base.game_loop(lang, solver, debug=args.debug)
    print(base.tr(lang, "bye"))


if __name__ == "__main__":
    main()
