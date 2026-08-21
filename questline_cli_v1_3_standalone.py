
"""QuestLine CLI v1.3 standalone

Stable v1.3 interaction layer for the existing `questline.py` solver.

This is a standalone single-file version. It imports only `questline.py` and does
not depend on earlier CLI experiment files.

Included v1.3 features:
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
import random
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
        "commands": "指令：q/quit 退出，new/restart 新局，undo/back 撤回，history/h 历史，story/book 故事书，report/r 报告，save/replay/export，help/? 帮助",
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
        "commands": "Commands: q/quit, new/restart, undo/back, history/h, story/book, report/r, save/replay/export, help/?",
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
    print("  story    -> read the readable case book")
    print("  book     -> read the readable case book")
    print("  book full -> read the complete audit case book")
    print("  save     -> save the current replay JSON")
    print("  replay   -> print structured replay JSON")
    print("  export   -> export the current case as Markdown")
    print("  --mode assist      -> 协查模式：用户行动，引擎解释")
    print("  --mode simulation  -> 推演模式：用户给出答案，引擎行动")
    print("  --mode adventure   -> 冒险模式：系统出题，用户行动")


def print_history(history: History, lang: str) -> None:
    print(f"[{tr(lang, 'history_title')}]")
    if not history:
        print(tr(lang, "empty_history")); return
    for i, (g, fb) in enumerate(history, 1):
        print(f"  {i}. {g} -> {fb_text(fb)}")


def print_story(history: History, solver: Any, lang: str, audit: bool = False) -> None:
    """Print the readable book, or the complete audit book when requested."""
    book = questline.StoryBook.from_history(history, solver=solver)
    print(book.render_audit() if audit else book.render())


def save_case_json(history: History, replay: ReplayRows, solver: Any, lang: str) -> Path:
    path = Path(f"questline_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    data = {
        "project": "QuestLine",
        "ui_language": lang,
        "mode": "assist",
        "history": [(guess, fb_text(feedback)) for guess, feedback in history],
        "replay": replay,
        "story": questline.StoryBook.from_history(history, solver=solver).to_dict(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_case_markdown(history: History, solver: Any) -> Path:
    path = Path(f"questline_case_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
    path.write_text(
        questline.StoryBook.from_history(history, solver=solver).render_audit(),
        encoding="utf-8",
    )
    return path


def print_replay_json(history: History, replay: ReplayRows, solver: Any) -> None:
    payload = {
        "history": [(guess, fb_text(feedback)) for guess, feedback in history],
        "accepted": replay,
        "story": questline.StoryBook.from_history(history, solver=solver).to_dict(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def handle_case_command(command: str, history: History, replay: ReplayRows, solver: Any, lang: str) -> bool:
    """Handle non-mutating case inspection and export commands."""
    if command == "save":
        print(tr(lang, "saved", path=save_case_json(history, replay, solver, lang)))
    elif command == "replay":
        print_replay_json(history, replay, solver)
    elif command == "export":
        path = export_case_markdown(history, solver)
        print(f"已导出案件 Markdown：{path}" if lang == "zh" else f"Case Markdown exported: {path}")
    else:
        return False
    return True


def story_answer(rng: Optional[random.Random] = None) -> str:
    """Create a hidden answer for the system-led story mode."""
    source = rng or random
    return "".join(source.sample(list("0123456789"), 4))


def story_feedback(answer: str, guess: str) -> Feedback:
    """Return truthful feedback for a story-mode guess."""
    return questline.raw_feedback(answer, guess)


def story_game_loop(lang: str, solver: Any, answer: Optional[str] = None, rng: Optional[random.Random] = None) -> bool:
    """Run a system-led game where each guess advances the case book."""
    hidden_answer = answer or story_answer(rng)
    session = questline.GameSession(mode="adventure", solver=solver, answer=hidden_answer)
    print("\n[冒险模式]" if lang == "zh" else "\n[Adventure mode]")
    print("系统已经建立案件。请输入 4 位不重复数字开始调查。" if lang == "zh" else "The case is ready. Enter four distinct digits to investigate.")
    while True:
        try:
            raw = input("猜测 / Guess: ").strip()
        except EOFError:
            return False
        low = raw.lower()
        if low in {"q", "quit", "exit"}:
            return False
        if low in {"story", "book"}:
            print(session.read_story())
            continue
        if low in {"book full", "book+", "audit"}:
            print(session.story.render_audit())
            continue
        if low in {"h", "help", "?"}:
            print("输入 4 位不重复数字；story/book 查看故事；q 退出。" if lang == "zh" else "Enter four distinct digits; story/book reads the case; q quits.")
            continue
        try:
            guess = validate_guess_digits(raw, lang)
        except ValueError as exc:
            print(tr(lang, "invalid", err=exc))
            continue
        if any(previous_guess == guess for previous_guess, _ in session.history):
            print(tr(lang, "duplicate_same", guess=guess, fb=""))
            continue
        feedback = story_feedback(hidden_answer, guess)
        event = session.apply_turn(guess, feedback, source="Manual")
        print(f"反馈 / Feedback: {fb_text(feedback)}")
        print(event["narrative"])
        if feedback == (4, 0):
            print("\n案件告破。" if lang == "zh" else "\nCase solved.")
            print(session.read_story())
            return True


def explore_game_loop(lang: str, solver: Any, answer: Optional[str] = None, max_steps: int = 10) -> bool:
    """Run an engine-led exploration against a user-supplied hidden answer."""
    if answer is None:
        while True:
            try:
                answer = validate_guess_digits(input("答案 / Hidden answer: ").strip(), lang)
                break
            except EOFError:
                return False
            except ValueError as exc:
                print(tr(lang, "invalid", err=exc))
    else:
        answer = validate_guess_digits(answer, lang)

    session = questline.GameSession(mode="simulation", solver=solver, answer=answer)
    print("\n[推演模式]" if lang == "zh" else "\n[Simulation mode]")
    print("答案已锁定，由引擎负责推进调查。" if lang == "zh" else "The answer is locked; the engine will lead the investigation.")
    for _ in range(max_steps):
        event = session.simulation_step()
        guess = event["action"]["guess"]
        feedback = questline.parse_feedback(event["action"]["feedback"])
        print(f"\n第 {session.round} 轮：引擎选择 {guess}，反馈 {fb_text(feedback)}" if lang == "zh" else f"\nRound {session.round}: engine chose {guess}, feedback {fb_text(feedback)}")
        print(event["narrative"])
        if feedback == (4, 0):
            print(session.read_story())
            return True
        try:
            command = input("回车继续，story 查看故事，q 退出: ").strip().lower()
        except EOFError:
            return False
        if command in {"q", "quit", "exit"}:
            return False
        if command in {"story", "book"}:
            print(session.read_story())
        elif command in {"book full", "book+", "audit"}:
            print(session.story.render_audit())
    print("达到探索步数上限。" if lang == "zh" else "Exploration step limit reached.")
    print(session.read_story())
    return False


class CliState:
    def __init__(self, debug: bool = False) -> None:
        self.engine_notice_shown = False
        self.in_recovery = False
        self.debug = debug


def synthetic_opening_result(history: History) -> Optional[Dict[str, Any]]:
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
    investigation = result.get("investigation") or {}
    task = investigation.get("task")
    labels = {
        "establish_foundation": "建立基础事实",
        "introduce_45": "引入 45 组",
        "investigate_outer_groups": "调查外围组",
        "cross_test_new_group": "交叉测试新组",
        "converge_outer_choice": "外围选择性收束",
        "resolve_group_conflict": "解决组内冲突",
        "apply_position_pressure": "验证数字位置",
        "resolve_endgame": "残局直接验证",
    }
    if task: return labels.get(task, task) if lang == "zh" else task
    return tr(lang, "normal")


def build_menu(solver: Any, result: Dict[str, Any], history: History) -> List[Dict[str, Any]]:
    phase = result.get("phase")
    if phase == "opening_first":
        recommendation = result.get("recommendations", [{}])[0]
        return [dict(recommendation, source="QuestLine"), {"guess": "9876", "source": "Conspiracy"}]
    if phase == "opening_second":
        rec = result["recommendations"][0]
        return [dict(rec, source="QuestLine")]
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
                menu.append({"guess": avg_guess, "source": "AVG", "normal_expected": avg_e, "normal_max_bucket": avg_m, "bucket_count": avg_b}); seen.add(avg_guess)
            mm_i, mm_e, mm_m, mm_b = solver.best_pure_guess(cand_idx, "mm")
            mm_guess = questline.ALL_CODES[mm_i]
            if mm_guess not in seen:
                menu.append({"guess": mm_guess, "source": "MM", "normal_expected": mm_e, "normal_max_bucket": mm_m, "bucket_count": mm_b}); seen.add(mm_guess)
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
        action = item.get("action", {})
        action_label = action.get("type", "") if isinstance(action, dict) else ""
        if isinstance(exp, (int, float)) and exp:
            print(f"  {i}. {guess}  [{src}]  action={action_label} AVG={exp:.2f} max={item.get('normal_max_bucket')}")
        else:
            print(f"  {i}. {guess}  [{src}]  action={action_label}")


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
    investigation = result.get("investigation") or {}
    if investigation:
        task_labels = {
            "establish_foundation": "建立基础事实",
            "introduce_45": "引入 45 组",
            "cross_test_new_group": "交叉测试并引入新组",
            "investigate_outer_groups": "调查外围组",
            "resolve_group_conflict": "解决组内冲突",
            "apply_position_pressure": "施加位置压力",
            "resolve_endgame": "收束残局",
        }
        task = investigation.get("task", "unknown")
        task_text = task_labels.get(task, task) if lang == "zh" else task
        print(f"调查任务: {task_text}" if lang == "zh" else f"Investigation task: {task_text}")
        print(f"已调查组: {', '.join(investigation.get('tested_groups', [])) or '无'}" if lang == "zh" else f"Tested groups: {', '.join(investigation.get('tested_groups', [])) or 'none'}")
        print(f"待调查组: {', '.join(investigation.get('untested_groups', [])) or '无'}" if lang == "zh" else f"Untested groups: {', '.join(investigation.get('untested_groups', [])) or 'none'}")
        confirmed = investigation.get("confirmed_digits", [])
        likely = investigation.get("likely_digits", [])
        conflicts = investigation.get("strong_conflict_groups", [])
        uncertain_positions = investigation.get("position_uncertainty", [])
        if lang == "zh":
            print(f"身份事实: 已确定 {''.join(confirmed) or '无'}；大概率 {''.join(likely) or '无'}")
            print(f"组内冲突: {', '.join(conflicts) or '无'}")
            print(f"待验证位置: {''.join(uncertain_positions) or '无'}")
        else:
            print(f"Identity facts: confirmed {''.join(confirmed) or 'none'}; likely {''.join(likely) or 'none'}")
            print(f"Group conflicts: {', '.join(conflicts) or 'none'}")
            print(f"Positions needing verification: {''.join(uncertain_positions) or 'none'}")
        action_summary = result.get("action_summary") or {}
        if action_summary:
            print(f"行动候选: {action_summary}" if lang == "zh" else f"Action candidates: {action_summary}")
    ans = unique_answer(solver, history) if rem == 1 else None
    if ans:
        print(tr(lang, "logic_solved", answer=ans))
    anchor = result.get("avg_anchor")
    if anchor:
        print(f"AVG: {anchor['guess']} exp={anchor['exp']:.3f} max={anchor['max']} buckets={anchor['bucket_count']}")
    menu = build_menu(solver, result, history)
    print_menu(menu, lang, len(history)+1)
    world = solver.world_line_analysis(history)
    if world.get("main_world"):
        main = world["main_world"]
        title = "世界线分析" if lang == "zh" else "World-line analysis"
        main_label = "主世界" if lang == "zh" else "Main world"
        groups = "+".join(main["groups"])
        print(f"\n[{title}]")
        print(f"{main_label}: {groups}  support={main['support']:.1%} ({main['count']}/{world['candidate_count']})")
        confidence = main.get("confidence")
        if lang == "zh":
            if confidence == "tied":
                explanation = f"解释: {groups} 当前与另外 {main['tied_world_count'] - 1} 条世界线并列，暂不算唯一主线。"
            elif confidence == "weak":
                explanation = f"解释: {groups} 仅弱领先第二世界线 {main['lead_over_runner_up']:.1%}，需要继续观察。"
            else:
                explanation = f"解释: 主世界由 {groups} 组成，比第二世界线高 {main['lead_over_runner_up']:.1%}。"
            print(explanation)
        else:
            if confidence == "tied":
                print(f"Why: {groups} is tied with {main['tied_world_count'] - 1} other world(s); it is not uniquely dominant yet.")
            elif confidence == "weak":
                print(f"Why: {groups} weakly leads the next world by {main['lead_over_runner_up']:.1%}; keep observing.")
            else:
                print(f"Why: {groups} clearly leads the next world by {main['lead_over_runner_up']:.1%}.")
        for key, label in (("top_pairs", "Top 2-digit groups"), ("top_triples", "Top 3-digit groups"), ("top_quads", "Top 4-digit candidates")):
            entries = world[key]
            if entries:
                rendered = ", ".join(f"{entry['pattern']} ({entry['support']:.1%})" for entry in entries[:3])
                print(f"{label}: {rendered}")
        if len(world["timeline"]) > 1:
            timeline_parts = []
            for item in world["timeline"]:
                delta = item.get("support_delta")
                marker = "" if delta is None else f" ({delta:+.1%})"
                timeline_parts.append(f"r{item['round']} {item['support']:.1%}{marker}")
            timeline = " -> ".join(timeline_parts)
            label = "支持度变化" if lang == "zh" else "Support over time"
            print(f"{label}: {timeline}")
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
        try:
            ans = input(prompt + " ").strip().lower()
        except EOFError:
            return default_yes
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
    print("\n[完整审计版案件记录]")
    print_story(history, solver, lang, audit=True)
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
            try:
                raw = input(f"{tr(lang, 'prompt')}: ").strip()
            except EOFError:
                return False
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
            if low in {"story", "book"}: print_story(history, solver, lang); continue
            if low in {"book full", "book+", "audit"}: print_story(history, solver, lang, audit=True); continue
            if handle_case_command(low, history, replay, solver, lang): continue
            replaced = try_replace_last(raw, history, replay, solver, lang)
            if replaced is not None: return replaced
            print(tr(lang, "correction_prompt")); continue
        menu = build_menu(solver, result, history)
        print_turn(solver, history, result, menu, lang)
        try:
            raw = input(f"{tr(lang, 'prompt')}: ").strip()
        except EOFError:
            return False
        low = raw.lower()
        if low in {"q", "quit", "exit"}: return False
        if low in {"new", "restart"}: print(tr(lang, "restart")); return True
        if low in {"help", "?"}: print_help(lang); continue
        if low in {"h", "history"}: print_history(history, lang); continue
        if low in {"story", "book"}: print_story(history, solver, lang); continue
        if low in {"book full", "book+", "audit"}: print_story(history, solver, lang, audit=True); continue
        if low in {"r", "report"}: print_report(solver, history, lang, state); continue
        if handle_case_command(low, history, replay, solver, lang): continue
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
    parser = argparse.ArgumentParser(description="QuestLine interactive CLI v1.3")
    parser.add_argument("--lang", choices=["zh", "en"], default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--mode",
        choices=["assist", "simulation", "adventure", "solver", "explore", "story"],
        default="assist",
    )
    parser.add_argument("--answer", help="hidden answer for story/explore mode")
    parser.add_argument("--max-steps", type=int, default=10)
    args = parser.parse_args(argv)
    lang = args.lang or choose_language("zh")
    print_welcome(lang)
    solver = questline.QuestLineSolver(verbose=True)
    mode = {
        "solver": "assist",
        "explore": "simulation",
        "story": "adventure",
    }.get(args.mode, args.mode)
    if mode == "adventure":
        story_game_loop(lang, solver, answer=args.answer)
        print(tr(lang, "bye"))
        return
    if mode == "simulation":
        explore_game_loop(lang, solver, answer=args.answer, max_steps=args.max_steps)
        print(tr(lang, "bye"))
        return
    keep = True
    while keep:
        keep = game_loop(lang, solver, debug=args.debug)
    print(tr(lang, "bye"))


if __name__ == "__main__":
    main()
