"""In-review heads-up display and the per-card time goal badge.

Both are injected into the reviewer's webview as a small self-contained
widget.  Nothing here touches your note types or card templates, so the goal
badge works on every card in every deck without editing a single template.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .. import consts as K
from ..collector import Snapshot
from ..session import LiveSession, remaining_estimate

_STYLE = """
#rvp-hud, #rvp-goal, #rvp-alert {
  position: fixed; z-index: 2147483000; pointer-events: none;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-variant-numeric: tabular-nums; user-select: none;
}
#rvp-hud {
  display: flex; flex-direction: column; gap: 3px;
  padding: 8px 11px; border-radius: 9px; line-height: 1.25;
  background: var(--canvas-elevated, rgba(128,128,128,.16));
  border: 1px solid var(--border-subtle, rgba(128,128,128,.30));
  color: var(--fg, inherit);
  box-shadow: 0 2px 8px rgba(0,0,0,.14);
  backdrop-filter: blur(6px);
  min-width: 108px;
}
#rvp-hud .rvp-row { display: flex; justify-content: space-between; gap: 10px; }
#rvp-hud .rvp-k { opacity: .62; font-size: .78em; }
#rvp-hud .rvp-v { font-weight: 600; }
#rvp-hud .rvp-bar {
  height: 3px; border-radius: 2px; margin-top: 4px; overflow: hidden;
  background: var(--canvas-inset, rgba(128,128,128,.25));
}
#rvp-hud .rvp-bar > i {
  display: block; height: 100%; border-radius: 2px;
  background: var(--accent-card, #3a7bd5); transition: width .25s ease;
}
#rvp-goal {
  display: flex; align-items: center; justify-content: center;
  min-width: 2.6em; padding: 4px 9px; border-radius: 999px;
  font-weight: 700; letter-spacing: .02em;
  background: var(--canvas-elevated, rgba(128,128,128,.16));
  border: 1px solid var(--border-subtle, rgba(128,128,128,.30));
  color: var(--fg, inherit);
  transition: background-color .2s ease, color .2s ease, border-color .2s ease;
}
#rvp-goal.rvp-over {
  color: #fff; background: #d9484d; border-color: #d9484d;
  animation: rvp-pulse 1s ease-in-out infinite;
}
#rvp-goal.rvp-nopulse { animation: none; }
#rvp-alert {
  left: 0; right: 0; display: none;
  align-items: center; justify-content: center;
  color: #d9484d; font-weight: 800; line-height: 1;
  text-shadow: 0 2px 14px rgba(0,0,0,.28);
  opacity: 0; transition: opacity .18s ease;
}
#rvp-alert.rvp-show { display: flex; opacity: .92; }
#rvp-alert.rvp-pulsing { animation: rvp-pulse 1s ease-in-out infinite; }
@keyframes rvp-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50%      { transform: scale(1.09); opacity: .82; }
}
"""

_JS = r"""
(function () {
  var S = %(payload)s;
  function place(el, pos, inset) {
    el.style.top = el.style.bottom = el.style.left = el.style.right = "auto";
    var v = pos.indexOf("top") === 0 ? "top" : "bottom";
    var h = pos.indexOf("right") >= 0 ? "right" : "left";
    el.style[v] = inset + "px";
    el.style[h] = inset + "px";
  }
  function ensure(id) {
    var el = document.getElementById(id);
    if (!el) {
      el = document.createElement("div");
      el.id = id;
      document.body.appendChild(el);
    }
    return el;
  }
  if (!document.getElementById("rvp-style")) {
    var st = document.createElement("style");
    st.id = "rvp-style";
    st.textContent = %(style)s;
    document.head.appendChild(st);
  }

  var hud = document.getElementById("rvp-hud");
  if (S.hud) {
    hud = ensure("rvp-hud");
    hud.innerHTML = S.hud.html;
    hud.style.opacity = S.hud.opacity;
    hud.style.fontSize = S.hud.scale + "em";
    place(hud, S.hud.position, 14);
    hud.style.display = "";
  } else if (hud) {
    hud.style.display = "none";
  }

  if (window.__rvpTimer) { clearInterval(window.__rvpTimer); window.__rvpTimer = null; }
  var badge = document.getElementById("rvp-goal");
  var alert = document.getElementById("rvp-alert");
  if (!S.goal) {
    if (badge) badge.style.display = "none";
    if (alert) alert.className = "";
    return;
  }
  var G = S.goal;

  if (G.show_timer) {
    badge = ensure("rvp-goal");
    badge.style.display = "";
    badge.style.fontSize = G.scale + "em";
    place(badge, G.position, 14);
  } else if (badge) {
    badge.style.display = "none";
  }

  // The warning can be limited to one side of the card, so a timer may run
  // with no warning attached to it in this phase.
  var allowAlert = G.alert_enabled;
  var wantAlert = allowAlert &&
    (G.alert_style === "exclamation" || G.alert_style === "both");
  if (wantAlert) {
    alert = ensure("rvp-alert");
    alert.textContent = G.alert_text;
    alert.className = "";
    alert.style.fontSize = (22 * G.alert_scale) + "vh";
    alert.style.top = "auto"; alert.style.bottom = "auto"; alert.style.height = "auto";
    var p = G.alert_position;
    if (p === "center") {
      alert.style.top = "0"; alert.style.height = "100%%";
    } else if (p === "upper-half") {
      alert.style.top = "0"; alert.style.height = "50%%";
    } else if (p === "lower-half") {
      alert.style.top = "50%%"; alert.style.height = "50%%";
    } else if (p === "top") {
      alert.style.top = "6vh";
    } else {
      alert.style.bottom = "6vh";
    }
  } else if (alert) {
    alert.className = "";
  }

  // The clock starts when the card appeared, not when this script ran. The
  // stamp is injected before any database work, so a slow snapshot rebuild
  // cannot eat into the card's time. Re-injecting mid-card (toggling the HUD,
  // for instance) reuses the same stamp instead of restarting the timer.
  var start = (typeof window.__rvpCardStart === "number" && window.__rvpCardStart)
    ? window.__rvpCardStart : Date.now();
  var target = G.seconds * 1000;
  var fired = false;
  function beep() {
    try {
      var ctx = new (window.AudioContext || window.webkitAudioContext)();
      var osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.frequency.value = 660; osc.type = "sine";
      gain.gain.setValueAtTime(0.0001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.12, ctx.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.30);
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start(); osc.stop(ctx.currentTime + 0.32);
    } catch (e) {}
  }
  // A countdown rounds up and a count-up rounds down. With 11.8s left a
  // countdown still reads 12 and only reaches 0 when the time is genuinely
  // gone; rounding the other way makes it drop a second immediately and look
  // like it is running fast.
  function fmt(ms, countingUp) {
    var neg = ms < 0;
    var abs = Math.abs(ms) / 1000;
    var s = countingUp ? Math.floor(abs) : Math.ceil(abs);
    var m = Math.floor(s / 60);
    s = s %% 60;
    var txt = m > 0 ? m + ":" + (s < 10 ? "0" : "") + s : String(s);
    return (neg ? "+" : "") + txt;
  }
  function tick() {
    var elapsed = Date.now() - start;
    var over = elapsed >= target;
    if (G.show_timer && badge) {
      badge.textContent = G.count_down
        ? fmt(target - elapsed, false)
        : fmt(elapsed, true);
      var recolour = over && allowAlert &&
        (G.alert_style === "badge" || G.alert_style === "both");
      badge.className = recolour ? (G.pulse ? "rvp-over" : "rvp-over rvp-nopulse") : "";
    }
    if (wantAlert && alert) {
      alert.className = over ? (G.pulse ? "rvp-show rvp-pulsing" : "rvp-show") : "";
    }
    if (over && allowAlert && !fired) { fired = true; if (G.sound) beep(); }
  }
  tick();
  window.__rvpTimer = setInterval(tick, 100);
})();
"""


def _row(key: str, value: str) -> str:
    return '<div class="rvp-row"><span class="rvp-k">%s</span>' '<span class="rvp-v">%s</span></div>' % (
        key,
        value,
    )


def build_hud_html(snap: Snapshot, cfg, session: LiveSession) -> str:
    ov = cfg["overlay"]
    mode = cfg["speed"]["mode"]
    rows = []

    est = remaining_estimate(snap, cfg, session)
    remaining_cards = snap.total_cards
    if ov["show_remaining"]:
        rows.append(_row("left", str(remaining_cards)))
    if ov["show_eta"]:
        rows.append(_row("eta", K.fmt_duration(est.seconds)))
        if cfg["display"]["show_finish_time"]:
            import time as _t

            rows.append(
                _row("by", K.fmt_clock(_t.time() + est.seconds, cfg["display"]["clock_24h"]))
            )
    if ov["show_session_speed"] and session.answers:
        rows.append(_row("pace", K.fmt_secs_per_card(session.per_card_for(mode))))
    if ov["show_elapsed"] and session.answers:
        rows.append(_row("spent", K.fmt_duration(session.active_seconds)))

    if ov["show_progress_bar"]:
        done = session.answers
        total = done + max(0, int(est.total_reps))
        pct = (done / total * 100.0) if total else 0.0
        rows.append('<div class="rvp-bar"><i style="width:%.1f%%"></i></div>' % pct)

    return "".join(rows)


def build_payload(snap: Optional[Snapshot], cfg, session: LiveSession,
                  goal_seconds: Optional[float], hud_visible: bool,
                  alert_enabled: bool = True) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"hud": None, "goal": None}

    if cfg["overlay"]["enabled"] and hud_visible and snap is not None:
        html = build_hud_html(snap, cfg, session)
        if html:
            payload["hud"] = {
                "html": html,
                "opacity": float(cfg["overlay"]["opacity"]),
                "scale": float(cfg["overlay"]["scale"]),
                "position": cfg["overlay"]["position"],
            }

    goal = cfg["goal"]
    if goal["enabled"] and goal_seconds:
        payload["goal"] = {
            "seconds": float(goal_seconds),
            "show_timer": bool(goal["show_timer"]),
            "count_down": bool(goal["count_down"]),
            "position": goal["badge_position"],
            "scale": float(goal["scale"]),
            "alert_enabled": bool(alert_enabled),
            "alert_style": goal["alert_style"],
            "alert_position": goal["alert_position"],
            "alert_text": str(goal["alert_text"]),
            "alert_scale": float(goal["alert_scale"]),
            "pulse": bool(goal["pulse_when_over"]),
            "sound": bool(goal["sound"]),
        }
    return payload


def script(payload: Dict[str, Any]) -> str:
    return _JS % {"payload": json.dumps(payload), "style": json.dumps(_STYLE)}


def clear_script() -> str:
    return script({"hud": None, "goal": None}) + "\nwindow.__rvpCardStart = null;"


def stamp_script() -> str:
    """Record when the card became visible.

    Injected before the add-on does any database work, so the per-card timer
    measures the card rather than the add-on.
    """
    return "window.__rvpCardStart = Date.now();"
