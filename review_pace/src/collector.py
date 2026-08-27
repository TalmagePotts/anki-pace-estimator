"""Bridge between the Anki collection and the pure logic in :mod:`stats`.

Everything that touches ``mw.col`` lives here.  The result of a gather is a
:class:`Snapshot` -- a plain, immutable-ish object the UI layers can render
without doing any further database work.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from . import stats as S

DAY = 86400


@dataclass
class DeckLine:
    """Per-deck row used by the breakdown table."""

    deck_id: int
    name: str
    new: int = 0
    learning: int = 0
    review: int = 0
    seconds: float = 0.0


@dataclass
class Snapshot:
    ok: bool = True
    reason: str = ""
    deck_ids: List[int] = field(default_factory=list)
    deck_names: List[str] = field(default_factory=list)
    speeds: S.Speeds = field(default_factory=S.Speeds)
    behaviour: S.Behaviour = field(default_factory=S.Behaviour)
    workload: S.Workload = field(default_factory=S.Workload)
    estimate: S.Estimate = field(default_factory=S.Estimate)
    today: S.DoneTotals = field(default_factory=S.DoneTotals)
    week: S.DoneTotals = field(default_factory=S.DoneTotals)
    month: S.DoneTotals = field(default_factory=S.DoneTotals)
    per_deck: List[DeckLine] = field(default_factory=list)
    sample_size: int = 0
    lookback_days: int = 30
    day_cutoff: int = 0
    generated_at: float = 0.0

    @property
    def has_speed_data(self) -> bool:
        return self.sample_size > 0

    @property
    def total_cards(self) -> int:
        return self.workload.new_cards + self.workload.review_cards + self.workload.learning_reps

    @property
    def finish_epoch(self) -> float:
        return time.time() + self.estimate.seconds

    @property
    def finish_epoch_slow(self) -> float:
        return time.time() + self.estimate.seconds_slow

    def deck_label(self, limit: int = 3) -> str:
        if not self.deck_names:
            return "All decks"
        if len(self.deck_names) <= limit:
            return ", ".join(self.deck_names)
        return "%s +%d more" % (", ".join(self.deck_names[:limit]), len(self.deck_names) - limit)


# ---------------------------------------------------------------------------
# Deck resolution
# ---------------------------------------------------------------------------


def all_deck_rows(col) -> List[Tuple[int, str]]:
    """``[(deck_id, name), ...]`` sorted by name, filtered decks excluded."""
    rows = []
    for entry in col.decks.all_names_and_ids(skip_empty_default=False, include_filtered=False):
        rows.append((int(entry.id), entry.name))
    rows.sort(key=lambda r: r[1].lower())
    return rows


def resolve_deck_ids(col, cfg) -> Tuple[List[int], Set[int], List[str]]:
    """Return ``(selected_ids, expanded_ids, names)``.

    ``selected_ids`` is what the user picked (existing decks only);
    ``expanded_ids`` additionally contains subdecks when that option is on and
    is what card/revlog filtering uses.  An empty selection means "everything",
    which is signalled by an empty ``expanded_ids``.
    """
    wanted = [int(d) for d in cfg["decks"]["ids"]]
    selected: List[int] = []
    names: List[str] = []
    for did in wanted:
        name = col.decks.name_if_exists(did)
        if name:
            selected.append(did)
            names.append(name)
    if not selected:
        return [], set(), []

    expanded: Set[int] = set(selected)
    if cfg["decks"]["include_subdecks"]:
        for did in selected:
            try:
                expanded.update(int(x) for x in col.decks.deck_and_child_ids(did))
            except Exception:
                pass
    return selected, expanded, names


def _sql_id_list(ids: Sequence[int]) -> str:
    return "(%s)" % ",".join(str(int(i)) for i in ids)


# ---------------------------------------------------------------------------
# Workload
# ---------------------------------------------------------------------------


def _node_counts(node) -> Tuple[int, int, int]:
    return int(node.new_count), int(node.learn_count), int(node.review_count)


def _walk_workload(node, selected: Set[int], include_subdecks: bool, out: List[DeckLine]) -> None:
    """Collect counts for the top-most selected decks, never double counting.

    In the v3 scheduler a parent's counts already include (and cap) its
    children, so once a deck is taken its subtree must not be walked again.
    """
    did = int(node.deck_id)
    if did in selected:
        new, learn, review = _node_counts(node)
        if not include_subdecks:
            for child in node.children:
                cn, cl, cr = _node_counts(child)
                new, learn, review = new - cn, learn - cl, review - cr
        out.append(
            DeckLine(
                deck_id=did,
                name=node.name,
                new=max(0, new),
                learning=max(0, learn),
                review=max(0, review),
            )
        )
        if include_subdecks:
            return
    for child in node.children:
        _walk_workload(child, selected, include_subdecks, out)


def gather_workload(col, cfg, selected: Sequence[int]) -> Tuple[S.Workload, List[DeckLine]]:
    tree = col.sched.deck_due_tree()
    lines: List[DeckLine] = []
    if selected:
        _walk_workload(tree, set(selected), cfg["decks"]["include_subdecks"], lines)
    else:
        for child in tree.children:
            new, learn, review = _node_counts(child)
            lines.append(
                DeckLine(child.deck_id, child.name, max(0, new), max(0, learn), max(0, review))
            )

    work = S.Workload(
        new_cards=sum(l.new for l in lines),
        review_cards=sum(l.review for l in lines),
        learning_reps=sum(l.learning for l in lines),
    )
    if cfg["speed"]["count_full_learning"]:
        # ``learn_count`` counts cards, but a card halfway through its steps
        # still owes more than one answer. ``cards.left % 1000`` is exactly the
        # number of answers Anki still expects from it.
        work.learning_reps = _remaining_learning_reps(col, cfg, work.learning_reps)

    extra_new, extra_review, extra_reps = filtered_workload(
        col, set(cfg.get("_expanded_ids") or [])
    )
    if extra_new or extra_review or extra_reps:
        work.new_cards += extra_new
        work.review_cards += extra_review
        work.learning_reps += extra_reps
        lines.append(
            DeckLine(0, "Custom study", extra_new, extra_reps, extra_review)
        )
    return work, lines


# Anki queue numbers.
QUEUE_NEW = 0
QUEUE_LEARN = 1
QUEUE_REVIEW = 2
QUEUE_DAY_LEARN = 3
QUEUE_PREVIEW = 4


def classify_filtered(rows, today: int, now_secs: int) -> Tuple[int, int, int]:
    """Turn rows of ``(queue, due, left)`` into ``(new, review, learning_reps)``.

    Cards pulled into a filtered deck by Custom Study still belong to their
    home deck, but Anki's deck tree files them under the filtered deck, so a
    selection would stop counting them mid-session. They are counted here
    instead. ``due`` is an epoch timestamp for intraday queues and a day number
    for the rest, which is why the two are compared against different clocks.
    """
    new = review = reps = 0
    for queue, due, left in rows:
        queue = int(queue)
        due = int(due or 0)
        if queue == QUEUE_NEW:
            new += 1
        elif queue in (QUEUE_LEARN, QUEUE_PREVIEW):
            if due <= now_secs:
                reps += _steps_left(left) if queue == QUEUE_LEARN else 1
        elif queue == QUEUE_DAY_LEARN:
            if due <= today:
                reps += _steps_left(left)
        elif queue == QUEUE_REVIEW:
            if due <= today:
                review += 1
    return new, review, reps


def _steps_left(left) -> int:
    steps = int(left or 0) % 1000
    return steps if steps > 0 else 1


def filtered_workload(col, expanded: Set[int]) -> Tuple[int, int, int]:
    """Counts for cards of the selected decks that are sitting in a filtered deck."""
    if not expanded:
        return 0, 0, 0
    try:
        rows = col.db.all(
            "select queue, due, left from cards where odid != 0 and odid in %s"
            % _sql_id_list(sorted(expanded))
        )
    except Exception:
        return 0, 0, 0
    if not rows:
        return 0, 0, 0
    return classify_filtered(rows, int(col.sched.today), int(time.time()))


def _remaining_learning_reps(col, cfg, fallback: int) -> int:
    ids = cfg.get("_expanded_ids") or []
    where = "queue in (1, 3)"
    if ids:
        where += " and (case when odid != 0 then odid else did end) in %s" % _sql_id_list(ids)
    try:
        rows = col.db.list("select left from cards where " + where)
    except Exception:
        return fallback
    if not rows:
        return 0
    total = 0
    for left in rows:
        steps = int(left or 0) % 1000
        total += steps if steps > 0 else 1
    return total


# ---------------------------------------------------------------------------
# Review history
# ---------------------------------------------------------------------------


_REVIEW_SQL = """
    select r.id, r.cid, case when c.odid != 0 then c.odid else c.did end,
           r.ease, r.ivl, r.lastIvl, r.time, r.type, r.factor
    from revlog r join cards c on c.id = r.cid
    where r.id >= ?
    order by r.id desc
    limit ?
