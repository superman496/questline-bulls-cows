"""QuestLine CLI v1.2.1

Interactive UX patch for QuestLine.

Changes over v1.2:
- Loading / preparing message is shown only once per game session.
- Round 2 shows an opening read instead of misleading pace labels.
- "Remaining candidates" is renamed to "Remaining possible answers".
- Direct hit chance is displayed as 1 / N and percentage.
- Round 1 conspiracy opening is kept as an intentional alternate timeline option.
- Menu-choice errors are friendlier.
- Replay JSON includes solved, final_answer, source, and remaining_after.

This file imports the existing questline.py and does not modify the solver core.
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
ReplayRows = List[Dict[str, Any]]

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
        "remaining_possible": "Remaining possible answers",
        "direct_hit": "Direct hit chance",
        "pace": "Pace",
        "opening_read": "Opening read",
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
        "ready": "QuestLine reasoning engine is ready.",
        "help_title": "Help",
        "report_title": "QuestLine report",
        "opening_book": "Opening book",
        "alternate_opening": "Conspiracy / alternate opening",
        "endgame": "Endgame compression",
        "fallback": "Fallback / stabilization",
        "brake": "Complicated midgame brake",
        "push": "Narrative push",
        "normal": "Narrative midgame",
        "ahead": "ahead",
        "normal_pace": "normal",
        "slow": "slow",
        "hard": "hard",
        "unknown": "unknown",
        "direct_hit_opening": "Direct hit",
        "lucky_break": "Lucky break",
        "clean_line": "Clean line",
        "stable_line": "Stable line",
        "difficult_line": "Difficult line",
        "rough_start": "Rough start",
        "manual": "manual",
        "menu_pick": "menu pick",
        "default_pick": "default",
        "only_menu": "Only recommendations #1-#{n} are available. Use something like `{n} 2b2c`, or enter feedback only to use #1.",
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
        "remaining_possible": "剩余可能答案数量",
        "direct_hit": "直接命中率",
        "pace": "节奏评价",
        "opening_read": "开局评价",
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
        "ready": "QuestLine 推理引擎已就绪。",
        "help_title": "帮助",
        "report_title": "QuestLine 分析报告",
        "opening_book": "开局书",
        "alternate_opening": "阴谋论开局 / 平行世界线",
        "endgame": "残局收束",
        "fallback": "回防 / 稳定化",
        "brake": "复杂中盘降速",
        "push": "叙事推进",
        "normal": "叙事中盘",
        "ahead": "领先",
        "normal_pace": "正常",
        "slow": "偏慢",
        "hard": "困难",
        "unknown": "未知",
        "direct_hit_opening": "直接中了",
        "lucky_break": "撞大运了",
        "clean_line": "简单开局",
        "stable_line": "普通开局",
        "difficult_line": "困难开局",
        "rough_start": "天崩开局",
        "manual": "手动输入",
        "menu_pick": "菜单选择",
        "default_pick": "默认推荐",
        "only_menu": "当前只有 1-{n} 号推荐。请输入有效编号，例如：{n} 2b2c；也可以只输入反馈，默认使用 #1。",
    },
}


def tr(lang: str, key: str, **kwargs: Any) -> str:
    text = TEXT.get(lang, TEXT["en"]).get(key, TEXT["en"].get(key, key))
    return text.format(**kwargs)


def fb_text(fb: Feedback) -> str:
    return questline.fb_to_str(fb)


def direct_hit_chance(remaining: Optional[int]) -> str:
    if not remaining or remaining <= 0:
        return "?"
    return f"1/{remaining} = {100.0 / remaining:.2f}%"


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


def opening_read(history: History, lang: str) -> Optional[str]:
    if len(history) != 1 or history[0][0] != getattr(questline, "OPENING_FIRST", "0123"):
        return None
    fb = history[0][1]
    remaining = FIRST_BRANCH_COUNTS.get(fb)
    if remaining is None:
        return tr(lang, "unknown")
    if fb == (4, 0) or remaining == 1:
        return tr(lang, "direct_hit_opening")
    if remaining == 1440:
        return tr(lang, "rough_start")
    if remaining == 1260:
        return tr(lang, "difficult_line")
    if remaining == 720:
        return tr(lang, "stable_line")
    if 100 <= remaining < 720:
        return tr(lang, "clean_line")
    return tr(lang, "lucky_break")


def pace_label(round_number: int, remaining: Optional[int], lang: str) -> str:
    if remaining is None:
        return tr(lang, "unknown")
    # Round 2 uses opening_read instead of pace. These bands are for Round 3+.
    if round_number <= 2:
        return tr(lang, "normal_pace")
    if round_number == 3:
        if remaining <= 15:
            return tr(lang, "ahead")
        if remaining <= 80:
            return tr(lang, "normal_pace")
        if remaining <= 150:
            return tr(lang, "slow")
        return tr(lang, "hard")
    if round_number == 4:
        if remaining <= 4:
            return tr(lang, "ahead")
        if remaining <= 20:
            return tr(lang, "normal_pace")
        if remaining <= 50:
            return tr(lang, "slow")
        return tr(lang, "hard")
    if remaining <= 2:
        return tr(lang, "ahead")
    if remaining <= 8:
        return tr(lang, "normal_pace")
    if remaining <= 20:
        return tr(lang, "slow")
    return tr(lang, "hard")


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


class CliState:
    def __init__(self) -> None:
        self.engine_notice_shown = False


def get_result_safe(solver: Any, history: History, lang: str, state: CliState, top_k: int = 12) -> Optional[Dict[str, Any]]:
    try:
        if len(history) >= 2 and not state.engine_notice_shown:
            print(tr(lang, "loading"))
            state.engine_notice_shown = True
        return solver.choose(history, top_k=top_k)
    except Exception as exc:
        print()
        print(tr(lang, "inconsistent"))
        print(tr(lang, "inconsistent_hint"))
        print(f"Debug: {exc}")
        return None


def build_menu(solver: Any, result: Dict[str, Any], history: History) -> List[Dict[str, Any]]:
    menu: List[Dict[str, Any]] = []
    seen = set()

    # QuestLine top 3
    for rec in result.get("recommendations", [])[:3]:
        guess = str(rec.get("guess")) if isinstance(rec, dict) and rec.get("guess") else None
        if guess and guess not in seen:
            item = dict(rec)
            item["source"] = "QuestLine"
            menu.append(item)
            seen.add(guess)

    candidates = result.get("candidates") or []

    # AVG / MM only if candidates are known; opening book may skip candidates intentionally.
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

    # Conspiracy pick. For opening round this is an intentional alternate opening.
    if not history:
        alt = "9876"
        if alt not in seen:
            menu.append({"guess": alt, "source": "Conspiracy", "score": 0})
            seen.add(alt)
    elif candidates:
        for candidate in reversed(candidates):
            if candidate not in seen:
                menu.append({"guess": candidate, "source": "Conspiracy", "score": 0})
                seen.add(candidate)
                break

    return menu[:6]


def print_menu(menu: List[Dict[str, Any]], lang: str) -> None:
    print(f"[{tr(lang, 'recommendations')}]")
    for idx, item in enumerate(menu, 1):
        guess = item.get("guess", "????")
        source = item.get("source", "QuestLine")
        if source == "Conspiracy" and idx == 2:
            source_label = tr(lang, "alternate_opening") if len(menu) <= 2 else source
        else:
            source_label = source
        exp = item.get("normal_expected")
        max_bucket = item.get("normal_max_bucket")
        trigger = item.get("trigger_bonus", 0)
        brake = item.get("brake_penalty", 0)
        if isinstance(exp, (int, float)) and exp:
            print(f"  {idx}. {guess}  [{source_label}]  AVG={exp:.2f} max={max_bucket} trig={trigger:.2f} brake={brake:.3f}")
        else:
            print(f"  {idx}. {guess}  [{source_label}]")


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
        print(f"{tr(lang, 'remaining_possible')}: {remaining}")
        print(f"{tr(lang, 'direct_hit')}: {direct_hit_chance(remaining)}")
        read = opening_read(history, lang)
        if read is not None:
            print(f"{tr(lang, 'opening_read')}: {read}")
        elif round_number >= 3:
            print(f"{tr(lang, 'pace')}: {pace_label(round_number, remaining, lang)}")
    else:
        print(f"{tr(lang, 'remaining_possible')}: {tr(lang, 'unknown')}")
    print(f"{tr(lang, 'strategy')}: {strategy}")
    print_menu(menu, lang)


def parse_turn_input(text: str, menu: List[Dict[str, Any]]) -> Tuple[str, Feedback, str, str]:
    """Return (guess, feedback, source_label, input_mode)."""
    parts = text.strip().split()
    if not parts:
        raise ValueError("empty input")

    # Feedback only: applies to #1 recommendation.
    if len(parts) == 1:
        token = parts[0]
        if token.isdigit() and len(token) == 1 and 1 <= int(token) <= len(menu):
            raise ValueError("menu number needs feedback, e.g. `2 1b2c`")
        feedback = questline.parse_feedback(token)
        item = menu[0]
        return str(item["guess"]), feedback, str(item.get("source", "QuestLine")), "default"

    # Menu pick: "2 1b2c"
    if parts[0].isdigit() and len(parts[0]) <= 2:
        choice = int(parts[0])
        if not (1 <= choice <= len(menu)):
            raise ValueError(f"MENU_RANGE::{len(menu)}")
        feedback = questline.parse_feedback(parts[1])
        item = menu[choice - 1]
        return str(item["guess"]), feedback, str(item.get("source", "QuestLine")), "menu"

    # Manual external guess: "3846 1b2c"
    guess = questline.validate_code(parts[0])
    feedback = questline.parse_feedback(parts[1])
    return guess, feedback, "Manual", "manual"


def print_report(solver: Any, history: History, lang: str, state: CliState) -> None:
    result = get_result_safe(solver, history, lang, state, top_k=12)
    if result is None:
        return
    print()
    print(f"[{tr(lang, 'report_title')}]")
    print_history(history, lang)
    remaining = candidate_count_for_display(solver, history)
    if remaining is not None:
        print(f"{tr(lang, 'remaining_possible')}: {remaining}")
        print(f"{tr(lang, 'direct_hit')}: {direct_hit_chance(remaining)}")
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


def save_replay(history: History, replay_rows: ReplayRows, lang: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(f"questline_replay_{timestamp}.json")
    solved = bool(history and history[-1][1] == (4, 0))
    final_answer = history[-1][0] if solved else None
    data = {
        "project": "QuestLine",
        "saved_at": datetime.now().isoformat(),
        "solved": solved,
        "final_answer": final_answer,
        "rounds": len(history),
        "history": replay_rows,
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
    state = CliState()
    history: History = []
    replay_rows: ReplayRows = []

    while True:
        result = get_result_safe(solver, history, lang, state, top_k=12)
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
                    if replay_rows:
                        replay_rows.pop()
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
            print_report(solver, history, lang, state)
            continue
        if lower in {"new", "restart"}:
            print(tr(lang, "restart"))
            return True
        if lower in {"undo", "back"}:
            if history:
                guess, fb = history.pop()
                if replay_rows:
                    replay_rows.pop()
                print(tr(lang, "removed", guess=guess, fb=fb_text(fb)))
            else:
                print(tr(lang, "empty_history"))
            continue

        try:
            guess, fb, source, input_mode = parse_turn_input(raw, menu)
        except Exception as exc:
            msg = str(exc)
            if msg.startswith("MENU_RANGE::"):
                n = int(msg.split("::", 1)[1])
                print(tr(lang, "invalid", err=tr(lang, "only_menu", n=n)))
            else:
                print(tr(lang, "invalid", err=exc))
            continue

        history.append((guess, fb))
        remaining_after = candidate_count_for_display(solver, history)
        replay_rows.append({
            "round": len(history),
            "guess": guess,
            "feedback": fb_text(fb),
            "source": source,
            "input_mode": input_mode,
            "remaining_after": remaining_after,
        })

        if fb == (4, 0):
            print()
            print(f"{tr(lang, 'solved')}!")
            print(tr(lang, "solved_in", n=len(history)))
            print_history(history, lang)
            if ask_yes_no(tr(lang, "save_prompt"), default_yes=False):
                path = save_replay(history, replay_rows, lang)
                print(tr(lang, "saved", path=path))
            else:
                print(tr(lang, "not_saved"))
            return ask_yes_no(tr(lang, "new_game_prompt"), default_yes=True)


def choose_language(default: str = "en") -> str:
    print("Choose language / 选择语言:")
    print("  1. 中文")
    print("  2. English")
    raw = input("> ").strip().lower()
    if raw in {"1", "zh", "cn", "chinese", "中文"}:
        return "zh"
    if raw in {"2", "en", "english"}:
        return "en"
    return default


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="QuestLine interactive CLI v1.2.1")
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
