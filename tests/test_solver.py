from pathlib import Path
import sys

# Make sure tests can import questline.py from the repository root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from questline import GameSession, QuestLineSolver, StoryBook, fb_to_str, parse_feedback


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


def test_world_line_analysis_reports_main_world_and_timeline():
    solver = QuestLineSolver(use_cache=False)
    analysis = solver.world_line_analysis([("0123", "0b1c")])

    assert analysis["candidate_count"] > 0
    assert analysis["main_world"]["support"] >= 0.0
    assert analysis["main_world"]["groups"]
    assert analysis["main_world"]["lead_over_runner_up"] >= 0.0
    assert analysis["main_world"]["confidence"] in {"tied", "weak", "clear"}
    assert analysis["main_world"]["tied_world_count"] >= 1
    assert len(analysis["timeline"]) == 2
    assert analysis["timeline"][1]["support_delta"] is not None
    assert analysis["timeline"][1]["tied_world_count"] >= 1
    assert analysis["top_pairs"]


def test_investigation_state_separates_task_from_scoring():
    solver = QuestLineSolver(use_cache=False)

    opening = solver.investigation_state([])
    assert opening["task"] == "establish_foundation"
    assert opening["tested_groups"] == []
    assert opening["preferred_actions"] == ["group_probe", "position_probe"]

    after_first = solver.investigation_state([("0123", "0b1c")])
    assert after_first["task"] == "introduce_45"
    assert after_first["tested_groups"] == ["01", "23"]
    assert "45" in after_first["untested_groups"]

    after_second = solver.investigation_state([
        ("0123", "0b1c"),
        ("1045", "0b1c"),
    ])
    assert after_second["task"] == "cross_test_new_group"
    assert after_second["group_states"]["01"]["tested"] is True
    assert after_second["group_states"]["67"]["tested"] is False
    assert set(after_second["digit_status"]) == set("0123456789")
    assert not after_second["confirmed_digits"]
    assert after_second["task"] == "cross_test_new_group"


def test_action_classifier_identifies_group_and_position_probes():
    solver = QuestLineSolver(use_cache=False)
    history = [("0123", "0b1c"), ("1045", "0b1c")]
    state = solver.investigation_state(history)

    group_action = solver.classify_action("2568", history, state, False)
    assert group_action["type"] == "group_probe"
    assert "67" in group_action["new_groups"] or "89" in group_action["new_groups"]
    assert solver.action_is_eligible(group_action, "cross_test_new_group") is False

    balanced_group_action = solver.classify_action("0167", history, state, True)
    assert balanced_group_action["new_groups"] == ["67"]
    assert balanced_group_action["new_group_digit_counts"]["67"] == 2
    assert solver.action_is_eligible(balanced_group_action, "cross_test_new_group") is True

    position_action = solver.classify_action("1204", history, state, False)
    assert position_action["type"] == "position_probe"
    assert position_action["new_groups"] == []


def test_convergence_allows_single_outer_digit_probe():
    solver = QuestLineSolver(use_cache=False)
    history = [("0123", "1b1c"), ("0145", "1b0c")]
    state = solver.investigation_state(history)

    assert state["task"] == "converge_outer_choice"
    assert state["outer_is_symmetric"] is True
    action = solver.classify_action("2654", history, state, False)
    assert action["type"] == "group_probe"
    assert solver.action_is_eligible(action, state["task"]) is True


def test_task_filter_is_hard_before_efficiency_fallback():
    solver = QuestLineSolver(use_cache=False)
    history = [("0123", "0b1c"), ("1045", "0b1c")]
    result = solver.choose(history, top_k=20)

    assert result["investigation"]["task"] == "cross_test_new_group"
    assert result["task_eligible_count"] > 0
    assert result["recommendations"]
    assert all(
        item["action"]["type"] == "group_probe"
        and len(item["action"]["new_groups"]) == 1
        and item["action"]["new_group_digit_counts"][item["action"]["new_groups"][0]] == 2
        for item in result["recommendations"]
    )


