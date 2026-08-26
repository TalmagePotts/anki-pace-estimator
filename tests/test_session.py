import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "review_pace"))

from src.session import FULL_TRUST_AT, LiveSession, _scaled  # noqa: E402
from src import stats as S  # noqa: E402


def test_first_answer_uses_its_own_time():
    s = LiveSession()
    s.reset()
    s.record(8000)
    assert abs(s.wall_per_card - 8.0) < 0.2
    assert abs(s.answer_per_card - 8.0) < 0.01


def test_long_break_is_not_counted_as_study_time():
    s = LiveSession()
    s.reset(idle_cutoff_s=1)
    s.record(500)
    time.sleep(1.05)
    s.record(500)
    # The 1s break exceeds the cutoff, so only the two 0.5s answers count.
    assert s.active_seconds < 1.5


def test_blended_speed_moves_from_history_to_the_session():
    s = LiveSession()
    s.reset()
    s.answers = 1
    s.active_seconds = 20.0
    near_history = s.blended_speed(10.0, "wall")
    s.answers = FULL_TRUST_AT
    s.active_seconds = 20.0 * FULL_TRUST_AT
    fully_live = s.blended_speed(10.0, "wall")
    assert 10.0 < near_history < fully_live
    assert abs(fully_live - 20.0) < 0.01


def test_blended_speed_handles_missing_inputs():
    s = LiveSession()
    s.reset()
    assert s.blended_speed(9.0, "wall") == 9.0
    s.answers, s.active_seconds = 4, 40.0
    assert s.blended_speed(0.0, "wall") == 10.0


def test_pace_ratio():
    s = LiveSession()
    s.reset()
    assert s.pace_ratio(10.0, "wall") is None
    s.answers, s.active_seconds = 4, 60.0
    assert abs(s.pace_ratio(10.0, "wall") - 1.5) < 0.01
    assert s.pace_ratio(0.0, "wall") is None


def test_scaling_speeds_preserves_relative_costs():
    speeds = S.Speeds(
        per_class={S.MATURE: S.ClassSpeed(n=100, answer=4, wall=5, answer_slow=8, wall_slow=9)},
        overall=S.ClassSpeed(n=100, answer=4, wall=5, answer_slow=8, wall_slow=9),
    )
    doubled = _scaled(speeds, 2.0)
    assert doubled.overall.wall == 10
    assert doubled.per_class[S.MATURE].answer_slow == 16
    assert _scaled(speeds, 1.0) is speeds


def test_scaling_keeps_the_spread_fields():
    speeds = S.Speeds(
        per_class={S.MATURE: S.ClassSpeed(n=100, answer=4, wall=5, answer_sd=2, wall_sd=3)},
        overall=S.ClassSpeed(n=100, answer=4, wall=5, answer_sd=2, wall_sd=3),
        day_cv=0.2,
    )
    doubled = _scaled(speeds, 2.0)
    assert doubled.overall.wall_sd == 6
    assert doubled.per_class[S.MATURE].answer_sd == 4
    assert doubled.day_cv == 0.2
