"""QuestLine CLI v1.2.2

Chinese-first interactive CLI for QuestLine.

This file imports the existing questline.py and does not change the solver core.
It focuses on play experience and input tolerance.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
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
    "zh": {
        "title": "QuestLine",
        "subtitle": "一个叙事驱动的 Bulls & Cows 求解器。",
        "slogan": "沿着最可信的世界线逼近真相，不轻信巧合。",
        "rules": "规则：4 位不重复数字，允许前导 0。",
        "feedback": "反馈示例：0b1c、1b2c、1a2b、1,2、1，2、1、2、12",
        "commands": "指令：q/quit 退出，new/restart 新局，undo/back 撤回，history/h 历史，report/r 报告，help/? 帮助",
        "input_help": "输入：只输入反馈默认用于 #1；`2 1b2c` 选择菜单第 2 手；`3846 1b2c` 手动输入外部猜法；`411` 表示选 #4 并给 1b1c。",
        "round": "第 {n} 轮",
        "next": "默认下一手",
        "remaining": "剩余可能答案数量",
        "hit": "直接命中率",
        "opening": "开局评价",
        "pace": "节奏评价",
        "strategy": "当前策略",
        "recs": "推荐面板",
        "prompt": "请输入",
        "solved": "已解决！",
        "solved_in": "用 {n} 轮解决。",
        "save": "是否保存复盘 JSON？[y/N]",
        "new": "开始新一局？[Y/n]",
        "saved": "复盘已保存到 {path}",
        "not_saved": "未保存复盘。",
        "bye": "再见。",
        "history": "历史记录",
        "empty": "当前没有历史。",
        "removed": "已撤回：{guess} -> {fb}",
        "restart": "开始新一局。",
        "invalid": "输入错误：{err}",
        "inconsistent": "当前没有任何候选答案，反馈历史存在矛盾。",
        "inconsistent_hint": "你可以输入 undo 撤回上一手，输入 new 重新开始，或直接输入新的反馈来修正上一手。",
        "fixed_last": "已将上一手修正为：{guess} -> {fb}",
        "loading": "正在准备 QuestLine 推理引擎……",
        "report": "QuestLine 分析报告",
        "opening_book": "开局书",
        "alternate": "阴谋论开局 / 平行世界线",
        "conspiracy": "阴谋论候选",
        "endgame": "残局收束",
        "fallback": "回防 / 稳定化",
        "brake": "复杂中盘降速",
        "push": "叙事推进",
        "midgame": "叙事中盘",
        "ahead": "领先",
        "normal": "正常",
        "slow": "偏慢",
        "hard": "困难",
        "unknown": "未知",
        "direct": "直接中了",
        "lucky": "撞大运了",
        "clean": "简单开局",
        "stable": "普通开局",
        "difficult": "困难开局",
        "rough": "天崩开局",
        "only_menu": "当前只有 1-{n} 号推荐。请输入有效编号，例如：{n} 2b2c；也可以只输入反馈，默认使用 #1。",
        "missing_feedback": "{guess} 看起来是一个合法猜法，但缺少反馈。请使用：{guess} 1b2c",
        "json_input": "检测到 JSON 内容。当前输入框不支持载入复盘 JSON。请输入反馈、指令，或手动猜法。",
    },
    "en": {
        "title": "QuestLine",
        "subtitle": "A narrative-driven Bulls & Cows solver.",
        "slogan": "Follow the strongest story. Distrust coincidence.",
        "rules": "Rules: 4 distinct digits, leading zero allowed.",
        "feedback": "Feedback examples: 0b1c, 1b2c, 1a2b, 1,2, 1，2, 12",
        "commands": "Commands: q/quit, new/restart, undo/back, history/h, report/r, help/?",
        "input_help": "Input: feedback only for #1; `2 1b2c`; `3846 1b2c`; compact `411` means #4 with 1b1c.",
        "round": "Round {n}",
        "next": "Default next guess",
        "remaining": "Remaining possible answers",
        "hit": "Direct hit chance",
        "opening": "Opening read",
        "pace": "Pace",
        "strategy": "Strategy",
        "recs": "Recommendations",
        "prompt": "Your input",
        "solved": "Solved!",
        "solved_in": "Solved in {n} rounds.",
        "save": "Save replay JSON? [y/N]",
        "new": "Start a new game? [Y/n]",
        "saved": "Saved replay to {path}",
        "not_saved": "Replay not saved.",
        "bye": "Goodbye.",
        "history": "History",
        "empty": "History is empty.",
        "removed": "Removed: {guess} -> {fb}",
        "restart": "Starting a new game.",
        "invalid": "Input error: {err}",
        "inconsistent": "No candidates remain. The feedback history is inconsistent.",
        "inconsistent_hint": "Type undo, new, or enter a new feedback to replace the last feedback.",
        "fixed_last": "Replaced last feedback: {guess} -> {fb}",
        "loading": "Preparing QuestLine reasoning engine...",
        "report": "QuestLine report",
        "opening_book": "Opening book",
        "alternate": "Conspiracy / alternate opening",
        "conspiracy": "Conspiracy Pick",
        "endgame": "Endgame compression",
        "fallback": "Fallback / stabilization",
        "brake": "Complicated midgame brake",
        "push": "Narrative push",
        "midgame": "Narrative midgame",
        "ahead": "ahead",
        "normal": "normal",
        "slow": "slow",
        "hard": "hard",
        "unknown": "unknown",
        "direct": "Direct hit",
        "lucky": "Lucky break",
        "clean": "Clean line",
        "stable": "Stable line",
        "difficult": "Difficult line",
        "rough": "Rough start",
        "only_menu": "Only recommendations #1-#{n} are available. Use `{n} 2b2c`, or feedback only for #1.",
        "missing_feedback": "{guess} looks like a valid guess, but feedback is missing. Use: {guess} 1b2c",
        "json_input": "This looks like JSON. Enter feedback, a command, or a manual guess.",
    },
}


def tr(lang: str, key: str, **kwargs: Any) -> str:
    return TEXT.get(lang, TEXT["zh"]).get(key, key).format(**kwargs)


def fb_text(fb: Feedback) -> str:
    return questline.fb_to_str(fb)


def normalize_feedback_text(text: str) -> str:
    return text.strip().lower().replace("，", ",").replace("、", ",")


def parse_feedback_friendly(text: str) -> Feedback:
    text = normalize_feedback_text(text)
    parts = [p for p in text.split() if p]
    if len(parts) == 2 and all(len(p) == 1 and p.isdigit() for p in parts):
        return int(parts[0]), int(parts[1])
    return questline.parse_feedback(text)


def direct_hit_chance(n: Optional[int]) -> str:
    if not n or n <= 0:
        return "?"
    return f"1/{n} = {100.0 / n:.2f}%"


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
    print(f"\n[{tr(lang, 'history') if False else 'Help' if lang == 'en' else '帮助'}]")
    print(tr(lang, "feedback"))
    print(tr(lang, "commands"))
    print(tr(lang, "input_help"))
    print("  1b2c       -> #1 推荐的反馈")
    print("  2 1b2c     -> 选择 #2 并给反馈")
    print("  411        -> 选择 #4 并给 1b1c")
    print("  3846 1b2c  -> 手动猜 3846 并给反馈")


def print_history(history: History, lang: str) -> None:
    print(f"[{tr(lang, 'history')}]")
    if not history:
        print(tr(lang, "empty"))
        return
    for i, (g, f) in enumerate(history, 1):
        print(f"  {i}. {g} -> {fb_text(f)}")


def candidate_count_for_display(solver: Any, history: History) -> Optional[int]:
    if not history:
        return len(questline.ALL_CODES)
    try:
        return len(solver.filter_candidates(history))
    except Exception:
        return None


def opening_read_from_remaining(n: Optional[int], lang: str) -> str:
    if n is None:
        return tr(lang, "unknown")
    if n <= 1:
        return tr(lang, "direct")
    if n == 1440:
        return tr(lang, "rough")
    if n == 1260:
        return tr(lang, "difficult")
    if n == 720:
        return tr(lang, "stable")
    if 100 <= n < 720:
        return tr(lang, "clean")
    if n < 100:
        return tr(lang, "lucky")
    return tr(lang, "normal")


def pace_label(round_number: int, n: Optional[int], lang: str) -> str:
    if n is None:
        return tr(lang, "unknown")
    if round_number <= 2:
        return tr(lang, "normal")
    if round_number == 3:
        if n <= 15: return tr(lang, "ahead")
        if n <= 80: return tr(lang, "normal")
        if n <= 180: return tr(lang, "slow")
        return tr(lang, "hard")
    if round_number == 4:
        if n <= 4: return tr(lang, "ahead")
        if n <= 20: return tr(lang, "normal")
        if n <= 80: return tr(lang, "slow")
        return tr(lang, "hard")
    if n <= 2: return tr(lang, "ahead")
    if n <= 12: return tr(lang, "normal")
    if n <= 30: return tr(lang, "slow")
    return tr(lang, "hard")


def infer_strategy_state(result: Dict[str, Any], lang: str) -> str:
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
    return tr(lang, "midgame")


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
    phase = result.get("phase")
    if phase == "opening_first":
        return [
            {"guess": getattr(questline, "OPENING_FIRST", "0123"), "source": "QuestLine", "score": 0},
            {"guess": "9876", "source": "Conspiracy", "score": 0},
        ]
    if phase == "opening_second":
        recs = result.get("recommendations", [])
        if recs and isinstance(recs[0], dict) and recs[0].get("guess"):
            return [{"guess": recs[0]["guess"], "source": "QuestLine", "score": 0}]

    menu: List[Dict[str, Any]] = []
    seen = set()
    for rec in result.get("recommendations", [])[:3]:
        if isinstance(rec, dict) and rec.get("guess") and rec["guess"] not in seen:
            item = dict(rec)
            item["source"] = "QuestLine"
            menu.append(item)
            seen.add(item["guess"])

    candidates = result.get("candidates") or []
    if candidates:
        try:
            cand_idx = tuple(questline.CODE_TO_INDEX[c] for c in candidates)
            avg_i, avg_e, avg_m, avg_b = solver.best_pure_guess(cand_idx, "avg")
            avg_g = questline.ALL_CODES[avg_i]
            if avg_g not in seen:
                menu.append({"guess": avg_g, "source": "AVG", "score": avg_e, "normal_expected": avg_e, "normal_max_bucket": avg_m, "bucket_count": avg_b, "trigger_bonus": 0, "brake_penalty": 0})
                seen.add(avg_g)
            mm_i, mm_e, mm_m, mm_b = solver.best_pure_guess(cand_idx, "mm")
            mm_g = questline.ALL_CODES[mm_i]
            if mm_g not in seen:
                menu.append({"guess": mm_g, "source": "MM", "score": mm_m, "normal_expected": mm_e, "normal_max_bucket": mm_m, "bucket_count": mm_b, "trigger_bonus": 0, "brake_penalty": 0})
                seen.add(mm_g)
        except Exception:
            pass
        for c in reversed(candidates):
            if c not in seen:
                menu.append({"guess": c, "source": "Conspiracy", "score": 0})
                break
    return menu[:6]


def source_label(source: str, round_number: int, lang: str) -> str:
    if source == "Conspiracy":
        return tr(lang, "alternate") if round_number == 1 else tr(lang, "conspiracy")
    return source


def print_menu(menu: List[Dict[str, Any]], lang: str, round_number: int) -> None:
    print(f"[{tr(lang, 'recs')}]")
    for i, item in enumerate(menu, 1):
        guess = item.get("guess", "????")
        label = source_label(str(item.get("source", "QuestLine")), round_number, lang)
        exp = item.get("normal_expected")
        if isinstance(exp, (int, float)) and exp:
            print(f"  {i}. {guess}  [{label}]  AVG={exp:.2f} max={item.get('normal_max_bucket')} trig={item.get('trigger_bonus', 0):.2f} brake={item.get('brake_penalty', 0):.3f}")
        else:
            print(f"  {i}. {guess}  [{label}]")


def print_turn(solver: Any, history: History, result: Dict[str, Any], menu: List[Dict[str, Any]], lang: str) -> None:
    round_number = len(history) + 1
    remaining = candidate_count_for_display(solver, history)
    print()
    print(tr(lang, "round", n=round_number))
    print(f"{tr(lang, 'next')}: {menu[0]['guess']}")
    if remaining is not None:
        print(f"{tr(lang, 'remaining')}: {remaining}")
        print(f"{tr(lang, 'hit')}: {direct_hit_chance(remaining)}")
        if round_number == 2:
            print(f"{tr(lang, 'opening')}: {opening_read_from_remaining(remaining, lang)}")
        elif round_number >= 3:
            print(f"{tr(lang, 'pace')}: {pace_label(round_number, remaining, lang)}")
    else:
        print(f"{tr(lang, 'remaining')}: {tr(lang, 'unknown')}")
    print(f"{tr(lang, 'strategy')}: {infer_strategy_state(result, lang)}")
    print_menu(menu, lang, round_number)


def parse_turn_input(text: str, menu: List[Dict[str, Any]], lang: str) -> Tuple[str, Feedback, str, str]:
    raw = text.strip()
    if not raw:
        raise ValueError("empty input")
    if raw.startswith("{"):
        raise ValueError(tr(lang, "json_input"))

    compact = raw.replace(" ", "")
    if compact.isdigit() and len(compact) == 3 and compact[0] in "123456":
        choice = int(compact[0])
        if 1 <= choice <= len(menu):
            fb = parse_feedback_friendly(compact[1:])
            item = menu[choice - 1]
            return str(item["guess"]), fb, str(item.get("source", "QuestLine")), "menu"

    parts = raw.split()
    if len(parts) == 1:
        token = parts[0]
        if token.isdigit() and len(token) == 1 and 1 <= int(token) <= len(menu):
            raise ValueError("menu number needs feedback, e.g. `2 1b2c`")
        try:
            valid_guess = questline.validate_code(token)
        except Exception:
            valid_guess = None
        if valid_guess:
            raise ValueError(tr(lang, "missing_feedback", guess=valid_guess))
        fb = parse_feedback_friendly(token)
        item = menu[0]
        return str(item["guess"]), fb, str(item.get("source", "QuestLine")), "default"

    if len(parts) == 2 and all(len(p) == 1 and p.isdigit() for p in parts):
        fb = parse_feedback_friendly(" ".join(parts))
        item = menu[0]
        return str(item["guess"]), fb, str(item.get("source", "QuestLine")), "default"

    if parts[0].isdigit() and len(parts[0]) <= 2:
        choice = int(parts[0])
        if not (1 <= choice <= len(menu)):
            raise ValueError(f"MENU_RANGE::{len(menu)}")
        fb = parse_feedback_friendly(" ".join(parts[1:]))
        item = menu[choice - 1]
        return str(item["guess"]), fb, str(item.get("source", "QuestLine")), "menu"

    guess = questline.validate_code(parts[0])
    fb = parse_feedback_friendly(" ".join(parts[1:]))
    return guess, fb, "Manual", "manual"


def print_report(solver: Any, history: History, lang: str, state: CliState) -> None:
    result = get_result_safe(solver, history, lang, state, top_k=12)
    if result is None:
        return
    print(f"\n[{tr(lang, 'report')}]")
    print_history(history, lang)
    remaining = candidate_count_for_display(solver, history)
    if remaining is not None:
        print(f"{tr(lang, 'remaining')}: {remaining}")
        print(f"{tr(lang, 'hit')}: {direct_hit_chance(remaining)}")
    anchor = result.get("avg_anchor")
    if anchor:
        print(f"AVG: {anchor['guess']} exp={anchor['exp']:.3f} max={anchor['max']} buckets={anchor['bucket_count']}")
    menu = build_menu(solver, result, history)
    print_menu(menu, lang, len(history) + 1)
    candidates = result.get("candidates") or []
    if candidates and len(candidates) <= 20:
        print("\n残局候选：" if lang == "zh" else "\nCandidates:")
        for c in candidates:
            print(f"  {c}")


def save_replay(history: History, replay_rows: ReplayRows) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(f"questline_replay_{timestamp}.json")
    solved = bool(history and history[-1][1] == (4, 0))
    data = {
        "project": "QuestLine",
        "saved_at": datetime.now().isoformat(),
        "solved": solved,
        "final_answer": history[-1][0] if solved else None,
        "rounds": len(history),
        "history": replay_rows,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def ask_yes_no(prompt: str, default_yes: bool = True) -> bool:
    raw = input(prompt + " ").strip().lower()
    if not raw:
        return default_yes
    return raw in {"y", "yes", "是", "好", "可以"}


def replace_last_feedback(solver: Any, history: History, replay_rows: ReplayRows, fb: Feedback, lang: str) -> None:
    if not history:
        print(tr(lang, "empty"))
        return
    guess, _old = history[-1]
    history[-1] = (guess, fb)
    remaining = candidate_count_for_display(solver, history)
    if replay_rows:
        replay_rows[-1]["feedback"] = fb_text(fb)
        replay_rows[-1]["remaining_after"] = remaining
    print(tr(lang, "fixed_last", guess=guess, fb=fb_text(fb)))


def error_recovery_loop(solver: Any, history: History, replay_rows: ReplayRows, lang: str) -> Optional[bool]:
    raw = input(f"{tr(lang, 'prompt')}: ").strip()
    lower = raw.lower()
    if lower in {"q", "quit", "exit"}:
        return False
    if lower in {"new", "restart"}:
        print(tr(lang, "restart"))
        return True
    if lower in {"undo", "back"}:
        if history:
            g, f = history.pop()
            if replay_rows:
                replay_rows.pop()
            print(tr(lang, "removed", guess=g, fb=fb_text(f)))
        else:
            print(tr(lang, "empty"))
        return None
    if lower in {"h", "history"}:
        print_history(history, lang)
        return None
    try:
        fb = parse_feedback_friendly(raw)
        replace_last_feedback(solver, history, replay_rows, fb, lang)
    except Exception as exc:
        print(tr(lang, "invalid", err=exc))
    return None


def game_loop(lang: str) -> bool:
    solver = questline.QuestLineSolver(verbose=True)
    state = CliState()
    history: History = []
    replay_rows: ReplayRows = []

    while True:
        result = get_result_safe(solver, history, lang, state, top_k=12)
        if result is None:
            decision = error_recovery_loop(solver, history, replay_rows, lang)
            if decision is not None:
                return decision
            continue

        menu = build_menu(solver, result, history)
        if not menu:
            print(tr(lang, "inconsistent"))
            return True
        print_turn(solver, history, result, menu, lang)
        raw = input(f"{tr(lang, 'prompt')}: ").strip()
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
                g, f = history.pop()
                if replay_rows:
                    replay_rows.pop()
                print(tr(lang, "removed", guess=g, fb=fb_text(f)))
            else:
                print(tr(lang, "empty"))
            continue

        try:
            guess, fb, source, mode = parse_turn_input(raw, menu, lang)
        except Exception as exc:
            msg = str(exc)
            if msg.startswith("MENU_RANGE::"):
                n = int(msg.split("::", 1)[1])
                print(tr(lang, "invalid", err=tr(lang, "only_menu", n=n)))
            else:
                print(tr(lang, "invalid", err=exc))
            continue

        history.append((guess, fb))
        remaining = candidate_count_for_display(solver, history)
        replay_rows.append({
            "round": len(history),
            "guess": guess,
            "feedback": fb_text(fb),
            "source": source,
            "input_mode": mode,
            "remaining_after": remaining,
        })

        if fb == (4, 0):
            print("\n" + tr(lang, "solved"))
            print(tr(lang, "solved_in", n=len(history)))
            print_history(history, lang)
            if ask_yes_no(tr(lang, "save"), default_yes=False):
                path = save_replay(history, replay_rows)
                print(tr(lang, "saved", path=path))
            else:
                print(tr(lang, "not_saved"))
            return ask_yes_no(tr(lang, "new"), default_yes=True)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="QuestLine interactive CLI v1.2.2")
    parser.add_argument("--lang", choices=["zh", "en"], default="zh", help="UI language. Default: zh")
    args = parser.parse_args(argv)
    lang = args.lang
    print_welcome(lang)
    keep = True
    while keep:
        keep = game_loop(lang)
    print(tr(lang, "bye"))


if __name__ == "__main__":
    main()
