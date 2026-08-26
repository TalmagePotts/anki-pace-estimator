import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "review_pace"))

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
         "display": {"font_scale": 9.0}, "goal": {"warn_at_pct": 500}}
    )
    assert cfg["speed"]["lookback_days"] == 3650
    assert cfg["speed"]["idle_cutoff_s"] == 5
    assert cfg["speed"]["mode"] == "wall"
    assert cfg["display"]["font_scale"] == 2.0
    assert cfg["goal"]["warn_at_pct"] == 100


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
