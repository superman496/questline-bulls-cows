
"""QuestLine Bulls & Cows Solver

A narrative-driven solver for 4-digit Bulls & Cows with non-repeating digits.

QuestLine follows strong world lines, bull pressure, cow-to-bull rotation,
low-signal fallback, and exact endgame compression.

Performance note
----------------
QuestLine uses a feedback matrix for speed. The matrix is expensive to build but
small enough to cache as a binary file. The first run creates:

    .questline_cache/feedback_matrix_v1.bin

Later runs load that cache, so startup is much faster.

Feedback format
---------------
Internally QuestLine uses "1b2c" style feedback, but the parser also accepts
"1a2b", "1,2", and "12" for convenience.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations, permutations
from pathlib import Path
import argparse
import os
import re
import time
from typing import DefaultDict, Dict, Iterable, List, Optional, Sequence, Tuple, Union

Digit = str
Code = str
Feedback = Tuple[int, int]
History = Sequence[Tuple[Code, Union[Feedback, str]]]

DIGITS = "0123456789"
CODE_LEN = 4
ALL_CODES: List[Code] = ["".join(p) for p in permutations(DIGITS, CODE_LEN)]
CODE_TO_INDEX: Dict[Code, int] = {code: i for i, code in enumerate(ALL_CODES)}
ALL_INDEXES: Tuple[int, ...] = tuple(range(len(ALL_CODES)))

FIXED_GROUPS: Dict[str, set[str]] = {
    "01": set("01"),
    "23": set("23"),
    "45": set("45"),
    "67": set("67"),
    "89": set("89"),
}
GROUP_ORDER: Tuple[str, ...] = tuple(FIXED_GROUPS)

FB_TO_BYTE: Dict[Feedback, int] = {(b, c): b * 5 + c for b in range(5) for c in range(5 - b)}
BYTE_TO_FB: Dict[int, Feedback] = {v: k for k, v in FB_TO_BYTE.items()}

OPENING_FIRST: Code = "0123"
OPENING_SECOND_BY_FEEDBACK: Dict[Feedback, Code] = {
    (0, 0): "4567",
    (0, 1): "1045",
    (0, 2): "1435",
    (0, 3): "1435",
    (0, 4): "1230",
    (1, 0): "0456",
    (1, 1): "0145",
    (1, 2): "0245",
    (1, 3): "0134",
    (2, 0): "0245",
    (2, 1): "0245",
    (2, 2): "0214",
    (3, 0): "0245",
    (4, 0): "0123",
}

CACHE_DIR = Path(".questline_cache")
MATRIX_CACHE_NAME = "feedback_matrix_v1.bin"
MATRIX_MAGIC = b"QUESTLINE_FEEDBACK_MATRIX_V1\n"
MATRIX_SIZE = len(ALL_CODES) * len(ALL_CODES)

ONLINE_SAFE_MODE = True
MAX_MECH_REPORT_CANDIDATES = 650


def raw_feedback(answer: Code, guess: Code) -> Feedback:
    bulls = sum(a == g for a, g in zip(answer, guess))
    common = sum(ch in answer for ch in guess)
    return bulls, common - bulls


def fb_to_str(fb: Feedback) -> str:
    return f"{fb[0]}b{fb[1]}c"


def parse_feedback(value: Union[Feedback, str]) -> Feedback:
    if isinstance(value, tuple):
        return value
    text = str(value).strip().lower()
    patterns = [
        r"^\s*(\d)\s*b\s*(\d)\s*c\s*$",
        r"^\s*(\d)\s*a\s*(\d)\s*b\s*$",
        r"^\s*(\d)\s*,\s*(\d)\s*$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text)
        if match:
            return int(match.group(1)), int(match.group(2))
    if len(text) == 2 and text[0].isdigit() and text[1].isdigit():
        return int(text[0]), int(text[1])
    raise ValueError(f"Cannot parse feedback: {value}")


def validate_feedback(feedback: Feedback) -> Feedback:
    bulls, cows = feedback
    if bulls < 0 or cows < 0 or bulls > CODE_LEN or cows > CODE_LEN - bulls:
        raise ValueError(f"Invalid feedback: {feedback}")
    return feedback


def validate_code(code: Code) -> Code:
    code = str(code).strip()
    if len(code) != CODE_LEN:
        raise ValueError("Code must have 4 digits.")
    if len(set(code)) != CODE_LEN:
        raise ValueError("Digits must not repeat.")
    if not all(ch in DIGITS for ch in code):
        raise ValueError("Code must contain digits 0-9 only.")
    return code


def normalize_history(history: History) -> List[Tuple[Code, Feedback]]:
    return [(validate_code(guess), validate_feedback(parse_feedback(fb))) for guess, fb in history]


class _QuestLineCore:
    """Narrative-driven Bulls & Cows solver.

    The first and second moves are served from a small opening book. The feedback
    matrix is loaded lazily only when the solver needs deeper reasoning.
    """

    def __init__(self, use_cache: bool = True, verbose: bool = False) -> None:
        self.use_cache = use_cache
        self.verbose = verbose
        self.feedback_matrix: Optional[List[bytearray]] = None
        self._best_cache: Dict[Tuple[Tuple[int, ...], str], Tuple[Tuple[float, int, int, str], int, float, int, int]] = {}
        self._stats_cache: Dict[Tuple[int, ...], Dict[str, object]] = {}
        self._weights_cache: Dict[Tuple[int, ...], Tuple[Dict[int, float], Tuple[int, ...]]] = {}

    # ------------------------------------------------------------------
    # Matrix cache
    # ------------------------------------------------------------------

    @property
    def cache_path(self) -> Path:
        return CACHE_DIR / MATRIX_CACHE_NAME

    def ensure_matrix(self) -> None:
        if self.feedback_matrix is not None:
            return
        if self.use_cache and self.cache_path.exists():
            self.feedback_matrix = self._load_matrix_cache()
            return
        self.feedback_matrix = self._build_feedback_matrix()
        if self.use_cache:
            self._save_matrix_cache(self.feedback_matrix)

    def _load_matrix_cache(self) -> List[bytearray]:
        if self.verbose:
            print(f"Loading feedback matrix cache: {self.cache_path}")
        data = self.cache_path.read_bytes()
        if not data.startswith(MATRIX_MAGIC):
            raise ValueError("Invalid QuestLine matrix cache header. Delete .questline_cache and rebuild.")
        payload = data[len(MATRIX_MAGIC):]
        if len(payload) != MATRIX_SIZE:
            raise ValueError("Invalid QuestLine matrix cache size. Delete .questline_cache and rebuild.")
        matrix = []
        offset = 0
        row_len = len(ALL_CODES)
        for _ in ALL_CODES:
            matrix.append(bytearray(payload[offset: offset + row_len]))
            offset += row_len
        if self.verbose:
            print("Feedback matrix cache loaded.")
        return matrix

    def _save_matrix_cache(self, matrix: List[bytearray]) -> None:
        CACHE_DIR.mkdir(exist_ok=True)
        if self.verbose:
            print(f"Saving feedback matrix cache: {self.cache_path}")
        payload = b"".join(bytes(row) for row in matrix)
        self.cache_path.write_bytes(MATRIX_MAGIC + payload)

    def _build_feedback_matrix(self) -> List[bytearray]:
        if self.verbose:
            print("Building feedback matrix. This happens once and may take a while...")
        start = time.time()
        matrix: List[bytearray] = []
        for guess in ALL_CODES:
            row = bytearray(len(ALL_CODES))
            for answer_index, answer in enumerate(ALL_CODES):
                row[answer_index] = FB_TO_BYTE[raw_feedback(answer, guess)]
            matrix.append(row)
        if self.verbose:
            print(f"Feedback matrix built in {time.time() - start:.2f}s.")
        return matrix

    def feedback(self, answer: Code, guess: Code) -> Feedback:
        # For one-off feedback, raw calculation is faster than forcing matrix load.
        return raw_feedback(validate_code(answer), validate_code(guess))

    def matrix_feedback(self, answer_index: int, guess_index: int) -> Feedback:
        self.ensure_matrix()
        assert self.feedback_matrix is not None
        return BYTE_TO_FB[self.feedback_matrix[guess_index][answer_index]]

    # ------------------------------------------------------------------
    # Candidate filtering and mechanical anchors
    # ------------------------------------------------------------------

    def filter_candidates(self, history: History) -> Tuple[int, ...]:
        normalized = normalize_history(history)
        if not normalized:
            return ALL_INDEXES
        self.ensure_matrix()
        assert self.feedback_matrix is not None
        candidates = list(ALL_INDEXES)
        for guess, fb in normalized:
            row = self.feedback_matrix[CODE_TO_INDEX[guess]]
            target = FB_TO_BYTE[fb]
            candidates = [idx for idx in candidates if row[idx] == target]
        return tuple(candidates)

    def bucket_counts(self, candidates: Tuple[int, ...], guess_index: int) -> Dict[int, int]:
        self.ensure_matrix()
        assert self.feedback_matrix is not None
        row = self.feedback_matrix[guess_index]
        counts: Dict[int, int] = defaultdict(int)
        for answer_index in candidates:
            counts[row[answer_index]] += 1
        return counts

    def avg_remaining(self, candidates: Tuple[int, ...], guess_index: int) -> Tuple[float, int, int]:
        counts = self.bucket_counts(candidates, guess_index)
        n = len(candidates)
        return sum(v * v for v in counts.values()) / n, max(counts.values()), len(counts)

    def best_pure_guess(self, candidates: Tuple[int, ...], mode: str = "avg") -> Tuple[int, float, int, int]:
        key = (candidates, mode)
        cached = self._best_cache.get(key)
        if cached is not None:
            _, guess_index, exp, max_bucket, bucket_count = cached
            return guess_index, exp, max_bucket, bucket_count
        candidate_set = set(candidates)
        best: Optional[Tuple[Tuple[float, int, int, str], int, float, int, int]] = None
        for guess_index, guess in enumerate(ALL_CODES):
            exp, max_bucket, bucket_count = self.avg_remaining(candidates, guess_index)
            candidate_penalty = 0 if guess_index in candidate_set else 1
            sort_key = (exp, max_bucket, candidate_penalty, guess) if mode == "avg" else (max_bucket, exp, candidate_penalty, guess)
            if best is None or sort_key < best[0]:
                best = (sort_key, guess_index, exp, max_bucket, bucket_count)
        assert best is not None
        self._best_cache[key] = best
        _, guess_index, exp, max_bucket, bucket_count = best
        return guess_index, exp, max_bucket, bucket_count

    # ------------------------------------------------------------------
    # Stats and weighted candidate model
    # ------------------------------------------------------------------

    def stats(self, candidates: Tuple[int, ...]) -> Dict[str, object]:
        cached = self._stats_cache.get(candidates)
        if cached is not None:
            return cached
        n = len(candidates)
        dc: Counter[str] = Counter()
        pc: List[Counter[str]] = [Counter() for _ in range(CODE_LEN)]
        pair: Counter[str] = Counter()
        tri: Counter[str] = Counter()
        quad: Counter[str] = Counter()
        group_strength = {name: 0.0 for name in FIXED_GROUPS}
        for index in candidates:
            code = ALL_CODES[index]
            dc.update(code)
            for pos, ch in enumerate(code):
                pc[pos][ch] += 1
            sorted_code = sorted(code)
            for combo in combinations(sorted_code, 2):
                pair["".join(combo)] += 1
            for combo in combinations(sorted_code, 3):
                tri["".join(combo)] += 1
            quad["".join(sorted_code)] += 1
            for name, group in FIXED_GROUPS.items():
                group_strength[name] += sum(ch in group for ch in code)
        for name in group_strength:
            group_strength[name] /= n
        freqs = {digit: dc[digit] / n for digit in DIGITS}
        quad_common = quad.most_common()
        result = {
            "n": n,
            "dc": dc,
            "pc": pc,
            "pair": pair,
            "tri": tri,
            "quad": quad,
            "group_strength": group_strength,
            "freqs": freqs,
            "weak_threshold": sorted(freqs.values())[2],
            "top_digits": [d for d, _ in dc.most_common(4)],
            "top_pairs": [p for p, _ in pair.most_common(6)],
            "top_triples": [t for t, _ in tri.most_common(6)],
            "top_quad_count": quad_common[0][1] if quad_common else 0,
            "second_quad_count": quad_common[1][1] if len(quad_common) > 1 else 0,
        }
        self._stats_cache[candidates] = result
        return result

    @staticmethod
    def fixed_signature(code: Code) -> Tuple[int, ...]:
        return tuple(sum(ch in group for ch in code) for group in FIXED_GROUPS.values())

    def candidate_weights(self, candidates: Tuple[int, ...], stats: Dict[str, object]) -> Tuple[Dict[int, float], Tuple[int, ...]]:
        cached = self._weights_cache.get(candidates)
        if cached is not None:
            return cached
        worlds: DefaultDict[Tuple[int, ...], List[int]] = defaultdict(list)
        for index in candidates:
            worlds[self.fixed_signature(ALL_CODES[index])].append(index)
        total = len(candidates)
        world_scores = {signature: (len(members) / total) ** 1.35 for signature, members in worlds.items()}
        weights: Dict[int, float] = {}
        for signature, members in worlds.items():
            for index in members:
                weights[index] = world_scores[signature] * self._candidate_base_weight(ALL_CODES[index], stats)
        weight_sum = sum(weights.values())
        if weight_sum > 0:
            weights = {k: v / weight_sum for k, v in weights.items()}
        main_signature = max(world_scores, key=world_scores.get)
        result = (weights, tuple(worlds[main_signature]))
        self._weights_cache[candidates] = result
        return result

    def world_line_analysis(self, history: History) -> Dict[str, object]:
        """Summarize the strongest fixed-group world and its supporting patterns."""
        normalized = normalize_history(history)
        candidates = self.filter_candidates(normalized)
        if not candidates:
            return {"candidate_count": 0, "main_world": None, "worlds": [], "top_pairs": [], "top_triples": [], "top_quads": [], "timeline": []}

        stats = self.stats(candidates)
        world_counts: Counter[Tuple[int, ...]] = Counter(self.fixed_signature(ALL_CODES[index]) for index in candidates)
        ranked_worlds = sorted(world_counts.items(), key=lambda item: (-item[1], item[0]))
        main_signature, main_count = ranked_worlds[0]
        total = len(candidates)
        tied_worlds = [signature for signature, count in ranked_worlds if count == main_count]

        def ranked(counter: Counter[str], limit: int) -> List[Dict[str, object]]:
            return [{"pattern": key, "count": count, "support": count / total} for key, count in counter.most_common(limit)]

        worlds = [
            {
                "signature": list(signature),
                "groups": [name for name, amount in zip(FIXED_GROUPS, signature) if amount],
                "count": count,
                "support": count / total,
                "is_main": signature == main_signature,
            }
            for signature, count in sorted(world_counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        timeline: List[Dict[str, object]] = []
        for round_number in range(len(normalized) + 1):
            prefix = normalized[:round_number]
            prefix_candidates = self.filter_candidates(prefix)
            if not prefix_candidates:
                timeline.append({"round": round_number, "candidate_count": 0, "main_world": None, "support": 0.0})
                continue
            prefix_worlds = Counter(self.fixed_signature(ALL_CODES[index]) for index in prefix_candidates)
            signature, count = sorted(prefix_worlds.items(), key=lambda item: (-item[1], item[0]))[0]
            prefix_tied_count = sum(1 for world_count in prefix_worlds.values() if world_count == count)
            timeline.append({
                "round": round_number,
                "candidate_count": len(prefix_candidates),
                "main_world": list(signature),
                "support": count / len(prefix_candidates),
                "tied_world_count": prefix_tied_count,
            })

        previous_support = None
        for item in timeline:
            support = item["support"]
            item["support_delta"] = None if previous_support is None else support - previous_support
            previous_support = support

        runner_up_count = ranked_worlds[1][1] if len(ranked_worlds) > 1 else 0
        lead = (main_count - runner_up_count) / total
        confidence = "tied" if len(tied_worlds) > 1 else ("weak" if lead < 0.05 else "clear")
        main_world = {
            "signature": list(main_signature),
            "groups": [name for name, amount in zip(FIXED_GROUPS, main_signature) if amount],
            "count": main_count,
            "support": main_count / total,
            "lead_over_runner_up": lead,
            "runner_up_support": runner_up_count / total,
            "confidence": confidence,
            "tied_world_count": len(tied_worlds),
        }

        return {
            "candidate_count": total,
            "main_world": main_world,
            "worlds": worlds,
            "top_pairs": ranked(stats["pair"], 5),
            "top_triples": ranked(stats["tri"], 5),
            "top_quads": ranked(stats["quad"], 5),
            "timeline": timeline,
        }

    @staticmethod
    def _changed_digit_facts(before: Dict[str, object], after: Dict[str, object]) -> Dict[str, List[str]]:
        changes = {
            "confirmed": [], "likely": [], "excluded": [], "weakened": [], "strengthened": [],
            "support_risen": [], "support_fallen": [],
        }
        before_status = before.get("digit_status", {})
        after_status = after.get("digit_status", {})
        before_support = before.get("digit_support", {})
        after_support = after.get("digit_support", {})
        rank = {"excluded": 0, "possible": 1, "likely": 2, "confirmed": 3}
        for digit in DIGITS:
            old = before_status.get(digit, {}).get("status", "possible")
            new = after_status.get(digit, {}).get("status", "possible")
            delta = after_support.get(digit, 0.0) - before_support.get(digit, 0.0)
            if new == "confirmed" and old != "confirmed":
                changes["confirmed"].append(digit)
            elif new == "likely" and old != "likely":
                changes["likely"].append(digit)
            elif new == "excluded" and old != "excluded":
                changes["excluded"].append(digit)
            if rank.get(new, 1) > rank.get(old, 1):
                changes["strengthened"].append(digit)
            elif rank.get(new, 1) < rank.get(old, 1):
                changes["weakened"].append(digit)
            if delta >= 0.10:
                changes["support_risen"].append(digit)
            elif delta <= -0.10:
                changes["support_fallen"].append(digit)
        return changes

    @staticmethod
    def _changed_position_facts(before: Dict[str, object], after: Dict[str, object]) -> Dict[str, List[Dict[str, object]]]:
        changes = {"strengthened": [], "weakened": [], "confirmed": [], "excluded": []}
        before_support = before.get("digit_position_support", {})
        after_support = after.get("digit_position_support", {})
        before_status = before.get("digit_status", {})
        after_status = after.get("digit_status", {})
        for digit in DIGITS:
            old_values = before_support.get(digit, [0.0] * CODE_LEN)
            new_values = after_support.get(digit, [0.0] * CODE_LEN)
            for position, (old, new) in enumerate(zip(old_values, new_values)):
                delta = new - old
                old_status = before_status.get(digit, {}).get("position_status", ["possible"] * CODE_LEN)[position]
                new_status = after_status.get(digit, {}).get("position_status", ["possible"] * CODE_LEN)[position]
                item = {
                    "digit": digit,
                    "position": position,
                    "old_support": old,
                    "new_support": new,
                    "support_delta": delta,
                }
                if new_status == "confirmed" and old_status != "confirmed":
                    changes["confirmed"].append(item)
                elif new_status == "excluded" and old_status != "excluded":
                    changes["excluded"].append(item)
                elif delta >= 0.10:
                    changes["strengthened"].append(item)
                elif delta <= -0.10:
                    changes["weakened"].append(item)
        return changes

    def explain_transition(self, history: History, guess: Code, feedback: Union[Feedback, str]) -> Dict[str, object]:
        """Explain one action as a transition from one investigation state to another."""
        normalized = normalize_history(history)
        guess = validate_code(guess)
        feedback = validate_feedback(parse_feedback(feedback))
        before = self.investigation_state(normalized)
        action = self.classify_action(guess, normalized, before, CODE_TO_INDEX[guess] in set(self.filter_candidates(normalized)))
        rationale = self.action_rationale(action, before)
        after_history = normalized + [(guess, feedback)]
        after = self.investigation_state(after_history)
        before_world = self.world_line_analysis(normalized)
        after_world = self.world_line_analysis(after_history)
        digit_changes = self._changed_digit_facts(before, after)
        position_changes = self._changed_position_facts(before, after)
        group_changes = []
        for group in GROUP_ORDER:
            old = before.get("group_states", {}).get(group, {}).get("status")
            new = after.get("group_states", {}).get(group, {}).get("status")
            if old != new:
                group_changes.append({"group": group, "before": old, "after": new})
        old_task = before.get("task")
        new_task = after.get("task")
        old_main = (before_world.get("main_world") or {}).get("groups", [])
        new_main = (after_world.get("main_world") or {}).get("groups", [])
        if feedback == (CODE_LEN, 0):
            event_type = "solution_revealed"
            title = "答案被直接确认"
        elif after.get("candidate_count", 0) == 0:
            event_type = "state_inconsistent"
            title = "这条反馈与现有证据冲突"
        elif digit_changes["confirmed"] or digit_changes["excluded"]:
            event_type = "identity_breakthrough"
            title = "数字身份发生突破"
        elif any(position_changes.values()):
            event_type = "position_breakthrough"
            title = "数字位置发生变化"
        elif old_task != new_task:
            event_type = "investigation_shifted"
            title = "调查任务发生转移"
        elif old_main != new_main:
            event_type = "worldline_shifted"
            title = "主世界线发生变化"
        elif after.get("candidate_count", 0) < before.get("candidate_count", 0) * 0.25:
            event_type = "candidate_space_collapsed"
            title = "可能性空间明显收束"
        else:
            event_type = "evidence_updated"
            title = "证据继续累积"
        return {
            "round": len(after_history),
            "type": event_type,
            "title": title,
            "action": {"guess": guess, "feedback": fb_to_str(feedback), "classification": action},
            "decision": {"task": old_task, "rationale": rationale},
            "before": {
                "candidate_count": before.get("candidate_count"),
                "task": old_task,
                "main_world": old_main,
                "digit_support": before.get("digit_support", {}),
                "digit_position_support": before.get("digit_position_support", {}),
                "digit_status": before.get("digit_status", {}),
                "group_states": before.get("group_states", {}),
                "group_relations": before.get("group_relations", {}),
            },
            "after": {
                "candidate_count": after.get("candidate_count"),
                "task": new_task,
                "main_world": new_main,
                "digit_support": after.get("digit_support", {}),
                "digit_position_support": after.get("digit_position_support", {}),
                "digit_status": after.get("digit_status", {}),
                "group_states": after.get("group_states", {}),
                "group_relations": after.get("group_relations", {}),
            },
            "facts": digit_changes,
            "position_facts": position_changes,
            "group_changes": group_changes,
            "worldline": {
                "before_support": (before_world.get("main_world") or {}).get("support", 0.0),
                "after_support": (after_world.get("main_world") or {}).get("support", 0.0),
                "before_confidence": (before_world.get("main_world") or {}).get("confidence"),
                "after_confidence": (after_world.get("main_world") or {}).get("confidence"),
            },
            "narrative": self._transition_narrative(
                title, guess, action, feedback, before, after, digit_changes, position_changes, old_task, new_task, rationale
            ),
        }

    @staticmethod
    def action_rationale(action: Dict[str, object], state: Dict[str, object]) -> str:
        """Explain why an action answers the current investigation task."""
        task = state.get("task")
        groups = ", ".join(action.get("new_groups", [])) or "已调查组"
        if task == "establish_foundation":
            return "先建立基础数字关系，给后续组间比较提供共同参照。"
        if task == "introduce_45":
            return "01 与 23 已有第一层证据，现在引入 45，观察可信主线是否延伸。"
        if task in {"investigate_outer_groups", "cross_test_new_group"}:
            return f"当前需要补上尚未验证的线索，行动选择测试 {groups}，同时保持基本信息效率。"
        if task == "converge_outer_choice":
            return "外围仍有对称解释，选择一个外围分支施加压力，而不是假定某个数字已经领先。"
        if task == "resolve_group_conflict":
            conflicts = ", ".join(state.get("strong_conflict_groups", [])) or "组内关系"
            return f"当前需要拆解 {conflicts} 的组内关系，优先获取身份或位置上的分裂证据。"
        if task == "apply_position_pressure":
            digits = "".join(state.get("position_uncertainty", [])) or "已知数字"
            return f"身份线索已经足够，下一步针对 {digits} 的位置关系施加压力。"
        if task == "resolve_endgame":
            return "候选答案已经很少，优先直接验证残局答案，避免继续制造无意义的外围猜测。"
        return f"行动类型为 {action.get('type', 'unknown')}，用于推进当前调查。"

    @staticmethod
    def _transition_narrative(title: str, guess: Code, action: Dict[str, object], feedback: Feedback, before: Dict[str, object], after: Dict[str, object], changes: Dict[str, List[str]], position_changes: Dict[str, List[Dict[str, object]]], old_task: str, new_task: str, rationale: str) -> str:
        parts = [f"{title}：因为{rationale}行动 {guess}，得到 {fb_to_str(feedback)}。"]
        if changes["confirmed"]:
            parts.append(f"数字 {_QuestLineReasoningLayer._format_digits(changes['confirmed'])} 在当前答案范围内已基本确认。")
        if changes["excluded"]:
            parts.append(f"数字 {_QuestLineReasoningLayer._format_digits(changes['excluded'])} 被当前证据排除。")
            exposed = [
                digit for digit in changes["excluded"]
                if before.get("digit_status", {}).get(digit, {}).get("status") in {"likely", "confirmed"}
            ]
            if exposed:
                parts.append(f"数字 {_QuestLineReasoningLayer._format_digits(exposed)} 此前曾进入可信解释，本轮伪装破裂。")
        excluded_now = [
            digit for digit in DIGITS
            if after.get("digit_status", {}).get(digit, {}).get("status") == "excluded"
        ]
        if excluded_now and (changes["excluded"] or changes.get("confirmed")):
            confirmed_now = [
                digit for digit in DIGITS
                if after.get("digit_status", {}).get(digit, {}).get("status") == "confirmed"
            ]
            if len(confirmed_now) == CODE_LEN:
                focus = "调查重点转向四个已确认数字的排列与顺序"
            else:
                focus = "调查重点转向剩余数字的身份与位置"
            parts.append(f"截至本轮，数字 {_QuestLineReasoningLayer._format_digits(excluded_now)} 已从答案解释中排除；{focus}。")
        if changes["weakened"]:
            parts.append(f"数字 {_QuestLineReasoningLayer._format_digits(changes['weakened'])} 的支持度下降。")
        support_risen = [
            digit for digit in changes.get("support_risen", [])
            if digit not in changes.get("confirmed", []) and digit not in changes.get("excluded", [])
        ]
        if support_risen:
            parts.append(f"数字 {_QuestLineReasoningLayer._format_digits(support_risen)} 在当前答案范围内的支持上升，但这还不等于身份确认。")
        if changes.get("support_fallen"):
            parts.append(f"数字 {_QuestLineReasoningLayer._format_digits(changes['support_fallen'])} 在候选世界中的支持下降。")
        active_digits = {
            digit for digit in DIGITS
            if after.get("digit_status", {}).get(digit, {}).get("status") != "excluded"
        }
        strengthened_positions = [
            item for item in position_changes["strengthened"] + position_changes["confirmed"]
            if item.get("digit") in active_digits
        ]
        weakened_positions = [
            item for item in position_changes["weakened"] + position_changes["excluded"]
            if item.get("digit") in active_digits
        ]
        if strengthened_positions or weakened_positions:
            parts.append("位置盘面更新：\n" + "\n".join(_QuestLineReasoningLayer._position_board(after)))
        confirmed_position_facts = []
        excluded_position_facts = []
        for digit in active_digits:
            position_status = after.get("digit_status", {}).get(digit, {}).get("position_status", [])
            for position, status in enumerate(position_status):
                if status == "confirmed":
                    confirmed_position_facts.append(f"{digit}→第{position + 1}位")
                elif status == "excluded":
                    excluded_position_facts.append(f"{digit}×第{position + 1}位")
        if after.get("group_relations"):
            group_events = []
            for group in GROUP_ORDER:
                before_tested = before.get("group_states", {}).get(group, {}).get("tested", False)
                after_tested = after.get("group_states", {}).get(group, {}).get("tested", False)
                if not (before_tested or after_tested):
                    continue
                before_relation = before.get("group_relations", {}).get(group, {}).get("relation")
                after_relation = after.get("group_relations", {}).get(group, {}).get("relation")
                if before_relation != after_relation:
                    group_events.append(f"{group}:{before_relation}→{after_relation}")
            if group_events:
                parts.append(f"小组关系变化：{'、'.join(group_events[:3])}。")
        group_status_events = []
        for group in GROUP_ORDER:
            before_status = before.get("group_states", {}).get(group, {}).get("status")
            after_status = after.get("group_states", {}).get(group, {}).get("status")
            if before_status == after_status:
                continue
            if after_status == "excluded":
                group_status_events.append(f"{group} 的共同解释被证据整体排除")
            elif after_status == "full":
                group_status_events.append(f"{group} 的共同解释获得完整支持")
            elif after_status == "present" and before_status in {"unobserved", "unresolved", "contested"}:
                group_status_events.append(f"{group} 的解释重新进入可信范围，但尚不能确认组内成员")
        if group_status_events:
            parts.append(f"组级判断：{'；'.join(group_status_events)}。")
        split_groups = []
        for group in GROUP_ORDER:
            relation = after.get("group_relations", {}).get(group, {}).get("relation")
            if relation == "one_strong_one_weak":
                split_groups.append(group)
        if split_groups:
            split_details = []
            for group in split_groups:
                support = after.get("group_relations", {}).get(group, {}).get("support", {})
                if support:
                    strong = max(support, key=support.get)
                    weak = min(support, key=support.get)
                    weak_status = after.get("digit_status", {}).get(weak, {}).get("status")
                    if weak_status == "excluded":
                        split_details.append(f"{group} 内部证据已经完成拆分：{strong} 被保留，{weak} 被排除")
                    elif weak_status == "confirmed":
                        split_details.append(f"{group} 内部证据已经完成确认：{strong} 与 {weak} 均被保留")
                    else:
                        split_details.append(f"{group} 内部暂偏向 {strong}，{weak} 仍待排除")
                else:
                    split_details.append(group)
            parts.append(f"组内证据分化：{'；'.join(split_details)}。")
        if after.get("candidate_count") != before.get("candidate_count"):
            parts.append(f"答案范围从 {before.get('candidate_count')} 个缩小到 {after.get('candidate_count')} 个。")
        if old_task != new_task:
            parts.append(f"调查转向：{_QuestLineReasoningLayer.public_task(new_task)}。")
        return "".join(parts)

    def _candidate_base_weight(self, code: Code, stats: Dict[str, object]) -> float:
        n = stats["n"]
        dc: Counter[str] = stats["dc"]
        pc: List[Counter[str]] = stats["pc"]
        pair: Counter[str] = stats["pair"]
        tri: Counter[str] = stats["tri"]
        quad: Counter[str] = stats["quad"]
        sorted_code = sorted(code)
        digit_score = 1.0
        for ch in code:
            digit_score *= 0.35 + dc[ch] / n
        position_score = 1.0
        for pos, ch in enumerate(code):
            position_score *= 0.35 + pc[pos][ch] / n
        pair_score = 1.0
        for combo in combinations(sorted_code, 2):
            pair_score *= 0.55 + 0.35 * (pair["".join(combo)] / n)
        triple_score = 1.0
        for combo in combinations(sorted_code, 3):
            triple_score *= 0.70 + 0.18 * (tri["".join(combo)] / n)
        quad_score = 0.80 + 0.12 * (quad["".join(sorted_code)] / n)
        penalty = 1.0
        for digit in stats["top_digits"]:
            if digit not in code:
                penalty *= 0.86
        for p in stats["top_pairs"]:
            if not all(ch in code for ch in p):
                penalty *= 0.94
        for t in stats["top_triples"]:
            if not all(ch in code for ch in t):
                penalty *= 0.97
        penalty *= 0.80 + 0.40 * (quad["".join(sorted_code)] / n)
        return digit_score * position_score * pair_score * triple_score * quad_score * penalty


class _QuestLineReasoningLayer(_QuestLineCore):
    """Organize transition explanations into a continuous investigation story."""

    CHAPTERS: Dict[str, Tuple[str, str]] = {
        "establish_foundation": ("prologue", "案件建立"),
        "introduce_45": ("foundation", "核心事实"),
        "investigate_outer_groups": ("new_witnesses", "新的证人"),
        "cross_test_new_group": ("outer_split", "外围分裂"),
        "converge_outer_choice": ("outer_split", "外围分裂"),
        "resolve_group_conflict": ("group_conflict", "阵营冲突"),
        "apply_position_pressure": ("position_evidence", "位置证据"),
        "resolve_endgame": ("convergence", "收束"),
    }

    PUBLIC_TASKS = {
        "establish_foundation": "建立第一层参照",
        "introduce_45": "扩大调查范围",
        "investigate_outer_groups": "寻找外围线索",
        "cross_test_new_group": "交叉验证新线索",
        "converge_outer_choice": "收束外围分歧",
        "resolve_group_conflict": "拆解数字关系",
        "apply_position_pressure": "施加位置压力",
        "resolve_endgame": "验证残局排列",
    }

    @classmethod
    def public_task(cls, task: Optional[str]) -> str:
        return cls.PUBLIC_TASKS.get(task, "继续调查")

    @staticmethod
    def _position_board(state: Dict[str, object], limit: int = 3) -> List[str]:
        status_map = state.get("digit_status", {})
        support_map = state.get("digit_position_support", {})
        rows = []
        for position in range(CODE_LEN):
            excluded = []
            possible = []
            confirmed = []
            for digit in DIGITS:
                digit_state = status_map.get(digit, {})
                if digit_state.get("status") == "excluded":
                    continue
                position_status = digit_state.get("position_status", [])
                status = position_status[position] if position < len(position_status) else "possible"
                if status == "excluded":
                    excluded.append(digit)
                elif status == "confirmed":
                    confirmed.append(digit)
                else:
                    supports = support_map.get(digit) or digit_state.get("position_support", [])
                    possible.append((supports[position] if position < len(supports) else 0.0, digit))
            possible.sort(reverse=True)
            labels = [f"{digit}（{support:.0%}）" for support, digit in possible[:limit]]
            if confirmed:
                labels = [f"{digit}（锁定）" for digit in confirmed] + labels
            rows.append(f"第{position + 1}位：排除 {'、'.join(excluded) if excluded else '无'}；当前靠前 {'、'.join(labels) if labels else '无'}")
        return rows

    def _strength_board(self, history: History, previous_history: History = ()) -> List[str]:
        candidates = self.solver.filter_candidates(history)
        if not candidates:
            return []
        stats = self.solver.stats(candidates)
        total = stats["n"]

        def ranked(counter: Counter[str]) -> Tuple[List[str], List[str], bool]:
            entries = [(key, count / total) for key, count in counter.items()]
            entries.sort(key=lambda item: (-item[1], item[0]))
            if len(entries) < 2:
                return ([f"{key}（{support:.0%}）" for key, support in entries], [], False)
            gaps = [(entries[index][1] - entries[index + 1][1], index) for index in range(len(entries) - 1)]
            gap, split = max(gaps, key=lambda item: (item[0], -item[1]))
            spread = entries[0][1] - entries[-1][1]
            meaningful = gap >= max(0.08, spread * 0.30)
            if meaningful:
                strong_entries = entries[: split + 1]
                weak_entries = entries[split + 1:]
            else:
                strong_entries = entries[:1]
                weak_entries = entries[-1:]
            strong = [f"{key}（{support:.0%}）" for key, support in strong_entries]
            weak = [f"{key}（{support:.0%}）" for key, support in reversed(weak_entries)]
            return strong, weak, meaningful

        digit_status = self.solver.investigation_state(history).get("digit_status", {})
        confirmed_digits = [digit for digit in DIGITS if digit_status.get(digit, {}).get("status") == "confirmed"]
        excluded_digits = [digit for digit in DIGITS if digit_status.get(digit, {}).get("status") == "excluded"]
        digit_entries = sorted(
            (
                (digit, stats["freqs"].get(digit, 0.0))
                for digit in DIGITS
                if digit_status.get(digit, {}).get("status") not in {"excluded", "confirmed"}
            ),
            key=lambda item: (-item[1], item[0]),
        )
        digit_counter = Counter({digit: round(support * total) for digit, support in digit_entries})
        digit_strong, digit_weak, digit_gap = ranked(digit_counter)
        pair_strong, pair_weak, pair_gap = ranked(stats["pair"])
        tri_strong, tri_weak, tri_gap = ranked(stats["tri"])
        lines = []
        if confirmed_digits:
            lines.append(f"身份已锁定：{'、'.join(confirmed_digits)}。")
        if excluded_digits:
            lines.append(f"身份已排除：{'、'.join(excluded_digits)}。")
        lines.extend([
            f"单数字强弱：{'断档强势' if digit_gap else '当前靠前'} { '、'.join(digit_strong) or '无'}；{'断档弱势' if digit_gap else '当前靠后'} { '、'.join(digit_weak) or '无'}。",
            f"二数字组合：{'断档强势' if pair_gap else '当前靠前'} {'、'.join(pair_strong) or '无'}；{'断档弱势' if pair_gap else '当前靠后'} {'、'.join(pair_weak) or '无'}。",
            f"三数字组合：{'断档强势' if tri_gap else '当前靠前'} {'、'.join(tri_strong) or '无'}；{'断档弱势' if tri_gap else '当前靠后'} {'、'.join(tri_weak) or '无'}。",
        ])
        if previous_history:
            before_candidates = self.solver.filter_candidates(previous_history)
            if before_candidates:
                before_stats = self.solver.stats(before_candidates)
                changes = sorted(
                    (
                        digit,
                        stats["freqs"].get(digit, 0.0) - before_stats["freqs"].get(digit, 0.0),
                    )
                    for digit in DIGITS
                )
                risen = sorted(changes, key=lambda item: (-item[1], item[0]))[:2]
                fallen = sorted(changes, key=lambda item: (item[1], item[0]))[:2]
                if risen and risen[0][1] >= 0.05:
                    lines.append(
                        "本轮强弱变化：" + "、".join(
                            f"{digit} 上升至 {stats['freqs'].get(digit, 0.0):.0%}" for digit, delta in risen if delta >= 0.05
                        ) + "；" + "、".join(
                            f"{digit} 下沉至 {stats['freqs'].get(digit, 0.0):.0%}" for digit, delta in fallen if delta <= -0.05
                        ) + "。"
                    )
        return lines

    def __init__(self, solver: Optional[QuestLineSolver] = None) -> None:
        self.solver = solver or QuestLineSolver()
        self.events: List[Dict[str, object]] = []
        self.chapters: List[Dict[str, object]] = []
        self.digit_index: DefaultDict[str, List[int]] = defaultdict(list)
        self.group_index: DefaultDict[str, List[int]] = defaultdict(list)

    @staticmethod
    def _format_digits(digits: Iterable[str]) -> str:
        return "、".join(str(digit) for digit in digits)

    @classmethod
    def from_history(cls, history: History, solver: Optional[QuestLineSolver] = None) -> "StoryBook":
        book = cls(solver)
        normalized = normalize_history(history)
        prefix: List[Tuple[Code, Feedback]] = []
        for guess, feedback in normalized:
            book.add_turn(prefix, guess, feedback)
            prefix.append((guess, feedback))
        return book

    def add_turn(self, history: History, guess: Code, feedback: Union[Feedback, str]) -> Dict[str, object]:
        event = dict(self.solver.explain_transition(history, guess, feedback))
        event["deliberation"] = self._build_deliberation(history, guess, feedback, event)
        event["audit_review"] = self._build_audit_review(history, guess, feedback, event)
        chapter_key, chapter_title = self._chapter_for(event)
        event["chapter"] = {"key": chapter_key, "title": chapter_title}
        event_index = len(self.events)
        self.events.append(event)
        self._index_event(event_index, event)
        if not self.chapters or self.chapters[-1]["key"] != chapter_key:
            self.chapters.append({
                "key": chapter_key,
                "title": chapter_title,
                "start_round": event["round"],
                "end_round": event["round"],
                "event_indexes": [event_index],
                "narratives": [event["narrative"]],
            })
        else:
            chapter = self.chapters[-1]
            chapter["end_round"] = event["round"]
            chapter["event_indexes"].append(event_index)
            chapter["narratives"].append(event["narrative"])
        return event

    def _build_audit_review(self, history: History, guess: Code, feedback: Feedback, event: Dict[str, object]) -> Dict[str, object]:
        """Score one move against pure AVG/MM benchmarks for the audit book."""
        candidates = self.solver.filter_candidates(history)
        after_candidates = self.solver.filter_candidates(list(history) + [(guess, feedback)])
        if not candidates:
            return {"before_count": 0, "after_count": len(after_candidates), "classification": "无可用候选"}
        guess_index = CODE_TO_INDEX[guess]
        avg_index, avg_exp, avg_max, avg_buckets = self.solver.best_pure_guess(candidates, "avg")
        mm_index, mm_exp, mm_max, mm_buckets = self.solver.best_pure_guess(candidates, "mm")
        actual_exp, actual_max, actual_buckets = self.solver.avg_remaining(candidates, guess_index)
        reduction = 1 - (len(after_candidates) / len(candidates))
        relative = actual_exp / avg_exp if avg_exp else 0.0
        if guess_index == avg_index:
            classification = "纯 AVG 最优"
        elif guess_index == mm_index:
            classification = "纯 MM 最优"
        elif actual_exp <= avg_exp * 1.08 and actual_max <= avg_max + 1:
            classification = "接近基准，兼顾调查结构"
        elif reduction >= 0.75:
            classification = "有效推进，但不是纯数学最优"
        else:
            classification = "信息收益有限，偏向叙事或位置试探"
        structure_gain = []
        action = event.get("action", {}).get("classification", {})
        if action.get("new_groups"):
            structure_gain.append(f"引入新组 {', '.join(action['new_groups'])}")
        if action.get("new_positions"):
            structure_gain.append(f"测试新位置 {', '.join(str(pos + 1) for pos in action['new_positions'])}")
        if event.get("facts", {}).get("confirmed") or event.get("facts", {}).get("excluded"):
            structure_gain.append("产生身份状态变化")
        if event.get("position_facts", {}).get("confirmed") or event.get("position_facts", {}).get("strengthened"):
            structure_gain.append("产生位置证据")
        return {
            "before_count": len(candidates),
            "after_count": len(after_candidates),
            "reduction": reduction,
            "actual": {"guess": guess, "expected": actual_exp, "max_bucket": actual_max, "buckets": actual_buckets},
            "avg": {"guess": ALL_CODES[avg_index], "expected": avg_exp, "max_bucket": avg_max, "buckets": avg_buckets},
            "mm": {"guess": ALL_CODES[mm_index], "expected": mm_exp, "max_bucket": mm_max, "buckets": mm_buckets},
            "relative_to_avg": relative,
            "classification": classification,
            "structure_gain": structure_gain,
        }

    @staticmethod
    def _audit_review_text(review: Dict[str, object], round_number: int) -> str:
        if not review.get("actual"):
            return f"### 第 {round_number} 轮行动复盘\n候选空间无效，无法进行数学基准比较。"
        actual = review["actual"]
        avg = review["avg"]
        mm = review["mm"]
        cost = actual['expected'] - avg['expected']
        tradeoff = "本步不高于纯 AVG 基准。" if cost <= 0.0001 else f"本步比纯 AVG 多保留 {cost:.2f} 个期望世界。"
        structure = "；".join(review.get("structure_gain", [])) or "未记录额外结构收益"
        return "\n".join([
            f"### 第 {round_number} 轮行动复盘：{actual['guess']}",
            f"候选空间：{review['before_count']} → {review['after_count']}（缩减 {review['reduction']:.1%}）。",
            f"本步表现：AVG 期望剩余 {actual['expected']:.2f}，最坏分桶 {actual['max_bucket']}，反馈分桶 {actual['buckets']} 个。",
            f"AVG 基准：{avg['guess']} / 期望 {avg['expected']:.2f} / 最坏 {avg['max_bucket']} / {avg['buckets']} 桶。",
            f"MM 基准：{mm['guess']} / 期望 {mm['expected']:.2f} / 最坏 {mm['max_bucket']} / {mm['buckets']} 桶。",
            f"数学代价：{tradeoff}",
            f"结构收益：{structure}。",
            f"上帝视角判断：{review['classification']}。",
        ])

    def _build_deliberation(self, history: History, guess: Code, feedback: Feedback, event: Dict[str, object]) -> str:
        """Build a data-backed closing statement for the readable book."""
        after_history = list(history) + [(guess, feedback)]
        after = event.get("after", {})
        before = event.get("before", {})
        facts = event.get("facts", {})
        position_facts = event.get("position_facts", {})
        recommendations = self.solver.choose(after_history, top_k=3).get("recommendations", [])[:3]
        confirmed = [
            digit for digit in DIGITS
            if after.get("digit_status", {}).get(digit, {}).get("status") == "confirmed"
        ]
        excluded = [
            digit for digit in DIGITS
            if after.get("digit_status", {}).get(digit, {}).get("status") == "excluded"
        ]
        unresolved = [digit for digit in DIGITS if digit not in confirmed and digit not in excluded]
        parts = [f"### 第 {event['round']} 轮总结陈词：{guess} -> {fb_to_str(feedback)}"]

        if facts.get("confirmed") or facts.get("excluded"):
            parts.append("本轮新增事实：")
            direct_confirmed = list(guess) if sum(feedback) == CODE_LEN else []
            direct_excluded = list(guess) if sum(feedback) == 0 else []
            if facts.get("confirmed"):
                direct = [digit for digit in facts["confirmed"] if digit in direct_confirmed]
                inferred = [digit for digit in facts["confirmed"] if digit not in direct]
                if direct:
                    parts.append(f"- 显式证据（反馈）：{self._format_digits(direct)} 被本轮反馈明确保留。")
                if inferred:
                    parts.append(f"- 结果集归纳确认：{self._format_digits(inferred)}；它们是结合全部历史反馈后，在所有剩余世界中都被保留下来。")
            if facts.get("excluded"):
                direct = [digit for digit in facts["excluded"] if digit in direct_excluded]
                inferred = [digit for digit in facts["excluded"] if digit not in direct]
                if direct:
                    parts.append(f"- 显式证据（反馈）：{self._format_digits(direct)} 被本轮反馈明确排除。")
                if inferred:
                    parts.append(f"- 结果集归纳排除：{self._format_digits(inferred)}；它们不是被某一轮单独点名，而是在全局一致性检验后消失。")
        else:
            before_count = before.get("candidate_count", 0)
            after_count = after.get("candidate_count", 0)
            position_changes = position_facts.get("confirmed", []) + position_facts.get("strengthened", [])
            if position_changes and after_count < before_count:
                parts.append(
                    f"本轮没有新增身份定论，但位置盘面开始收紧；答案范围从 {before_count} 个缩小到 {after_count} 个，"
                    "下一步应优先利用这些位置压力，而不是重复确认数字身份。"
                )
            elif after_count < before_count:
                parts.append(
                    f"本轮没有新增身份定论，但全局一致性检验排除了部分答案；答案范围从 {before_count} 个缩小到 {after_count} 个。"
                )
            elif position_changes:
                parts.append("本轮身份没有新增定论，但位置证据有所增强；暂不把位置倾向误读成身份确认。")
            else:
                parts.append("本轮没有产生新的身份定论，现有证据主要在重新排列答案的可信度。")

        if len(confirmed) == CODE_LEN:
            parts.append(f"全局判断：{self._format_digits(confirmed)} 已组成唯一数字集合；身份调查结束，剩下的是位置排布。")
        elif confirmed or excluded:
            parts.append(f"全局判断：已确认 {self._format_digits(confirmed) or '无'}；已排除 {self._format_digits(excluded) or '无'}；仍在竞争 {self._format_digits(unresolved) or '无'}。当前不能把案件说成纯粹的排列问题。")
        else:
            parts.append("全局判断：身份仍然开放，下一轮应优先制造数字集合之间的区分，而不是过早锁定某条主线。")

        if before.get("task") != after.get("task"):
            parts.append(f"调查方向转向：{self.public_task(after.get('task'))}。")

        strength_lines = self._strength_board(after_history, history)
        if strength_lines:
            parts.append("数字强弱盘面：\n" + "\n".join(strength_lines))

        position_lines = self._position_board(after)
        if position_facts.get("strengthened") or position_facts.get("confirmed") or position_facts.get("excluded"):
            parts.append("位置盘面：\n" + "\n".join(position_lines))
        elif position_facts.get("strengthened") or position_facts.get("confirmed"):
            parts.append("位置盘面：本轮出现位置变化，但还不足以形成稳定的排布建议。")
        else:
            parts.append("位置盘面：当前仍以身份判断为主，位置证据暂未形成可独立行动的锚点。")

        if event.get("type") == "solution_revealed":
            parts.append("本轮已经验证上一轮锁定的唯一世界；不再需要新的组队建议。")
        elif recommendations and after.get("candidate_count", 0) > 1:
            proposals = []
            for item in recommendations:
                action = item.get("action", {})
                reason = item.get("reason") or action.get("reason") or action.get("type", "继续拆分")
                reason = {
                    "fixed first guess": "建立第一层参照",
                    "opening book: stable AVG second move": "扩大调查范围，建立共同参照",
                    "introduces untested groups": "寻找尚未验证的线索",
                    "reuses tested digits in new positions": "复用已知数字，施加位置压力",
                    "tests a remaining candidate directly": "直接验证残局候选",
                    "tests a remaining candidate": "测试仍在候选空间中的答案",
                    "primarily separates feedback buckets": "区分当前答案范围",
                    "perfect endgame split": "最大化区分残局候选",
                }.get(reason, reason)
                proposals.append(f"{item.get('guess')}（{reason}）")
            parts.append("下一轮组队建议：" + "；".join(proposals) + "。这些方案来自当前候选集的同一轮评分，分别代表不同的拆分取向；请玩家决定采用哪一队。")
        elif after.get("candidate_count", 0) == 1:
            parts.append("下一轮组队建议：逻辑上已经锁定唯一世界；可以直接验证当前唯一候选，不再进行新的候选拆分。")
        else:
            parts.append("下一轮组队建议：当前没有可行方案，需要先检查反馈是否互相矛盾。")
        return "\n".join(parts)

    def _chapter_for(self, event: Dict[str, object]) -> Tuple[str, str]:
        if event["type"] == "solution_revealed":
            return "resolution", "终章：破案"
        task = event["after"].get("task")
        if task in self.CHAPTERS:
            key, title = self.CHAPTERS[task]
            return key, title
        return "investigation", "调查展开"

    def _index_event(self, event_index: int, event: Dict[str, object]) -> None:
        facts = event.get("facts", {})
        for category in ("confirmed", "likely", "excluded", "weakened", "strengthened"):
            for digit in facts.get(category, []):
                if event_index not in self.digit_index[digit]:
                    self.digit_index[digit].append(event_index)
        for category in ("strengthened", "weakened", "confirmed", "excluded"):
            for item in event.get("position_facts", {}).get(category, []):
                digit = item.get("digit")
                if digit and event_index not in self.digit_index[digit]:
                    self.digit_index[digit].append(event_index)
        for change in event.get("group_changes", []):
            group = change.get("group")
            if group and event_index not in self.group_index[group]:
                self.group_index[group].append(event_index)

    def chapter(self, key: str) -> Optional[Dict[str, object]]:
        return next((item for item in self.chapters if item["key"] == key), None)

    def to_dict(self) -> Dict[str, object]:
        return {
            "event_count": len(self.events),
            "chapter_count": len(self.chapters),
            "chapters": self.chapters,
            "events": self.events,
            "digit_index": dict(self.digit_index),
            "group_index": dict(self.group_index),
        }

    def weighted_stats(self, candidates: Tuple[int, ...], guess_index: int, weights: Dict[int, float]) -> Tuple[float, float, int]:
        self.ensure_matrix()
        assert self.feedback_matrix is not None
        row = self.feedback_matrix[guess_index]
        buckets: DefaultDict[int, List[int]] = defaultdict(list)
        for answer_index in candidates:
            buckets[row[answer_index]].append(answer_index)
        total_w = sum(weights[idx] for idx in candidates)
        expected = 0.0
        max_weight = 0.0
        for bucket in buckets.values():
            bucket_w = sum(weights[idx] for idx in bucket)
            expected += (bucket_w / total_w) * len(bucket)
            max_weight = max(max_weight, bucket_w)
        return expected, max_weight, len(buckets)

    # ------------------------------------------------------------------
    # Signal modes and strategy scoring
    # ------------------------------------------------------------------

    def classify_action(self, guess: Code, history: History, investigation: Dict[str, object], is_candidate: bool) -> Dict[str, object]:
        """Describe what a guess is investigating, independent of its score."""
        normalized = normalize_history(history)
        if any(previous_guess == guess for previous_guess, _ in normalized):
            return {
                "type": "redundant",
                "reason": "repeats an already tested guess without adding information",
                "groups": [group for group in GROUP_ORDER if any(digit in FIXED_GROUPS[group] for digit in guess)],
                "new_groups": [],
                "new_group_digit_counts": {},
                "new_positions": [],
            }
        tested_groups = set(investigation.get("tested_groups", []))
        guess_groups = [group for group in GROUP_ORDER if any(digit in FIXED_GROUPS[group] for digit in guess)]
        new_groups = [group for group in guess_groups if group not in tested_groups]
        new_group_digit_counts = {
            group: sum(digit in FIXED_GROUPS[group] for digit in guess)
            for group in new_groups
        }
        used = self.used_positions(normalized)
        new_positions = [position for position, digit in enumerate(guess) if position not in used.get(digit, set())]

        if is_candidate and investigation.get("task") == "resolve_endgame":
            action_type = "candidate_probe"
            reason = "tests a remaining candidate directly"
        elif new_groups:
            action_type = "group_probe"
            reason = "introduces untested groups"
        elif new_positions:
            action_type = "position_probe"
            reason = "reuses tested digits in new positions"
        elif is_candidate:
            action_type = "candidate_probe"
            reason = "tests a remaining candidate"
        else:
            action_type = "mechanical_split"
            reason = "primarily separates feedback buckets"

        return {
            "type": action_type,
            "reason": reason,
            "groups": guess_groups,
            "new_groups": new_groups,
            "new_group_digit_counts": new_group_digit_counts,
            "new_positions": new_positions,
        }

    @staticmethod
    def action_is_eligible(action: Dict[str, object], task: str) -> bool:
        """Apply structural investigation rules before numerical ranking."""
        action_type = action.get("type")
        if action_type == "redundant":
            return False
        if task == "cross_test_new_group":
            if action_type != "group_probe":
                return False
            new_groups = action.get("new_groups", [])
            counts = action.get("new_group_digit_counts", {})
            if len(new_groups) != 1:
                return False
            new_group = new_groups[0]
            return counts.get(new_group) == 2
        if task == "converge_outer_choice":
            if action_type != "group_probe":
                return False
            new_groups = action.get("new_groups", [])
            counts = action.get("new_group_digit_counts", {})
            if len(new_groups) != 1:
                return False
            return counts.get(new_groups[0], 0) in {1, 2}
        return True


class StoryBook(_QuestLineReasoningLayer):
    """Public story organizer built on the solver's explanation layer."""

    STATUS_TITLES = {
        "excluded": "从解释空间移除",
        "possible": "候选保留",
        "likely": "较强解释",
        "confirmed": "身份锁定",
    }

    def render(self, include_indexes: bool = False, audit: bool = False) -> str:
        """Render either the readable case book or the complete audit record."""
        if not self.events:
            return "《QuestLine 案件记录》\n\n案件尚未开始。"

        lines = ["《QuestLine 案件记录》", "", f"共 {len(self.events)} 轮，形成 {len(self.chapters)} 个章节。"]
        for chapter in self.chapters:
            lines.extend(["", f"## {chapter['title']}"])
            for event_index in chapter["event_indexes"]:
                event = self.events[event_index]
                deliberation = event.get("deliberation")
                if audit:
                    review = event.get("audit_review")
                    if review:
                        lines.append(self._audit_review_text(review, event["round"]))
                    if deliberation:
                        lines.extend(["", deliberation])
                elif deliberation:
                    lines.append(deliberation)
                else:
                    lines.append(event["narrative"])

        final = self.events[-1]
        if final["type"] == "solution_revealed":
            lines.extend(["", "案件结论：反馈已经确认答案，调查结束。"])
        elif final["after"].get("candidate_count") == 0:
            lines.extend(["", "案件状态：反馈与现有证据冲突，需要检查输入或重新审理。"])
        elif final["after"].get("candidate_count") == 1:
            lines.extend(["", "案件状态：逻辑上已经锁定唯一世界，等待最终反馈确认。"])
        else:
            lines.extend(["", f"案件状态：仍有 {final['after'].get('candidate_count')} 个可能世界，调查尚未结束。"])

        facts = self.render_current_facts()
        if facts:
            lines.extend(["", "## 当前已知事实", facts])

        if include_indexes and not audit:
            lines.extend(["", "## 角色索引", self.render_digit_index()])
            lines.extend(["", "## 阵营索引", self.render_group_index()])
        return "\n".join(lines)

    def render_current_facts(self) -> str:
        """Render the latest factual readout for the readable case book."""
        if not self.events:
            return ""
        after = self.events[-1].get("after", {})
        status_map = after.get("digit_status", {})
        confirmed = [digit for digit in DIGITS if status_map.get(digit, {}).get("status") == "confirmed"]
        excluded = [digit for digit in DIGITS if status_map.get(digit, {}).get("status") == "excluded"]
        unresolved = [digit for digit in DIGITS if digit not in confirmed and digit not in excluded]
        confirmed_positions = []
        excluded_positions = []
        for digit in DIGITS:
            if status_map.get(digit, {}).get("status") == "excluded":
                continue
            for position, status in enumerate(status_map.get(digit, {}).get("position_status", [])):
                if status == "confirmed":
                    confirmed_positions.append(f"{digit}→第{position + 1}位")

        lines = []
        if confirmed:
            lines.append(f"已锁定数字：{self._format_digits(confirmed)}。")
        if excluded:
            lines.append(f"已淘汰数字：{self._format_digits(excluded)}。")
        if unresolved:
            lines.append(f"尚未定案数字：{self._format_digits(unresolved)}。")
        if confirmed_positions:
            lines.append(f"已锁定位置：{'、'.join(confirmed_positions)}。")
        lines.append("位置盘面：\n" + "\n".join(self._position_board(after)))
        history = [
            (event.get("action", {}).get("guess"), parse_feedback(event.get("action", {}).get("feedback")))
            for event in self.events
        ]
        strength_lines = self._strength_board(history, history[:-1])
        if strength_lines:
            lines.append("数字强弱盘面：\n" + "\n".join(strength_lines))
        if len(confirmed) == CODE_LEN:
            lines.append("数字身份已经确定，当前重点是安排四个数字的正确顺序。")
        elif confirmed and excluded:
            lines.append("调查重点：继续确定剩余数字的身份，并同步收集位置证据。")
        task = after.get("task")
        if task:
            lines.append(f"当前调查任务：{self.public_task(task)}。")
        return "\n".join(lines)

    def render_audit(self) -> str:
        """Render the complete case record for post-game review."""
        return self.render(audit=True)

    def render_identity_arc(self) -> str:
        """Summarize how trust in each digit evolved across the case."""
        if not self.events:
            return ""
        rows = []
        for digit in DIGITS:
            states = []
            for event in self.events:
                status = event.get("after", {}).get("digit_status", {}).get(digit, {}).get("status")
                if status and (not states or states[-1] != status):
                    states.append(status)
            changes = [
                event["round"] for event in self.events
                if digit in event.get("facts", {}).get("support_risen", [])
                or digit in event.get("facts", {}).get("support_fallen", [])
                or digit in event.get("facts", {}).get("confirmed", [])
                or digit in event.get("facts", {}).get("excluded", [])
            ]
            if len(states) > 1 or changes:
                max_support = max(
                    event.get("after", {}).get("digit_support", {}).get(digit, 0.0)
                    for event in self.events
                )
                final_status = self.events[-1].get("after", {}).get("digit_status", {}).get(digit, {}).get("status")
                if max_support < 0.75 and final_status == "excluded":
                    interpretation = "曾被保留在候选空间，始终未进入可信解释"
                elif final_status == "confirmed":
                    interpretation = "最终进入可信解释"
                else:
                    interpretation = "身份仍需结合组关系判断"
                rows.append(f"数字 {digit}：{' → '.join(states)}；{interpretation}；关键认知变化见第 {', '.join(map(str, changes))} 轮")
        return "\n".join(rows)

    def render_character_stories(self) -> str:
        """Render a separate evidence story for every digit that changed."""
        if not self.events:
            return ""
        rows = []
        for digit in DIGITS:
            entries = []
            previous_status = "possible"
            previous_support = None
            for event in self.events:
                before = event.get("before", {})
                after = event.get("after", {})
                if previous_support is None:
                    previous_status = before.get("digit_status", {}).get(digit, {}).get("status", "possible")
                    previous_support = before.get("digit_support", {}).get(digit, 0.0)
                status = after.get("digit_status", {}).get(digit, {}).get("status", "possible")
                support = after.get("digit_support", {}).get(digit, 0.0)
                delta = support - previous_support
                facts = event.get("facts", {})
                if status != previous_status:
                    entries.append(
                        f"第{event['round']}轮，证据地位由“{self.STATUS_TITLES.get(previous_status, previous_status)}”"
                        f"转为“{self.STATUS_TITLES.get(status, status)}”。"
                    )
                elif digit in facts.get("support_risen", []):
                    entries.append(f"第{event['round']}轮，其所在解释获得更多支撑，但尚未形成身份结论。")
                elif digit in facts.get("support_fallen", []):
                    entries.append(f"第{event['round']}轮，其所在解释的支撑减弱。")
                if digit in facts.get("confirmed", []):
                    entries.append(f"第{event['round']}轮，{digit} 的身份被锁定。")
                for group in GROUP_ORDER:
                    if digit not in group:
                        continue
                    partner = next(item for item in group if item != digit)
                    before_group = before.get("group_states", {}).get(group, {}).get("status")
                    after_group = after.get("group_states", {}).get(group, {}).get("status")
                    if before_group != after_group and after_group == "excluded":
                        entries.append(
                            f"第{event['round']}轮，与数字 {partner} 共同构成的组级解释被整体排除；"
                            f"{digit} 未因此获得身份信任。"
                        )
                    elif before_group != after_group and after_group == "full":
                        entries.append(
                            f"第{event['round']}轮，与数字 {partner} 共同构成的组级解释获得完整支持。"
                        )
                    relation = after.get("group_relations", {}).get(group, {}).get("relation")
                    if relation == "one_strong_one_weak":
                        group_support = after.get("group_relations", {}).get(group, {}).get("support", {})
                        strong = max(group_support, key=group_support.get)
                        weak = min(group_support, key=group_support.get)
                        if digit == strong and after.get("digit_status", {}).get(weak, {}).get("status") not in {"excluded", "confirmed"}:
                            entries.append(
                                f"第{event['round']}轮，{group} 内部证据分化；{digit} 暂时成为较强解释，"
                                f"但仍需等待对数字 {weak} 的排除。"
                            )
                        elif digit == weak and status not in {"excluded", "confirmed"}:
                            entries.append(
                                f"第{event['round']}轮，{group} 内部证据分化；{digit} 的解释被置于较弱位置，"
                                f"尚未完成排除。"
                            )
                previous_status = status
                previous_support = support
            if entries:
                final_status = self.events[-1].get("after", {}).get("digit_status", {}).get(digit, {}).get("status")
                max_support = max(
                    event.get("after", {}).get("digit_support", {}).get(digit, 0.0)
                    for event in self.events
                )
                if final_status == "excluded" and max_support < 0.75:
                    entries.append("结案判断：它始终只是候选空间中的影子，从未进入可信解释，也没有成为可信身份。")
                elif final_status == "confirmed":
                    entries.append("结案判断：它最终成为当前答案解释中不可替代的一员。")
                rows.append(f"数字 {digit}\n" + " ".join(entries))
        return "\n".join(rows)

    def render_digit_index(self) -> str:
        """Render the rounds in which each digit's evidence changed."""
        rows = []
        for digit in DIGITS:
            rounds = self.digit_index.get(digit, [])
            if rounds:
                rows.append(f"数字 {digit}：第 {', '.join(str(index + 1) for index in rounds)} 轮出现关键变化")
        return "\n".join(rows) if rows else "暂时没有数字获得新的证据。"

    def render_group_index(self) -> str:
        """Render the groups whose internal relation changed."""
        rows = []
        for group in GROUP_ORDER:
            rounds = self.group_index.get(group, [])
            if rounds:
                rows.append(f"小组 {group}：第 {', '.join(str(index + 1) for index in rounds)} 轮关系发生变化")
        return "\n".join(rows) if rows else "暂时没有小组关系发生结构性变化。"


