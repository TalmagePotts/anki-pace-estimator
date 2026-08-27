"""Run the injected reviewer script under Node against a stub DOM.

The per-card timer is the one piece of this add-on that lives entirely in
JavaScript, and it is exactly where a rounding mistake made the countdown look
like it was running fast. Driving it with a fake clock is the only way to check
it without sitting in front of a card.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "review_pace"))

from src import config as C  # noqa: E402
from src.session import LiveSession  # noqa: E402
from src.ui import reviewer as RV  # noqa: E402

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

HARNESS = r"""
let NOW = 1_000_000;
let tickFn = null;

function makeEl() {
  return {
    id: "", className: "", textContent: "", innerHTML: "",
    style: {}, childNodes: [],
    appendChild(c) { this.childNodes.push(c); },
  };
}
const registry = {};
const head = makeEl();
global.document = {
  head,
  body: { appendChild(c) { registry[c.id] = c; } },
  getElementById: (id) => registry[id] || (id === "rvp-style" ? null : null),
  createElement: () => makeEl(),
};
global.window = {};
global.Date = { now: () => NOW };
global.setInterval = (fn) => { tickFn = fn; return 1; };
global.clearInterval = () => {};

SCRIPT_PLACEHOLDER

const readings = [];
for (const offsetMs of OFFSETS_PLACEHOLDER) {
  NOW = 1_000_000 + offsetMs;
  tickFn();
  const badge = registry["rvp-goal"];
  const alert = registry["rvp-alert"];
  readings.push({
    ms: offsetMs,
    timer: badge && badge.style.display !== "none" ? badge.textContent : null,
    timerClass: badge ? badge.className : null,
    alertShown: !!(alert && alert.className.indexOf("rvp-show") >= 0),
    alertClass: alert ? alert.className : null,
  });
}
console.log(JSON.stringify(readings));
"""


def run_timer(goal_overrides, offsets_ms, goal_seconds=10.0):
    cfg = C.normalise({"goal": dict({"enabled": True}, **goal_overrides)})
    payload = RV.build_payload(None, cfg, LiveSession(), goal_seconds, False)
    assert payload["goal"] is not None, "the goal was disabled by normalise()"
    script = (
        HARNESS.replace("SCRIPT_PLACEHOLDER", RV.script(payload))
        .replace("OFFSETS_PLACEHOLDER", json.dumps(list(offsets_ms)))
    )
    out = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, timeout=30
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def timers(readings):
    return [r["timer"] for r in readings]


def test_countdown_starts_at_the_full_goal_and_does_not_skip():
    # The reported bug: a 10s goal showed 9 almost immediately.
    r = run_timer({"count_down": True}, [0, 100, 500, 999, 1000, 1500, 9000, 9999])
    assert timers(r) == ["10", "10", "10", "10", "9", "9", "1", "1"]


def test_countdown_reaches_zero_exactly_at_the_goal():
    r = run_timer({"count_down": True}, [9999, 10000, 10001, 11000])
    assert timers(r) == ["1", "0", "+1", "+1"]


def test_count_up_starts_at_zero():
    r = run_timer({"count_down": False}, [0, 500, 1000, 1999, 2000])
    assert timers(r) == ["0", "0", "1", "1", "2"]


def test_minutes_are_formatted():
    r = run_timer({"count_down": True}, [0, 65_000], goal_seconds=125.0)
    assert timers(r) == ["2:05", "1:00"]


def test_timer_uses_the_card_stamp_not_the_injection_time():
    # Simulate the add-on spending 2s on database work before injecting: the
    # card's clock must already be 2s in, not restarting from the goal.
    cfg = C.normalise({"goal": {"enabled": True, "count_down": True}})
    payload = RV.build_payload(None, cfg, LiveSession(), 10.0, False)
    script = (
        HARNESS.replace(
            "SCRIPT_PLACEHOLDER",
            "window.__rvpCardStart = NOW - 2000;\n" + RV.script(payload),
        ).replace("OFFSETS_PLACEHOLDER", json.dumps([0, 1000]))
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert timers(json.loads(out.stdout)) == ["8", "7"]


def test_badge_turns_red_only_when_over():
    r = run_timer({"count_down": True, "alert_style": "badge"}, [9000, 10000, 12000])
    assert r[0]["timerClass"] == ""
    assert "rvp-over" in r[1]["timerClass"]
    assert "rvp-over" in r[2]["timerClass"]


def test_no_early_warning_stage():
    # There is no amber stage any more: nothing happens before the goal.
    r = run_timer({"count_down": True, "alert_style": "both"},
                  [0, 5000, 8000, 9999, 10000])
    assert all(x["timerClass"] == "" for x in r[:4])
    assert all(not x["alertShown"] for x in r[:4])
    assert r[4]["alertShown"] is True


def test_warning_only_mode_shows_nothing_until_time_is_up():
    r = run_timer(
        {"show_timer": False, "alert_style": "exclamation"}, [0, 5000, 9999, 10000]
    )
    assert all(x["timer"] is None for x in r)  # no timer on screen at all
    assert [x["alertShown"] for x in r] == [False, False, False, True]


def test_pulse_can_be_turned_off():
    on = run_timer({"alert_style": "both", "pulse_when_over": True}, [11000])[0]
    off = run_timer({"alert_style": "both", "pulse_when_over": False}, [11000])[0]
    assert "rvp-pulsing" in on["alertClass"]
    assert "rvp-over" in on["timerClass"] and "rvp-nopulse" not in on["timerClass"]
    assert "rvp-pulsing" not in off["alertClass"]
    assert off["alertShown"] is True  # still shown, just not animated
    assert "rvp-nopulse" in off["timerClass"]


def test_bottom_middle_symbol_sits_at_the_bottom():
    r = run_timer(
        {"show_timer": False, "alert_style": "exclamation",
         "alert_position": "bottom", "alert_text": "!"},
        [9999, 10000],
    )
    assert r[0]["alertShown"] is False
    assert r[1]["alertShown"] is True


def test_every_alert_position_is_pinned_correctly():
    """Each position must clear the anchors it is not using.

    Setting only ``top`` while a previous card left ``bottom`` set would stretch
    the symbol across the whole screen.
    """
    import re

    for position, expected in (
        ("bottom", {"bottom": "6vh", "top": "auto", "height": "auto"}),
        ("top", {"top": "6vh", "bottom": "auto", "height": "auto"}),
        ("lower-half", {"top": "50%", "height": "50%", "bottom": "auto"}),
        ("upper-half", {"top": "0", "height": "50%", "bottom": "auto"}),
        ("center", {"top": "0", "height": "100%", "bottom": "auto"}),
    ):
        cfg = C.normalise({"goal": {"enabled": True, "alert_style": "exclamation",
                                    "alert_position": position}})
        payload = RV.build_payload(None, cfg, LiveSession(), 10.0, False)
        script = (
            HARNESS.replace("SCRIPT_PLACEHOLDER", RV.script(payload))
            .replace("OFFSETS_PLACEHOLDER", "[11000]")
            .replace(
                'console.log(JSON.stringify(readings));',
                'console.log(JSON.stringify(registry["rvp-alert"].style));',
            )
        )
        out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
        style = json.loads(out.stdout)
        for prop, value in expected.items():
            assert style.get(prop) == value, (position, prop, style)


def test_warning_can_be_suppressed_for_this_side_of_the_card():
    """``alert_enabled`` off means the clock runs but nothing fires."""
    cfg = C.normalise({"goal": {"enabled": True, "alert_style": "both"}})
    payload = RV.build_payload(None, cfg, LiveSession(), 10.0, False, alert_enabled=False)
    script = (
        HARNESS.replace("SCRIPT_PLACEHOLDER", RV.script(payload))
        .replace("OFFSETS_PLACEHOLDER", json.dumps([5000, 15000]))
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    readings = json.loads(out.stdout)
    assert timers(readings) == ["5", "+5"]      # the clock still runs and reads over
    assert readings[1]["timerClass"] == ""       # but it never turns red
    assert readings[1]["alertShown"] is False    # and no symbol appears


def test_warning_fires_when_enabled_for_this_side():
    cfg = C.normalise({"goal": {"enabled": True, "alert_style": "both"}})
    payload = RV.build_payload(None, cfg, LiveSession(), 10.0, False, alert_enabled=True)
    script = (
        HARNESS.replace("SCRIPT_PLACEHOLDER", RV.script(payload))
        .replace("OFFSETS_PLACEHOLDER", json.dumps([15000]))
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    readings = json.loads(out.stdout)
    assert "rvp-over" in readings[0]["timerClass"]
    assert readings[0]["alertShown"] is True
