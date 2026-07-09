"""QuestLine CLI v1.2

An improved interactive interface for QuestLine.

This file intentionally imports the existing questline.py and does not change the
solver core. It focuses on play experience:

- bilingual UI: Chinese / English
- welcome screen and help menu
- multi-game loop: solved games do not exit the program
- inconsistent feedback recovery instead of traceback
- commands: undo, history, report, new, quit, help
- recommendation menu with quick selection
- feedback-only input applies to the current #1 recommendation
- selected recommendation input: "2 1b2c"
- manual external input: "3846 1b2c"
- optional replay JSON save after each solved game

Suggested usage:

    python questline_cli_v1_2.py --lang zh
    python questline_cli_v1_2.py --lang en

If you like this version, you can later replace examples/interactive_demo.py or
integrate the CLI loop back into questline.py.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import questline
except ModuleNotFoundError:
    ROOT = Path(__file__).resolve().parent
    sys.path.insert(0, str(ROOT))
    import questline

Code = str
Feedback = Tuple[int, int]
History = List[Tuple[Code, Feedback]]

FIRST_BRANCH_COUNTS: Dict[Feedback, int] = {
    (0, 0): 360,
    (0, 1): 1440,
    (0, 2): 1260,
    (0, 3): 264,
    (0, 4): 9,
    (1, 0): 480,
    (1, 1): 720,
    (1, 2): 216,
    (1, 3): 8,
    (2, 0): 180,
    (2, 1): 72,
    (2, 2): 6,
    (3, 0): 24,
    (4, 0): 1,
}

TEXT = {
    "en": {
        "title": "QuestLine",
        "subtitle": "A narrative-driven Bulls & Cows solver.",
        "slogan": "Follow the strongest story. Distrust coincidence.",
        "rules": "Rules: 4 distinct digits, leading zero allowed.",
        "feedback": "Feedback examples: 0b1c, 1b2c, 1a2b, 1,2, 12",
        "commands": "Commands: q/quit, new/restart, undo/back, history/h, report/r, help/?",
        "input_help": "Input: feedback only for #1, `2 1b2c` for menu pick, or `3846 1b2c` for manual guess.",
        "round": "Round",
        "next": "Default next guess",
        "remaining": "Remaining candidates",
        "pace": "Pace",
        "strategy": "Strategy",
        "recommendations": "Recommendations",
        "feedback_prompt": "Your input",
        "solved": "Solved",
        "solved_in": "Solved in {n} rounds.",
        "new_game_prompt": "Start a new game? [Y/n]",
        "save_prompt": "Save replay JSON? [y/N]",
        "saved": "Saved replay to {path}",
        "not_saved": "Replay not saved.",
        "bye": "Goodbye.",
        "empty_history": "History is empty.",
        "removed": "Removed: {guess} -> {fb}",
        "history_title": "History",
        "restart": "Starting a new game.",
        "invalid": "Input error: {err}",
        "inconsistent": "No candidates remain. The feedback history is inconsistent.",
        "inconsistent_hint": "Use undo/back to remove the last feedback, or new/restart to start over.",
        "loading": "Preparing QuestLine reasoning engine...",
        "help_title": "Help",
        "report_title": "QuestLine report",
        "opening_book": "Opening book",
        "endgame": "Endgame compression",
        "fallback": "Fallback / stabilization",
        "brake": "Complicated midgame brake",
        "push": "Narrative push",
        "normal": "Narrative midgame",
        "ahead": "ahead",
        "normal_pace": "normal",
        "behind": "behind",
        "unknown": "unknown",
        "manual": "manual",
        "menu_pick": "menu pick",
        "default_pick": "default",
    },
    "zh": {
        "title": "QuestLine",
        "subtitle": "一个叙事驱动的 Bulls & Cows 求解器。",
        "slogan": "沿着最可信的世界线逼近真相，不轻信巧合。",
        "rules": "规则：4 位不重复数字，允许前导 0。",
        "feedback": "反馈示例：0b1c、1b2c、1a2b、1,2、12",
        "commands": "指令：q/quit 退出，new/restart 新局，undo/back 撤回，history/h 历史，report/r 报告，help/? 帮助",
        "input_help": "输入：只输入反馈默认用于 #1；`2 1b2c` 选择菜单第 2 手；`3846 1b2c` 手动输入外部猜法。",
        "round": "第 {n} 轮",
        "next": "默认下一手",
        "remaining": "剩余解空间",
        "pace": "进度",
        "strategy": "当前策略",
        "recommendations": "推荐面板",
        "feedback_prompt": "请输入",
        "solved": "已解决",
        "solved_in": "用 {n} 轮解决。",
        "new_game_prompt": "开始新一局？[Y/n]",
        "save_prompt": "是否保存复盘 JSON？[y/N]",
        "saved": "复盘已保存到 {path}",
        "not_saved": "未保存复盘。",
        "bye": "再见。",
        "empty_history": "当前没有历史。",
        "removed": "已撤回：{guess} -> {fb}",
        "history_title": "历史记录",
        "restart": "开始新一局。",
        "invalid": "输入错误：{err}",
        "inconsistent": "当前没有任何候选答案，反馈历史存在矛盾。",
        "inconsistent_hint": "请输入 undo/back 撤回上一条反馈，或 new/restart 重新开始。",
        "loading": "正在准备 QuestLine 推理引擎……",
        "help_title": "帮助",
        "report_title": "QuestLine 分析报告",
        "opening_book": "开局书",
        "endgame": "残局收束",
        "fallback": "回防 / 稳定化",
        "brake": "复杂中盘降速",
        "push": "叙事推进",
        "normal": "叙事中盘",
        "ahead": "领先",
        "normal_pace": "正常",
        "behind": "落后",
        "unknown": "未知",
        "manual": "手动输入",
        "menu_pick": "菜单选择",
        "default_pick": "默认推荐",
    },
}


def tr(lang: str, key: str, **kwargs: Any) -> str:
    text = TEXT.get(lang, TEXT["en"]).get(key, TEXT["en"].get(key, key))
    return text.format(**kwargs)


def fb_text(fb: Feedback) -> str:
    return questline.fb_to_str(fb)


def print_welcome(lang: str) -> None:
    print("=" * 72)
    print(tr(lang, "title"))
    print(tr(lang, "subtitle"))
    print(tr(lang, "slogan"))
    print()
    print(tr(lang, "rules"))
    print(tr(lang, "feedback"))
    print(tr(lang, "commands"))
    print(tr(lang, "input_help"))
    print("=" * 72)


def print_help(lang: str) -> None:
    print()
    print(f"[{tr(lang, 'help_title')}]")
    print(tr(lang, "feedback"))
    print(tr(lang, "commands"))
    print(tr(lang, "input_help"))
    print()
    print("Examples:" if lang == "en" else "示例：")
    print("  1b2c          -> feedback for #1")
    print("  2 1b2c        -> choose recommendation #2 and apply feedback")
    print("  3846 1b2c     -> manual guess 3846 with feedback")
    print()


def print_history(history: History, lang: str) -> None:
    print(f"[{tr(lang, 'history_title')}]")
    if not history:
        print(tr(lang, "empty_history"))
        return
    for idx, (guess, fb) in enumerate(history, 1):
        print(f"  {idx}. {guess} -> {fb_text(fb)}")


def candidate_count_for_display(solver: Any, history: History) -> Optional[int]:
    if not history:
        return len(questline.ALL_CODES)
    if len(history) == 1 and history[0][0] == getattr(questline, "OPENING_FIRST", "0123"):
        return FIRST_BRANCH_COUNTS.get(history[0][1])
    try:
        return len(solver.filter_candidates(history))
    except Exception:
        return None


def pace_label(round_number: int, remaining: Optional[int], lang: str) -> str:
    if remaining is None:
        return tr(lang, "unknown")
    # Simple explainable pace bands. These are UX labels, not strategy rules.
    if round_number <= 1:
        return tr(lang, "normal_pace")
    if round_number == 2:
        if remaining <= 80:
            return tr(lang, "ahead")
        if remaining <= 250:
            return tr(lang, "normal_pace")
        return tr(lang, "behind")
    if round_number == 3:
        if remaining <= 15:
            return tr(lang, "ahead")
        if remaining <= 80:
            return tr(lang, "normal_pace")
        return tr(lang, "behind")
    if round_number == 4:
        if remaining <= 4:
            return tr(lang, "ahead")
        if remaining <= 20:
            return tr(lang, "normal_pace")
        return tr(lang, "behind")
    if remaining <= 2:
        return tr(lang, "ahead")
    if remaining <= 8:
        return tr(lang, "normal_pace")
    return tr(lang, "behind")


def infer_strategy_state(result: Dict[str, Any], history: History, lang: str) -> str:
    phase = result.get("phase")
    recs = result.get("recommendations", [])
    top = recs[0] if recs else {}
    if phase in {"opening_first", "opening_second"}:
        return tr(lang, "opening_book")
    if phase == "endgame":
        return tr(lang, "endgame")
    if result.get("fallback_mode"):
        return tr(lang, "fallback")
    if isinstance(top, dict):
        if top.get("trigger_bonus", 0) and top.get("trigger_bonus", 0) > 0:
            return tr(lang, "push")
        if top.get("brake_penalty", 0) and top.get("brake_penalty", 0) > 0:
            return tr(lang, "brake")
    return tr(lang, "normal")


def get_result_safe(solver: Any, history: History, lang: str, top_k: int = 12) -> Optional[Dict[str, Any]]:
    try:
        if len(history) >= 2:
            # The third move is where the full engine is normally needed.
            # This message tells the user the program is not frozen.
            print(tr(lang, "loading"))
        return solver.choose(history, top_k=top_k)
    except Exception as exc:
        print()
        print(tr(lang, "inconsistent"))
        print(tr(lang, "inconsistent_hint"))
        print(f"Debug: {exc}")
        return None


def rec_guess(rec: Dict[str, Any]) -> Optional[str]:
    g = rec.get("guess")
    return str(g) if g else None


def build_menu(solver: Any, result: Dict[str, Any], history: History) -> List[Dict[str, Any]]:
    menu: List[Dict[str, Any]] = []
    seen = set()

    # QuestLine top 3
    for rec in result.get("recommendations", [])[:3]:
        guess = rec_guess(rec)
        if guess and guess not in seen:
            item = dict(rec)
            item["source"] = "QuestLine"
            menu.append(item)
            seen.add(guess)

    # AVG and MM anchors when candidates are known.
    candidates = result.get("candidates") or []
    if candidates:
        try:
            cand_idx = tuple(questline.CODE_TO_INDEX[c] for c in candidates)
            avg_i, avg_e, avg_m, avg_b = solver.best_pure_guess(cand_idx, "avg")
            avg_guess = questline.ALL_CODES[avg_i]
            if avg_guess not in seen:
                menu.append({
                    "guess": avg_guess,
                    "source": "AVG",
                    "score": avg_e,
                    "normal_expected": avg_e,
                    "normal_max_bucket": avg_m,
                    "bucket_count": avg_b,
                    "trigger_bonus": 0,
                    "brake_penalty": 0,
                })
                seen.add(avg_guess)
            mm_i, mm_e, mm_m, mm_b = solver.best_pure_guess(cand_idx, "mm")
            mm_guess = questline.ALL_CODES[mm_i]
            if mm_guess not in seen:
                menu.append({
                    "guess": mm_guess,
                    "source": "MM",
                    "score": mm_m,
                    "normal_expected": mm_e,
                    "normal_max_bucket": mm_m,
                    "bucket_count": mm_b,
                    "trigger_bonus": 0,
                    "brake_penalty": 0,
                })
                seen.add(mm_guess)
        except Exception:
            pass

    # Conspiracy pick: simple v1.2 version.
    # A legal candidate far from QuestLine's top picks. This will become more
    # narrative-weight-aware in v1.3 report work.
    candidates = result.get("candidates") or []
    if candidates:
        for candidate in reversed(candidates):
            if candidate not in seen:
                menu.append({
                    "guess": candidate,
                    "source": "Conspiracy",
                    "score": 0,
                    "normal_expected": 0,
                    "normal_max_bucket": 0,
                    "bucket_count": 0,
                    "trigger_bonus": 0,
                    "brake_penalty": 0,
                })
                seen.add(candidate)
                break

    return menu[:6]


def print_menu(menu: List[Dict[str, Any]], lang: str) -> None:
    print(f"[{tr(lang, 'recommendations')}]")
    for idx, item in enumerate(menu, 1):
        guess = item.get("guess", "????")
        source = item.get("source", "QuestLine")
        exp = item.get("normal_expected")
        max_bucket = item.get("normal_max_bucket")
        trigger = item.get("trigger_bonus", 0)
        brake = item.get("brake_penalty", 0)
        if isinstance(exp, (int, float)) and exp:
            print(f"  {idx}. {guess}  [{source}]  AVG={exp:.2f} max={max_bucket} trig={trigger:.2f} brake={brake:.3f}")
        else:
            print(f"  {idx}. {guess}  [{source}]")


def print_turn(solver: Any, history: History, result: Dict[str, Any], menu: List[Dict[str, Any]], lang: str) -> None:
    round_number = len(history) + 1
    remaining = candidate_count_for_display(solver, history)
    strategy = infer_strategy_state(result, history, lang)
    default_guess = menu[0]["guess"] if menu else result["recommendations"][0]["guess"]

    print()
    if lang == "zh":
        print(tr(lang, "round", n=round_number))
    else:
        print(f"{tr(lang, 'round')} {round_number}")
    print(f"{tr(lang, 'next')}: {default_guess}")
    if remaining is not None:
        print(f"{tr(lang, 'remaining')}: {remaining}")
        print(f"{tr(lang, 'pace')}: {pace_label(round_number, remaining, lang)}")
    else:
        print(f"{tr(lang, 'remaining')}: {tr(lang, 'unknown')}")
    print(f"{tr(lang, 'strategy')}: {strategy}")
    print_menu(menu, lang)


def parse_turn_input(text: str, menu: List[Dict[str, Any]]) -> Tuple[str, Feedback, str]:
    """Return (guess, feedback, source_label)."""
    parts = text.strip().split()
    if not parts:
        raise ValueError("empty input")

    # Feedback only: applies to #1 recommendation.
    if len(parts) == 1:
        token = parts[0]
        if token.isdigit() and len(token) == 1 and 1 <= int(token) <= len(menu):
            raise ValueError("menu number needs feedback, e.g. `2 1b2c`")
        feedback = questline.parse_feedback(token)
        return str(menu[0]["guess"]), feedback, "default"

    # Menu pick: "2 1b2c"
    if parts[0].isdigit() and len(parts[0]) <= 2:
        choice = int(parts[0])
        if not (1 <= choice <= len(menu)):
            raise ValueError(f"menu choice must be 1-{len(menu)}")
        feedback = questline.parse_feedback(parts[1])
        return str(menu[choice - 1]["guess"]), feedback, "menu"

    # Manual external guess: "3846 1b2c"
    guess = questline.validate_code(parts[0])
    feedback = questline.parse_feedback(parts[1])
    return guess, feedback, "manual"


def print_report(solver: Any, history: History, lang: str) -> None:
    result = get_result_safe(solver, history, lang, top_k=12)
    if result is None:
        return
    print()
    print(f"[{tr(lang, 'report_title')}]")
    print_history(history, lang)
    remaining = candidate_count_for_display(solver, history)
    if remaining is not None:
        print(f"{tr(lang, 'remaining')}: {remaining}")
    anchor = result.get("avg_anchor")
    if anchor:
        print(f"AVG: {anchor['guess']} exp={anchor['exp']:.3f} max={anchor['max']} buckets={anchor['bucket_count']}")
    menu = build_menu(solver, result, history)
    print_menu(menu, lang)

    candidates = result.get("candidates") or []
    if candidates and len(candidates) <= 20:
        print()
        print("Candidates:" if lang == "en" else "残局候选：")
        for code in candidates:
            print(f"  {code}")


def save_replay(history: History, lang: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(f"questline_replay_{timestamp}.json")
    data = {
        "project": "QuestLine",
        "saved_at": datetime.now().isoformat(),
        "rounds": len(history),
        "history": [
            {"round": idx, "guess": guess, "feedback": fb_text(fb)}
            for idx, (guess, fb) in enumerate(history, 1)
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def ask_yes_no(prompt: str, default_yes: bool = True) -> bool:
    suffix = "" if prompt.endswith(" ") else " "
    text = input(prompt + suffix).strip().lower()
    if not text:
        return default_yes
    return text in {"y", "yes", "是", "好", "可以"}


def game_loop(lang: str) -> bool:
    """Run one game. Return True if user wants another game."""
    solver = questline.QuestLineSolver(verbose=True)
    history: History = []

    while True:
        result = get_result_safe(solver, history, lang, top_k=12)
        if result is None:
            cmd = input(f"{tr(lang, 'feedback_prompt')}: ").strip().lower()
            if cmd in {"q", "quit", "exit"}:
                return False
            if cmd in {"new", "restart"}:
                print(tr(lang, "restart"))
                return True
            if cmd in {"undo", "back"}:
                if history:
                    guess, fb = history.pop()
                    print(tr(lang, "removed", guess=guess, fb=fb_text(fb)))
                else:
                    print(tr(lang, "empty_history"))
                continue
            if cmd in {"h", "history"}:
                print_history(history, lang)
                continue
            print(tr(lang, "inconsistent_hint"))
            continue

        menu = build_menu(solver, result, history)
        if not menu:
            print(tr(lang, "inconsistent"))
            return True

        print_turn(solver, history, result, menu, lang)
        raw = input(f"{tr(lang, 'feedback_prompt')}: ").strip()
        lower = raw.lower()

        if lower in {"q", "quit", "exit"}:
            return False
        if lower in {"help", "?"}:
            print_help(lang)
            continue
        if lower in {"h", "history"}:
            print_history(history, lang)
            continue
        if lower in {"r", "report"}:
            print_report(solver, history, lang)
            continue
        if lower in {"new", "restart"}:
            print(tr(lang, "restart"))
            return True
        if lower in {"undo", "back"}:
            if history:
                guess, fb = history.pop()
                print(tr(lang, "removed", guess=guess, fb=fb_text(fb)))
            else:
                print(tr(lang, "empty_history"))
            continue

        try:
            guess, fb, source = parse_turn_input(raw, menu)
        except Exception as exc:
            print(tr(lang, "invalid", err=exc))
            continue

        history.append((guess, fb))

        if fb == (4, 0):
            print()
            print(f"{tr(lang, 'solved')}!")
            print(tr(lang, "solved_in", n=len(history)))
            print_history(history, lang)
            if ask_yes_no(tr(lang, "save_prompt"), default_yes=False):
                path = save_replay(history, lang)
                print(tr(lang, "saved", path=path))
            else:
                print(tr(lang, "not_saved"))
            return ask_yes_no(tr(lang, "new_game_prompt"), default_yes=True)


def choose_language(default: str = "en") -> str:
    print("Choose language / 选择语言:")
    print("  1. 中文")
    print("  2. English")
    raw = input(f"> ").strip().lower()
    if raw in {"1", "zh", "cn", "chinese", "中文"}:
        return "zh"
    if raw in {"2", "en", "english"}:
        return "en"
    return default


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="QuestLine interactive CLI v1.2")
    parser.add_argument("--lang", choices=["zh", "en"], default=None, help="UI language.")
    args = parser.parse_args(argv)

    lang = args.lang or choose_language(default="en")
    print_welcome(lang)

    keep_playing = True
    while keep_playing:
        keep_playing = game_loop(lang)
    print(tr(lang, "bye"))


if __name__ == "__main__":
    main()
