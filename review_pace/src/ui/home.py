"""The home-screen panel, shared by the deck browser and the deck overview."""

from __future__ import annotations

from typing import List, Tuple

from .. import consts as K
from ..collector import Snapshot
from . import theme as T


def _eta_component(snap: Snapshot, cfg) -> Tuple[List[str], List[str]]:
    if not snap.total_cards:
        return [T.tile("All done", "Time left", "nothing waiting", "review")], []
    if not snap.has_speed_data:
        return [T.tile("--", "Time left", "no review history yet", "accent")], []

    est = snap.estimate
    subs = []
    if cfg["display"]["show_eta_range"] and est.seconds_slow > est.seconds * 1.02:
        subs.append("up to %s" % K.fmt_duration(est.seconds_slow))
    if cfg["display"]["show_finish_time"]:
        subs.append("by %s" % K.fmt_clock(snap.finish_epoch, cfg["display"]["clock_24h"]))
    return [T.tile(K.fmt_duration(est.seconds), "Time left", " · ".join(subs), "accent")], []


def _workload_component(snap: Snapshot, cfg) -> Tuple[List[str], List[str]]:
    w = snap.workload
    tiles = [
        T.tile(str(w.review_cards), "Due", "", "review"),
        T.tile(str(w.new_cards), "New", "", "new"),
    ]
    if w.learning_reps:
        sub = "answers left" if cfg["speed"]["count_full_learning"] else ""
        tiles.append(T.tile(str(w.learning_reps), "Learning", sub, "learn"))
    return tiles, []


def _speed_component(snap: Snapshot, cfg) -> Tuple[List[str], List[str]]:
    if not snap.has_speed_data:
        return [], []
    overall = snap.speeds.overall
    wall_mode = cfg["speed"]["mode"] == K.SPEED_MODE_WALL
    average = overall.wall if wall_mode else overall.answer
    typical = overall.wall_typical if wall_mode else overall.answer_typical
    other = overall.answer if wall_mode else overall.wall
    kind = "Wall-clock" if wall_mode else "Answer"

    display = cfg["display"]["speed_display"]
    if display == "typical":
        # The middle card, which is what a session *feels* like -- deliberately
        # not the figure the estimate is built from.
        return [
            T.tile("%.1f" % typical, "%s, typical card" % kind,
                   "average %.1fs" % average, "accent", unit="s/card")
        ], []
    if display == "both":
        return [
            T.tile("%.1f" % average, "%s speed" % kind,
                   "typical card %.1fs" % typical, "accent", unit="s/card")
        ], []
    sub = "%s %.1fs" % ("answer only" if wall_mode else "with gaps", other)
    return [T.tile("%.1f" % average, "%s speed" % kind, sub, "accent", unit="s/card")], []


def _learned_component(snap: Snapshot, cfg) -> Tuple[List[str], List[str]]:
    if cfg["display"]["period_mode"] == "calendar":
        sub = "%d this week · %d this month" % (snap.week.introduced, snap.month.introduced)
    else:
        sub = "%d in 7d · %d in 30d" % (snap.week.introduced, snap.month.introduced)
    return [T.tile(str(snap.today.introduced), "New learned today", sub, "new")], []


def _done_component(snap: Snapshot, cfg) -> Tuple[List[str], List[str]]:
    t = snap.today
    if not t.reviews:
        return [T.tile("0", "Answered today", "nothing yet", "review")], []
    sub = "%s · %.1fs each" % (K.fmt_duration(t.seconds), t.seconds / t.reviews)
    return [T.tile(str(t.reviews), "Answered today", sub, "review")], []


def _session_component(snap: Snapshot, cfg) -> Tuple[List[str], List[str]]:
    """What you just did, shown while it is still the thing on your mind."""
    from ..session import LAST_SESSION

    minutes = int(cfg["display"]["session_summary_minutes"])
    if not minutes or not LAST_SESSION.is_fresh(minutes * 60):
        return [], []

    last = LAST_SESSION
    bits = [K.fmt_duration(last.seconds)]
    if last.per_card:
        bits.append("%.1fs each" % last.per_card)
    if last.introduced:
        bits.append("%d new" % last.introduced)
    tiles = [T.tile(str(last.answers), "Just finished", " · ".join(bits), "review")]

    chips = []
    if last.has_comparison:
        pct = last.pct_vs_usual
        if abs(pct) < 5:
            chips.append(T.chip("This session", "right on your usual pace"))
        else:
            faster = pct < 0
            chips.append(
                T.chip(
                    "This session",
                    "%.0f%% %s than usual" % (abs(pct), "faster" if faster else "slower"),
                )
            )
    return tiles, chips


def _breakdown_component(snap: Snapshot, cfg) -> Tuple[List[str], List[str]]:
    if not snap.has_speed_data:
        return [], []
    mode = cfg["speed"]["mode"]
    chips = []
    from ..stats import CLASS_LABELS, CLASSES

    for cls in CLASSES:
        cs = snap.speeds.per_class.get(cls)
        if not cs or not cs.n:
            continue
        chips.append(T.chip(CLASS_LABELS[cls], "%.1fs" % cs.pick(mode)))
    if snap.behaviour.reps_per_new > 1.05:
        chips.append(T.chip("Answers per new card", "%.1f" % snap.behaviour.reps_per_new))
    if snap.behaviour.lapse_rate:
        chips.append(T.chip("Again rate", "%.0f%%" % (snap.behaviour.lapse_rate * 100)))
    return [], chips


BUILDERS = {
    K.COMP_SESSION: _session_component,
    K.COMP_ETA: _eta_component,
    K.COMP_WORKLOAD: _workload_component,
    K.COMP_SPEED: _speed_component,
    K.COMP_LEARNED: _learned_component,
    K.COMP_DONE: _done_component,
    K.COMP_BREAKDOWN: _breakdown_component,
}


def render(snap: Snapshot, cfg, show_buttons: bool = True) -> str:
    from ..config import enabled_components

    tiles: List[str] = []
    chips: List[str] = []
    for cid in enabled_components(cfg):
        builder = BUILDERS.get(cid)
        if not builder:
            continue
        try:
            t, c = builder(snap, cfg)
        except Exception:  # never let one component break the home screen
            continue
        tiles.extend(t)
        chips.extend(c)

    if not tiles and not chips:
        return ""

    footer_left = ""
    if snap.has_speed_data:
        footer_left = "%s reviews over %d days" % (
            "{:,}".format(snap.sample_size),
            snap.lookback_days,
        )
    else:
        footer_left = "No reviews in the last %d days" % snap.lookback_days

    footer_right = ""
    if show_buttons:
        footer_right = (
            '<a class="{p}-btn" href="#" title="Detailed stats" '
            "onclick=\"pycmd('rvp:stats');return false;\">📊</a> "
            '<a class="{p}-btn" href="#" title="Review Pace settings" '
            "onclick=\"pycmd('rvp:config');return false;\">⚙</a>"
        ).format(p=T.PREFIX)

    return T.panel(
        cfg,
        tiles,
        chips,
        footer_left=footer_left,
        footer_right=footer_right,
        deck_label=snap.deck_label(),
    )