class QuestLineSolver(_QuestLineReasoningLayer):
    """Complete solver assembled from the core and investigation layers."""

    def __init__(self, use_cache: bool = True, verbose: bool = False) -> None:
        _QuestLineCore.__init__(self, use_cache=use_cache, verbose=verbose)

    def investigation_state(self, history: History) -> Dict[str, object]:
        """Build the factual investigation state without applying score weights.

        This is the first layer of the refactored engine. It describes what has
        been tested and what the remaining candidate set says about each group;
        it does not decide which candidate is more narratively likely.
        """
        normalized = normalize_history(history)
        candidates = self.filter_candidates(normalized)
        candidate_count = len(candidates)
        tested_groups = [
            group for group in GROUP_ORDER
            if any(any(digit in FIXED_GROUPS[group] for digit in guess) for guess, _ in normalized)
        ]
        untested_groups = [group for group in GROUP_ORDER if group not in tested_groups]

        group_states: Dict[str, Dict[str, object]] = {}
        for group in GROUP_ORDER:
            occupancy = Counter(
                sum(digit in FIXED_GROUPS[group] for digit in ALL_CODES[index])
                for index in candidates
            )
            zero_count = occupancy.get(0, 0)
            two_count = occupancy.get(2, 0)
            if not normalized:
                status = "unobserved"
            elif candidate_count == 0:
                status = "inconsistent"
            elif zero_count == candidate_count:
                status = "excluded"
            elif two_count == candidate_count:
                status = "full"
            elif group not in tested_groups:
                status = "unobserved"
            elif zero_count == 0:
                status = "present"
            else:
                status = "contested"
            group_states[group] = {
                "status": status,
                "tested": group in tested_groups,
                "occupancy_counts": {str(amount): occupancy.get(amount, 0) for amount in range(3)},
                "possible_candidate_support": (candidate_count - zero_count) / candidate_count if candidate_count else 0.0,
                "full_candidate_support": two_count / candidate_count if candidate_count else 0.0,
            }

        digit_support = {
            digit: sum(digit in ALL_CODES[index] for index in candidates) / candidate_count
            if candidate_count else 0.0
            for digit in DIGITS
        }
        digit_position_support = {
            digit: [
                sum(ALL_CODES[index][position] == digit for index in candidates) / candidate_count
                if candidate_count else 0.0
                for position in range(CODE_LEN)
            ]
            for digit in DIGITS
        }

        def support_status(support: float) -> str:
            if support <= 0.02:
                return "excluded"
            if support >= 0.98:
                return "confirmed"
            if support >= 0.75:
                return "likely"
            return "possible"

        digit_status = {}
        for digit, support in digit_support.items():
            positions = digit_position_support[digit]
            digit_status[digit] = {
                "support": support,
                "status": support_status(support),
                "position_support": positions,
                "position_status": [support_status(value) for value in positions],
                "most_likely_position": max(range(CODE_LEN), key=lambda position: positions[position]),
            }

        group_relations: Dict[str, Dict[str, object]] = {}
        for group in GROUP_ORDER:
            group_digits = sorted(FIXED_GROUPS[group])
            first, second = group_digits
            first_support = digit_support[first]
            second_support = digit_support[second]
            support_gap = abs(first_support - second_support)
            position_gap = max(
                abs(left - right)
                for left, right in zip(
                    digit_position_support[first], digit_position_support[second]
                )
            )
            both_supported = first_support > 0.25 and second_support > 0.25
            both_excluded = first_support <= 0.02 and second_support <= 0.02
            one_strong_one_weak = (
                max(first_support, second_support) >= 0.75
                and min(first_support, second_support) <= 0.25
            )
            if both_excluded:
                relation = "both_excluded"
            elif one_strong_one_weak:
                relation = "one_strong_one_weak"
            elif both_supported and support_gap <= 0.03:
                relation = "symmetric"
            elif both_supported and position_gap >= 0.35:
                relation = "position_conflict"
            elif both_supported:
                relation = "both_supported"
            else:
                relation = "unresolved"
            group_relations[group] = {
                "digits": group_digits,
                "relation": relation,
                "support": {first: first_support, second: second_support},
                "support_gap": support_gap,
                "position_gap": position_gap,
                "both_supported": both_supported,
                "both_excluded": both_excluded,
            }
        confirmed_digits = [digit for digit in DIGITS if digit_status[digit]["status"] == "confirmed"]
        likely_digits = [digit for digit in DIGITS if digit_status[digit]["status"] == "likely"]
        excluded_digits = [digit for digit in DIGITS if digit_status[digit]["status"] == "excluded"]
        weak_tested_groups = [
            group for group in tested_groups
            if group_states[group]["possible_candidate_support"] <= 0.15
        ]
        outer_supports = [digit_support[digit] for digit in "6789"]
        outer_is_symmetric = bool(outer_supports) and max(outer_supports) - min(outer_supports) <= 0.03
        strong_conflict_groups = [
            group for group, relation in group_relations.items()
            if relation["relation"] in {"one_strong_one_weak", "position_conflict"}
        ]
        position_uncertainty = [
            digit for digit in DIGITS
            if digit_status[digit]["status"] in {"confirmed", "likely"}
            and max(digit_position_support[digit]) < 0.98
        ]

        if not normalized:
            task = "establish_foundation"
        elif set(tested_groups) == {"01", "23"} and "45" not in tested_groups:
            task = "introduce_45"
        elif candidate_count <= 12:
            task = "resolve_endgame"
        elif strong_conflict_groups and not untested_groups:
            task = "resolve_group_conflict"
        elif position_uncertainty and not untested_groups:
            task = "apply_position_pressure"
        elif candidate_count <= 150 and (len(confirmed_digits) >= 3 or (weak_tested_groups and outer_is_symmetric)):
            task = "converge_outer_choice"
        elif len(untested_groups) >= 1:
            task = "cross_test_new_group" if len(tested_groups) >= 2 else "investigate_outer_groups"
        elif any(state["status"] == "contested" for state in group_states.values()):
            task = "resolve_group_conflict"
        else:
            task = "apply_position_pressure"

        available_actions = ["group_probe", "position_probe", "candidate_probe", "mechanical_split"]
        if task in {"establish_foundation", "introduce_45", "cross_test_new_group", "investigate_outer_groups", "converge_outer_choice"}:
            preferred_actions = ["group_probe", "position_probe"]
        elif task == "resolve_endgame":
            preferred_actions = ["candidate_probe", "mechanical_split"]
        elif task == "resolve_group_conflict":
            preferred_actions = ["group_probe", "position_probe", "mechanical_split"]
        else:
            preferred_actions = ["position_probe", "group_probe", "mechanical_split"]

        return {
            "round": len(normalized),
            "candidate_count": candidate_count,
            "tested_groups": tested_groups,
            "untested_groups": untested_groups,
            "group_states": group_states,
            "digit_support": digit_support,
            "digit_position_support": digit_position_support,
            "digit_status": digit_status,
            "confirmed_digits": confirmed_digits,
            "likely_digits": likely_digits,
            "excluded_digits": excluded_digits,
            "weak_tested_groups": weak_tested_groups,
            "group_relations": group_relations,
            "strong_conflict_groups": strong_conflict_groups,
            "position_uncertainty": position_uncertainty,
            "outer_is_symmetric": outer_is_symmetric,
            "task": task,
            "available_actions": available_actions,
            "preferred_actions": preferred_actions,
            "task_status": "ready",
            "task_policy": self.task_policy(task, candidate_count),
        }

    def game_phase(self, history: List[Tuple[Code, Feedback]], candidates: Tuple[int, ...]) -> str:
        if not history:
            return "opening_first"
        if len(history) == 1 and history[0][0] == OPENING_FIRST:
            return "opening_second"
        if len(candidates) <= 12:
            return "endgame"
        return "case"

    @staticmethod
    def task_policy(task: str, candidate_count: int) -> Dict[str, object]:
        """Describe the current task's objective and efficiency contract."""
        policies = {
            "establish_foundation": ("weighted_expected", 1.20, 2.0, 1.35, 4),
            "introduce_45": ("weighted_expected", 1.20, 2.0, 1.35, 4),
            "investigate_outer_groups": ("weighted_expected", 1.35, 2.5, 1.50, 5),
            "cross_test_new_group": ("weighted_expected", 1.35, 2.5, 1.50, 5),
            "converge_outer_choice": ("main_world_expected", 1.55, 3.0, 1.75, 6),
            "resolve_group_conflict": ("main_world_expected", 1.45, 3.0, 1.65, 6),
            "apply_position_pressure": ("normal_expected", 1.30, 2.5, 1.50, 5),
            "resolve_endgame": ("normal_max_bucket", 1.80, 3.0, 2.00, 6),
        }
        objective, exp_ratio, exp_slack, max_ratio, max_slack = policies.get(
            task, ("normal_expected", 1.35, 2.5, 1.55, 5)
        )
        return {
            "task": task,
            "objective": objective,
            "expected_ratio": exp_ratio,
            "expected_slack": exp_slack,
            "max_ratio": max_ratio,
            "max_slack": max_slack,
            "candidate_count": candidate_count,
        }

    @staticmethod
    def task_transition(task: str) -> Optional[str]:
        transitions = {
            "establish_foundation": "investigate_outer_groups",
            "introduce_45": "investigate_outer_groups",
            "investigate_outer_groups": "apply_position_pressure",
            "cross_test_new_group": "apply_position_pressure",
            "converge_outer_choice": "resolve_group_conflict",
            "resolve_group_conflict": "apply_position_pressure",
            "apply_position_pressure": "resolve_endgame",
            "resolve_endgame": None,
        }
        return transitions.get(task)

    @staticmethod
    def task_sort_key(item: Dict[str, object], investigation: Dict[str, object]) -> Tuple[object, ...]:
        """Rank eligible actions by the current investigation objective.

        The legacy score is deliberately absent from this key. AVG/MM limits
        are applied before sorting; the task objectives and deterministic code
        order decide the result from this point onward.
        """
        task = investigation.get("task")
        action = item["action"]
        action_type = action["type"]
        preferred = investigation.get("preferred_actions", [])
        action_rank = preferred.index(action_type) if action_type in preferred else len(preferred)

        if task in {"establish_foundation", "introduce_45", "cross_test_new_group", "investigate_outer_groups"}:
            objective = (
                item["weighted_expected"],
                item["main_world_expected"],
                item["normal_expected"],
                item["normal_max_bucket"],
            )
        elif task == "converge_outer_choice":
            objective = (
                item["main_world_expected"],
                item["weighted_expected"],
                item["normal_expected"],
                item["normal_max_bucket"],
            )
        elif task == "resolve_group_conflict":
            objective = (
                item["main_world_expected"],
                item["normal_max_bucket"],
                item["normal_expected"],
                item["weighted_expected"],
            )
        elif task == "apply_position_pressure":
            objective = (
                item["normal_expected"],
                item["normal_max_bucket"],
                item["weighted_expected"],
                item["main_world_expected"],
            )
        else:
            objective = (
                -int(item["is_candidate"]),
                item["normal_max_bucket"],
                item["normal_expected"],
                item["weighted_expected"],
                item["main_world_expected"],
            )
        return (action_rank,) + objective + (item["guess"],)

    @staticmethod
    def used_positions(history: List[Tuple[Code, Feedback]]) -> Dict[str, set[int]]:
        used: Dict[str, set[int]] = defaultdict(set)
        for guess, _ in history:
            for pos, ch in enumerate(guess):
                used[ch].add(pos)
        return used

    def choose(self, history: History, top_k: int = 15) -> Dict[str, object]:
        normalized = normalize_history(history)
        investigation = self.investigation_state(normalized)

        # Serve opening book without loading the matrix.
        if len(normalized) == 0:
            opening_action = self.classify_action(OPENING_FIRST, normalized, investigation, True)
            return {"phase": "opening_first", "investigation": investigation, "candidates": ALL_CODES, "recommendations":[{"guess": OPENING_FIRST, "score": 0.0, "is_candidate": True, "reason": "fixed first guess", "action": opening_action}]}
        if len(normalized) == 1 and normalized[0][0] == OPENING_FIRST:
            second = OPENING_SECOND_BY_FEEDBACK.get(normalized[0][1])
            if second is not None:
                second_action = self.classify_action(second, normalized, investigation, False)
                return {"phase": "opening_second", "investigation": investigation, "candidates": [], "recommendations":[{"guess": second, "score": 0.0, "is_candidate": False, "reason": "opening book: stable AVG second move", "action": second_action}]}

        candidates = self.filter_candidates(normalized)
        if not candidates:
            investigation["task_status"] = "state_inconsistent"
            return {
                "phase": "inconsistent",
                "investigation": investigation,
                "candidates": [],
                "recommendations": [],
                "raw_recommendations": [],
                "task_eligible_count": 0,
            }
        phase = self.game_phase(normalized, candidates)
        stats = self.stats(candidates)
        n = stats["n"]
        weights, main_candidates = self.candidate_weights(candidates, stats)
        candidate_set = set(candidates)
        used = self.used_positions(normalized)
        avg_index, avg_exp, avg_max, avg_bucket_count = self.best_pure_guess(candidates, "avg")

        if phase == "endgame" and len(candidates) <= 10 and avg_max == 1:
            return {
                "phase": phase,
                "investigation": investigation,
                "candidates": [ALL_CODES[i] for i in candidates],
                "avg_anchor": {"guess": ALL_CODES[avg_index], "exp": avg_exp, "max": avg_max, "bucket_count": avg_bucket_count},
                "recommendations": [{"guess": ALL_CODES[avg_index], "score": avg_exp, "is_candidate": avg_index in candidate_set, "reason": "perfect endgame split", "action": self.classify_action(ALL_CODES[avg_index], normalized, investigation, avg_index in candidate_set)}],
            }

        policy = investigation["task_policy"]
        exp_limit = avg_exp * policy["expected_ratio"] + policy["expected_slack"]
        max_limit = avg_max * policy["max_ratio"] + policy["max_slack"]
        scored: List[Dict[str, object]] = []
        for guess_index, guess in enumerate(ALL_CODES):
            weighted_exp, weighted_max, bucket_count = self.weighted_stats(candidates, guess_index, weights)
            normal_exp, normal_max, _ = self.avg_remaining(candidates, guess_index)
            main_exp, _, _ = self.avg_remaining(main_candidates, guess_index)
            is_candidate = guess_index in candidate_set
            scored.append({
                "guess": guess,
                "is_candidate": is_candidate,
                "weighted_expected": weighted_exp,
                "normal_expected": normal_exp,
                "normal_max_bucket": normal_max,
                "main_world_expected": main_exp,
                "bucket_count": bucket_count,
            })
            scored[-1]["action"] = self.classify_action(guess, normalized, investigation, is_candidate)
        guarded = [
            x for x in scored
            if x["normal_expected"] <= exp_limit + 1e-9
            and x["normal_max_bucket"] <= max_limit
        ]
        task = investigation.get("task")
        structurally_eligible = [x for x in scored if self.action_is_eligible(x["action"], task)]
        task_eligible = [x for x in guarded if self.action_is_eligible(x["action"], task)]
        if task_eligible:
            guarded = task_eligible
            investigation["task_status"] = "ready"
        elif structurally_eligible:
            guarded = structurally_eligible
            investigation["task_status"] = "task_relaxable"
        else:
            guarded = scored
            investigation["task_status"] = "task_infeasible"
            investigation["next_task"] = self.task_transition(task)
        if all(x["guess"] != ALL_CODES[avg_index] for x in guarded) and not structurally_eligible:
            avg_item = next((x for x in scored if x["guess"] == ALL_CODES[avg_index]), None)
            if avg_item:
                guarded.append(avg_item)
        guarded.sort(key=lambda x: self.task_sort_key(x, investigation))
        action_summary = Counter(item["action"]["type"] for item in guarded)
        return {
            "phase": phase,
            "investigation": investigation,
            "candidates": [ALL_CODES[i] for i in candidates],
            "avg_anchor": {"guess": ALL_CODES[avg_index], "exp": avg_exp, "max": avg_max, "bucket_count": avg_bucket_count},
            "task_policy": policy,
            "action_summary": dict(action_summary),
            "task_eligible_count": len(task_eligible),
            "recommendations": guarded[:top_k],
            "raw_recommendations": guarded[:top_k],
        }

    def next_guess(self, history: History) -> Code:
        return self.choose(history, top_k=1)["recommendations"][0]["guess"]


    def play_answer(self, answer: Code, max_steps: int = 10) -> List[Tuple[Code, Feedback, int]]:
        answer = validate_code(answer)
        history: List[Tuple[Code, Feedback]] = []
        rows: List[Tuple[Code, Feedback, int]] = []
        for _ in range(max_steps):
            guess = self.next_guess(history)
            fb = self.feedback(answer, guess)
            history.append((guess, fb))
            remaining = len(self.filter_candidates(history))
            rows.append((guess, fb, remaining))
            if fb == (4, 0):
                break
        return rows


