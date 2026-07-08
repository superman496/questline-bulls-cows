
"""Bulls & Cows Human-like Solver Final

A fast, explainable solver for 4-digit Bulls & Cows with non-repeating digits.

Rules
-----
- Secret code: 4 distinct digits from 0-9. Leading zero is allowed.
- Guess: 4 distinct digits from 0-9.
- Feedback format: "xb yc", e.g. "1b2c".
  - bull: correct digit, correct position
  - cow : correct digit, wrong position

Strategy personality
--------------------
- Opening: fixed first guess 0123.
- Second move: mechanical AVG with stable lexicographic tie-break.
- Middle game: human-like weighted reasoning via digit/pair/triple/quad strength,
  bull pressure, position rotation, fixed world lines, and weighted candidate model.
- Advantage: push bull spikes and dominant quad structures.
- Disadvantage: low-signal / no-bull fallback returns to safer cutting.
- Complicated middle game: semi-advantage brake slows down no-trigger over-commitment.
- Endgame: if AVG can perfectly split all remaining candidates, use it.

This file is intended to be GitHub-ready: single-file, no third-party dependencies,
fast enough for interactive use, and deterministic under lexicographic tie-breaks.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations, permutations
import re
import time
from typing import DefaultDict, Dict, Iterable, List, Optional, Sequence, Tuple

Digit = str
Code = str
Feedback = Tuple[int, int]
History = Sequence[Tuple[Code, Feedback | str]]

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

FB_TO_BYTE: Dict[Feedback, int] = {(b, c): b * 5 + c for b in range(5) for c in range(5 - b)}
BYTE_TO_FB: Dict[int, Feedback] = {v: k for k, v in FB_TO_BYTE.items()}

ONLINE_SAFE_MODE = True
MAX_MECH_REPORT_CANDIDATES = 650


@dataclass(frozen=True)
class GuardParams:
    """Safety guard: allowed <= AVG * ratio + slack."""

    exp_ratio: float
    exp_slack: float
    max_ratio: float
    max_slack: float

    def allows(self, expected: float, max_bucket: int, avg_exp: float, avg_max: int) -> bool:
        return expected <= avg_exp * self.exp_ratio + self.exp_slack + 1e-9 and max_bucket <= avg_max * self.max_ratio + self.max_slack


@dataclass(frozen=True)
class SemiAdvantageBrake:
    """Light brake for no-trigger complex midgame.

    This is deliberately narrow. It should not override bull spikes, dominant quad
    triggers, fallback mode, or endgame logic.
    """

    enabled: bool = True
    min_candidates: int = 30
    max_candidates: int = 100
    exp_ratio_free: float = 1.05
    exp_slack_free: float = 1.0
    max_ratio_free: float = 1.12
    max_slack_free: float = 2.0
    exp_penalty: float = 0.050
    max_penalty: float = 0.120
    candidate_relief: float = 0.20


@dataclass(frozen=True)
class StrategyConfig:
    """All hard parameters in one place for easy tuning."""

    fallback_strong_guard: GuardParams = GuardParams(1.06, 2.0, 1.14, 3)
    fallback_soft_guard: GuardParams = GuardParams(1.10, 2.0, 1.20, 3)
    third_guard: GuardParams = GuardParams(1.18, 3.0, 1.30, 5)
    case_big_guard: GuardParams = GuardParams(1.13, 2.5, 1.24, 4)
    case_mid_guard: GuardParams = GuardParams(1.24, 2.0, 1.34, 4)
    case_small_guard: GuardParams = GuardParams(1.55, 2.0, 1.75, 3)
    endgame_guard: GuardParams = GuardParams(1.70, 2.0, 1.90, 4)
    default_guard: GuardParams = GuardParams(1.20, 2.0, 1.35, 4)
    semi_brake: SemiAdvantageBrake = SemiAdvantageBrake()


@dataclass
class CandidateStats:
    n: int
    digit_count: Counter[str]
    position_count: List[Counter[str]]
    pair_count: Counter[str]
    triple_count: Counter[str]
    quad_count: Counter[str]
    pair_structures: Counter[Tuple[str, str]]
    group_strength: Dict[str, float]
    freqs: Dict[str, float]
    weak_threshold: float
    top_digits: List[str]
    top_pairs: List[str]
    top_triples: List[str]
    top_quad_count: int
    second_quad_count: int


@dataclass
class Recommendation:
    guess: Code
    score: float
    is_candidate: bool
    weighted_expected: float = 0.0
    normal_expected: float = 0.0
    normal_max_bucket: int = 0
    main_world_expected: float = 0.0
    direct_prob: float = 0.0
    bucket_count: int = 0
    digit_strength: float = 0.0
    pair_strength: float = 0.0
    triple_strength: float = 0.0
    quad_strength: float = 0.0
    fixed_group_score: float = 0.0
    rotation_score: float = 0.0
    bull_score: float = 0.0
    weak_penalty: float = 0.0
    bull_bonus: float = 0.0
    quad_bonus: float = 0.0
    trigger_bonus: float = 0.0
    brake_penalty: float = 0.0
    reason: str = ""

    def as_dict(self) -> Dict[str, object]:
        return self.__dict__.copy()


# ---------------------------------------------------------------------------
# Parsing and basic feedback
# ---------------------------------------------------------------------------

def raw_feedback(answer: Code, guess: Code) -> Feedback:
    bulls = sum(a == g for a, g in zip(answer, guess))
    common = sum(ch in answer for ch in guess)
    return bulls, common - bulls


def fb_to_str(fb: Feedback) -> str:
    return f"{fb[0]}b{fb[1]}c"


def parse_feedback(value: Feedback | str) -> Feedback:
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
    raise ValueError(f"无法解析反馈：{value}")


def validate_code(code: Code) -> Code:
    code = str(code).strip()
    if len(code) != CODE_LEN:
        raise ValueError("猜测必须是 4 位。")
    if len(set(code)) != CODE_LEN:
        raise ValueError("4 位数字不能重复。")
    if not all(ch in DIGITS for ch in code):
        raise ValueError("猜测只能包含 0-9。")
    return code


def normalize_history(history: History) -> List[Tuple[Code, Feedback]]:
    return [(validate_code(guess), parse_feedback(fb)) for guess, fb in history]


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

class BullsCowsSolver:
    """Fast deterministic human-like Bulls & Cows solver."""

    def __init__(self, config: StrategyConfig | None = None, build_matrix: bool = True) -> None:
        self.config = config or StrategyConfig()
        self.feedback_matrix: Optional[List[bytearray]] = self._build_feedback_matrix() if build_matrix else None
        self._best_cache: Dict[Tuple[Tuple[int, ...], str], Tuple[Tuple[float, int, int, str], int, float, int, int]] = {}
        self._stats_cache: Dict[Tuple[int, ...], CandidateStats] = {}
        self._weights_cache: Dict[Tuple[int, ...], Tuple[Dict[int, float], Tuple[int, ...], Dict[Tuple[int, ...], List[int]], Dict[Tuple[int, ...], float]]] = {}

    @staticmethod
    def _build_feedback_matrix() -> List[bytearray]:
        matrix: List[bytearray] = []
        for guess in ALL_CODES:
            row = bytearray(len(ALL_CODES))
            for answer_index, answer in enumerate(ALL_CODES):
                row[answer_index] = FB_TO_BYTE[raw_feedback(answer, guess)]
            matrix.append(row)
        return matrix

    def feedback(self, answer: Code, guess: Code) -> Feedback:
        if self.feedback_matrix is None:
            return raw_feedback(answer, guess)
        return BYTE_TO_FB[self.feedback_matrix[CODE_TO_INDEX[guess]][CODE_TO_INDEX[answer]]]

    def filter_candidates(self, history: History) -> Tuple[int, ...]:
        normalized = normalize_history(history)
        candidates = list(ALL_INDEXES)
        if self.feedback_matrix is None:
            for guess, fb in normalized:
                candidates = [i for i in candidates if raw_feedback(ALL_CODES[i], guess) == fb]
        else:
            for guess, fb in normalized:
                row = self.feedback_matrix[CODE_TO_INDEX[guess]]
                target = FB_TO_BYTE[fb]
                candidates = [i for i in candidates if row[i] == target]
        return tuple(candidates)

    def bucket_counts(self, candidates: Tuple[int, ...], guess_index: int) -> Dict[int, int]:
        counts: Dict[int, int] = defaultdict(int)
        if self.feedback_matrix is None:
            guess = ALL_CODES[guess_index]
            for answer_index in candidates:
                counts[FB_TO_BYTE[raw_feedback(ALL_CODES[answer_index], guess)]] += 1
        else:
            row = self.feedback_matrix[guess_index]
            for answer_index in candidates:
                counts[row[answer_index]] += 1
        return counts

    def bucket_size_for_answer(self, candidates: Tuple[int, ...], guess_index: int, answer_index: int) -> int:
        if self.feedback_matrix is None:
            target = FB_TO_BYTE[raw_feedback(ALL_CODES[answer_index], ALL_CODES[guess_index])]
            return sum(1 for ai in candidates if FB_TO_BYTE[raw_feedback(ALL_CODES[ai], ALL_CODES[guess_index])] == target)
        row = self.feedback_matrix[guess_index]
        target = row[answer_index]
        return sum(1 for ai in candidates if row[ai] == target)

    def avg_remaining(self, candidates: Tuple[int, ...], guess_index: int) -> Tuple[float, int, int]:
        counts = self.bucket_counts(candidates, guess_index)
        n = len(candidates)
        expected = sum(v * v for v in counts.values()) / n
        max_bucket = max(counts.values())
        return expected, max_bucket, len(counts)

    def best_pure_guess(self, candidates: Tuple[int, ...], mode: str = "avg") -> Tuple[int, float, int, int]:
        cache_key = (candidates, mode)
        cached = self._best_cache.get(cache_key)
        if cached is not None:
            _, guess_index, exp, max_bucket, bucket_count = cached
            return guess_index, exp, max_bucket, bucket_count

        candidate_set = set(candidates)
        best: Optional[Tuple[Tuple[float, int, int, str], int, float, int, int]] = None
        for guess_index, guess in enumerate(ALL_CODES):
            exp, max_bucket, bucket_count = self.avg_remaining(candidates, guess_index)
            candidate_penalty = 0 if guess_index in candidate_set else 1
            if mode == "avg":
                key = (exp, max_bucket, candidate_penalty, guess)
            elif mode == "mm":
                key = (max_bucket, exp, candidate_penalty, guess)
            else:
                raise ValueError("mode 必须是 avg 或 mm")
            if best is None or key < best[0]:
                best = (key, guess_index, exp, max_bucket, bucket_count)

        assert best is not None
        self._best_cache[cache_key] = best
        _, guess_index, exp, max_bucket, bucket_count = best
        return guess_index, exp, max_bucket, bucket_count

    def stats(self, candidates: Tuple[int, ...]) -> CandidateStats:
        cached = self._stats_cache.get(candidates)
        if cached is not None:
            return cached

        n = len(candidates)
        digit_count: Counter[str] = Counter()
        position_count: List[Counter[str]] = [Counter() for _ in range(CODE_LEN)]
        pair_count: Counter[str] = Counter()
        triple_count: Counter[str] = Counter()
        quad_count: Counter[str] = Counter()
        pair_structures: Counter[Tuple[str, str]] = Counter()
        group_strength = {name: 0.0 for name in FIXED_GROUPS}

        for index in candidates:
            code = ALL_CODES[index]
            digit_count.update(code)
            for pos, ch in enumerate(code):
                position_count[pos][ch] += 1
            sorted_code = sorted(code)
            for combo in combinations(sorted_code, 2):
                pair_count["".join(combo)] += 1
            for combo in combinations(sorted_code, 3):
                triple_count["".join(combo)] += 1
            quad_count["".join(sorted_code)] += 1
            for name, group in FIXED_GROUPS.items():
                group_strength[name] += sum(ch in group for ch in code)
            partitions = [
                (sorted_code[0] + sorted_code[1], sorted_code[2] + sorted_code[3]),
                (sorted_code[0] + sorted_code[2], sorted_code[1] + sorted_code[3]),
                (sorted_code[0] + sorted_code[3], sorted_code[1] + sorted_code[2]),
            ]
            for left, right in partitions:
                pair_structures[tuple(sorted((left, right)))] += 1

        for name in group_strength:
            group_strength[name] /= n
        freqs = {digit: digit_count[digit] / n for digit in DIGITS}
        quad_common = quad_count.most_common()
        result = CandidateStats(
            n=n,
            digit_count=digit_count,
            position_count=position_count,
            pair_count=pair_count,
            triple_count=triple_count,
            quad_count=quad_count,
            pair_structures=pair_structures,
            group_strength=group_strength,
            freqs=freqs,
            weak_threshold=sorted(freqs.values())[2],
            top_digits=[digit for digit, _ in digit_count.most_common(4)],
            top_pairs=[pair for pair, _ in pair_count.most_common(6)],
            top_triples=[triple for triple, _ in triple_count.most_common(6)],
            top_quad_count=quad_common[0][1] if quad_common else 0,
            second_quad_count=quad_common[1][1] if len(quad_common) > 1 else 0,
        )
        self._stats_cache[candidates] = result
        return result

    @staticmethod
    def fixed_world_signature(code: Code) -> Tuple[int, ...]:
        return tuple(sum(ch in group for ch in code) for group in FIXED_GROUPS.values())

    def candidate_weights(self, candidates: Tuple[int, ...], stats: CandidateStats) -> Tuple[Dict[int, float], Tuple[int, ...], Dict[Tuple[int, ...], List[int]], Dict[Tuple[int, ...], float]]:
        cached = self._weights_cache.get(candidates)
        if cached is not None:
            return cached

        worlds: Dict[Tuple[int, ...], List[int]] = defaultdict(list)
        for index in candidates:
            worlds[self.fixed_world_signature(ALL_CODES[index])].append(index)
        total = len(candidates)
        world_scores = {signature: (len(members) / total) ** 1.35 for signature, members in worlds.items()}

        weights: Dict[int, float] = {}
        for signature, members in worlds.items():
            world_score = world_scores[signature]
            for index in members:
                weights[index] = world_score * self._candidate_base_weight(ALL_CODES[index], stats)
        weight_total = sum(weights.values())
        if weight_total > 0:
            weights = {k: v / weight_total for k, v in weights.items()}
        main_signature = max(world_scores, key=world_scores.get)
        result = (weights, tuple(worlds[main_signature]), worlds, world_scores)
        self._weights_cache[candidates] = result
        return result

    def _candidate_base_weight(self, code: Code, stats: CandidateStats) -> float:
        n = stats.n
        sorted_code = sorted(code)
        digit_score = 1.0
        for ch in code:
            digit_score *= 0.35 + stats.digit_count[ch] / n
        position_score = 1.0
        for pos, ch in enumerate(code):
            position_score *= 0.35 + stats.position_count[pos][ch] / n
        pair_score = 1.0
        for combo in combinations(sorted_code, 2):
            pair_score *= 0.55 + 0.35 * (stats.pair_count["".join(combo)] / n)
        triple_score = 1.0
        for combo in combinations(sorted_code, 3):
            triple_score *= 0.70 + 0.18 * (stats.triple_count["".join(combo)] / n)
        quad_score = 0.80 + 0.12 * (stats.quad_count["".join(sorted_code)] / n)
        return digit_score * position_score * pair_score * triple_score * quad_score * self._explanation_penalty(code, stats)

    @staticmethod
    def _explanation_penalty(code: Code, stats: CandidateStats) -> float:
        n = stats.n
        penalty = 1.0
        penalty *= 0.86 ** sum(1 for digit in stats.top_digits if digit not in code)
        penalty *= 0.94 ** sum(1 for pair in stats.top_pairs if not all(ch in code for ch in pair))
        penalty *= 0.97 ** sum(1 for triple in stats.top_triples if not all(ch in code for ch in triple))
        penalty *= 0.80 + 0.40 * (stats.quad_count["".join(sorted(code))] / n)
        return penalty

    def weighted_expected_remaining(self, candidates: Tuple[int, ...], guess_index: int, weights: Dict[int, float]) -> Tuple[float, float, int]:
        if self.feedback_matrix is None:
            grouped: Dict[int, List[int]] = defaultdict(list)
            guess = ALL_CODES[guess_index]
            for answer_index in candidates:
                grouped[FB_TO_BYTE[raw_feedback(ALL_CODES[answer_index], guess)]].append(answer_index)
        else:
            row = self.feedback_matrix[guess_index]
            grouped = defaultdict(list)
            for answer_index in candidates:
                grouped[row[answer_index]].append(answer_index)
        total_weight = sum(weights[index] for index in candidates)
        expected = 0.0
        max_weight = 0.0
        for bucket in grouped.values():
            bucket_weight = sum(weights[index] for index in bucket)
            expected += (bucket_weight / total_weight) * len(bucket)
            max_weight = max(max_weight, bucket_weight)
        return expected, max_weight, len(grouped)

    # ------------------------------------------------------------------
    # Signal modes and feature scoring
    # ------------------------------------------------------------------

    @staticmethod
    def total_previous_bulls(history: List[Tuple[Code, Feedback]]) -> int:
        return sum(fb[0] for _, fb in history)

    @staticmethod
    def last_feedback(history: List[Tuple[Code, Feedback]]) -> Feedback:
        return history[-1][1] if history else (0, 0)

    @staticmethod
    def is_low_signal_feedback(fb: Feedback) -> bool:
        return fb[0] == 0 and (fb[0] + fb[1]) <= 2

    def low_signal_intensity(self, history: List[Tuple[Code, Feedback]], k: int = 3) -> int:
        if len(history) < k or not all(self.is_low_signal_feedback(fb) for _, fb in history[-k:]):
            return 0
        return 2 if all(fb == (0, 1) for _, fb in history[-k:]) else 1

    def no_bull_fallback_intensity(self, history: List[Tuple[Code, Feedback]], k: int = 3) -> int:
        if len(history) < k:
            return 0
        recent = [fb for _, fb in history[-k:]]
        bull_sum = sum(fb[0] for fb in recent)
        hit_sum = sum(fb[0] + fb[1] for fb in recent)
        if bull_sum == 0 and hit_sum <= 7:
            return 2 if all(fb[1] <= 2 for fb in recent) else 1
        if len(history) >= 4:
            recent4 = [fb for _, fb in history[-4:]]
            if sum(fb[0] for fb in recent4) <= 1 and sum(fb[0] + fb[1] for fb in recent4) <= 9:
                return 1
        return 0

    def fallback_mode(self, history: List[Tuple[Code, Feedback]]) -> int:
        return max(self.low_signal_intensity(history), self.no_bull_fallback_intensity(history))

    @staticmethod
    def used_positions(history: List[Tuple[Code, Feedback]]) -> Dict[str, set[int]]:
        positions: Dict[str, set[int]] = defaultdict(set)
        for guess, _ in history:
            for pos, ch in enumerate(guess):
                positions[ch].add(pos)
        return positions

    @staticmethod
    def rotation_score(history: List[Tuple[Code, Feedback]], guess: Code, used: Dict[str, set[int]]) -> float:
        if not history:
            return 0.0
        return sum(1.0 if pos not in used[ch] else -0.35 for pos, ch in enumerate(guess)) / CODE_LEN

    @staticmethod
    def digit_strength(stats: CandidateStats, guess: Code) -> float:
        return sum(stats.digit_count[ch] / stats.n for ch in guess) / CODE_LEN

    @staticmethod
    def pair_strength(stats: CandidateStats, guess: Code) -> float:
        return sum(stats.pair_count["".join(combo)] / stats.n for combo in combinations(sorted(guess), 2)) / 6.0

    @staticmethod
    def triple_strength(stats: CandidateStats, guess: Code) -> float:
        return sum(stats.triple_count["".join(combo)] / stats.n for combo in combinations(sorted(guess), 3)) / 4.0

    @staticmethod
    def quad_strength(stats: CandidateStats, guess: Code) -> float:
        return stats.quad_count["".join(sorted(guess))] / stats.n

    @staticmethod
    def fixed_group_score(stats: CandidateStats, guess: Code) -> float:
        return sum(
            stats.group_strength[name] * min(sum(ch in group for ch in guess), 2) / 2
            for name, group in FIXED_GROUPS.items()
        ) / len(FIXED_GROUPS)

    @staticmethod
    def bull_pressure(stats: CandidateStats, guess: Code) -> float:
        return sum(stats.position_count[pos][ch] / stats.n for pos, ch in enumerate(guess)) / CODE_LEN

    @staticmethod
    def weak_digit_penalty(stats: CandidateStats, guess: Code) -> float:
        return sum(1.0 for ch in guess if stats.freqs[ch] <= stats.weak_threshold) / CODE_LEN

    def dominant_quad_bonus(self, stats: CandidateStats, guess: Code, is_candidate: bool, normal_exp: float, avg_exp: float, normal_max: int, avg_max: int) -> float:
        if stats.n > 80:
            return 0.0
        key = "".join(sorted(guess))
        q_count = stats.quad_count[key]
        top = stats.top_quad_count
        second = stats.second_quad_count
        if top <= 0:
            return 0.0
        near_top = q_count >= top * 0.90
        dominant = second == 0 or top >= second * 1.35 or top / stats.n >= 0.18
        safe = normal_exp <= avg_exp * 1.35 + 2.0 and normal_max <= avg_max * 1.55 + 3
        if near_top and safe:
            return 0.35 + (0.35 if is_candidate else 0.0) + (0.35 if dominant else 0.0) + (0.35 if stats.n <= 20 else 0.0)
        return 0.0

    def bull_spike_bonus(self, stats: CandidateStats, guess: Code, bull_score: float, normal_exp: float, avg_exp: float, normal_max: int, avg_max: int, history: List[Tuple[Code, Feedback]]) -> float:
        total_b = self.total_previous_bulls(history)
        last_b = self.last_feedback(history)[0]
        if total_b == 0 and last_b == 0:
            return 0.0
        if not (normal_exp <= avg_exp * 1.28 + 2.0 and normal_max <= avg_max * 1.45 + 3):
            return 0.0
        threshold = 0.34 if stats.n <= 30 else 0.30
        if total_b >= 3:
            threshold -= 0.03
        if last_b >= 2:
            threshold -= 0.03
        if bull_score >= threshold:
            return 0.35 + 0.12 * min(total_b, 4) + 0.15 * min(last_b, 3) + (0.25 if stats.n <= 20 else 0.0)
        return 0.0

    def game_phase(self, history: List[Tuple[Code, Feedback]], candidates: Tuple[int, ...]) -> str:
        if len(history) == 0:
            return "opening_first"
        if len(history) == 1 and history[0][0] == "0123":
            return "opening_second"
        if len(history) == 2:
            return "third"
        if len(candidates) <= 12:
            return "endgame"
        return "case"

    def guard_params(self, phase: str, n: int, history: List[Tuple[Code, Feedback]]) -> GuardParams:
        mode = self.fallback_mode(history)
        if mode == 2:
            return self.config.fallback_strong_guard
        if mode == 1:
            return self.config.fallback_soft_guard
        if phase == "third":
            return self.config.third_guard
        if phase == "case":
            if n > 25:
                return self.config.case_big_guard
            if n > 12:
                return self.config.case_mid_guard
            return self.config.case_small_guard
        if phase == "endgame":
            return self.config.endgame_guard
        return self.config.default_guard

    def phase_weights(self, phase: str, n: int, history: List[Tuple[Code, Feedback]]) -> Dict[str, float]:
        total_b = self.total_previous_bulls(history)
        last_b = self.last_feedback(history)[0]
        bull_boost = 0.10 * min(total_b, 4) + 0.08 * min(last_b, 3)
        fallback = self.fallback_mode(history)

        if fallback:
            extra = 0.08 if fallback == 2 else 0.0
            return {
                "w_exp": 0.56 + extra,
                "normal_exp": 0.24 + extra,
                "main_exp": 0.16,
                "max_weight": 0.28 + extra,
                "digit": -0.45,
                "pair": -0.42,
                "triple": -0.18,
                "quad": -0.08,
                "fixed_group": -0.22,
                "rotation": -0.25,
                "bull": -0.92 - bull_boost,
                "weak_penalty": 0.12,
                "direct_prob": -0.90,
                "candidate_bonus": -0.05,
                "non_candidate_penalty": 0.02,
                "trigger_bonus": -0.12,
            }

        if phase == "third":
            return {
                "w_exp": 0.44,
                "normal_exp": 0.16,
                "main_exp": 0.34,
                "max_weight": 0.20,
                "digit": -1.10,
                "pair": -1.05,
                "triple": -0.50,
                "quad": -0.25,
                "fixed_group": -0.48,
                "rotation": -0.40,
                "bull": -0.72 - bull_boost,
                "weak_penalty": 0.95,
                "direct_prob": -2.00,
                "candidate_bonus": -0.15,
                "non_candidate_penalty": 0.00,
                "trigger_bonus": -1.00,
            }

        if phase == "case":
            if n > 25:
                return {
                    "w_exp": 0.36,
                    "normal_exp": 0.14,
                    "main_exp": 0.34,
                    "max_weight": 0.18,
                    "digit": -1.20,
                    "pair": -1.35,
                    "triple": -1.10,
                    "quad": -1.25,
                    "fixed_group": -0.55,
                    "rotation": -0.40,
                    "bull": -0.95 - bull_boost,
                    "weak_penalty": 1.10,
                    "direct_prob": -4.00,
                    "candidate_bonus": -0.70,
                    "non_candidate_penalty": 0.35,
                    "trigger_bonus": -1.10,
                }
            return {
                "w_exp": 0.24,
                "normal_exp": 0.08,
                "main_exp": 0.28,
                "max_weight": 0.10,
                "digit": -1.45,
                "pair": -1.75,
                "triple": -1.75,
                "quad": -2.85,
                "fixed_group": -0.65,
                "rotation": -0.42,
                "bull": -1.15 - bull_boost,
                "weak_penalty": 1.35,
                "direct_prob": -7.50,
                "candidate_bonus": -1.80,
                "non_candidate_penalty": 0.90,
                "trigger_bonus": -1.20,
            }

        if phase == "endgame":
            return {
                "w_exp": 0.10,
                "normal_exp": 0.03,
                "main_exp": 0.14,
                "max_weight": 0.04,
                "digit": -1.10,
                "pair": -1.45,
                "triple": -1.70,
                "quad": -3.40,
                "fixed_group": -0.25,
                "rotation": -0.20,
                "bull": -1.30 - bull_boost,
                "weak_penalty": 1.00,
                "direct_prob": -14.0,
                "candidate_bonus": -3.50,
                "non_candidate_penalty": 3.50,
                "trigger_bonus": -0.80,
            }

        return {
            "w_exp": 0.36,
            "normal_exp": 0.12,
            "main_exp": 0.34,
            "max_weight": 0.16,
            "digit": -1.00,
            "pair": -1.00,
            "triple": -0.70,
            "quad": -0.55,
            "fixed_group": -0.45,
            "rotation": -0.30,
            "bull": -0.70 - bull_boost,
            "weak_penalty": 0.95,
            "direct_prob": -3.00,
            "candidate_bonus": -0.50,
            "non_candidate_penalty": 0.20,
            "trigger_bonus": -1.00,
        }

    def semi_advantage_brake(self, score: float, expected: float, max_bucket: int, avg_exp: float, avg_max: int, trigger_bonus: float, is_candidate: bool, phase: str, n: int, history: List[Tuple[Code, Feedback]]) -> Tuple[float, float]:
        cfg = self.config.semi_brake
        if not cfg.enabled:
            return score, 0.0
        if phase == "endgame" or self.fallback_mode(history) != 0:
            return score, 0.0
        if not (cfg.min_candidates <= n <= cfg.max_candidates):
            return score, 0.0
        if trigger_bonus > 0:
            return score, 0.0
        exp_free = avg_exp * cfg.exp_ratio_free + cfg.exp_slack_free
        max_free = avg_max * cfg.max_ratio_free + cfg.max_slack_free
        penalty = cfg.exp_penalty * max(0.0, expected - exp_free) + cfg.max_penalty * max(0.0, max_bucket - max_free)
        if is_candidate:
            penalty *= 1.0 - cfg.candidate_relief
        return score + penalty, penalty

    # ------------------------------------------------------------------
    # Main recommendation API
    # ------------------------------------------------------------------

    def choose(self, history: History, top_k: int = 15) -> Dict[str, object]:
        normalized = normalize_history(history)
        candidates = self.filter_candidates(normalized)
        if not candidates:
            raise ValueError("当前反馈矛盾，没有合法候选。")

        phase = self.game_phase(normalized, candidates)

        if phase == "opening_first":
            return {
                "phase": phase,
                "candidates": [ALL_CODES[i] for i in candidates],
                "recommendations": [Recommendation("0123", 0.0, True, reason="固定第一手")],
            }

        if phase == "opening_second":
            guess_index, exp, max_bucket, bucket_count = self.best_pure_guess(candidates, "avg")
            guess = ALL_CODES[guess_index]
            return {
                "phase": phase,
                "candidates": [ALL_CODES[i] for i in candidates],
                "recommendations": [
                    Recommendation(
                        guess=guess,
                        score=exp,
                        is_candidate=guess_index in candidates,
                        weighted_expected=exp,
                        normal_expected=exp,
                        normal_max_bucket=max_bucket,
                        main_world_expected=exp,
                        direct_prob=1.0 / len(candidates) if guess_index in candidates else 0.0,
                        bucket_count=bucket_count,
                        reason="第二手固定机械 AVG，等价时字典序最小",
                    )
                ],
            }

        stats = self.stats(candidates)
        candidate_set = set(candidates)
        used = self.used_positions(normalized)
        weights, main_candidates, worlds, world_scores = self.candidate_weights(candidates, stats)
        avg_index, avg_exp, avg_max, avg_bucket_count = self.best_pure_guess(candidates, "avg")
        avg_guess = ALL_CODES[avg_index]

        # Endgame hard rule: if AVG can perfectly distinguish every candidate, use it.
        if phase == "endgame" and len(candidates) <= 10 and avg_max == 1:
            rec = Recommendation(
                guess=avg_guess,
                score=avg_exp,
                is_candidate=avg_index in candidate_set,
                weighted_expected=avg_exp,
                normal_expected=avg_exp,
                normal_max_bucket=avg_max,
                main_world_expected=avg_exp,
                direct_prob=weights.get(avg_index, 0.0),
                bucket_count=avg_bucket_count,
                digit_strength=self.digit_strength(stats, avg_guess),
                pair_strength=self.pair_strength(stats, avg_guess),
                triple_strength=self.triple_strength(stats, avg_guess),
                quad_strength=self.quad_strength(stats, avg_guess),
                fixed_group_score=self.fixed_group_score(stats, avg_guess),
                rotation_score=self.rotation_score(normalized, avg_guess, used),
                bull_score=self.bull_pressure(stats, avg_guess),
                weak_penalty=self.weak_digit_penalty(stats, avg_guess),
                reason="残局 max_bucket=1，机械 AVG 可完全区分，强制收束",
            )
            return {
                "phase": phase,
                "candidates": [ALL_CODES[i] for i in candidates],
                "stats": stats,
                "avg_anchor": {"guess": avg_guess, "exp": avg_exp, "max": avg_max, "bucket_count": avg_bucket_count},
                "fallback_mode": self.fallback_mode(normalized),
                "guard": self.guard_params(phase, stats.n, normalized),
                "recommendations": [rec],
                "raw_recommendations": [],
            }

        phase_weights = self.phase_weights(phase, stats.n, normalized)
        scored: List[Recommendation] = []

        for guess_index, guess in enumerate(ALL_CODES):
            weighted_exp, weighted_max, bucket_count = self.weighted_expected_remaining(candidates, guess_index, weights)
            normal_exp, normal_max, _ = self.avg_remaining(candidates, guess_index)
            main_exp, _, _ = self.avg_remaining(main_candidates, guess_index)
            is_candidate = guess_index in candidate_set
            direct_prob = weights.get(guess_index, 0.0)

            digit_s = self.digit_strength(stats, guess)
            pair_s = self.pair_strength(stats, guess)
            triple_s = self.triple_strength(stats, guess)
            quad_s = self.quad_strength(stats, guess)
            fixed_s = self.fixed_group_score(stats, guess)
            rotation_s = self.rotation_score(normalized, guess, used)
            bull_s = self.bull_pressure(stats, guess)
            weak_p = self.weak_digit_penalty(stats, guess)
            bull_bonus = self.bull_spike_bonus(stats, guess, bull_s, normal_exp, avg_exp, normal_max, avg_max, normalized)
            quad_bonus = self.dominant_quad_bonus(stats, guess, is_candidate, normal_exp, avg_exp, normal_max, avg_max)
            trigger_bonus = bull_bonus + quad_bonus

            base_score = (
                phase_weights["w_exp"] * weighted_exp
                + phase_weights["normal_exp"] * normal_exp
                + phase_weights["main_exp"] * main_exp
                + phase_weights["max_weight"] * weighted_max * stats.n
                + phase_weights["digit"] * digit_s
                + phase_weights["pair"] * pair_s
                + phase_weights["triple"] * triple_s
                + phase_weights["quad"] * quad_s
                + phase_weights["fixed_group"] * fixed_s
                + phase_weights["rotation"] * rotation_s
                + phase_weights["bull"] * bull_s
                + phase_weights["weak_penalty"] * weak_p
                + phase_weights["direct_prob"] * direct_prob
                + phase_weights["candidate_bonus"] * int(is_candidate)
                + phase_weights["non_candidate_penalty"] * int(not is_candidate)
                + phase_weights["trigger_bonus"] * trigger_bonus
            )

            final_score, brake_penalty = self.semi_advantage_brake(
                score=base_score,
                expected=normal_exp,
                max_bucket=normal_max,
                avg_exp=avg_exp,
                avg_max=avg_max,
                trigger_bonus=trigger_bonus,
                is_candidate=is_candidate,
                phase=phase,
                n=stats.n,
                history=normalized,
            )

            scored.append(
                Recommendation(
                    guess=guess,
                    score=final_score,
                    is_candidate=is_candidate,
                    weighted_expected=weighted_exp,
                    normal_expected=normal_exp,
                    normal_max_bucket=normal_max,
                    main_world_expected=main_exp,
                    direct_prob=direct_prob,
                    bucket_count=bucket_count,
                    digit_strength=digit_s,
                    pair_strength=pair_s,
                    triple_strength=triple_s,
                    quad_strength=quad_s,
                    fixed_group_score=fixed_s,
                    rotation_score=rotation_s,
                    bull_score=bull_s,
                    weak_penalty=weak_p,
                    bull_bonus=bull_bonus,
                    quad_bonus=quad_bonus,
                    trigger_bonus=trigger_bonus,
                    brake_penalty=brake_penalty,
                )
            )

        scored.sort(key=lambda r: (r.score, r.guess))
        guard = self.guard_params(phase, stats.n, normalized)
        guarded = [r for r in scored if guard.allows(r.normal_expected, r.normal_max_bucket, avg_exp, avg_max)]
        if not guarded:
            guarded = scored
        if all(r.guess != avg_guess for r in guarded):
            avg_rec = next((r for r in scored if r.guess == avg_guess), None)
            if avg_rec is not None:
                guarded.append(avg_rec)
        guarded.sort(key=lambda r: (r.score, r.guess))

        return {
            "phase": phase,
            "candidates": [ALL_CODES[i] for i in candidates],
            "stats": stats,
            "avg_anchor": {"guess": avg_guess, "exp": avg_exp, "max": avg_max, "bucket_count": avg_bucket_count},
            "fallback_mode": self.fallback_mode(normalized),
            "guard": guard,
            "recommendations": guarded[:top_k],
            "raw_recommendations": scored[:top_k],
        }

    def next_guess(self, history: History) -> Code:
        return self.choose(history, top_k=1)["recommendations"][0].guess

    def play_answer(self, answer: Code, max_steps: int = 10) -> List[Tuple[Code, Feedback, int]]:
        answer = validate_code(answer)
        history: List[Tuple[Code, Feedback]] = []
        rows: List[Tuple[Code, Feedback, int]] = []
        for _ in range(max_steps):
            guess = self.next_guess(history)
            fb = self.feedback(answer, guess)
            history.append((guess, fb))
            remain = len(self.filter_candidates(history))
            rows.append((guess, fb, remain))
            if fb == (4, 0):
                break
        return rows


# ---------------------------------------------------------------------------
# Compatibility helper functions
# ---------------------------------------------------------------------------

_DEFAULT_SOLVER = BullsCowsSolver()

def choose_human_like_guess(history: History, top_k: int = 15) -> Dict[str, object]:
    return _DEFAULT_SOLVER.choose(history, top_k=top_k)

def print_report(history: History, top_k: int = 15, show_time: bool = True) -> None:
    start = time.time()
    result = _DEFAULT_SOLVER.choose(history, top_k=top_k)
    candidates = result["candidates"]
    print("=" * 80)
    print("当前历史：")
    normalized = normalize_history(history)
    if not normalized:
        print("  无")
    else:
        for guess, fb in normalized:
            print(f"  {guess} -> {fb_to_str(fb)}")
    print()
    print(f"候选数：{len(candidates)}")
    if len(candidates) <= 30:
        print("候选：", candidates)
    print()
    print(f"阶段：{result.get('phase')}")
    if result.get("fallback_mode"):
        print(f"无 bull / 低信号回退模式：ON，强度={result.get('fallback_mode')}")
    anchor = result.get("avg_anchor")
    if anchor:
        print(f"AVG安全锚点：{anchor['guess']} exp={anchor['exp']:.3f}, max={anchor['max']}, buckets={anchor['bucket_count']}")
    guard = result.get("guard")
    if isinstance(guard, GuardParams):
        print(f"Guard: exp <= AVG*{guard.exp_ratio:.3f}+{guard.exp_slack:.1f}, max <= AVG*{guard.max_ratio:.3f}+{guard.max_slack:.1f}")
    print()
    print("Human-like 推荐：")
    for i, rec in enumerate(result["recommendations"], 1):
        text = "(候选)" if rec.is_candidate else "(测试)"
        if rec.reason:
            print(f"{i:2d}. {rec.guess} {text} score={rec.score:.3f} {rec.reason}")
            continue
        print(
            f"{i:2d}. {rec.guess} {text} "
            f"score={rec.score:.3f} brake={rec.brake_penalty:.3f} "
            f"wAVG={rec.weighted_expected:.3f} mainAVG={rec.main_world_expected:.3f} "
            f"AVG={rec.normal_expected:.3f} max={rec.normal_max_bucket} "
            f"hitW={rec.direct_prob:.4f} quad={rec.quad_strength:.3f} "
            f"bull={rec.bull_score:.3f} trig={rec.trigger_bonus:.2f}"
        )
    if not (ONLINE_SAFE_MODE and len(candidates) > MAX_MECH_REPORT_CANDIDATES):
        cand_idx = tuple(CODE_TO_INDEX[c] for c in candidates)
        avg_i, avg_e, avg_m, avg_b = _DEFAULT_SOLVER.best_pure_guess(cand_idx, "avg")
        mm_i, mm_e, mm_m, mm_b = _DEFAULT_SOLVER.best_pure_guess(cand_idx, "mm")
        print()
        print("机械 AVG：")
        print(f"  {ALL_CODES[avg_i]} exp={avg_e:.3f}, max={avg_m}, buckets={avg_b}")
        print("机械 MM：")
        print(f"  {ALL_CODES[mm_i]} max={mm_m}, exp={mm_e:.3f}, buckets={mm_b}")
    else:
        print()
        print("机械 AVG/MM：在线加速模式跳过。")
    if show_time:
        print()
        print(f"运行耗时：{time.time() - start:.3f} 秒")
    print("=" * 80)


def interactive() -> None:
    history: List[Tuple[Code, Feedback]] = []
    print("Bulls & Cows Human-like Solver Final")
    print("反馈格式：0b1c / 1b2c / 4b0c，输入 q 退出。")
    while True:
        print_report(history, top_k=10)
        guess = choose_human_like_guess(history, top_k=1)["recommendations"][0].guess
        print()
        print(f"建议下一手：{guess}")
        fb_text = input(f"请输入 {guess} 的反馈：").strip()
        if fb_text.lower() in {"q", "quit", "exit"}:
            break
        try:
            history.append((guess, parse_feedback(fb_text)))
        except Exception as exc:
            print("输入错误：", exc)


if __name__ == "__main__":
    demo_history = [
        ("0123", (0, 1)),
        ("1045", (0, 1)),
    ]
    print_report(demo_history, top_k=15)
    # interactive()
