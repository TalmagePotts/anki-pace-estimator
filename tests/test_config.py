import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pace_estimator"))

from src import config as C  # noqa: E402
from src import consts as K  # noqa: E402


def test_defaults_round_trip():
    cfg = C.normalise({})
    assert cfg["speed"]["mode"] == "wall"
    assert cfg["version"] == C.CONFIG_VERSION
    assert C.normalise(cfg) == cfg


def test_missing_keys_are_filled_in():
    cfg = C.normalise({"speed": {"lookback_days": 7}})
    assert cfg["speed"]["lookback_days"] == 7
    assert cfg["speed"]["idle_cutoff_s"] == 60  # untouched default survives
    assert "goal" in cfg


def test_unknown_keys_are_preserved():
    cfg = C.normalise({"speed": {"future_option": 3}})
    assert cfg["speed"]["future_option"] == 3


def test_out_of_range_values_are_clamped():
    cfg = C.normalise(
        {"speed": {"lookback_days": 99999, "idle_cutoff_s": 0, "mode": "nonsense"},
         "display": {"font_scale": 9.0}, "goal": {"alert_scale": 99}}
    )
    assert cfg["speed"]["lookback_days"] == 3650
    assert cfg["speed"]["idle_cutoff_s"] == 5
    assert cfg["speed"]["mode"] == "wall"
    assert cfg["display"]["font_scale"] == 2.0
    assert cfg["goal"]["alert_scale"] == 4.0


def test_component_list_is_repaired():
    cfg = C.normalise(
        {"display": {"components": [{"id": "speed", "enabled": True},
                                    {"id": "speed", "enabled": False},
                                    {"id": "bogus", "enabled": True}]}}
    )
    ids = [c["id"] for c in cfg["display"]["components"]]
    assert ids[0] == "speed"                       # user's ordering respected
    assert len(ids) == len(set(ids))               # no duplicates
    assert set(ids) == set(K.DEFAULT_COMPONENT_ORDER)  # nothing missing
    assert "bogus" not in ids


def test_legacy_string_components_still_work():
    cfg = C.normalise({"display": {"components": ["eta", "learned"]}})
    enabled = C.enabled_components(cfg)
    assert enabled[:2] == ["eta", "learned"]


def test_deck_ids_are_coerced_to_ints():
    cfg = C.normalise({"decks": {"ids": ["123", 456, "oops", None]}})
    assert cfg["decks"]["ids"] == [123, 456]


def test_per_deck_goal_overrides_global():
    cfg = C.normalise({"goal": {"seconds_per_card": 10, "per_deck_seconds": {"5": 25}}})
    assert C.goal_seconds_for(cfg, 5) == 25.0
    assert C.goal_seconds_for(cfg, 999) == 10.0


def test_bad_per_deck_goal_falls_back():
    cfg = C.normalise({"goal": {"seconds_per_card": 10, "per_deck_seconds": {"5": "abc", "6": 0}}})
    assert C.goal_seconds_for(cfg, 5) == 10.0
    assert C.goal_seconds_for(cfg, 6) == 10.0


def test_timer_off_forces_a_visible_warning_style():
    # "Turn the timer red" is meaningless with no timer on screen.
    cfg = C.normalise({"goal": {"show_timer": False, "alert_style": "badge"}})
    assert cfg["goal"]["alert_style"] == "exclamation"


def test_nothing_to_show_turns_the_goal_off():
    cfg = C.normalise({"goal": {"enabled": True, "show_timer": False,
                                "alert_style": "none"}})
    assert cfg["goal"]["enabled"] is False


def test_timer_only_is_allowed():
    cfg = C.normalise({"goal": {"enabled": True, "show_timer": True,
                                "alert_style": "none"}})
    assert cfg["goal"]["enabled"] is True
    assert cfg["goal"]["alert_style"] == "none"


def test_percentage_warning_is_dropped_from_old_configs():
    cfg = C.normalise({"goal": {"warn_at_pct": 80, "show_badge": True}})
    assert "warn_at_pct" not in cfg["goal"]
    assert "show_badge" not in cfg["goal"]


def test_bad_alert_values_are_repaired():
    cfg = C.normalise({"goal": {"show_timer": True, "alert_style": "sparkles",
                                "alert_position": "sideways", "alert_text": "   ",
                                "badge_position": "middle"}})
    assert cfg["goal"]["alert_style"] == "badge"
    assert cfg["goal"]["alert_position"] == "bottom"
    assert cfg["goal"]["alert_text"] == "!"
    assert cfg["goal"]["badge_position"] == "top-right"