class GameSession:
    """Shared product state for Assist, Simulation, and Adventure modes."""

    MODES = {"assist", "simulation", "adventure"}
    ACTIVE = "active"
    LOGICALLY_SOLVED = "logically_solved"
    SOLVED = "solved"
    INCONSISTENT = "inconsistent"

    def __init__(self, mode: str = "assist", solver: Optional[QuestLineSolver] = None, answer: Optional[Code] = None) -> None:
        if mode not in self.MODES:
            raise ValueError(f"Unknown GameSession mode: {mode}")
        if mode in {"simulation", "adventure"} and answer is None:
            raise ValueError(f"{mode.capitalize()} mode requires an answer.")
        self.mode = mode
        self.solver = solver or QuestLineSolver()
        self.answer = validate_code(answer) if answer is not None else None
        self.history: List[Tuple[Code, Feedback]] = []
        self.story = StoryBook(solver=self.solver)
        self.status = self.ACTIVE
        self.logical_answer: Optional[Code] = None
        self.last_event: Optional[Dict[str, object]] = None
        self.rejected_turns: List[Dict[str, object]] = []

    @property
    def round(self) -> int:
        return len(self.history)

    def state(self) -> Dict[str, object]:
        candidates = self.solver.filter_candidates(self.history)
        investigation = self.solver.investigation_state(self.history)
        if len(candidates) == 1:
            self.logical_answer = ALL_CODES[candidates[0]]
            if self.status == self.ACTIVE:
                self.status = self.LOGICALLY_SOLVED
        elif not candidates:
            self.status = self.INCONSISTENT
        return {
            "mode": self.mode,
            "status": self.status,
            "round": self.round,
            "candidate_count": len(candidates),
            "logical_answer": self.logical_answer,
            "answer_known": self.answer is not None,
            "investigation": investigation,
            "next_action": self.next_action(),
        }

    def next_action(self) -> Optional[Dict[str, object]]:
        if self.status in {self.SOLVED, self.INCONSISTENT}:
            return None
        result = self.solver.choose(self.history, top_k=1)
        recommendations = result.get("recommendations", [])
        return recommendations[0] if recommendations else None

    def apply_turn(self, guess: Code, feedback: Optional[Union[Feedback, str]] = None, source: str = "QuestLine") -> Dict[str, object]:
        if self.status in {self.SOLVED, self.INCONSISTENT}:
            raise ValueError(f"Session is not accepting turns: {self.status}")
        guess = validate_code(guess)
        if self.mode == "adventure":
            if self.answer is None:
                raise ValueError("Adventure mode requires a hidden answer.")
            actual_feedback = self.solver.feedback(self.answer, guess)
            if feedback is not None and validate_feedback(parse_feedback(feedback)) != actual_feedback:
                self._reject_turn(guess, feedback, "feedback does not match the hidden answer", source)
                raise ValueError("Adventure feedback does not match the hidden answer.")
            parsed_feedback = actual_feedback
        else:
            if feedback is None:
                raise ValueError("This mode requires feedback.")
            parsed_feedback = validate_feedback(parse_feedback(feedback))
        trial = self.history + [(guess, parsed_feedback)]
        if not self.solver.filter_candidates(trial):
            self._reject_turn(guess, parsed_feedback, "feedback leaves no possible answer", source)
            raise ValueError("Feedback leaves no possible answer.")
        event = self.story.add_turn(self.history, guess, parsed_feedback)
        self.history.append((guess, parsed_feedback))
        self.last_event = event
        if parsed_feedback == (CODE_LEN, 0):
            self.status = self.SOLVED
        else:
            self.state()
        event["session"] = {"mode": self.mode, "status": self.status, "round": self.round, "source": source}
        return event

    def _reject_turn(self, guess: Code, feedback: object, reason: str, source: str) -> None:
        self.rejected_turns.append({
            "round": self.round + 1,
            "guess": guess,
            "feedback": fb_to_str(parse_feedback(feedback)) if feedback is not None else None,
            "source": source,
            "reason": reason,
        })

    def simulation_step(self) -> Dict[str, object]:
        if self.mode != "simulation":
            raise ValueError("simulation_step is only available in Simulation mode.")
        action = self.next_action()
        if not action:
            raise ValueError("No action is available.")
        guess = action["guess"]
        assert self.answer is not None
        return self.apply_turn(guess, self.solver.feedback(self.answer, guess), source="QuestLine")

    def read_story(self, include_indexes: bool = False) -> str:
        return self.story.render(include_indexes=include_indexes)

    def current_state(self) -> Dict[str, object]:
        """Structured read API for clients such as a future WebUI."""
        state = self.state()
        investigation = state["investigation"]
        world_line = self.solver.world_line_analysis(self.history)
        state.update({
            "digits": investigation.get("digit_status", {}),
            "groups": investigation.get("group_states", {}),
            "group_relations": investigation.get("group_relations", {}),
            "world_line": world_line,
            "chapters": list(self.story.chapters),
            "suspense": self._suspense(state),
            "last_event": self.last_event,
        })
        return state

    @staticmethod
    def _suspense(state: Dict[str, object]) -> Dict[str, object]:
        """Expose a small narrative status object for UI clients."""
        investigation = state.get("investigation", {})
        candidate_count = int(state.get("candidate_count", 0))
        task = investigation.get("task")
        if state.get("status") == GameSession.SOLVED:
            level, title = "resolved", "案件已告破"
        elif state.get("status") == GameSession.INCONSISTENT:
            level, title = "fractured", "证据链出现矛盾"
        elif candidate_count == 1:
            level, title = "final", "真相只剩一条解释"
        elif task == "resolve_endgame":
            level, title = "closing", "外围解释正在收束"
        elif task == "resolve_group_conflict":
            level, title = "turning_point", "组内关系等待拆分"
        else:
            level, title = "open", "案件仍在展开"
        return {"level": level, "title": title, "candidate_count": candidate_count, "task": task}

    def timeline(self) -> List[Dict[str, object]]:
        return list(self.story.events)

    def replay(self) -> Dict[str, object]:
        """Return accepted transitions and rejected attempts for replay clients."""
        return {
            "mode": self.mode,
            "status": self.status,
            "accepted": [
                {
                    "round": event["round"],
                    "guess": event["action"]["guess"],
                    "feedback": event["action"]["feedback"],
                    "source": event.get("session", {}).get("source", "QuestLine"),
                    "chapter": event.get("chapter"),
                }
                for event in self.story.events
            ],
            "rejected": list(self.rejected_turns),
        }

    def export_markdown(self, include_indexes: bool = True) -> str:
        """Export the current case as a portable Markdown case file."""
        lines = [self.read_story(include_indexes=include_indexes), "", "## 会话信息"]
        lines.append(f"- 模式：{self.mode}")
        lines.append(f"- 状态：{self.status}")
        lines.append(f"- 已接受行动：{len(self.history)}")
        if self.rejected_turns:
            lines.extend(["", "## 被拒绝的输入"])
            for item in self.rejected_turns:
                lines.append(
                    f"- 第{item['round']}轮，{item['guess']} / {item['feedback'] or '未提供反馈'}：{item['reason']}"
                )
        return "\n".join(lines)

    def save(self, include_answer: bool = False) -> Dict[str, object]:
        """Return a JSON-safe session snapshot suitable for save/resume."""
        return self.to_dict(include_answer=include_answer)

    @classmethod
    def resume(cls, snapshot: Dict[str, object], solver: Optional[QuestLineSolver] = None) -> "GameSession":
        """Resume a session from a snapshot without trusting rendered text."""
        mode = str(snapshot.get("mode", "assist"))
        answer = snapshot.get("answer")
        if mode in {"simulation", "adventure"} and answer is None:
            raise ValueError("A hidden answer is required to resume this mode.")
        session = cls(mode=mode, solver=solver, answer=answer)
        for row in snapshot.get("history", []):
            guess, feedback = row
            session.apply_turn(str(guess), str(feedback))
        session.rejected_turns = list(snapshot.get("rejected_turns", snapshot.get("replay", {}).get("rejected", [])))
        return session

    def to_dict(self, include_answer: bool = False) -> Dict[str, object]:
        data = self.current_state()
        data["history"] = [(guess, fb_to_str(feedback)) for guess, feedback in self.history]
        data["story"] = self.story.to_dict()
        data["rejected_turns"] = list(self.rejected_turns)
        data["replay"] = self.replay()
        if include_answer and self.answer is not None:
            data["answer"] = self.answer
        return data


