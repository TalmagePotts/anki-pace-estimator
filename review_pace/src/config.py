"""Typed, self-healing access to the add-on's configuration.

Anki hands add-ons a raw ``dict`` loaded from ``config.json``.  Users (and
older versions of this add-on) can leave keys missing, so every read goes
through :func:`get` which deep-merges the stored values over the defaults.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

from .consts import DEFAULT_COMPONENT_ORDER, SPEED_MODE_WALL

CONFIG_VERSION = 1

DEFAULTS: Dict[str, Any] = {
    "version": CONFIG_VERSION,
    "decks": {
        # Empty list means "every deck".
        "ids": [],
        "include_subdecks": True,
        # When reviewing, measure the deck you are actually in rather than the
        # saved selection.
        "follow_current_deck": True,
    },
    "speed": {
        "mode": SPEED_MODE_WALL,  # "wall" or "answer"
        # What the ETA is built from. "mean" is the only unbiased choice for a
        # total; the others are offered because they are yours to pick.
        "estimator": "mean",  # "mean", "trimmed" or "median"
        # Extra ways to split the speed measurement, on top of card type.
        # Backtesting found these change accuracy by well under a percentage
        # point, so they are off by default -- but they are yours to turn on.
        "features": [],  # any of "ease", "interval"
        # Fourteen days, not thirty: backtesting against real review history
        # showed a shorter window tracks your current pace noticeably better.
        "lookback_days": 14,
        # If the window is thin, widen it rather than estimate from noise.
        "min_sample": 200,
        "max_rows": 60000,
        "idle_cutoff_s": 60,
        "max_answer_s": 60,
        "per_card_class": True,
        "count_full_learning": True,
        "include_lapses": True,
    },
    "display": {
        "components": [
            {"id": cid, "enabled": cid != "breakdown"} for cid in DEFAULT_COMPONENT_ORDER
        ],
        "show_on_deck_browser": True,
        "show_on_overview": True,
        "show_eta_range": True,
        "show_finish_time": True,
        "clock_24h": False,
        "compact": False,
        # 0 picks a column count from the number of tiles, so the last row
        # is full wherever the arithmetic allows.
        "columns": 0,
        "accent": "",  # "" follows Anki's theme accent
        "font_scale": 1.0,
        "period_mode": "rolling",  # "rolling" or "calendar"
        # Which seconds-per-card figure the home screen leads with.
        "speed_display": "mean",  # "mean", "typical" or "both"
        "title": "Review Pace",
        "show_title": True,
    },
    "toolbar": {
        "enabled": True,
        "template": "⏱ {eta}",
        "click_action": "stats",  # "stats", "config" or "none"
        "hide_when_empty": True,
    },
    "overlay": {
        "enabled": True,
        "position": "top-right",
        "opacity": 0.92,
        "show_remaining": True,
        "show_eta": True,
        "show_session_speed": True,
        "show_progress_bar": True,
        "show_elapsed": False,
        "hotkey": "Shift+P",
        "scale": 1.0,
    },
    "goal": {
        "enabled": False,
        "seconds_per_card": 12.0,
        "per_deck_seconds": {},  # {"<deck id>": seconds}
        # The running timer and the out-of-time warning are independent: you
        # can have a timer with no warning, a warning with no timer, or both.
        "show_timer": True,
        "count_down": True,
        "badge_position": "top-right",
        "scale": 1.0,
        "alert_style": "badge",  # "none", "badge", "exclamation" or "both"
        "alert_position": "bottom",
        "alert_text": "!",
        "alert_scale": 1.0,
        # When the clock runs, and whether revealing the answer restarts it.
        #   whole_card -- one clock from question to grade
        #   question   -- clock stops when you reveal the answer
        #   answer     -- clock starts when you reveal the answer
        #   separate   -- a fresh clock, with its own goal, for the answer
        "timer_phase": "whole_card",
        "answer_seconds": 8.0,
        # When the out-of-time warning is allowed to appear.
        "alert_phase": "always",  # "always", "question" or "answer"
        "pulse_when_over": True,
        "sound": False,
    },
    "debug": False,
}


def _merge(defaults: Any, stored: Any) -> Any:
    if isinstance(defaults, dict):
        out = {}
        stored_d = stored if isinstance(stored, dict) else {}
        for key, dval in defaults.items():
            out[key] = _merge(dval, stored_d.get(key))
        # Preserve unknown keys so a downgrade does not silently drop settings.
        for key, sval in stored_d.items():
            if key not in out:
                out[key] = sval
        return out
    if stored is None:
        return copy.deepcopy(defaults)
    if isinstance(defaults, bool):
        return bool(stored)
    if isinstance(defaults, float) and isinstance(stored, (int, float)):
        return float(stored)
    if isinstance(defaults, int) and not isinstance(defaults, bool):
        try:
            return int(stored)
        except (TypeError, ValueError):
            return defaults
    if isinstance(defaults, list) and not isinstance(stored, list):
        return copy.deepcopy(defaults)
    return stored


def normalise(stored: Any) -> Dict[str, Any]:
    """Deep-merge ``stored`` over :data:`DEFAULTS` and repair known problems."""
    cfg = _merge(DEFAULTS, stored)

    # The component list must contain every known component exactly once, so a
    # new release can add one without the user losing their ordering.
    seen = []
    cleaned: List[Dict[str, Any]] = []
    for entry in cfg["display"]["components"]:
        if not isinstance(entry, dict):
            entry = {"id": str(entry), "enabled": True}
        cid = entry.get("id")
        if cid in DEFAULT_COMPONENT_ORDER and cid not in seen:
            seen.append(cid)
            cleaned.append({"id": cid, "enabled": bool(entry.get("enabled", True))})
    for cid in DEFAULT_COMPONENT_ORDER:
        if cid not in seen:
            cleaned.append({"id": cid, "enabled": False})
    cfg["display"]["components"] = cleaned

    sp = cfg["speed"]
    sp["lookback_days"] = max(1, min(3650, sp["lookback_days"]))
    sp["idle_cutoff_s"] = max(5, min(3600, sp["idle_cutoff_s"]))
    sp["max_answer_s"] = max(5, min(600, sp["max_answer_s"]))
    sp["max_rows"] = max(500, min(1000000, sp["max_rows"]))
    sp["min_sample"] = max(0, min(100000, sp["min_sample"]))
    if sp["mode"] not in ("wall", "answer"):
        sp["mode"] = "wall"
    # "aggregate" was the old name and defaulted to the median, which
    # underestimates every session. It is dropped rather than carried over, so
    # existing users land on the mean and can opt back out deliberately.
    sp.pop("aggregate", None)
    if sp["estimator"] not in ("mean", "trimmed", "median"):
        sp["estimator"] = "mean"
    known = ("ease", "interval")
    seen = []
    for feature in sp["features"]:
        if feature in known and feature not in seen:
            seen.append(feature)
    sp["features"] = seen

    disp = cfg["display"]
    if disp["speed_display"] not in ("mean", "typical", "both"):
        disp["speed_display"] = "mean"
    disp["font_scale"] = max(0.7, min(2.0, float(disp["font_scale"])))
    disp["columns"] = max(0, min(6, int(disp["columns"])))

    ov = cfg["overlay"]
    ov["opacity"] = max(0.2, min(1.0, float(ov["opacity"])))
    ov["scale"] = max(0.6, min(2.0, float(ov["scale"])))
    if ov["position"] not in ("top-right", "top-left", "bottom-right", "bottom-left"):
        ov["position"] = "top-right"

    goal = cfg["goal"]
    goal["seconds_per_card"] = max(1.0, min(600.0, float(goal["seconds_per_card"])))
    goal["answer_seconds"] = max(1.0, min(600.0, float(goal["answer_seconds"])))
    if goal["timer_phase"] not in ("whole_card", "question", "answer", "separate"):
        goal["timer_phase"] = "whole_card"
    if goal["alert_phase"] not in ("always", "question", "answer"):
        goal["alert_phase"] = "always"
    goal["scale"] = max(0.6, min(2.0, float(goal["scale"])))
    goal["alert_scale"] = max(0.5, min(4.0, float(goal["alert_scale"])))
    if goal["alert_style"] not in ("none", "badge", "exclamation", "both"):
        goal["alert_style"] = "badge"
    if goal["alert_position"] not in (
        "bottom", "lower-half", "center", "upper-half", "top"
    ):
        goal["alert_position"] = "bottom"
    if goal["badge_position"] not in (
        "top-right", "top-left", "bottom-right", "bottom-left"
    ):
        goal["badge_position"] = "top-right"
    if not str(goal["alert_text"]).strip():
        goal["alert_text"] = "!"
    if not isinstance(goal["per_deck_seconds"], dict):
        goal["per_deck_seconds"] = {}
    # An alert that recolours the timer needs the timer to be on screen.
    if not goal["show_timer"] and goal["alert_style"] == "badge":
        goal["alert_style"] = "exclamation"
    # Nothing to show at all means the feature is off.
    if not goal["show_timer"] and goal["alert_style"] == "none":
        goal["enabled"] = False
    # "start_on" became the richer timer_phase; carry the old meaning across.
    legacy_start = goal.pop("start_on", None)
    if legacy_start == "answer" and goal["timer_phase"] == "whole_card":
        goal["timer_phase"] = "answer"
    # Old configs used a percentage warning stage; it is gone.
    goal.pop("warn_at_pct", None)
    goal.pop("show_badge", None)
    goal.pop("session_pace_warning", None)

    cfg["decks"]["ids"] = [int(x) for x in cfg["decks"]["ids"] if str(x).lstrip("-").isdigit()]
    cfg["version"] = CONFIG_VERSION
    return cfg


def enabled_components(cfg: Dict[str, Any]) -> List[str]:
    return [c["id"] for c in cfg["display"]["components"] if c["enabled"]]


def goal_seconds_for(cfg: Dict[str, Any], deck_id: int) -> float:
    """Per-card goal for a deck, falling back to the global default."""
    per_deck = cfg["goal"]["per_deck_seconds"]
    val = per_deck.get(str(deck_id), per_deck.get(deck_id))
    try:
        if val is not None and float(val) > 0:
            return float(val)
    except (TypeError, ValueError):
        pass
    return float(cfg["goal"]["seconds_per_card"])
