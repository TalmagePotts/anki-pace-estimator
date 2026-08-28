"""Which clock runs, and when the warning is allowed to fire.

``_goal_for_phase`` is the single place that decides what happens as a card
moves from question to answer, so every combination is pinned down here.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))

import pytest  # noqa: E402

import test_imports  # noqa: E402


class FakeCard:
    def __init__(self, did=1, odid=0):
        self.did = did
        self.odid = odid


def runtime_with(goal_overrides):
    test_imports._install_stubs()
    import importlib

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pace_estimator"))
    runtime = importlib.import_module("src.runtime")
    config = importlib.import_module("src.config")
    cfg = config.normalise({"goal": dict({"enabled": True}, **goal_overrides)})
    runtime.config = lambda: cfg
    return runtime


def decide(goal_overrides, phase, card=None):
    runtime = runtime_with(goal_overrides)
    return runtime._goal_for_phase(card or FakeCard(), phase)


QUESTION = "question"
ANSWER = "answer"


def test_whole_card_runs_one_clock_across_both_sides():
    seconds, restart, _ = decide({"timer_phase": "whole_card"}, QUESTION)
    assert (seconds, restart) == (12.0, True)
    seconds, restart, _ = decide({"timer_phase": "whole_card"}, ANSWER)
    # Same goal, and crucially not restarted -- the clock keeps running.
    assert (seconds, restart) == (12.0, False)


def test_question_only_clock_stops_when_the_answer_appears():
    assert decide({"timer_phase": "question"}, QUESTION)[:2] == (12.0, True)
    assert decide({"timer_phase": "question"}, ANSWER)[0] is None


def test_answer_only_clock_shows_nothing_on_the_question():
    assert decide({"timer_phase": "answer"}, QUESTION)[0] is None
    assert decide({"timer_phase": "answer"}, ANSWER)[:2] == (12.0, True)


def test_separate_clock_uses_its_own_allowance_and_restarts():
    overrides = {"timer_phase": "separate", "seconds_per_card": 20, "answer_seconds": 6}
    assert decide(overrides, QUESTION)[:2] == (20.0, True)
    assert decide(overrides, ANSWER)[:2] == (6.0, True)


def test_answer_seconds_is_ignored_unless_the_clock_is_separate():
    overrides = {"timer_phase": "whole_card", "seconds_per_card": 20, "answer_seconds": 6}
    assert decide(overrides, ANSWER)[0] == 20.0


@pytest.mark.parametrize(
    "alert_phase,on_question,on_answer",
    [("always", True, True), ("question", True, False), ("answer", False, True)],
)
def test_warning_side_is_independent_of_the_clock(alert_phase, on_question, on_answer):
    overrides = {"timer_phase": "whole_card", "alert_phase": alert_phase}
    assert decide(overrides, QUESTION)[2] is on_question
    assert decide(overrides, ANSWER)[2] is on_answer
    # The clock is unaffected by where the warning is allowed.
    assert decide(overrides, QUESTION)[0] == 12.0
    assert decide(overrides, ANSWER)[0] == 12.0


def test_disabled_goal_produces_nothing_on_either_side():
    for phase in (QUESTION, ANSWER):
        assert decide({"enabled": False}, phase) == (None, False, False)


def test_no_card_produces_nothing():
    runtime = runtime_with({"timer_phase": "whole_card"})
    assert runtime._goal_for_phase(None, QUESTION) == (None, False, False)


def test_per_deck_time_is_used_for_the_card_s_deck():
    overrides = {"seconds_per_card": 12, "per_deck_seconds": {"7": 30}}
    assert decide(overrides, QUESTION, FakeCard(did=7))[0] == 30.0
    assert decide(overrides, QUESTION, FakeCard(did=1))[0] == 12.0


def test_filtered_cards_use_their_home_deck_s_time():
    # A card in a filtered deck keeps its original deck in ``odid``.
    overrides = {"seconds_per_card": 12, "per_deck_seconds": {"7": 30}}
    assert decide(overrides, QUESTION, FakeCard(did=999, odid=7))[0] == 30.0


def test_shipped_defaults_warn_while_the_question_is_still_up():
    runtime = runtime_with({})          # goal switched on, everything else default
    q = runtime._goal_for_phase(FakeCard(), QUESTION)
    a = runtime._goal_for_phase(FakeCard(), ANSWER)
    assert q == (12.0, True, True)      # clock starts and the warning may fire
    assert a == (12.0, False, False)    # clock continues, but nothing is shown