_DEFAULT_SOLVER: Optional[QuestLineSolver] = None

def get_default_solver(verbose: bool = False) -> QuestLineSolver:
    global _DEFAULT_SOLVER
    if _DEFAULT_SOLVER is None:
        _DEFAULT_SOLVER = QuestLineSolver(verbose=verbose)
    elif verbose:
        _DEFAULT_SOLVER.verbose = True
    return _DEFAULT_SOLVER


def choose_questline_guess(history: History, top_k: int = 15) -> Dict[str, object]:
    return get_default_solver().choose(history, top_k=top_k)


def choose_human_like_guess(history: History, top_k: int = 15) -> Dict[str, object]:
    """Backward-compatible alias."""
    return choose_questline_guess(history, top_k=top_k)


def print_report(history: History, top_k: int = 15) -> None:
    result = get_default_solver(verbose=True).choose(history, top_k=top_k)
    print("=" * 80)
    print("History:")
    normalized = normalize_history(history)
    if not normalized:
        print("  <empty>")
    else:
        for guess, fb in normalized:
            print(f"  {guess} -> {fb_to_str(fb)}")
    print()
    print(f"Phase: {result.get('phase')}")
    if result.get("candidates"):
        print(f"Candidates: {len(result['candidates'])}")
    anchor = result.get("avg_anchor")
    if anchor:
        print(f"AVG anchor: {anchor['guess']} exp={anchor['exp']:.3f}, max={anchor['max']}, buckets={anchor['bucket_count']}")
    print()
    print("QuestLine recommendations:")
    for i, rec in enumerate(result["recommendations"], 1):
        if isinstance(rec, dict):
            reason = rec.get("reason")
            if reason:
                print(f"{i:2d}. {rec['guess']}  {reason}")
            else:
                print(f"{i:2d}. {rec['guess']} AVG={rec['normal_expected']:.3f} max={rec['normal_max_bucket']}")
    print("=" * 80)


