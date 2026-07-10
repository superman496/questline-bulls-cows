
"""QuestLine CLI v1.2 standalone

Stable v1.2 interaction layer for the existing `questline.py` solver.

This is a standalone single-file version. It imports only `questline.py` and does
not depend on earlier CLI experiment files.

Included v1.2 features:
- Chinese / English UI
- multi-game loop
- undo / history / report / new / quit / help
- recommendation menu: QuestLine / AVG / MM / Conspiracy
- strict 2/3/6 digit input grammar
- duplicate-guess conflict checks
- full consistency check before accepting any input, including 4b0c
- jackpot messages
- logical-solved state with post-logic probing
- replay JSON with parsed_as, corrected, post_logic_probe, ui_language,
  logical_answer, logical_solved_at_round, verified_at_round,
  verification_delay_rounds, and post_logic_probe_count
- lightweight opening / jackpot saving: avoids unnecessary feedback-matrix loads
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

OPENING_FIRST = getattr(questline, "OPENING_FIRST", "0123")
OPENING_SECOND_BY_FEEDBACK = getattr(questline, "OPENING_SECOND_BY_FEEDBACK", {})

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
        "feedback": "反馈示例：40、4:0、4x0、4b0c、1，2、1、2、(1,2)",
        "commands": "指令：q/quit 退出，new/restart 新局，undo/back 撤回，history/h 历史，report/r 报告，help/? 帮助",
        "input_help": "输入语法：2位=反馈；3位=推荐编号+反馈；6位=手动猜法+反馈。例如 40、411、932840。",
        "round": "第 {n} 轮",
        "next": "默认下一手",
        "remaining": "剩余可能答案数量",
        "direct_hit": "直接命中率",
        "opening_read": "开局评价",
        "pace": "节奏评价",
        "strategy": "当前策略",
        "recommendations": "推荐面板",
        "prompt": "请输入",
        "history_title": "历史记录",
        "empty_history": "当前没有历史。",
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
        "direct_opening": "直接中了",
        "lucky": "撞大运了",
        "clean": "简单开局",
        "stable": "普通开局",
        "difficult": "困难开局",
        "rough": "天崩开局",
        "logic_solved": "逻辑已破案：唯一可能答案是 {answer}。输入 40 可确认解决，也可以继续手动验证。",
        "src_questline": "QuestLine",
        "src_avg": "AVG",
        "src_mm": "MM",
        "src_manual": "手动输入",
        "src_conspiracy_open": "阴谋论开局 / 平行世界线",
        "src_conspiracy": "阴谋论候选",
        "parsed_default": "已解析：默认 #1 {guess} -> {fb}（{source}）",
        "parsed_menu": "已解析：#{rank} {guess} -> {fb}（{source}）",
        "parsed_manual_match": "已解析：手动输入 {guess} -> {fb}（命中推荐 #{rank}：{source}）",
        "parsed_manual": "已解析：手动输入 {guess} -> {fb}（外部猜法）",
        "invalid": "输入错误：{err}",
        "bad_digits": "输入数字结构不合法。合法结构只有：2位反馈、3位推荐编号+反馈、6位猜法+反馈。",
        "bad_grouping": "输入结构不明确。手动猜法请使用 932840、9328 40 或 9328 4 0。",
        "bad_feedback": "反馈不合法：bull 和 cow 必须在 0-4，且 bull + cow <= 4。",
        "bad_guess": "猜测必须是 4 位不重复数字，允许 0 开头。",
        "digits_repeat": "猜测数字不能重复。",
        "guess_missing": "{guess} 看起来是一个合法猜法，但缺少反馈。请使用：{guess} 1b2c。",
        "menu_range": "当前只有 1-{n} 号推荐。请输入有效编号，例如：{n} 2b2c；也可以只输入反馈，默认使用 #1。",
        "duplicate_same": "{guess} 已经记录过 {fb}，重复输入没有新信息。",
        "duplicate_conflict": "{guess} 已经记录过 {old_fb}，不能再次记录为 {new_fb}。如需修正，请使用 undo。",
        "inconsistent": "当前没有任何候选答案，反馈历史存在矛盾。",
        "inconsistent_hint": "可以输入 undo/back 撤回，输入 new/restart 重开，或直接输入新的反馈来修正上一手。",
        "correction_prompt": "请继续输入新的反馈，或 undo 撤回上一手。",
        "corrected": "已将上一手修正为：{guess} -> {fb}",
        "correction_rejected": "修正后仍然没有候选答案，未保存该修正。",
        "input_rejected_inconsistent": "该输入会使候选答案数量变为 0，已拒绝。请检查反馈或使用 undo。",
        "removed": "已撤回：{guess} -> {fb}",
        "loading": "正在准备 QuestLine 推理引擎……",
        "report_title": "QuestLine 分析报告",
        "candidates": "残局候选：",
        "solved": "已解决！",
        "solved_in": "用 {n} 轮解决。",
        "jackpot_questline": "一击必杀！主线开局直接命中，你就是天选之人。",
        "jackpot_conspiracy": "阴谋论开局一击命中！平行世界线直接成为主世界。",
        "jackpot_manual": "手动开局一击命中！这不是猜测，这是预言。",
        "save_prompt": "是否保存复盘 JSON？[y/N]",
        "new_prompt": "开始新一局？[Y/n]",
        "saved": "复盘已保存到 {path}",
        "not_saved": "未保存复盘。",
        "yn_only": "请输入 y 或 n。",
        "ended_no_undo": "这一局已经结束。请输入 y 开始新局，或 n 退出。",
        "restart": "开始新一局。",
        "bye": "再见。",
        "help_title": "帮助",
    },
    "en": {
        "title": "QuestLine",
        "subtitle": "A narrative-driven Bulls & Cows solver.",
        "slogan": "Follow the strongest story. Distrust coincidence.",
        "rules": "Rules: 4 distinct digits, leading zero allowed.",
        "feedback": "Feedback examples: 40, 4:0, 4x0, 4b0c, 1,2, (1,2)",
        "commands": "Commands: q/quit, new/restart, undo/back, history/h, report/r, help/?",
        "input_help": "Input grammar: 2 digits=feedback; 3 digits=menu+feedback; 6 digits=manual guess+feedback. Examples: 40, 411, 932840.",
        "round": "Round {n}",
        "next": "Default next guess",
        "remaining": "Remaining possible answers",
        "direct_hit": "Direct hit chance",
        "opening_read": "Opening read",
        "pace": "Pace",
        "strategy": "Strategy",
        "recommendations": "Recommendations",
        "prompt": "Your input",
        "history_title": "History",
        "empty_history": "History is empty.",
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
        "direct_opening": "Direct hit",
        "lucky": "Lucky break",
        "clean": "Clean line",
        "stable": "Stable line",
        "difficult": "Difficult line",
        "rough": "Rough start",
        "logic_solved": "Logically solved: the only possible answer is {answer}. Enter 40 to confirm, or keep probing manually.",
        "src_questline": "QuestLine",
        "src_avg": "AVG",
        "src_mm": "MM",
        "src_manual": "Manual",
        "src_conspiracy_open": "Conspiracy / alternate opening",
        "src_conspiracy": "Conspiracy Pick",
        "parsed_default": "Parsed: default #1 {guess} -> {fb} ({source})",
        "parsed_menu": "Parsed: #{rank} {guess} -> {fb} ({source})",
        "parsed_manual_match": "Parsed: manual {guess} -> {fb} (matched #{rank}: {source})",
        "parsed_manual": "Parsed: manual {guess} -> {fb} (external guess)",
        "invalid": "Input error: {err}",
        "bad_digits": "Invalid digit structure. Valid structures are: 2 feedback digits, 3 menu+feedback digits, or 6 guess+feedback digits.",
        "bad_grouping": "Ambiguous input structure. Use 932840, 9328 40, or 9328 4 0 for manual guesses.",
        "bad_feedback": "Invalid feedback: bull and cow must be 0-4, and bull + cow <= 4.",
        "bad_guess": "Guess must be 4 distinct digits from 0-9, leading zero allowed.",
        "digits_repeat": "digits must not repeat.",
        "guess_missing": "{guess} looks like a valid guess, but feedback is missing. Use: {guess} 1b2c.",
        "menu_range": "Only recommendations #1-#{n} are available. Use `{n} 2b2c`, or enter feedback only for #1.",
        "duplicate_same": "{guess} has already been recorded as {fb}. Repeating it adds no new information.",
        "duplicate_conflict": "{guess} was already recorded as {old_fb}; it cannot also be {new_fb}. Use undo if the previous feedback was wrong.",
        "inconsistent": "No candidates remain. The feedback history is inconsistent.",
        "inconsistent_hint": "Type undo/back, new/restart, or enter a new feedback to replace the last feedback.",
        "correction_prompt": "Enter another feedback or use undo.",
        "corrected": "Corrected last move to: {guess} -> {fb}",
        "correction_rejected": "The correction still leaves no candidates, so it was not saved.",
        "input_rejected_inconsistent": "This input would leave zero possible answers, so it was rejected. Check the feedback or use undo.",
        "removed": "Removed: {guess} -> {fb}",
        "loading": "Preparing QuestLine reasoning engine...",
        "report_title": "QuestLine report",
        "candidates": "Candidates:",
        "solved": "Solved!",
        "solved_in_one": "Solved in 1 round.",
        "solved_in_many": "Solved in {n} rounds.",
        "jackpot_questline": "Jackpot! The main QuestLine hit the answer on the first guess. You are the chosen one.",
        "jackpot_conspiracy": "Conspiracy jackpot! The alternate timeline became the main world.",
        "jackpot_manual": "Manual jackpot! That was not a guess. That was a prophecy.",
        "save_prompt": "Save replay JSON? [y/N]",
        "new_prompt": "Start a new game? [Y/n]",
        "saved": "Saved replay to {path}",
        "not_saved": "Replay not saved.",
        "yn_only": "Please answer y or n.",
        "ended_no_undo": "This game is already solved. Use y to start a new game or n to quit.",
        "restart": "Starting a new game.",
        "bye": "Goodbye.",
        "help_title": "Help",
    },
}


def tr(lang: str, key: str, **kwargs: Any) -> str:
    return TEXT.get(lang, TEXT["en"]).get(key, key).format(**kwargs)


def solved_in_text(lang: str, n: int) -> str:
    if lang == "zh":
        return tr(lang, "solved_in", n=n)
    if n == 1:
        return tr(lang, "solved_in_one")
    return tr(lang, "solved_in_many", n=n)


def fb_text(fb: Feedback) -> str:
    return questline.fb_to_str(fb)


def digit_groups(raw: str) -> List[str]:
    return re.findall(r"\d+", raw)


def all_digits(groups: List[str]) -> str:
    return "".join(groups)


def validate_feedback_digits(b: str, c: str, lang: str) -> Feedback:
    if not (b.isdigit() and c.isdigit() and len(b) == 1 and len(c) == 1):
        raise ValueError(tr(lang, "bad_feedback"))
    bull, cow = int(b), int(c)
    if not (0 <= bull <= 4 and 0 <= cow <= 4 and bull + cow <= 4):
        raise ValueError(tr(lang, "bad_feedback"))
    return bull, cow


def validate_guess_digits(guess: str, lang: str) -> str:
    if not (guess.isdigit() and len(guess) == 4):
        raise ValueError(tr(lang, "bad_guess"))
    if len(set(guess)) != 4:
        raise ValueError(tr(lang, "digits_repeat"))
    return guess


def parse_2_feedback(groups: List[str], lang: str) -> Feedback:
    if len(groups) == 1 and len(groups[0]) == 2:
        return validate_feedback_digits(groups[0][0], groups[0][1], lang)
    if len(groups) == 2 and len(groups[0]) == 1 and len(groups[1]) == 1:
        return validate_feedback_digits(groups[0], groups[1], lang)
    raise ValueError(tr(lang, "bad_digits"))


def parse_3_menu(groups: List[str], menu_len: int, lang: str) -> Tuple[int, Feedback]:
    if len(groups) == 1 and len(groups[0]) == 3:
        choice, b, c = groups[0][0], groups[0][1], groups[0][2]
    elif len(groups) == 2 and len(groups[0]) == 1 and len(groups[1]) == 2:
        choice, b, c = groups[0], groups[1][0], groups[1][1]
    elif len(groups) == 3 and all(len(g) == 1 for g in groups):
        choice, b, c = groups
    else:
        raise ValueError(tr(lang, "bad_digits"))
    choice_i = int(choice)
    if not (1 <= choice_i <= menu_len):
        raise ValueError("MENU_RANGE")
    return choice_i, validate_feedback_digits(b, c, lang)


def parse_6_manual(groups: List[str], lang: str) -> Tuple[str, Feedback]:
    if len(groups) == 1 and len(groups[0]) == 6:
        guess, b, c = groups[0][:4], groups[0][4], groups[0][5]
    elif len(groups) == 2 and len(groups[0]) == 4 and len(groups[1]) == 2:
        guess, b, c = groups[0], groups[1][0], groups[1][1]
    elif len(groups) == 3 and len(groups[0]) == 4 and len(groups[1]) == 1 and len(groups[2]) == 1:
        guess, b, c = groups[0], groups[1], groups[2]
    else:
        raise ValueError(tr(lang, "bad_grouping"))
    return validate_guess_digits(guess, lang), validate_feedback_digits(b, c, lang)


def parse_numeric_input(raw: str, menu_len: int, lang: str) -> Tuple[Any, ...]:
    groups = digit_groups(raw)
    digits = all_digits(groups)
    if not digits:
        raise ValueError(tr(lang, "bad_digits"))
    if len(digits) == 2:
        return "feedback", parse_2_feedback(groups, lang)
    if len(digits) == 3:
        choice, fb = parse_3_menu(groups, menu_len, lang)
        return "menu", choice, fb
    if len(digits) == 4:
        guess = validate_guess_digits(digits, lang)
        raise ValueError(tr(lang, "guess_missing", guess=guess))
    if len(digits) == 6:
        guess, fb = parse_6_manual(groups, lang)
        return "manual", guess, fb
    raise ValueError(tr(lang, "bad_digits"))


def source_label(source: str, round_number: int, lang: str) -> str:
    if source == "QuestLine": return tr(lang, "src_questline")
    if source == "AVG": return tr(lang, "src_avg")
    if source == "MM": return tr(lang, "src_mm")
    if source == "Manual": return tr(lang, "src_manual")
    if source == "Conspiracy": return tr(lang, "src_conspiracy_open") if round_number == 1 else tr(lang, "src_conspiracy")
    return source


def direct_hit(remaining: Optional[int]) -> str:
    if not remaining or remaining <= 0:
        return "?"
    return f"1/{remaining} = {100.0 / remaining:.2f}%"


def candidate_indexes(solver: Any, history: History) -> Tuple[int, ...]:
    if not history:
        return tuple(range(len(questline.ALL_CODES)))
    return solver.filter_candidates(history)


def candidate_count(solver: Any, history: History) -> Optional[int]:
    if not history:
        return len(questline.ALL_CODES)
    if len(history) == 1:
        return FIRST_BRANCH_COUNTS.get(history[0][1])
    try:
        return len(candidate_indexes(solver, history))
    except Exception:
        return None


def unique_answer(solver: Any, history: History) -> Optional[str]:
    if not history:
        return None
    try:
        idxs = candidate_indexes(solver, history)
        if len(idxs) == 1:
            return questline.ALL_CODES[idxs[0]]
    except Exception:
        return None
    return None


def history_has_candidates(solver: Any, history: History) -> bool:
    cnt = candidate_count(solver, history)
    return bool(cnt and cnt > 0)


def opening_read(remaining: Optional[int], fb: Feedback, lang: str) -> Optional[str]:
    if remaining is None: return tr(lang, "unknown")
    if fb == (4, 0) or remaining == 1: return tr(lang, "direct_opening")
    if remaining == 1440: return tr(lang, "rough")
    if remaining == 1260: return tr(lang, "difficult")
    if remaining == 720: return tr(lang, "stable")
    if 100 <= remaining < 720: return tr(lang, "clean")
    if remaining < 100: return tr(lang, "lucky")
    return None


def pace(round_number: int, remaining: Optional[int], lang: str) -> str:
    if remaining is None: return tr(lang, "unknown")
    if round_number <= 2: return tr(lang, "normal_pace")
    if round_number == 3:
        if remaining <= 15: return tr(lang, "ahead")
        if remaining <= 80: return tr(lang, "normal_pace")
        if remaining <= 150: return tr(lang, "slow")
        return tr(lang, "hard")
    if round_number == 4:
        if remaining <= 4: return tr(lang, "ahead")
        if remaining <= 20: return tr(lang, "normal_pace")
        if remaining <= 80: return tr(lang, "slow")
        return tr(lang, "hard")
    if remaining <= 2: return tr(lang, "ahead")
    if remaining <= 8: return tr(lang, "normal_pace")
    if remaining <= 20: return tr(lang, "slow")
    return tr(lang, "hard")


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
    print(f"\n[{tr(lang, 'help_title')}]")
    print(tr(lang, "feedback"))
    print(tr(lang, "commands"))
    print(tr(lang, "input_help"))
    print("  40       -> #1 + 4b0c")
    print("  411      -> #4 + 1b1c")
    print("  932840   -> manual 9328 + 4b0c")
    print("  9328 4 0 -> manual 9328 + 4b0c")


def print_history(history: History, lang: str) -> None:
    print(f"[{tr(lang, 'history_title')}]")
    if not history:
        print(tr(lang, "empty_history")); return
    for i, (g, fb) in enumerate(history, 1):
        print(f"  {i}. {g} -> {fb_text(fb)}")


class CliState:
    def __init__(self, debug: bool = False) -> None:
        self.engine_notice_shown = False
        self.in_recovery = False
        self.debug = debug


def synthetic_opening_result(history: History) -> Optional[Dict[str, Any]]:
    if not history:
        return {"phase": "opening_first", "candidates": [], "recommendations": [{"guess": OPENING_FIRST, "source": "QuestLine", "score": 0}]}
    if len(history) == 1 and history[0][0] == OPENING_FIRST:
        second = OPENING_SECOND_BY_FEEDBACK.get(history[0][1])
        if second:
            return {"phase": "opening_second", "candidates": [], "recommendations": [{"guess": second, "source": "QuestLine", "score": 0}]}
    return None


def get_result(solver: Any, history: History, lang: str, state: CliState, top_k: int = 12) -> Optional[Dict[str, Any]]:
    synthetic = synthetic_opening_result(history)
    if synthetic is not None:
        state.in_recovery = False
        return synthetic
    try:
        if solver.feedback_matrix is None and not state.engine_notice_shown:
            print(tr(lang, "loading"))
            state.engine_notice_shown = True
        result = solver.choose(history, top_k=top_k)
        state.in_recovery = False
        return result
    except Exception as exc:
        if not state.in_recovery:
            print()
            print(tr(lang, "inconsistent"))
            print(tr(lang, "inconsistent_hint"))
            state.in_recovery = True
        if state.debug:
            print(f"Debug: {exc}")
        return None


def strategy_state(result: Dict[str, Any], lang: str) -> str:
    phase = result.get("phase")
    recs = result.get("recommendations", [])
    top = recs[0] if recs else {}
    if phase in {"opening_first", "opening_second"}: return tr(lang, "opening_book")
    if phase == "endgame": return tr(lang, "endgame")
    if result.get("fallback_mode"): return tr(lang, "fallback")
    if isinstance(top, dict):
        if top.get("trigger_bonus", 0) > 0: return tr(lang, "push")
        if top.get("brake_penalty", 0) > 0: return tr(lang, "brake")
    return tr(lang, "normal")


def build_menu(solver: Any, result: Dict[str, Any], history: History) -> List[Dict[str, Any]]:
    phase = result.get("phase")
    if phase == "opening_first":
        return [{"guess": OPENING_FIRST, "source": "QuestLine", "score": 0}, {"guess": "9876", "source": "Conspiracy", "score": 0}]
    if phase == "opening_second":
        rec = result["recommendations"][0]
        return [{"guess": rec["guess"], "source": "QuestLine", "score": 0}]
    menu: List[Dict[str, Any]] = []
    seen = set()
    for rec in result.get("recommendations", [])[:3]:
        guess = str(rec.get("guess")) if isinstance(rec, dict) and rec.get("guess") else None
        if guess and guess not in seen:
            item = dict(rec); item["source"] = "QuestLine"; menu.append(item); seen.add(guess)
    candidates = result.get("candidates") or []
    if candidates:
        try:
            cand_idx = tuple(questline.CODE_TO_INDEX[c] for c in candidates)
            avg_i, avg_e, avg_m, avg_b = solver.best_pure_guess(cand_idx, "avg")
            avg_guess = questline.ALL_CODES[avg_i]
            if avg_guess not in seen:
                menu.append({"guess": avg_guess, "source": "AVG", "score": avg_e, "normal_expected": avg_e, "normal_max_bucket": avg_m, "bucket_count": avg_b, "trigger_bonus": 0, "brake_penalty": 0}); seen.add(avg_guess)
            mm_i, mm_e, mm_m, mm_b = solver.best_pure_guess(cand_idx, "mm")
            mm_guess = questline.ALL_CODES[mm_i]
            if mm_guess not in seen:
                menu.append({"guess": mm_guess, "source": "MM", "score": mm_m, "normal_expected": mm_e, "normal_max_bucket": mm_m, "bucket_count": mm_b, "trigger_bonus": 0, "brake_penalty": 0}); seen.add(mm_guess)
        except Exception:
            pass
        for candidate in reversed(candidates):
            if candidate not in seen:
                menu.append({"guess": candidate, "source": "Conspiracy", "score": 0}); seen.add(candidate); break
    return menu[:6]


def print_menu(menu: List[Dict[str, Any]], lang: str, round_number: int) -> None:
    print(f"[{tr(lang, 'recommendations')}]")
    for i, item in enumerate(menu, 1):
        src = source_label(str(item.get("source", "QuestLine")), round_number, lang)
        guess = item.get("guess", "????")
        exp = item.get("normal_expected")
        if isinstance(exp, (int, float)) and exp:
            print(f"  {i}. {guess}  [{src}]  AVG={exp:.2f} max={item.get('normal_max_bucket')} trig={item.get('trigger_bonus',0):.2f} brake={item.get('brake_penalty',0):.3f}")
        else:
            print(f"  {i}. {guess}  [{src}]")


def print_turn(solver: Any, history: History, result: Dict[str, Any], menu: List[Dict[str, Any]], lang: str) -> None:
    round_number = len(history) + 1
    rem = candidate_count(solver, history)
    print()
    print(tr(lang, "round", n=round_number))
    print(f"{tr(lang, 'next')}: {menu[0]['guess']}")
    if rem is not None:
        print(f"{tr(lang, 'remaining')}: {rem}")
        print(f"{tr(lang, 'direct_hit')}: {direct_hit(rem)}")
        if len(history) == 1:
            read = opening_read(rem, history[0][1], lang)
            if read: print(f"{tr(lang, 'opening_read')}: {read}")
        elif round_number >= 3:
            print(f"{tr(lang, 'pace')}: {pace(round_number, rem, lang)}")
    else:
        print(f"{tr(lang, 'remaining')}: {tr(lang, 'unknown')}")
    ans = unique_answer(solver, history) if rem == 1 else None
    if ans and not (history and history[-1][1] == (4, 0)):
        print(tr(lang, "logic_solved", answer=ans))
    print(f"{tr(lang, 'strategy')}: {strategy_state(result, lang)}")
    print_menu(menu, lang, round_number)


def print_report(solver: Any, history: History, lang: str, state: CliState) -> None:
    result = get_result(solver, history, lang, state, top_k=12)
    if result is None: return
    print(f"\n[{tr(lang, 'report_title')}]")
    print_history(history, lang)
    rem = candidate_count(solver, history)
    if rem is not None:
        print(f"{tr(lang, 'remaining')}: {rem}")
        print(f"{tr(lang, 'direct_hit')}: {direct_hit(rem)}")
    ans = unique_answer(solver, history) if rem == 1 else None
    if ans:
        print(tr(lang, "logic_solved", answer=ans))
    anchor = result.get("avg_anchor")
    if anchor:
        print(f"AVG: {anchor['guess']} exp={anchor['exp']:.3f} max={anchor['max']} buckets={anchor['bucket_count']}")
    menu = build_menu(solver, result, history)
    print_menu(menu, lang, len(history)+1)
    candidates = result.get("candidates") or []
    if candidates and len(candidates) <= 20:
        print(f"\n{tr(lang, 'candidates')}")
        for code in candidates: print(f"  {code}")


def find_menu_match(guess: str, menu: List[Dict[str, Any]]) -> Tuple[str, Optional[int]]:
    for i, item in enumerate(menu, 1):
        if str(item.get("guess")) == guess:
            return str(item.get("source", "QuestLine")), i
    return "Manual", None


def duplicate_error(history: History, guess: str, fb: Feedback, lang: str) -> Optional[str]:
    for old_guess, old_fb in history:
        if old_guess == guess:
            if old_fb == fb:
                return tr(lang, "duplicate_same", guess=guess, fb=fb_text(fb))
            return tr(lang, "duplicate_conflict", guess=guess, old_fb=fb_text(old_fb), new_fb=fb_text(fb))
    return None


def parse_turn_input(raw: str, menu: List[Dict[str, Any]], lang: str) -> Tuple[str, Feedback, str, str, Optional[int]]:
    kind = parse_numeric_input(raw, len(menu), lang)
    if kind[0] == "feedback":
        fb = kind[1]
        item = menu[0]
        return str(item["guess"]), fb, str(item.get("source", "QuestLine")), "default", 1
    if kind[0] == "menu":
        _, choice, fb = kind
        item = menu[choice-1]
        return str(item["guess"]), fb, str(item.get("source", "QuestLine")), "menu", choice
    if kind[0] == "manual":
        _, guess, fb = kind
        source, rank = find_menu_match(guess, menu)
        return guess, fb, source, "manual", rank
    raise ValueError(tr(lang, "bad_digits"))


def parsed_line(guess: str, fb: Feedback, source: str, mode: str, rank: Optional[int], lang: str, round_number: int) -> str:
    src = source_label(source, round_number, lang)
    if mode == "default":
        return tr(lang, "parsed_default", guess=guess, fb=fb_text(fb), source=src)
    if mode == "menu":
        return tr(lang, "parsed_menu", rank=rank, guess=guess, fb=fb_text(fb), source=src)
    if mode == "manual" and rank is not None:
        return tr(lang, "parsed_manual_match", guess=guess, fb=fb_text(fb), rank=rank, source=src)
    return tr(lang, "parsed_manual", guess=guess, fb=fb_text(fb))


def append_replay(history: History, replay: ReplayRows, guess: str, fb: Feedback, source: str, mode: str, rank: Optional[int], solver: Any, parsed_as: str, post_logic_probe: bool, corrected: bool = False) -> None:
    replay.append({
        "round": len(history),
        "guess": guess,
        "feedback": fb_text(fb),
        "source": source,
        "input_mode": mode,
        "matched_menu_rank": rank,
        "parsed_as": parsed_as,
        "corrected": corrected,
        "post_logic_probe": post_logic_probe,
        "remaining_after": candidate_count(solver, history),
    })


def save_replay(history: History, replay: ReplayRows, solver: Any, jackpot: bool, lang: str) -> Path:
    path = Path(f"questline_replay_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    solved = bool(history and history[-1][1] == (4,0))
    final_answer = history[-1][0] if solved else None
    logical_answer = None
    logical_round = None
    for row in replay:
        if row.get("remaining_after") == 1:
            logical_round = int(row.get("round", 0)) or None
            if row.get("feedback") == "4b0c":
                logical_answer = str(row.get("guess"))
            elif solved:
                logical_answer = final_answer
            break
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


def ask_yes_no(prompt: str, lang: str, default_yes: bool, solved_context: bool = False) -> bool:
    while True:
        ans = input(prompt + " ").strip().lower()
        if not ans: return default_yes
        if ans in {"y", "yes", "是", "好", "可以"}: return True
        if ans in {"n", "no", "否", "不", "不用"}: return False
        if solved_context and ans in {"undo", "back"}: print(tr(lang, "ended_no_undo"))
        else: print(tr(lang, "yn_only"))


def jackpot_msg(source: str, lang: str) -> str:
    if source == "Conspiracy": return tr(lang, "jackpot_conspiracy")
    if source == "Manual": return tr(lang, "jackpot_manual")
    return tr(lang, "jackpot_questline")


def solved_flow(history: History, replay: ReplayRows, solver: Any, lang: str, jackpot: bool) -> bool:
    print()
    if jackpot:
        print(jackpot_msg(str(replay[-1].get("source", "QuestLine")), lang))
    print(tr(lang, "solved"))
    print(solved_in_text(lang, len(history)))
    print_history(history, lang)
    if ask_yes_no(tr(lang, "save_prompt"), lang, default_yes=False, solved_context=True):
        print(tr(lang, "saved", path=save_replay(history, replay, solver, jackpot, lang)))
    else:
        print(tr(lang, "not_saved"))
    return ask_yes_no(tr(lang, "new_prompt"), lang, default_yes=True, solved_context=True)


def try_replace_last(raw: str, history: History, replay: ReplayRows, solver: Any, lang: str) -> Optional[bool]:
    if not history: return None
    try:
        kind = parse_numeric_input(raw, 1, lang)
        if kind[0] != "feedback": return None
        fb = kind[1]
    except Exception:
        return None
    old_guess, old_fb = history[-1]
    old_replay = dict(replay[-1]) if replay else None
    history[-1] = (old_guess, fb)
    if not history_has_candidates(solver, history):
        history[-1] = (old_guess, old_fb)
        if replay and old_replay is not None:
            replay[-1] = old_replay
        print(tr(lang, "correction_rejected"))
        return None
    if replay:
        row = replay[-1]
        mode = str(row.get("input_mode", "manual"))
        source = str(row.get("source", "Manual"))
        rank = row.get("matched_menu_rank")
        row["feedback"] = fb_text(fb)
        row["remaining_after"] = candidate_count(solver, history)
        row["corrected"] = True
        row["parsed_as"] = parsed_line(old_guess, fb, source, mode, rank, lang, len(history))
    print(tr(lang, "corrected", guess=old_guess, fb=fb_text(fb)))
    if fb == (4,0):
        return solved_flow(history, replay, solver, lang, jackpot=len(history)==1)
    return None


def game_loop(lang: str, solver: Any, debug: bool = False) -> bool:
    state = CliState(debug=debug)
    history: History = []
    replay: ReplayRows = []
    while True:
        result = get_result(solver, history, lang, state, top_k=12)
        if result is None:
            raw = input(f"{tr(lang, 'prompt')}: ").strip()
            low = raw.lower()
            if low in {"q", "quit", "exit"}: return False
            if low in {"new", "restart"}: print(tr(lang, "restart")); return True
            if low in {"undo", "back"}:
                if history:
                    g, fb = history.pop()
                    if replay: replay.pop()
                    print(tr(lang, "removed", guess=g, fb=fb_text(fb)))
                else: print(tr(lang, "empty_history"))
                continue
            if low in {"h", "history"}: print_history(history, lang); continue
            replaced = try_replace_last(raw, history, replay, solver, lang)
            if replaced is not None: return replaced
            print(tr(lang, "correction_prompt")); continue
        menu = build_menu(solver, result, history)
        print_turn(solver, history, result, menu, lang)
        raw = input(f"{tr(lang, 'prompt')}: ").strip()
        low = raw.lower()
        if low in {"q", "quit", "exit"}: return False
        if low in {"new", "restart"}: print(tr(lang, "restart")); return True
        if low in {"help", "?"}: print_help(lang); continue
        if low in {"h", "history"}: print_history(history, lang); continue
        if low in {"r", "report"}: print_report(solver, history, lang, state); continue
        if low in {"undo", "back"}:
            if history:
                g, fb = history.pop()
                if replay: replay.pop()
                print(tr(lang, "removed", guess=g, fb=fb_text(fb)))
            else: print(tr(lang, "empty_history"))
            continue
        try:
            guess, fb, source, mode, rank = parse_turn_input(raw, menu, lang)
            dup = duplicate_error(history, guess, fb, lang)
            if dup: raise ValueError(dup)
        except Exception as exc:
            msg = str(exc)
            if msg == "MENU_RANGE": print(tr(lang, "invalid", err=tr(lang, "menu_range", n=len(menu))))
            else: print(tr(lang, "invalid", err=exc))
            continue
        logical_before = unique_answer(solver, history) if candidate_count(solver, history) == 1 else None
        post_logic_probe = bool(logical_before and not (guess == logical_before and fb == (4,0)))
        trial = history + [(guess, fb)]
        if not history_has_candidates(solver, trial):
            print(tr(lang, "input_rejected_inconsistent"))
            continue
        history.append((guess, fb))
        pline = parsed_line(guess, fb, source, mode, rank, lang, len(history))
        print(pline)
        append_replay(history, replay, guess, fb, source, mode, rank, solver, pline, post_logic_probe)
        if fb == (4,0):
            return solved_flow(history, replay, solver, lang, jackpot=len(history)==1)


def choose_language(default: str = "zh") -> str:
    print("Choose language / 选择语言:")
    print("  1. 中文")
    print("  2. English")
    raw = input("> ").strip().lower()
    if raw in {"1", "zh", "cn", "chinese", "中文"}: return "zh"
    if raw in {"2", "en", "english"}: return "en"
    return default


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="QuestLine interactive CLI v1.2 stable")
    parser.add_argument("--lang", choices=["zh", "en"], default=None)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    lang = args.lang or choose_language("zh")
    print_welcome(lang)
    solver = questline.QuestLineSolver(verbose=True)
    keep = True
    while keep:
        keep = game_loop(lang, solver, debug=args.debug)
    print(tr(lang, "bye"))


if __name__ == "__main__":
    main()
