from pathlib import Path
import sys

# Make sure tests can import questline.py from the repository root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from questline import QuestLineSolver, fb_to_str, parse_feedback


def test_parse_feedback():
    assert parse_feedback("0b1c") == (0, 1)
    assert parse_feedback("1b2c") == (1, 2)
    assert parse_feedback("4b0c") == (4, 0)

    # Friendly input aliases
    assert parse_feedback("1a2b") == (1, 2)
    assert parse_feedback("1,2") == (1, 2)
    assert parse_feedback("12") == (1, 2)


def test_opening_moves_are_stable():
    solver = QuestLineSolver(use_cache=False)

    assert solver.next_guess([]) == "0123"
    assert solver.next_guess([("0123", "0b1c")]) == "1045"
    assert solver.next_guess([("0123", "1b0c")]) == "0456"


def test_feedback_format():
    assert fb_to_str((1, 2)) == "1b2c"
    assert fb_to_str((0, 1)) == "0b1c"
    assert fb_to_str((4, 0)) == "4b0c"


def test_known_answer_0456_finishes_fast():
    solver = QuestLineSolver(use_cache=False)

    rows = solver.play_answer("0456")

    assert rows[-1][1] == (4, 0)
    assert len(rows) <= 2