def interactive() -> None:
    print("QuestLine")
    print("A narrative-driven Bulls & Cows solver.")
    print("Feedback examples: 0b1c, 1b2c, 1a2b, 1,2, 12")
    print("Commands: q/quit/exit, undo, history, report, help")
    history: List[Tuple[Code, Feedback]] = []
    solver = get_default_solver(verbose=False)
    while True:
        guess = solver.next_guess(history)
        print()
        print(f"Round {len(history) + 1}")
        print(f"Next guess: {guess}")
        text = input("Feedback: ").strip()
        lower = text.lower()
        if lower in {"q", "quit", "exit"}:
            break
        if lower in {"undo", "back"}:
            if history:
                removed = history.pop()
                print(f"Removed: {removed[0]} -> {fb_to_str(removed[1])}")
            else:
                print("History is already empty.")
            continue
        if lower in {"h", "history"}:
            if not history:
                print("History is empty.")
            else:
                for g, fb in history:
                    print(f"  {g} -> {fb_to_str(fb)}")
            continue
        if lower in {"r", "report"}:
            print_report(history)
            continue
        if lower in {"help", "?"}:
            print("Feedback examples: 0b1c, 1b2c, 1a2b, 1,2, 12")
            print("Commands: q/quit/exit, undo, history, report, help")
            continue
        try:
            fb = parse_feedback(text)
        except Exception as exc:
            print(f"Input error: {exc}")
            continue
        history.append((guess, fb))
        if fb == (4, 0):
            print("Solved!")
            break


def build_cache() -> None:
    solver = QuestLineSolver(verbose=True)
    solver.ensure_matrix()
    print("Cache ready.")


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="QuestLine Bulls & Cows solver")
    parser.add_argument("--demo", action="store_true", help="show a fixed report demo")
    parser.add_argument("--build-cache", action="store_true", help="build feedback matrix cache and exit")
    args = parser.parse_args(argv)
    if args.build_cache:
        build_cache()
        return
    if args.demo:
        print_report([("0123", "0b1c"), ("1045", "0b1c")])
        return
    interactive()


if __name__ == "__main__":
    main()