"""


def fetch_reviews(col, cfg, expanded: Set[int]) -> Tuple[List[S.Review], Dict[int, int], int]:
    """Load the review window.

    Rows are fetched for *every* deck and filtered afterwards: the wall-clock
    gap between two answers is real time spent even when the two cards live in
    different decks, so the gaps have to be measured on the full stream.

    If the configured window holds too few reviews *for the decks being
    reported on* -- a deck you study once a week, or a collection you have just
    started -- the window is widened rather than an estimate being built from
    noise.
    """
    days = int(cfg["speed"]["lookback_days"])
    limit = int(cfg["speed"]["max_rows"])
    min_sample = int(cfg["speed"].get("min_sample", 0))
    cutoff_ms = int((col.sched.day_cutoff - days * DAY) * 1000)

    rows = col.db.all(_REVIEW_SQL, cutoff_ms, limit)
    if min_sample and _scoped_count(rows, expanded) < min_sample:
        widened = col.db.all(_REVIEW_SQL, 0, min(limit, max(min_sample * 4, 2000)))
        if len(widened) > len(rows):
            rows = widened

    reviews = [S.Review(*row) for row in rows]
    # Rows come back newest first, so the last one marks how far back we
    # actually reached -- which is what "first seen in this window" must use.
    effective_cutoff = int(rows[-1][0]) if rows else cutoff_ms

    first_rows = col.db.all(
        "select cid, min(id) from revlog where type not in (4, 5) "
        "group by cid having min(id) >= ?",
        effective_cutoff,
    )
    first_seen = {int(cid): int(first) for cid, first in first_rows}
    return reviews, first_seen, effective_cutoff


def _scoped_count(rows, expanded: Set[int]) -> int:
    if not expanded:
        return len(rows)
    return sum(1 for row in rows if row[2] in expanded)


def period_start_ms(col, cfg, days: int) -> int:
    """Epoch-ms start of a period, honouring Anki's rollover hour."""
    if cfg["display"]["period_mode"] == "calendar" and days > 1:
        lt = time.localtime(col.sched.day_cutoff - DAY // 2)
        if days <= 7:
            back = lt.tm_wday  # Monday-based week
        else:
            back = lt.tm_mday - 1
        return int((col.sched.day_cutoff - back * DAY - DAY) * 1000) + DAY * 1000
    return int((col.sched.day_cutoff - days * DAY) * 1000)


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def build_snapshot(col, cfg, override_decks: Optional[Sequence[int]] = None) -> Snapshot:
    if col is None:
        return Snapshot(ok=False, reason="No collection open.")

    if override_decks:
        selected = [int(d) for d in override_decks]
        names = [col.decks.name_if_exists(d) or "" for d in selected]
        names = [n for n in names if n]
        expanded: Set[int] = set(selected)
        if cfg["decks"]["include_subdecks"]:
            for did in selected:
                try:
                    expanded.update(int(x) for x in col.decks.deck_and_child_ids(did))
                except Exception:
                    pass
    else:
        selected, expanded, names = resolve_deck_ids(col, cfg)

    scoped_cfg = dict(cfg)
    scoped_cfg["_expanded_ids"] = sorted(expanded)

    snap = Snapshot(
        deck_ids=list(selected),
        deck_names=names,
        lookback_days=int(cfg["speed"]["lookback_days"]),
        day_cutoff=int(col.sched.day_cutoff),
        generated_at=time.time(),
    )

    reviews, first_seen, effective_cutoff = fetch_reviews(col, scoped_cfg, expanded)
    reached_days = max(
        1,
        int(round((col.sched.day_cutoff - effective_cutoff / 1000.0) / DAY)),
    )
    snap.lookback_days = reached_days
    timed_all = S.annotate(
        reviews,
        idle_cutoff_s=float(cfg["speed"]["idle_cutoff_s"]),
        max_answer_s=float(cfg["speed"]["max_answer_s"]),
    )
    timed = [t for t in timed_all if not expanded or t.review.did in expanded]
    snap.sample_size = len(timed)

    features = tuple(cfg["speed"]["features"])
    snap.speeds = S.compute_speeds(
        timed,
        cfg["speed"]["estimator"],
        features,
        hour_shrinkage=(
            float(cfg["speed"]["time_of_day_shrinkage"])
            if cfg["speed"]["time_of_day"]
            else None
        ),
        hour_min_days=int(cfg["speed"]["time_of_day_min_days"]),
    )
    if not cfg["speed"]["per_card_class"]:
        # Collapse to a single figure by making every class defer to the
        # overall average.
        snap.speeds.per_class = {}

    fresh_ids = {cid for cid in first_seen}
    snap.behaviour = S.measure_behaviour(timed, new_card_ids=fresh_ids)

    snap.workload, snap.per_deck = gather_workload(col, scoped_cfg, selected)
    snap.workload.review_buckets = review_buckets(col, expanded, snap.workload, features)
    snap.estimate = S.estimate(
        snap.workload,
        snap.speeds,
        snap.behaviour,
        mode=cfg["speed"]["mode"],
        count_full_learning=cfg["speed"]["count_full_learning"],
        include_lapses=cfg["speed"]["include_lapses"],
        start_epoch=time.time(),
    )

    mode = cfg["speed"]["mode"]
    snap.today = S.totals_since(timed, period_start_ms(col, cfg, 1), first_seen, mode)
    snap.week = S.totals_since(timed, period_start_ms(col, cfg, 7), first_seen, mode)
    snap.month = S.totals_since(timed, period_start_ms(col, cfg, 30), first_seen, mode)

    _fill_per_deck_estimates(snap, cfg)
    return snap


def review_buckets(col, expanded: Set[int], workload: S.Workload,
                   features: Sequence[str]) -> Dict[tuple, float]:
    """Split today's due reviews across feature buckets.

    Anki's scheduler reports how many reviews are due after limits, but not
    which cards they are. The bucket *proportions* are read from the pool of
    cards that are due, then applied to that count -- which is right as long as
    the limit does not systematically prefer one kind of card, and Anki's does
    not.
    """
    if not features or not workload.review_cards:
        return {}
    where = "queue = 2 and due <= ?"
    if expanded:
        where += " and (case when odid != 0 then odid else did end) in %s" % _sql_id_list(
            sorted(expanded)
        )
    try:
        rows = col.db.all("select factor, ivl from cards where " + where, col.sched.today)
    except Exception:
        return {}
    if not rows:
        return {}

    counts: Dict[tuple, int] = {}
    for factor, ivl in rows:
        ivl = int(ivl or 0)
        cls = S.MATURE if ivl >= S.MATURE_IVL else S.YOUNG
        key = S.bucket_key(cls, int(factor or 0), ivl, features)
        counts[key] = counts.get(key, 0) + 1
    total = float(sum(counts.values()))
    return {k: v / total * workload.review_cards for k, v in counts.items()}


def _fill_per_deck_estimates(snap: Snapshot, cfg) -> None:
    total_reviews = float(sum(l.review for l in snap.per_deck)) or 1.0
    for line in snap.per_deck:
        share = line.review / total_reviews
        buckets = {k: v * share for k, v in snap.workload.review_buckets.items()}
        est = S.estimate(
            S.Workload(
                new_cards=line.new,
                review_cards=line.review,
                learning_reps=line.learning,
                review_buckets=buckets,
            ),
            snap.speeds,
            snap.behaviour,
            mode=cfg["speed"]["mode"],
            count_full_learning=cfg["speed"]["count_full_learning"],
            include_lapses=cfg["speed"]["include_lapses"],
            start_epoch=time.time(),
        )
        line.seconds = est.seconds
    snap.per_deck.sort(key=lambda l: l.seconds, reverse=True)


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


class SnapshotCache:
    """Keeps the deck browser snappy.

    A rebuild scans up to tens of thousands of revlog rows, which is fast but
    not free, and the deck browser re-renders on every return to the home
    screen.  The cache is dropped whenever the collection is modified.
    """

    def __init__(self) -> None:
        self._snap: Optional[Snapshot] = None
        self._key: Any = None

    def invalidate(self) -> None:
        self._snap = None
        self._key = None

    def get(self, col, cfg, override_decks=None, max_age: float = 30.0) -> Snapshot:
        key = (
            col.mod if col else 0,
            tuple(sorted(override_decks or ())),
            repr(sorted((k, repr(v)) for k, v in cfg.items() if not k.startswith("_"))),
        )
        now = time.time()
        if (
            self._snap is not None
            and self._key == key
            and (now - self._snap.generated_at) < max_age
        ):
            return self._snap
        self._snap = build_snapshot(col, cfg, override_decks)
        self._key = key
        return self._snap


CACHE = SnapshotCache()


def refresh_workload(snap: Snapshot, col, cfg) -> Snapshot:
    """Re-read the due counts on an existing snapshot.

    Reading the deck tree is cheap; rescanning tens of thousands of revlog rows
    is not.  During review the counts change with every answer while the speed
    figures barely move, so the reviewer refreshes only this half.
    """
    if col is None:
        return snap
    scoped_cfg = dict(cfg)
    scoped_cfg["_expanded_ids"] = _expand(col, cfg, snap.deck_ids)
    snap.workload, snap.per_deck = gather_workload(col, scoped_cfg, snap.deck_ids)
    snap.estimate = S.estimate(
        snap.workload,
        snap.speeds,
        snap.behaviour,
        mode=cfg["speed"]["mode"],
        count_full_learning=cfg["speed"]["count_full_learning"],
        include_lapses=cfg["speed"]["include_lapses"],
        start_epoch=time.time(),
    )
    _fill_per_deck_estimates(snap, cfg)
    return snap


def _expand(col, cfg, selected: Sequence[int]) -> List[int]:
    if not selected:
        return []
    out: Set[int] = set(int(d) for d in selected)
    if cfg["decks"]["include_subdecks"]:
        for did in selected:
            try:
                out.update(int(x) for x in col.decks.deck_and_child_ids(did))
            except Exception:
                pass
    return sorted(out)
