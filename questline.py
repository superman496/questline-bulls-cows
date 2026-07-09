
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
    raise ValueError(f"Cannot parse feedback: {value}")


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
    return [(validate_code(guess), parse_feedback(fb)) for guess, fb in history]


class QuestLineSolver:
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

    @staticmethod
    def total_bulls(history: List[Tuple[Code, Feedback]]) -> int:
        return sum(fb[0] for _, fb in history)

    @staticmethod
    def last_fb(history: List[Tuple[Code, Feedback]]) -> Feedback:
        return history[-1][1] if history else (0, 0)

    @staticmethod
    def is_low_signal(fb: Feedback) -> bool:
        return fb[0] == 0 and (fb[0] + fb[1]) <= 2

    def low_signal_intensity(self, history: List[Tuple[Code, Feedback]]) -> int:
        if len(history) < 3 or not all(self.is_low_signal(fb) for _, fb in history[-3:]):
            return 0
        return 2 if all(fb == (0, 1) for _, fb in history[-3:]) else 1

    def no_bull_intensity(self, history: List[Tuple[Code, Feedback]]) -> int:
        if len(history) < 3:
            return 0
        recent = [fb for _, fb in history[-3:]]
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
        return max(self.low_signal_intensity(history), self.no_bull_intensity(history))

    def game_phase(self, history: List[Tuple[Code, Feedback]], candidates: Tuple[int, ...]) -> str:
        if not history:
            return "opening_first"
        if len(history) == 1 and history[0][0] == OPENING_FIRST:
            return "opening_second"
        if len(history) == 2:
            return "third"
        if len(candidates) <= 12:
            return "endgame"
        return "case"

    def guard(self, phase: str, n: int, history: List[Tuple[Code, Feedback]]) -> Tuple[float, float, float, float]:
        mode = self.fallback_mode(history)
        if mode == 2:
            return 1.06, 2.0, 1.14, 3
        if mode == 1:
            return 1.10, 2.0, 1.20, 3
        if phase == "third":
            return 1.18, 3.0, 1.30, 5
        if phase == "case":
            if n > 25:
                return 1.13, 2.5, 1.24, 4
            if n > 12:
                return 1.24, 2.0, 1.34, 4
            return 1.55, 2.0, 1.75, 3
        if phase == "endgame":
            return 1.70, 2.0, 1.90, 4
        return 1.20, 2.0, 1.35, 4

    def phase_weights(self, phase: str, n: int, history: List[Tuple[Code, Feedback]]) -> Dict[str, float]:
        bull_boost = 0.10 * min(self.total_bulls(history), 4) + 0.08 * min(self.last_fb(history)[0], 3)
        mode = self.fallback_mode(history)
        if mode:
            extra = 0.08 if mode == 2 else 0.0
            return dict(w_exp=0.56+extra, normal_exp=0.24+extra, main_exp=0.16, max_weight=0.28+extra, digit=-0.45, pair=-0.42, triple=-0.18, quad=-0.08, fixed_group=-0.22, rotation=-0.25, bull=-0.92-bull_boost, weak_penalty=0.12, direct_prob=-0.90, candidate_bonus=-0.05, non_candidate_penalty=0.02, trigger_bonus=-0.12)
        if phase == "third":
            return dict(w_exp=0.44, normal_exp=0.16, main_exp=0.34, max_weight=0.20, digit=-1.10, pair=-1.05, triple=-0.50, quad=-0.25, fixed_group=-0.48, rotation=-0.40, bull=-0.72-bull_boost, weak_penalty=0.95, direct_prob=-2.00, candidate_bonus=-0.15, non_candidate_penalty=0.00, trigger_bonus=-1.00)
        if phase == "case":
            if n > 25:
                return dict(w_exp=0.36, normal_exp=0.14, main_exp=0.34, max_weight=0.18, digit=-1.20, pair=-1.35, triple=-1.10, quad=-1.25, fixed_group=-0.55, rotation=-0.40, bull=-0.95-bull_boost, weak_penalty=1.10, direct_prob=-4.00, candidate_bonus=-0.70, non_candidate_penalty=0.35, trigger_bonus=-1.10)
            return dict(w_exp=0.24, normal_exp=0.08, main_exp=0.28, max_weight=0.10, digit=-1.45, pair=-1.75, triple=-1.75, quad=-2.85, fixed_group=-0.65, rotation=-0.42, bull=-1.15-bull_boost, weak_penalty=1.35, direct_prob=-7.50, candidate_bonus=-1.80, non_candidate_penalty=0.90, trigger_bonus=-1.20)
        if phase == "endgame":
            return dict(w_exp=0.10, normal_exp=0.03, main_exp=0.14, max_weight=0.04, digit=-1.10, pair=-1.45, triple=-1.70, quad=-3.40, fixed_group=-0.25, rotation=-0.20, bull=-1.30-bull_boost, weak_penalty=1.00, direct_prob=-14.0, candidate_bonus=-3.50, non_candidate_penalty=3.50, trigger_bonus=-0.80)
        return {}

    @staticmethod
    def used_positions(history: List[Tuple[Code, Feedback]]) -> Dict[str, set[int]]:
        used: Dict[str, set[int]] = defaultdict(set)
        for guess, _ in history:
            for pos, ch in enumerate(guess):
                used[ch].add(pos)
        return used

    def score_guess_features(self, guess: Code, stats: Dict[str, object], history: List[Tuple[Code, Feedback]], used: Dict[str, set[int]]) -> Dict[str, float]:
        n = stats["n"]
        dc: Counter[str] = stats["dc"]
        pc: List[Counter[str]] = stats["pc"]
        pair: Counter[str] = stats["pair"]
        tri: Counter[str] = stats["tri"]
        quad: Counter[str] = stats["quad"]
        freqs: Dict[str, float] = stats["freqs"]
        sorted_guess = sorted(guess)
        return {
            "digit": sum(dc[ch] / n for ch in guess) / 4.0,
            "pair": sum(pair["".join(co)] / n for co in combinations(sorted_guess, 2)) / 6.0,
            "triple": sum(tri["".join(co)] / n for co in combinations(sorted_guess, 3)) / 4.0,
            "quad": quad["".join(sorted_guess)] / n,
            "fixed_group": sum(stats["group_strength"][name] * min(sum(ch in group for ch in guess), 2) / 2 for name, group in FIXED_GROUPS.items()) / len(FIXED_GROUPS),
            "rotation": sum(1.0 if pos not in used[ch] else -0.35 for pos, ch in enumerate(guess)) / 4.0 if history else 0.0,
            "bull": sum(pc[pos][ch] / n for pos, ch in enumerate(guess)) / 4.0,
            "weak": sum(1.0 for ch in guess if freqs[ch] <= stats["weak_threshold"]) / 4.0,
        }

    def trigger_bonus(self, stats: Dict[str, object], guess: Code, is_candidate: bool, normal_exp: float, avg_exp: float, normal_max: int, avg_max: int, bull_score: float, history: List[Tuple[Code, Feedback]]) -> float:
        n = stats["n"]
        bonus = 0.0
        total_b = self.total_bulls(history)
        last_b = self.last_fb(history)[0]
        if total_b > 0 or last_b > 0:
            if normal_exp <= avg_exp * 1.28 + 2.0 and normal_max <= avg_max * 1.45 + 3:
                threshold = 0.34 if n <= 30 else 0.30
                if total_b >= 3:
                    threshold -= 0.03
                if last_b >= 2:
                    threshold -= 0.03
                if bull_score >= threshold:
                    bonus += 0.35 + 0.12 * min(total_b, 4) + 0.15 * min(last_b, 3) + (0.25 if n <= 20 else 0.0)
        if n <= 80:
            quad: Counter[str] = stats["quad"]
            q = quad["".join(sorted(guess))]
            top = stats["top_quad_count"]
            second = stats["second_quad_count"]
            if top > 0 and q >= top * 0.90 and normal_exp <= avg_exp * 1.35 + 2.0 and normal_max <= avg_max * 1.55 + 3:
                dominant = second == 0 or top >= second * 1.35 or top / n >= 0.18
                bonus += 0.35 + (0.35 if is_candidate else 0.0) + (0.35 if dominant else 0.0) + (0.35 if n <= 20 else 0.0)
        return bonus

    @staticmethod
    def semi_brake(normal_exp: float, normal_max: int, avg_exp: float, avg_max: int, trigger: float, is_candidate: bool, phase: str, n: int, fallback_mode: int) -> float:
        if phase == "endgame" or fallback_mode != 0 or not (30 <= n <= 100) or trigger > 0:
            return 0.0
        penalty = 0.050 * max(0.0, normal_exp - (avg_exp * 1.05 + 1.0)) + 0.120 * max(0.0, normal_max - (avg_max * 1.12 + 2.0))
        return penalty * 0.8 if is_candidate else penalty

    def choose(self, history: History, top_k: int = 15) -> Dict[str, object]:
        normalized = normalize_history(history)

        # Serve opening book without loading the matrix.
        if len(normalized) == 0:
            return {"phase": "opening_first", "candidates": ALL_CODES, "recommendations": [{"guess": OPENING_FIRST, "score": 0.0, "is_candidate": True, "reason": "fixed first guess"}]}
        if len(normalized) == 1 and normalized[0][0] == OPENING_FIRST:
            second = OPENING_SECOND_BY_FEEDBACK.get(normalized[0][1])
            if second is not None:
                return {"phase": "opening_second", "candidates": [], "recommendations": [{"guess": second, "score": 0.0, "is_candidate": False, "reason": "opening book: stable AVG second move"}]}

        candidates = self.filter_candidates(normalized)
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
                "candidates": [ALL_CODES[i] for i in candidates],
                "avg_anchor": {"guess": ALL_CODES[avg_index], "exp": avg_exp, "max": avg_max, "bucket_count": avg_bucket_count},
                "fallback_mode": self.fallback_mode(normalized),
                "recommendations": [{"guess": ALL_CODES[avg_index], "score": avg_exp, "is_candidate": avg_index in candidate_set, "reason": "perfect endgame split"}],
            }

        phase_weights = self.phase_weights(phase, n, normalized)
        er, es, mr, ms = self.guard(phase, n, normalized)
        fallback = self.fallback_mode(normalized)
        scored: List[Dict[str, object]] = []
        for guess_index, guess in enumerate(ALL_CODES):
            weighted_exp, weighted_max, bucket_count = self.weighted_stats(candidates, guess_index, weights)
            normal_exp, normal_max, _ = self.avg_remaining(candidates, guess_index)
            main_exp, _, _ = self.avg_remaining(main_candidates, guess_index)
            is_candidate = guess_index in candidate_set
            features = self.score_guess_features(guess, stats, normalized, used)
            direct = weights.get(guess_index, 0.0)
            trigger = self.trigger_bonus(stats, guess, is_candidate, normal_exp, avg_exp, normal_max, avg_max, features["bull"], normalized)
            score = (
                phase_weights["w_exp"] * weighted_exp
                + phase_weights["normal_exp"] * normal_exp
                + phase_weights["main_exp"] * main_exp
                + phase_weights["max_weight"] * weighted_max * n
                + phase_weights["digit"] * features["digit"]
                + phase_weights["pair"] * features["pair"]
                + phase_weights["triple"] * features["triple"]
                + phase_weights["quad"] * features["quad"]
                + phase_weights["fixed_group"] * features["fixed_group"]
                + phase_weights["rotation"] * features["rotation"]
                + phase_weights["bull"] * features["bull"]
                + phase_weights["weak_penalty"] * features["weak"]
                + phase_weights["direct_prob"] * direct
                + phase_weights["candidate_bonus"] * int(is_candidate)
                + phase_weights["non_candidate_penalty"] * int(not is_candidate)
                + phase_weights["trigger_bonus"] * trigger
            )
            brake = self.semi_brake(normal_exp, normal_max, avg_exp, avg_max, trigger, is_candidate, phase, n, fallback)
            score += brake
            scored.append({
                "guess": guess,
                "score": score,
                "is_candidate": is_candidate,
                "weighted_expected": weighted_exp,
                "normal_expected": normal_exp,
                "normal_max_bucket": normal_max,
                "main_world_expected": main_exp,
                "direct_prob": direct,
                "bucket_count": bucket_count,
                "bull_score": features["bull"],
                "quad_strength": features["quad"],
                "trigger_bonus": trigger,
                "brake_penalty": brake,
            })
        scored.sort(key=lambda x: (x["score"], x["guess"]))
        guarded = [x for x in scored if x["normal_expected"] <= avg_exp * er + es + 1e-9 and x["normal_max_bucket"] <= avg_max * mr + ms]
        if not guarded:
            guarded = scored
        if all(x["guess"] != ALL_CODES[avg_index] for x in guarded):
            avg_item = next((x for x in scored if x["guess"] == ALL_CODES[avg_index]), None)
            if avg_item:
                guarded.append(avg_item)
        guarded.sort(key=lambda x: (x["score"], x["guess"]))
        return {
            "phase": phase,
            "candidates": [ALL_CODES[i] for i in candidates],
            "avg_anchor": {"guess": ALL_CODES[avg_index], "exp": avg_exp, "max": avg_max, "bucket_count": avg_bucket_count},
            "fallback_mode": fallback,
            "recommendations": guarded[:top_k],
            "raw_recommendations": scored[:top_k],
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
                print(f"{i:2d}. {rec['guess']} score={rec['score']:.3f}  {reason}")
            else:
                print(f"{i:2d}. {rec['guess']} score={rec['score']:.3f} AVG={rec['normal_expected']:.3f} max={rec['normal_max_bucket']} trig={rec['trigger_bonus']:.2f} brake={rec['brake_penalty']:.3f}")
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
