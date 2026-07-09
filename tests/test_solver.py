from questline import BullsCowsSolver, fb_to_str, parse_feedback


def test_parse_feedback():
    assert parse_feedback("0b1c") == (0, 1)
    assert parse_feedback("1b2c") == (1, 2)
    assert parse_feedback("4b0c") == (4, 0)
    assert parse_feedback("1,2") == (1, 2)


def test_opening_moves_are_stable():
    solver = BullsCowsSolver()
    assert solver.next_guess([]) == "0123"
    assert solver.next_guess([("0123", "0b1c")]) == "1045"
    assert solver.next_guess([("0123", "1b0c")]) == "0456"


def test_feedback_format():
    assert fb_to_str((1, 2)) == "1b2c"


def test_known_answer_0456_finishes_fast():
    solver = BullsCowsSolver()
    rows = solver.play_answer("0456")
    assert rows[-1][1] == (4, 0)
    assert len(rows) <= 2