def test_repeated_guess_is_structurally_ineligible():
    solver = QuestLineSolver(use_cache=False)
    history = [("0123", "0b1c"), ("1045", "0b1c")]
    state = solver.investigation_state(history)
    action = solver.classify_action("0123", history, state, False)
    assert action["type"] == "redundant"
    assert solver.action_is_eligible(action, state["task"]) is False


def test_endgame_prefers_remaining_candidate_directly():
    solver = QuestLineSolver(use_cache=False)
    result = solver.choose([
        ("0123", "3b0c"),
        ("0245", "1b1c"),
    ], top_k=5)
    assert result["investigation"]["task"] == "resolve_endgame"
    assert result["recommendations"]
    assert result["recommendations"][0]["is_candidate"] is True


def test_task_sorting_prefers_action_objective_before_legacy_score():
    solver = QuestLineSolver(use_cache=False)
    state = solver.investigation_state([
        ("0123", "0b1c"),
        ("1045", "0b1c"),
    ])
    low_score = {
        "action": {"type": "group_probe"},
        "weighted_expected": 1.0,
        "main_world_expected": 1.0,
        "normal_expected": 1.0,
        "normal_max_bucket": 1,
        "score": -100.0,
        "guess": "0167",
    }
    high_score = dict(low_score)
    high_score["score"] = 100.0
    assert solver.task_sort_key(low_score, state) == solver.task_sort_key(high_score, state)


def test_task_policy_replaces_phase_guard_contract():
    solver = QuestLineSolver(use_cache=False)
    state = solver.investigation_state([
        ("0123", "0b1c"),
        ("1045", "0b1c"),
    ])
    policy = state["task_policy"]
    assert policy["task"] == "cross_test_new_group"
    assert policy["objective"] == "weighted_expected"
    assert policy["expected_ratio"] > 1.0
    assert policy["max_slack"] > 0


def test_inconsistent_feedback_is_explicit_state():
    solver = QuestLineSolver(use_cache=False)
    result = solver.choose([
        ("0123", "4b0c"),
        ("0124", "0b0c"),
    ], top_k=5)
    assert result["phase"] == "inconsistent"
    assert result["investigation"]["task_status"] == "state_inconsistent"
    assert result["recommendations"] == []


def test_task_transition_is_explicit_for_infeasible_task():
    solver = QuestLineSolver(use_cache=False)
    assert solver.task_transition("cross_test_new_group") == "apply_position_pressure"
    assert solver.task_transition("resolve_endgame") is None


def test_investigation_state_reports_digit_positions():
    solver = QuestLineSolver(use_cache=False)
    state = solver.investigation_state([("0123", "0b1c")])

    assert len(state["digit_position_support"]["0"]) == 4
    assert sum(state["digit_position_support"]["0"]) == state["digit_support"]["0"]
    assert state["digit_status"]["0"]["position_support"] == state["digit_position_support"]["0"]
    assert len(state["digit_status"]["0"]["position_status"]) == 4


def test_outer_groups_remain_symmetric_when_identity_support_is_symmetric():
    solver = QuestLineSolver(use_cache=False)
    state = solver.investigation_state([
        ("0123", "1b1c"),
        ("0145", "1b0c"),
    ])

    assert state["group_relations"]["67"]["relation"] == "symmetric"
    assert state["group_relations"]["89"]["relation"] == "symmetric"


def test_group_relation_exposes_structured_identity_facts():
    solver = QuestLineSolver(use_cache=False)
    state = solver.investigation_state([
        ("0123", "4b0c"),
        ("4567", "0b0c"),
    ])

    relation = state["group_relations"]["45"]
    assert relation["digits"] == ["4", "5"]
    assert set(relation) >= {
        "relation", "support", "support_gap", "position_gap",
        "both_supported", "both_excluded",
    }
    assert set(state["strong_conflict_groups"]).issubset(set(state["group_relations"]))


