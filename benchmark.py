"""Small benchmark helper for QuestLine.

This script runs QuestLine on random answers and prints a step distribution.
It is intentionally simple and reproducible.

Usage:

    python benchmark.py
"""

from collections import Counter
import random

from questline import ALL_CODES, BullsCowsSolver


def run(seed: int = 20260711, sample_size: int = 100) -> None:
    random.seed(seed)
    answers = random.sample(ALL_CODES, sample_size)
    solver = BullsCowsSolver()

    steps = []
    for answer in answers:
        rows = solver.play_answer(answer)
        steps.append(len(rows))

    dist = dict(sorted(Counter(steps).items()))
    avg = sum(steps) / len(steps)

    print(f"seed={seed}")
    print(f"sample_size={sample_size}")
    print(f"average={avg:.4f}")
    print(f"distribution={dist}")
    print(f"<=4={sum(s <= 4 for s in steps)}")
    print(f"<=5={sum(s <= 5 for s in steps)}")
    print(f"<=6={sum(s <= 6 for s in steps)}")
    print(f"7+={sum(s >= 7 for s in steps)}")


if __name__ == "__main__":
    run()
