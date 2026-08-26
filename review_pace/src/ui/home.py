"""The home-screen panel, shared by the deck browser and the deck overview."""

from __future__ import annotations

from typing import List, Tuple

from .. import consts as K
from ..collector import Snapshot
from . import theme as T


def _eta_component(snap: Snapshot, cfg) -> Tuple[List[str], List[str]]:
    if not snap.total_cards:
        return [T.tile("All done", "Time remaining", "nothing waiting", "review")], []
    if not snap.has_speed_data:
        return [T.tile("--", "Time remaining", "no review history yet", "accent")], []

    est = snap.estimate
    value = K.fmt_duration(est.seconds)
    subs = []
    if cfg["display"]["show_eta_range"] and est.seconds_slow > est.seconds * 1.02:
        subs.append(
            "%s - %s"
            % (K.fmt_duration(est.seconds), K.fmt_duration(est.seconds_slow))
        )
    if cfg["display"]["show_finish_time"]:
        subs.append("done by %s" % K.fmt_clock(snap.finish_epoch, cfg["display"]["clock_24h"]))
    return [T.tile(value, "Time remaining", " · ".join(subs), "accent")], []


def _workload_component(snap: Snapshot, cfg) -> Tuple[List[str], List[str]]:
    w = snap.workload
    tiles = [
        T.tile(str(w.review_cards), "Due", "reviews", "review"),
        T.tile(str(w.new_cards), "New", "to introduce", "new"),
    ]
    if w.learning_reps:
        label = "answers left" if cfg["speed"]["count_full_learning"] else "cards"
        tiles.append(T.tile(str(w.learning_reps), "Learning", label, "learn"))
    return tiles, []


def _speed_component(snap: Snapshot, cfg) -> Tuple[List[str], List[str]]:
    if not snap.has_speed_data:
        return [], []
    overall = snap.speeds.overall
    primary_is_wall = cfg["speed"]["mode"] == K.SPEED_MODE_WALL
    primary = overall.wall if primary_is_wall else overall.answer
    other = overall.answer if primary_is_wall else overall.wall
    sub = "%s %s" % (
        K.fmt_secs_per_card(other),
        "answer only" if primary_is_wall else "incl. gaps",
    )
    label = "Wall-clock speed" if primary_is_wall else "Answer speed"
    return [T.tile(K.fmt_secs_per_card(primary) + "/card", label, sub, "accent")], []


def _learned_component(snap: Snapshot, cfg) -> Tuple[List[str], List[str]]:
    sub = "%d week · %d month" % (snap.week.introduced, snap.month.introduced)
    return [T.tile(str(snap.today.introduced), "New learned today", sub, "new")], []


def _done_component(snap: Snapshot, cfg) -> Tuple[List[str], List[str]]:
    t = snap.today
    sub = K.fmt_duration(t.seconds) if t.seconds else "nothing yet"
    if t.reviews:
        sub += " · %s/card" % K.fmt_secs_per_card(t.seconds / t.reviews)
    return [T.tile(str(t.reviews), "Answered today", sub, "review")], []


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
        chips.append(
            T.chip(
                CLASS_LABELS[cls],
                "%s  (%d)" % (K.fmt_secs_per_card(cs.pick(mode)), cs.n),
            )
        )
    if snap.behaviour.reps_per_new > 1.05:
        chips.append(T.chip("Answers per new card", "%.1f" % snap.behaviour.reps_per_new))
    if snap.behaviour.lapse_rate:
        chips.append(T.chip("Again rate", "%.0f%%" % (snap.behaviour.lapse_rate * 100)))
    return [], chips


BUILDERS = {
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