def test_transition_explains_action_feedback_and_state_change():
    solver = QuestLineSolver(use_cache=False)
    event = solver.explain_transition([], "0123", "0b0c")

    assert event["round"] == 1
    assert event["action"]["guess"] == "0123"
    assert event["action"]["feedback"] == "0b0c"
    assert event["before"]["candidate_count"] == 5040
    assert event["after"]["candidate_count"] == 360
    assert event["before"]["task"] == "establish_foundation"
    assert event["after"]["task"] == "introduce_45"
    assert event["type"] in {"identity_breakthrough", "candidate_space_collapsed", "investigation_shifted"}
    assert event["narrative"]
    assert event["decision"]["task"] == "establish_foundation"
    assert "基础数字关系" in event["decision"]["rationale"]
    assert "因为" in event["narrative"]
    assert set(event["position_facts"]) == {"strengthened", "weakened", "confirmed", "excluded"}


def test_story_book_builds_chapters_from_task_transitions():
    solver = QuestLineSolver(use_cache=False)
    book = StoryBook.from_history([
        ("0123", "0b0c"),
        ("4567", "0b2c"),
        ("6895", "1b2c"),
        ("9785", "2b1c"),
        ("6789", "4b0c"),
    ], solver=solver)

    assert len(book.events) == 5
    assert [chapter["key"] for chapter in book.chapters] == [
        "foundation", "outer_split", "position_evidence", "convergence", "resolution"
    ]
    assert book.events[-1]["type"] == "solution_revealed"
    assert book.events[-1]["chapter"]["title"] == "终章：破案"
    assert book.digit_index["6"]
    assert book.group_index["67"]


def test_story_book_keeps_digit_and_position_events_together():
    solver = QuestLineSolver(use_cache=False)
    book = StoryBook.from_history([
        ("0123", "0b0c"),
        ("4567", "0b2c"),
        ("6895", "1b2c"),
    ], solver=solver)

    event = book.events[-1]
    assert event["chapter"]["key"] == "position_evidence"
    assert event["position_facts"]
    assert book.digit_index["5"]
    assert book.to_dict()["event_count"] == 3


def test_story_book_renders_case_and_indexes():
    solver = QuestLineSolver(use_cache=False)
    empty_book = StoryBook(solver=solver)
    assert "案件尚未开始" in empty_book.render()

    book = StoryBook.from_history([
        ("0123", "0b0c"),
        ("4567", "0b2c"),
        ("6895", "1b2c"),
        ("9785", "2b1c"),
        ("6789", "4b0c"),
    ], solver=solver)
    rendered = book.render(include_indexes=True)
    assert "《QuestLine 案件记录》" in rendered
    assert "## 核心事实" in rendered
    assert "## 终章：破案" in rendered
    assert "## 角色索引" in rendered
    assert "数字 6" in rendered
    assert "案件结论" in rendered


def test_story_book_preserves_identity_turning_points():
    solver = QuestLineSolver(use_cache=True)
    book = StoryBook.from_history([
        ("0123", "0b1c"),
        ("1045", "0b2c"),
        ("6470", "1b1c"),
        ("9680", "0b0c"),
        ("5274", "0b3c"),
    ], solver=solver)
    rendered = book.render()
    assert "伪装破裂" in rendered
    assert "组内证据分化" in rendered
    assert "01 的共同解释被证据整体排除" in rendered
    assert "89 的共同解释被证据整体排除" in rendered
    assert "数字 1" in rendered and "从未成为可信身份" in rendered
    assert "身份认知轨迹" in rendered
    assert "数字 3" in rendered


def test_game_session_assist_uses_shared_transition_pipeline():
    session = GameSession(mode="assist", solver=QuestLineSolver(use_cache=False))
    event = session.apply_turn("0123", "0b1c", source="Manual")
    assert session.round == 1
    assert session.status == session.ACTIVE
    assert event["session"]["mode"] == "assist"
    assert event["session"]["source"] == "Manual"
    assert session.story.events[0] is event
    snapshot = session.to_dict()
    assert snapshot["history"] == [("0123", "0b1c")]
    assert snapshot["story"]["event_count"] == 1
    assert snapshot["answer_known"] is False


