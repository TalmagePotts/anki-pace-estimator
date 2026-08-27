"""Names, defaults and small formatting helpers shared across the add-on."""

from __future__ import annotations

ADDON_NAME = "Review Pace"
ADDON_PACKAGE = "review_pace"

# Component ids available on the home screen, in their default order.
COMP_ETA = "eta"
COMP_WORKLOAD = "workload"
COMP_SPEED = "speed"
COMP_LEARNED = "learned"
COMP_DONE = "done_today"
COMP_BREAKDOWN = "breakdown"
COMP_SESSION = "session"

COMPONENT_LABELS = {
    COMP_ETA: "Time remaining / ETA",
    COMP_WORKLOAD: "Cards waiting (due, new, learning)",
    COMP_SPEED: "Speed (answer & wall-clock)",
    COMP_LEARNED: "New cards learned (today / week / month)",
    COMP_DONE: "Done today (reviews & time)",
    COMP_BREAKDOWN: "Speed breakdown by card type",
    COMP_SESSION: "Summary of the session you just finished",
}

COMPONENT_HELP = {
    COMP_ETA: "How long the selected decks should take, and the clock time you finish at.",
    COMP_WORKLOAD: "Due, new and learning counts after your deck limits are applied.",
    COMP_SPEED: "Seconds per card, both pure answer time and full wall-clock time.",
    COMP_LEARNED: "Cards you saw for the very first time in each period.",
    COMP_DONE: "Reviews answered and time spent since today's rollover.",
    COMP_BREAKDOWN: "Separate speeds for learning, young, mature and relearning cards.",
    COMP_SESSION: "Appears for a while after you finish studying, then disappears.",
}

DEFAULT_COMPONENT_ORDER = [
    COMP_SESSION,
    COMP_ETA,
    COMP_WORKLOAD,
    COMP_SPEED,
    COMP_LEARNED,
    COMP_DONE,
    COMP_BREAKDOWN,
]

SPEED_MODE_WALL = "wall"
SPEED_MODE_ANSWER = "answer"

OVERLAY_POSITIONS = ["top-right", "top-left", "bottom-right", "bottom-left"]


def fmt_duration(seconds: float, style: str = "short") -> str:
    """Human duration. ``short`` -> ``1h 04m``; ``clock`` -> ``64:12``."""
    seconds = max(0.0, float(seconds))
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    if style == "clock":
        if hours:
            return "%d:%02d:%02d" % (hours, mins, secs)
        return "%d:%02d" % (mins, secs)
    if hours:
        return "%dh %02dm" % (hours, mins)
    if mins:
        return "%dm %02ds" % (mins, secs) if mins < 10 else "%dm" % mins
    return "%ds" % secs


def fmt_secs_per_card(seconds: float) -> str:
    if seconds <= 0:
        return "--"
    return "%.1fs" % seconds


def fmt_clock(epoch_seconds: float, use_24h: bool) -> str:
    import time as _time

    lt = _time.localtime(epoch_seconds)
    if use_24h:
        return _time.strftime("%H:%M", lt)
    return _time.strftime("%I:%M %p", lt).lstrip("0")