def test_alert_positions_include_bottom_middle():
    for position in ("bottom", "lower-half", "center", "upper-half", "top"):
        cfg = C.normalise({"goal": {"alert_position": position}})
        assert cfg["goal"]["alert_position"] == position


def test_default_window_is_short_and_has_a_floor():
    cfg = C.normalise({})
    assert cfg["speed"]["lookback_days"] == 14
    assert cfg["speed"]["min_sample"] > 0


def test_estimator_choices_are_all_allowed():
    for name in ("mean", "trimmed", "median"):
        assert C.normalise({"speed": {"estimator": name}})["speed"]["estimator"] == name
    assert C.normalise({"speed": {"estimator": "vibes"}})["speed"]["estimator"] == "mean"


def test_old_aggregate_key_is_dropped_not_carried_over():
    # It defaulted to the median, which underestimates; users land on the mean
    # and can opt back in deliberately.
    cfg = C.normalise({"speed": {"aggregate": "median"}})
    assert "aggregate" not in cfg["speed"]
    assert cfg["speed"]["estimator"] == "mean"


def test_features_are_validated_and_deduplicated():
    cfg = C.normalise({"speed": {"features": ["ease", "ease", "tarot", "interval"]}})
    assert cfg["speed"]["features"] == ["ease", "interval"]
    assert C.normalise({})["speed"]["features"] == []


def test_speed_display_choices():
    for name in ("mean", "typical", "both"):
        assert C.normalise({"display": {"speed_display": name}})["display"][
            "speed_display"
        ] == name
    assert C.normalise({"display": {"speed_display": "?"}})["display"][
        "speed_display"
    ] == "mean"


def test_timer_phase_and_alert_phase_are_independent():
    cfg = C.normalise({"goal": {"timer_phase": "whole_card", "alert_phase": "answer"}})
    assert cfg["goal"]["timer_phase"] == "whole_card"
    assert cfg["goal"]["alert_phase"] == "answer"


def test_bad_phase_values_are_repaired():
    cfg = C.normalise({"goal": {"timer_phase": "sideways", "alert_phase": "maybe"}})
    assert cfg["goal"]["timer_phase"] == "whole_card"
    assert cfg["goal"]["alert_phase"] == "always"


def test_old_start_on_answer_becomes_an_answer_phase_timer():
    cfg = C.normalise({"goal": {"start_on": "answer"}})
    assert "start_on" not in cfg["goal"]
    assert cfg["goal"]["timer_phase"] == "answer"


def test_old_start_on_question_keeps_the_whole_card_clock():
    cfg = C.normalise({"goal": {"start_on": "question"}})
    assert cfg["goal"]["timer_phase"] == "whole_card"


def test_answer_seconds_is_clamped():
    assert C.normalise({"goal": {"answer_seconds": 0}})["goal"]["answer_seconds"] == 1.0
    assert C.normalise({"goal": {"answer_seconds": 9999}})["goal"]["answer_seconds"] == 600.0


def test_a_newly_added_component_arrives_switched_on():
    # Otherwise every feature added after a user's config was written would be
    # invisible to them.
    cfg = C.normalise({"display": {"components": [{"id": "eta", "enabled": True}]}})
    states = {c["id"]: c["enabled"] for c in cfg["display"]["components"]}
    assert states["session"] is True
    assert states["breakdown"] is False  # ships off, stays off
    assert list(states)[0] == "eta"      # the user's ordering is still respected


def test_shipped_goal_defaults_are_quiet():
    """Off by default, and unobtrusive the moment it is switched on.

    Someone enabling this wants to know when a card ran long, not a clock
    ticking at them -- and a warning on the question side would double as a
    hint that they are struggling to recall the answer.
    """
    goal = C.normalise({})["goal"]
    assert goal["enabled"] is False
    assert goal["show_timer"] is False
    assert goal["alert_style"] == "exclamation"
    assert goal["alert_phase"] == "answer"
    assert goal["alert_position"] == "bottom"
    assert goal["timer_phase"] == "whole_card"   # times the card, not just the answer


def test_switching_the_goal_on_changes_nothing_else():
    on = C.normalise({"goal": {"enabled": True}})["goal"]
    off = C.normalise({})["goal"]
    assert on["enabled"] is True
    assert {k: v for k, v in on.items() if k != "enabled"} == {
        k: v for k, v in off.items() if k != "enabled"
    }