def test_game_session_simulation_steps_engine_action():
    session = GameSession(
        mode="simulation",
        answer="3457",
        solver=QuestLineSolver(use_cache=True),
    )
    event = session.simulation_step()
    assert event["action"]["guess"] == "0123"
    assert session.history[0] == ("0123", (0, 1))
    assert session.status == session.ACTIVE
    assert session.to_dict(include_answer=True)["answer"] == "3457"


def test_game_session_adventure_generates_truthful_feedback():
    session = GameSession(
        mode="adventure",
        answer="3457",
        solver=QuestLineSolver(use_cache=False),
    )
    event = session.apply_turn("0123")
    assert event["action"]["feedback"] == "0b1c"
    assert session.history == [("0123", (0, 1))]


def test_game_session_reaches_logical_solved_state():
    session = GameSession(mode="assist", solver=QuestLineSolver(use_cache=True))
    for guess, feedback in [
        ("0123", "0b1c"),
        ("1045", "0b2c"),
        ("6470", "1b1c"),
        ("9680", "0b0c"),
        ("5274", "0b3c"),
    ]:
        session.apply_turn(guess, feedback)
    assert session.status == session.LOGICALLY_SOLVED
    assert session.logical_answer == "3457"
    assert session.to_dict()["candidate_count"] == 1


def test_game_session_save_and_resume_preserves_case_state():
    session = GameSession(mode="assist", solver=QuestLineSolver(use_cache=False))
    session.apply_turn("0123", "0b1c")
    snapshot = session.save()
    resumed = GameSession.resume(snapshot, solver=QuestLineSolver(use_cache=False))
    assert resumed.mode == "assist"
    assert resumed.history == [("0123", (0, 1))]
    assert resumed.story.to_dict()["event_count"] == 1
    assert resumed.current_state()["candidate_count"] == 1440


def test_game_session_replay_and_markdown_keep_rejected_attempts_separate():
    session = GameSession(mode="assist", solver=QuestLineSolver(use_cache=False))
    session.apply_turn("0123", "0b1c")
    try:
        session.apply_turn("1045", "4b0c")
    except ValueError as exc:
        assert "no possible answer" in str(exc)
    else:
        raise AssertionError("inconsistent feedback should be rejected")
    assert session.history == [("0123", (0, 1))]
    assert len(session.replay()["rejected"]) == 1
    assert "被拒绝的输入" in session.export_markdown()


def test_adventure_rejects_cheating_feedback_without_polluting_story():
    session = GameSession(mode="adventure", answer="3457", solver=QuestLineSolver(use_cache=False))
    try:
        session.apply_turn("0123", "4b0c")
    except ValueError as exc:
        assert "hidden answer" in str(exc)
    else:
        raise AssertionError("dishonest adventure feedback should be rejected")
    assert session.history == []
    assert session.story.events == []
    assert session.replay()["rejected"][0]["reason"] == "feedback does not match the hidden answer"


def test_game_session_current_state_exposes_webui_read_model():
    session = GameSession(mode="assist", solver=QuestLineSolver(use_cache=False))
    session.apply_turn("0123", "0b1c")
    state = session.current_state()
    assert state["mode"] == "assist"
    assert state["candidate_count"] == 1440
    assert "digits" in state and "0" in state["digits"]
    assert "groups" in state and "01" in state["groups"]
    assert "group_relations" in state
    assert "world_line" in state and "main_world" in state["world_line"]
    assert state["chapters"]
    assert state["suspense"]["level"] == "open"


def test_game_session_replay_contains_last_chapter_and_markdown_metadata():
    session = GameSession(mode="assist", solver=QuestLineSolver(use_cache=False))
    session.apply_turn("0123", "0b1c", source="Manual")
    replay = session.replay()
    assert replay["accepted"][0]["source"] == "Manual"
    assert replay["accepted"][0]["chapter"]["title"]
    markdown = session.export_markdown()
    assert "## 会话信息" in markdown
    assert "已接受行动：1" in markdown
