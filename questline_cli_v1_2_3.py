"""QuestLine CLI v1.2.3

Interactive UX patch for QuestLine.

This file imports the existing questline.py and does not modify the solver core.

Highlights
----------
- Chinese / English UI.
- Opening book + conspiracy alternate opening.
- Robust feedback parsing for common Chinese/English punctuation.
- Compact inputs:
  - 411 -> choose #4 with 1b1c
  - 1,03 -> choose #1 with 0b3c
  - 932840 -> manual guess 9328 with 4b0c
- Manual input that matches a recommendation inherits the recommendation source.
- Inconsistent feedback recovery: enter a new feedback to replace the last one.
- Jackpot messages for first-round 4b0c.
- Replay JSON includes source, input mode, matched menu rank, remaining_after, jackpot.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import json
import re
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
        "feedback": "Feedback examples: 0b1c, 1b2c, 1a2b, 1,2, 1，2, 1、2, 1:2, 12",
        "commands": "Commands: q/quit, new/restart, undo/back, history/h, report/r, help/?",
        "input_help": "Input: feedback only for #1; `2 1b2c` for #2; `3846 1b2c` manual; `411` means #4 with 1b1c.",
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
        "corrected": "Corrected last move to: {guess} -> {fb}",
        "history_title": "History",
        "restart": "Starting a new game.",
        "invalid": "Input error: {err}",
        "inconsistent": "No candidates remain. The feedback history is inconsistent.",
        "inconsistent_hint": "Type undo/back, new/restart, or enter a new feedback to replace the last feedback.",
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
        "slow": "slow",
        "hard": "hard",
        "unknown": "unknown",
        "direct_hit_opening": "Direct hit",
        "lucky_break": "Lucky break",
        "clean_line": "Clean line",
        "stable_line": "Stable line",
        "difficult_line": "Difficult line",
        "rough_start": "Rough start",
        "only_menu": "Only recommendations #1-#{n} are available. Use `{n} 2b2c`, or enter feedback only for #1.",
        "guess_missing_feedback": "{guess} looks like a valid guess, but feedback is missing. Use: {guess} 1b2c",
        "digits_repeat": "digits must not repeat",
        "bad_code": "guess must be 4 distinct digits from 0-9",
        "bad_json": "This looks like JSON. Replay JSON loading is not supported here. Enter feedback, a command, or a manual guess.",
        "yn_only": "Please answer y or n.",
        "ended_no_undo": "This game is already solved. Use y to start a new game or n to quit.",
        "jackpot_questline": "Jackpot! The main QuestLine hit the answer on the first guess. You are the chosen one.",
        "jackpot_conspiracy": "Conspiracy jackpot! The alternate timeline became the main world.",
        "jackpot_manual": "Manual jackpot! That was not a guess. That was a prophecy.",
        "source_questline": "QuestLine",
        "source_avg": "AVG",
        "source_mm": "MM",
        "source_manual": "Manual",
        "source_conspiracy_opening": "Conspiracy / alternate opening",
        "source_conspiracy_pick": "Conspiracy Pick",
    },
    "zh": {
        "title": "QuestLine",
        "subtitle": "一个叙事驱动的 Bulls & Cows 求解器。",
        "slogan": "沿着最可信的世界线逼近真相，不轻信巧合。",
        "rules": "规则：4 位不重复数字，允许前导 0。",
        "feedback": "反馈示例：0b1c、1b2c、1a2b、1,2、1，2、1、2、1:2、12",
        "commands": "指令：q/quit 退出，new/restart 新局，undo/back 撤回，history/h 历史，report/r 报告，help/? 帮助",
        "input_help": "输入：只输入反馈默认用于 #1；`2 1b2c` 选择 #2；`3846 1b2c` 手动猜；`411` 表示选 #4 并给 1b1c。",
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
        "corrected": "已将上一手修正为：{guess} -> {fb}",
        "history_title": "历史记录",
        "restart": "开始新一局。",
        "invalid": "输入错误：{err}",
        "inconsistent": "当前没有任何候选答案，反馈历史存在矛盾。",
        "inconsistent_hint": "可以输入 undo/back 撤回，输入 new/restart 重开，或直接输入新的反馈来修正上一手。",
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
        "slow": "偏慢",
        "hard": "困难",
        "unknown": "未知",
        "direct_hit_opening": "直接中了",
        "lucky_break": "撞大运了",
        "clean_line": "简单开局",
        "stable_line": "普通开局",
        "difficult_line": "困难开局",
        "rough_start": "天崩开局",
        "only_menu": "当前只有 1-{n} 号推荐。请输入有效编号，例如：{n} 2b2c；也可以只输入反馈，默认使用 #1。",
        "guess_missing_feedback": "{guess} 看起来是一个合法猜法，但缺少反馈。请使用：{guess} 1b2c",
        "digits_repeat": "猜测数字不能重复",
        "bad_code": "猜测必须是 4 位不重复数字",
        "bad_json": "检测到 JSON 内容。当前输入框不支持载入复盘 JSON。请输入反馈、指令，或手动猜法。",
        "yn_only": "请输入 y 或 n。",
        "ended_no_undo": "这一局已经结束。请输入 y 开始新局，或 n 退出。",
        "jackpot_questline": "一击必杀！主线开局直接命中，你就是天选之人。",
        "jackpot_conspiracy": "阴谋论开局一击命中！平行世界线直接成为主世界。",
        "jackpot_manual": "手动开局一击命中！这不是猜测，这是预言。",
        "source_questline": "QuestLine",
        "source_avg": "AVG",
        "source_mm": "MM",
        "source_manual": "手动输入",
        "source_conspiracy_opening": "阴谋论开局 / 平行世界线",
        "source_conspiracy_pick": "阴谋论候选",
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


def normalize_token(text: str) -> str:
    """Normalize common full-width punctuation for command parsing."""
    return (
        text.strip()
        .replace("，", ",")
        .replace("、", ",")
        .replace("。", ".")
        .replace("．", ".")
        .replace("：", ":")
        .replace("；", ";")
    )


def parse_feedback_loose(value: str | Feedback) -> Feedback:
    if isinstance(value, tuple):
        return value
    s = normalize_token(str(value)).lower().strip()
    # Convert common separators to comma.
    for sep in [":", ";", "/", "\\", "-", "."]:
        s = s.replace(sep, ",")
    if " " in s:
        parts = [p for p in s.split() if p]
        if len(parts) == 2 and all(p.isdigit() and len(p) == 1 for p in parts):
            return int(parts[0]), int(parts[1])
    if re.fullmatch(r"\d,\d", s):
        return int(s[0]), int(s[2])
    return questline.parse_feedback(s)


def validate_guess_friendly(guess: str, lang: str) -> str:
    try:
        return questline.validate_code(guess)
    except Exception as exc:
        msg = str(exc).lower()
        if "repeat" in msg or "重复" in msg:
            raise ValueError(tr(lang, "digits_repeat")) from exc
        raise ValueError(tr(lang, "bad_code")) from exc


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
    print("  411           -> choose recommendation #4 with 1b1c")
    print("  306702        -> manual guess 3067 with 0b2c")
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
    # Standard first opening can be counted without loading the matrix.
    if len(history) == 1 and history[0][0] == getattr(questline, "OPENING_FIRST", "0123"):
        return FIRST_BRANCH_COUNTS.get(history[0][1])
    try:
        return len(solver.filter_candidates(history))
    except Exception:
        return None


def opening_read_from_remaining(remaining: Optional[int], fb: Optional[Feedback], lang: str) -> Optional[str]:
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
    if remaining < 100:
        return tr(lang, "lucky_break")
    return None


def pace_label(round_number: int, remaining: Optional[int], lang: str) -> str:
    if remaining is None:
        return tr(lang, "unknown")
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
        if remaining <= 80:
            return tr(lang, "slow")
        return tr(lang, "hard")
    if remaining <= 2:
        return tr(lang, "ahead")
    if remaining <= 8:
        return tr(lang, "normal_pace")
    if remaining <= 20:
        return tr(lang, "slow")
    return tr(lang, "hard")


def display_source(source: str, round_number: int, lang: str) -> str:
    if source == "QuestLine":
        return tr(lang, "source_questline")
    if source == "AVG":
        return tr(lang, "source_avg")
    if source == "MM":
        return tr(lang, "source_mm")
    if source == "Manual":
        return tr(lang, "source_manual")
    if source == "Conspiracy":
        return tr(lang, "source_conspiracy_opening") if round_number == 1 else tr(lang, "source_conspiracy_pick")
    return source


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
        # Standard opening book states should not trigger the full engine.
        if len(history) >= 2 and solver.feedback_matrix is None and not state.engine_notice_shown:
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
    phase = result.get("phase")

    # Opening states should stay lightweight: no AVG/MM, no matrix load.
    if phase == "opening_first":
        return [
            {"guess": getattr(questline, "OPENING_FIRST", "0123"), "source": "QuestLine", "score": 0},
            {"guess": "9876", "source": "Conspiracy", "score": 0},
        ]
    if phase == "opening_second":
        recs = result.get("recommendations", [])
        if recs:
            return [{"guess": recs[0]["guess"], "source": "QuestLine", "score": 0}]

    # QuestLine top 3
    for rec in result.get("recommendations", [])[:3]:
        guess = str(rec.get("guess")) if isinstance(rec, dict) and rec.get("guess") else None
        if guess and guess not in seen:
            item = dict(rec)
            item["source"] = "QuestLine"
            menu.append(item)
            seen.add(guess)

    candidates = result.get("candidates") or []
    if candidates:
        try:
            cand_idx = tuple(questline.CODE_TO_INDEX[c] for c in candidates)
            avg_i, avg_e, avg_m, avg_b = solver.best_pure_guess(cand_idx, "avg")
            avg_guess = questline.ALL_CODES[avg_i]
            if avg_guess not in seen:
                menu.append({"guess": avg_guess, "source": "AVG", "score": avg_e, "normal_expected": avg_e, "normal_max_bucket": avg_m, "bucket_count": avg_b, "trigger_bonus": 0, "brake_penalty": 0})
                seen.add(avg_guess)
            mm_i, mm_e, mm_m, mm_b = solver.best_pure_guess(cand_idx, "mm")
            mm_guess = questline.ALL_CODES[mm_i]
            if mm_guess not in seen:
                menu.append({"guess": mm_guess, "source": "MM", "score": mm_m, "normal_expected": mm_e, "normal_max_bucket": mm_m, "bucket_count": mm_b, "trigger_bonus": 0, "brake_penalty": 0})
                seen.add(mm_guess)
        except Exception:
            pass

    if candidates:
        for candidate in reversed(candidates):
            if candidate not in seen:
                menu.append({"guess": candidate, "source": "Conspiracy", "score": 0})
                seen.add(candidate)
                break

    return menu[:6]


def print_menu(menu: List[Dict[str, Any]], lang: str, round_number: int) -> None:
    print(f"[{tr(lang, 'recommendations')}]")
    for idx, item in enumerate(menu, 1):
        guess = item.get("guess", "????")
        source = display_source(str(item.get("source", "QuestLine")), round_number, lang)
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
        print(f"{tr(lang, 'remaining_possible')}: {remaining}")
        print(f"{tr(lang, 'direct_hit')}: {direct_hit_chance(remaining)}")
        if len(history) == 1:
            read = opening_read_from_remaining(remaining, history[0][1], lang)
            if read:
                print(f"{tr(lang, 'opening_read')}: {read}")
        elif round_number >= 3:
            print(f"{tr(lang, 'pace')}: {pace_label(round_number, remaining, lang)}")
    else:
        print(f"{tr(lang, 'remaining_possible')}: {tr(lang, 'unknown')}")
    print(f"{tr(lang, 'strategy')}: {strategy}")
    print_menu(menu, lang, round_number)


def find_menu_match(guess: str, menu: List[Dict[str, Any]]) -> Tuple[str, Optional[int]]:
    for idx, item in enumerate(menu, 1):
        if str(item.get("guess")) == guess:
            return str(item.get("source", "QuestLine")), idx
    return "Manual", None


def parse_turn_input(text: str, menu: List[Dict[str, Any]], lang: str) -> Tuple[str, Feedback, str, str, Optional[int]]:
    """Return (guess, feedback, source, input_mode, matched_menu_rank)."""
    original = text.strip()
    if not original:
        raise ValueError("empty input")
    if original.lstrip().startswith("{"):
        raise ValueError(tr(lang, "bad_json"))

    text = normalize_token(original)
    parts = [p for p in text.split() if p]

    # 6-digit compact manual input: 932840 -> 9328 + 4b0c
    if len(parts) == 1 and re.fullmatch(r"\d{6}", parts[0]):
        guess = validate_guess_friendly(parts[0][:4], lang)
        fb = parse_feedback_loose(parts[0][4:])
        source, rank = find_menu_match(guess, menu)
        return guess, fb, source, "manual", rank

    # Compact menu input: 411 -> #4 + 1b1c
    if len(parts) == 1 and re.fullmatch(r"\d{3}", parts[0]):
        choice = int(parts[0][0])
        if not (1 <= choice <= len(menu)):
            raise ValueError(f"MENU_RANGE::{len(menu)}")
        fb = parse_feedback_loose(parts[0][1:])
        item = menu[choice - 1]
        return str(item["guess"]), fb, str(item.get("source", "QuestLine")), "menu", choice

    # Menu input with punctuation: 1,03 / 1:03 / 1，03 -> #1 + 0b3c
    if len(parts) == 1:
        packed = normalize_token(parts[0])
        for sep in [",", ":", ";", "/", "\\", "-", "."]:
            if sep in packed:
                left, right = packed.split(sep, 1)
                if left.isdigit() and right.isdigit() and len(left) <= 2 and len(right) == 2:
                    choice = int(left)
                    if not (1 <= choice <= len(menu)):
                        raise ValueError(f"MENU_RANGE::{len(menu)}")
                    fb = parse_feedback_loose(right)
                    item = menu[choice - 1]
                    return str(item["guess"]), fb, str(item.get("source", "QuestLine")), "menu", choice

    # Feedback only: applies to #1.
    if len(parts) == 1:
        token = parts[0]
        if token.isdigit() and len(token) == 4:
            try:
                guess = validate_guess_friendly(token, lang)
                raise ValueError(tr(lang, "guess_missing_feedback", guess=guess))
            except ValueError as exc:
                # If the 4 digits are invalid, report that invalidity.
                if str(exc).startswith(token):
                    raise
                raise
        if token.isdigit() and len(token) == 1 and 1 <= int(token) <= len(menu):
            raise ValueError("menu number needs feedback, e.g. `2 1b2c`")
        fb = parse_feedback_loose(token)
        item = menu[0]
        return str(item["guess"]), fb, str(item.get("source", "QuestLine")), "default", 1

    # "guess 4 0" -> manual guess + feedback
    if len(parts) >= 3 and parts[0].isdigit() and len(parts[0]) == 4 and parts[1].isdigit() and parts[2].isdigit():
        guess = validate_guess_friendly(parts[0], lang)
        fb = parse_feedback_loose(parts[1] + parts[2])
        source, rank = find_menu_match(guess, menu)
        return guess, fb, source, "manual", rank

    # Menu pick: "2 1b2c"
    if parts[0].isdigit() and len(parts[0]) <= 2:
        choice = int(parts[0])
        if not (1 <= choice <= len(menu)):
            raise ValueError(f"MENU_RANGE::{len(menu)}")
        fb = parse_feedback_loose(" ".join(parts[1:]))
        item = menu[choice - 1]
        return str(item["guess"]), fb, str(item.get("source", "QuestLine")), "menu", choice

    # Manual external guess: "3846 1b2c"
    guess = validate_guess_friendly(parts[0], lang)
    fb = parse_feedback_loose(" ".join(parts[1:]))
    source, rank = find_menu_match(guess, menu)
    return guess, fb, source, "manual", rank


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
    print_menu(menu, lang, len(history) + 1)

    candidates = result.get("candidates") or []
    if candidates and len(candidates) <= 20:
        print()
        print("Candidates:" if lang == "en" else "残局候选：")
        for code in candidates:
            print(f"  {code}")


def save_replay(history: History, replay_rows: ReplayRows, jackpot: bool) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(f"questline_replay_{timestamp}.json")
    solved = bool(history and history[-1][1] == (4, 0))
    final_answer = history[-1][0] if solved else None
    data = {
        "project": "QuestLine",
        "saved_at": datetime.now().isoformat(),
        "solved": solved,
        "jackpot": jackpot,
        "final_answer": final_answer,
        "rounds": len(history),
        "history": replay_rows,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def ask_yes_no(prompt: str, lang: str, default_yes: bool = True, solved_context: bool = False) -> bool:
    while True:
        suffix = "" if prompt.endswith(" ") else " "
        text = input(prompt + suffix).strip().lower()
        if not text:
            return default_yes
        if text in {"y", "yes", "是", "好", "可以"}:
            return True
        if text in {"n", "no", "否", "不", "不用"}:
            return False
        if solved_context and text in {"undo", "back"}:
            print(tr(lang, "ended_no_undo"))
        else:
            print(tr(lang, "yn_only"))


def append_replay_row(history: History, replay_rows: ReplayRows, guess: str, fb: Feedback, source: str, mode: str, rank: Optional[int], solver: Any) -> None:
    remaining_after = candidate_count_for_display(solver, history)
    replay_rows.append({
        "round": len(history),
        "guess": guess,
        "feedback": fb_text(fb),
        "source": source,
        "input_mode": mode,
        "matched_menu_rank": rank,
        "remaining_after": remaining_after,
    })


def jackpot_message(source: str, lang: str) -> Optional[str]:
    if source == "QuestLine":
        return tr(lang, "jackpot_questline")
    if source == "Conspiracy":
        return tr(lang, "jackpot_conspiracy")
    if source == "Manual":
        return tr(lang, "jackpot_manual")
    return tr(lang, "jackpot_questline")


def solved_flow(history: History, replay_rows: ReplayRows, lang: str, jackpot: bool) -> bool:
    print()
    if jackpot:
        msg = jackpot_message(str(replay_rows[-1].get("source", "QuestLine")), lang)
        if msg:
            print(msg)
    print(f"{tr(lang, 'solved')}!")
    print(tr(lang, "solved_in", n=len(history)))
    print_history(history, lang)
    if ask_yes_no(tr(lang, "save_prompt"), lang, default_yes=False, solved_context=True):
        path = save_replay(history, replay_rows, jackpot)
        print(tr(lang, "saved", path=path))
    else:
        print(tr(lang, "not_saved"))
    return ask_yes_no(tr(lang, "new_game_prompt"), lang, default_yes=True, solved_context=True)


def try_replace_last_feedback(text: str, history: History, replay_rows: ReplayRows, solver: Any, lang: str) -> Optional[bool]:
    if not history:
        return None
    try:
        fb = parse_feedback_loose(text)
    except Exception:
        return None
    guess, _old = history[-1]
    history[-1] = (guess, fb)
    if replay_rows:
        replay_rows[-1]["feedback"] = fb_text(fb)
        replay_rows[-1]["remaining_after"] = candidate_count_for_display(solver, history)
    print(tr(lang, "corrected", guess=guess, fb=fb_text(fb)))
    if fb == (4, 0):
        jackpot = len(history) == 1
        return solved_flow(history, replay_rows, lang, jackpot)
    return None


def game_loop(lang: str, solver: Any) -> bool:
    """Run one game. Return True if user wants another game."""
    state = CliState()
    history: History = []
    replay_rows: ReplayRows = []

    while True:
        result = get_result_safe(solver, history, lang, state, top_k=12)
        if result is None:
            raw = input(f"{tr(lang, 'feedback_prompt')}: ").strip()
            cmd = raw.lower()
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
            replaced = try_replace_last_feedback(raw, history, replay_rows, solver, lang)
            if replaced is not None:
                return replaced
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
            guess, fb, source, input_mode, rank = parse_turn_input(raw, menu, lang)
        except Exception as exc:
            msg = str(exc)
            if msg.startswith("MENU_RANGE::"):
                n = int(msg.split("::", 1)[1])
                print(tr(lang, "invalid", err=tr(lang, "only_menu", n=n)))
            else:
                print(tr(lang, "invalid", err=exc))
            continue

        history.append((guess, fb))
        append_replay_row(history, replay_rows, guess, fb, source, input_mode, rank, solver)

        if fb == (4, 0):
            jackpot = len(history) == 1
            return solved_flow(history, replay_rows, lang, jackpot)


def choose_language(default: str = "zh") -> str:
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
    parser = argparse.ArgumentParser(description="QuestLine interactive CLI v1.2.3")
    parser.add_argument("--lang", choices=["zh", "en"], default=None, help="UI language.")
    args = parser.parse_args(argv)

    lang = args.lang or choose_language(default="zh")
    print_welcome(lang)

    # Reuse one solver for the whole CLI session, so the cache is loaded at most once.
    solver = questline.QuestLineSolver(verbose=True)

    keep_playing = True
    while keep_playing:
        keep_playing = game_loop(lang, solver)
    print(tr(lang, "bye"))


if __name__ == "__main__":
    main()
