"""Pure statistics core for Review Pace.

This module deliberately imports nothing from ``anki`` or ``aqt`` so that every
number the add-on displays can be unit-tested without launching Anki.  The
Anki-facing code lives in ``collector.py`` and is responsible for turning the
collection into the plain dataclasses defined here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Card classes
# ---------------------------------------------------------------------------

LEARN = "learn"
YOUNG = "young"
MATURE = "mature"
RELEARN = "relearn"

CLASSES = (LEARN, YOUNG, MATURE, RELEARN)

CLASS_LABELS = {
    LEARN: "Learning",
    YOUNG: "Young",
    MATURE: "Mature",
    RELEARN: "Relearning",
}

# revlog.type values
RT_LEARN = 0
RT_REVIEW = 1
RT_RELEARN = 2
RT_FILTERED = 3
RT_MANUAL = 4
RT_RESCHEDULED = 5

#: Interval (days) at which Anki considers a card "mature".
MATURE_IVL = 21


@dataclass(frozen=True)
class Review:
    """One row of ``revlog``, joined with its card's deck id."""

    id: int  # epoch milliseconds, taken when the answer button was pressed
    cid: int
    did: int
    ease: int
    ivl: int
    last_ivl: int
    time_ms: int
    type: int


@dataclass
class TimedReview:
    """A :class:`Review` annotated with its wall-clock cost."""

    review: Review
    answer_s: float
    wall_s: float
    #: True when this review opened a session (no usable predecessor gap).
    session_start: bool = False

    @property
    def overhead_s(self) -> float:
        return max(0.0, self.wall_s - self.answer_s)


def classify(review: Review) -> Optional[str]:
    """Return the speed class of a review, or ``None`` if it should be ignored.

    Manual reschedules carry ``time == 0`` and would drag every average down,
    so they are dropped rather than counted as instant answers.
    """
    if review.type in (RT_MANUAL, RT_RESCHEDULED):
        return None
    if review.type == RT_LEARN:
        return LEARN
    if review.type == RT_RELEARN:
        return RELEARN
    if review.type in (RT_REVIEW, RT_FILTERED):
        # Filtered/cram reviews are graded like reviews; bucket them by the
        # interval the card had *before* the answer, which is what the user
        # actually faced.
        ivl = review.last_ivl if review.last_ivl > 0 else review.ivl
        return MATURE if ivl >= MATURE_IVL else YOUNG
    return None


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolated percentile. ``pct`` is 0-100."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (pct / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return ordered[int(k)]
    return ordered[lo] * (hi - k) + ordered[hi] * (k - lo)


def trimmed_mean(values: Sequence[float], trim_pct: float = 10.0) -> float:
    """Mean after discarding ``trim_pct``% from each tail."""
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    cut = int(n * trim_pct / 100.0)
    if n - 2 * cut < 1:
        cut = 0
    kept = ordered[cut : n - cut] if cut else ordered
    return sum(kept) / len(kept)


def aggregate(values: Sequence[float], method: str) -> float:
    """The per-card figure an ETA should be built from.

    This is deliberately a mean, not a median.  The total time for a session is
    the *sum* of its cards, and the expected sum is ``n x mean``.  Card times
    are right-skewed -- most are quick, a few are slow -- so the median sits
    well below the mean, and multiplying it by the card count underestimates
    every session.  Outliers are already bounded by the answer-time cap and the
    idle cutoff, so the mean is safe to use here; ``trimmed`` is available for
    anyone who wants the slowest tail discarded as well.
    """
    if not values:
        return 0.0
    if method == "trimmed":
        return trimmed_mean(values)
    return sum(values) / len(values)


# ---------------------------------------------------------------------------
# Wall-clock annotation
# ---------------------------------------------------------------------------


def annotate(
    reviews: Iterable[Review],
    idle_cutoff_s: float = 60.0,
    max_answer_s: float = 60.0,
) -> List[TimedReview]:
    """Attach answer-time and wall-clock cost to each review.

    ``revlog.id`` is stamped when the answer button is pressed, so the elapsed
    time between two consecutive reviews covers the second card's *entire*
    cost: rendering, your pause before hitting space, reading, and grading.
    That is the "wall-clock" speed.

    Gaps longer than ``idle_cutoff_s`` mean you walked away, so the review is
    treated as the start of a fresh session and falls back to its answer time.

    The gap must be measured across the *whole* review stream, not just the
    decks being reported on -- if you interleave two decks, the time between a
    card in deck A and the next card in deck B is real time you spent.  Filter
    to the decks of interest only *after* calling this function.
    """
    ordered = sorted(reviews, key=lambda r: r.id)
    out: List[TimedReview] = []
    prev_id: Optional[int] = None
    for rev in ordered:
        answer_s = min(max(rev.time_ms, 0) / 1000.0, max_answer_s)
        if prev_id is None:
            wall_s, start = answer_s, True
        else:
            gap_s = (rev.id - prev_id) / 1000.0
            if gap_s <= 0 or gap_s > idle_cutoff_s:
                wall_s, start = answer_s, True
            else:
                # A gap can never be shorter than the answer itself; guard
                # against clock skew and against Anki's answer-time cap making
                # answer_s look longer than the true elapsed time.
                wall_s, start = max(gap_s, answer_s), False
        prev_id = rev.id
        out.append(TimedReview(rev, answer_s, wall_s, start))
    return out


# ---------------------------------------------------------------------------
# Speeds
# ---------------------------------------------------------------------------


@dataclass
class ClassSpeed:
    """Seconds per answer for one card class."""

    n: int = 0
    answer: float = 0.0
    wall: float = 0.0
    #: The middle card. Lower than the mean, because card times are
    #: right-skewed. Shown as "typical", never multiplied by a card count.
    answer_typical: float = 0.0
    wall_typical: float = 0.0
    #: 80th percentile of a *single* answer. Shown in the breakdown table; not
    #: used for the ETA -- see :func:`estimate` for why.
    answer_slow: float = 0.0
    wall_slow: float = 0.0
    #: Standard deviation of a single answer, which is what the ETA's error
    #: bound is propagated from.
    answer_sd: float = 0.0
    wall_sd: float = 0.0

    def pick(self, mode: str, slow: bool = False) -> float:
        if mode == "answer":
            return self.answer_slow if slow else self.answer
        return self.wall_slow if slow else self.wall

    def sd(self, mode: str) -> float:
        return self.answer_sd if mode == "answer" else self.wall_sd

    def typical(self, mode: str) -> float:
        return self.answer_typical if mode == "answer" else self.wall_typical


@dataclass
class Speeds:
    per_class: Dict[str, ClassSpeed] = field(default_factory=dict)
    overall: ClassSpeed = field(default_factory=ClassSpeed)
    #: Fraction of wall time that is *not* answering (rendering, hesitation).
    overhead_ratio: float = 0.0
    #: How much your average pace swings from one day to the next, as a
    #: coefficient of variation. Tired days are slow days, and that moves the
    #: whole session together rather than card by card.
    day_cv: float = 0.0

    def for_class(self, cls: str) -> ClassSpeed:
        """Speed for a class, falling back to the overall figure when a class
        has too little history of its own to be trustworthy."""
        cs = self.per_class.get(cls)
        if cs is None or cs.n < MIN_SAMPLES:
            return self.overall
        return cs

    def secs(self, cls: str, mode: str, slow: bool = False) -> float:
        return self.for_class(cls).pick(mode, slow)


#: Below this many samples a class borrows the overall average instead.
MIN_SAMPLES = 20

#: Percentile used for the pessimistic end of the ETA range.
SLOW_PCT = 80.0


def stdev(values: Sequence[float]) -> float:
    """Sample standard deviation; 0 for fewer than two values."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def _class_speed(items: Sequence[TimedReview], method: str) -> ClassSpeed:
    if not items:
        return ClassSpeed()
    answers = [t.answer_s for t in items]
    walls = [t.wall_s for t in items]
    return ClassSpeed(
        n=len(items),
        answer=aggregate(answers, method),
        wall=aggregate(walls, method),
        answer_typical=percentile(answers, 50.0),
        wall_typical=percentile(walls, 50.0),
        answer_slow=percentile(answers, SLOW_PCT),
        wall_slow=percentile(walls, SLOW_PCT),
        answer_sd=stdev(answers),
        wall_sd=stdev(walls),
    )


#: Days needing at least this many answers to count towards :attr:`day_cv`.
MIN_REVIEWS_PER_DAY = 10

#: Day-to-day pace swings above this are almost certainly a change of habit
#: rather than noise, and would make the range meaningless.
MAX_DAY_CV = 0.5


def day_variation(timed: Sequence[TimedReview], mode: str = "wall") -> float:
    """Coefficient of variation of your daily average pace."""
    by_day: Dict[int, List[float]] = {}
    for t in timed:
        if classify(t.review) is None:
            continue
        day = t.review.id // 86_400_000
        by_day.setdefault(day, []).append(t.wall_s if mode == "wall" else t.answer_s)
    means = [
        sum(v) / len(v) for v in by_day.values() if len(v) >= MIN_REVIEWS_PER_DAY
    ]
    if len(means) < 3:
        return 0.0
    grand = sum(means) / len(means)
    if grand <= 0:
        return 0.0
    return min(MAX_DAY_CV, stdev(means) / grand)


def compute_speeds(timed: Sequence[TimedReview], method: str = "median") -> Speeds:
    buckets: Dict[str, List[TimedReview]] = {c: [] for c in CLASSES}
    usable: List[TimedReview] = []
    for t in timed:
        cls = classify(t.review)
        if cls is None:
            continue
        buckets[cls].append(t)
        usable.append(t)
    speeds = Speeds(
        per_class={c: _class_speed(v, method) for c, v in buckets.items()},
        overall=_class_speed(usable, method),
    )
    total_wall = sum(t.wall_s for t in usable)
    if total_wall > 0:
        speeds.overhead_ratio = sum(t.overhead_s for t in usable) / total_wall
    speeds.day_cv = day_variation(usable)
    return speeds


# ---------------------------------------------------------------------------
# Workload
# ---------------------------------------------------------------------------


@dataclass
class Workload:
    """Cards Anki will actually hand you today, after deck limits."""

    new_cards: int = 0
    review_cards: int = 0
    #: Reps (not cards) still owed by cards already part-way through learning.
    learning_reps: int = 0


@dataclass
class Behaviour:
    """Empirically measured study behaviour, used to turn cards into reps."""

    #: Total learning answers per new card introduced (>= 1).
    reps_per_new: float = 2.0
    #: Fraction of review answers graded "Again".
    lapse_rate: float = 0.10
    #: Relearning answers per lapse.
    reps_per_lapse: float = 2.0


@dataclass
class EtaPart:
    label: str
    reps: float
    secs_each: float

    @property
    def seconds(self) -> float:
        return self.reps * self.secs_each


@dataclass
class Estimate:
    seconds: float = 0.0
    seconds_slow: float = 0.0
    total_reps: float = 0.0
    parts: List[EtaPart] = field(default_factory=list)

    @property
    def secs_per_rep(self) -> float:
        return self.seconds / self.total_reps if self.total_reps else 0.0


#: z-score for an 80% one-sided bound -- the pessimistic end of the ETA range.
Z80 = 0.8416


def estimate(
    workload: Workload,
    speeds: Speeds,
    behaviour: Behaviour,
    mode: str = "wall",
    count_full_learning: bool = True,
    include_lapses: bool = True,
) -> Estimate:
    """Turn a workload into an ETA.

    The accuracy of this function comes from three places that a flat
    "seconds x cards" estimate misses:

    * a new card is not one answer -- it is ``reps_per_new`` answers, measured
      from your own history rather than assumed from the deck preset;
    * cards mid-way through learning still owe their remaining steps;
    * a share of today's reviews will be failed and come back as relearning
      answers within the same session.

    The upper bound is *not* "every card takes as long as your slowest cards".
    Over hundreds of answers the slow ones are cancelled out by the fast ones,
    so per-card spread is propagated as a variance -- it grows with the square
    root of the workload, not linearly.  What does move a whole session
    together is your own day-to-day form, so that is added as a separate,
    proportional term.
    """
    parts: List[EtaPart] = []
    variance = 0.0

    def add(label: str, reps: float, secs: float, sd: float) -> None:
        nonlocal variance
        if reps <= 0 or secs <= 0:
            return
        parts.append(EtaPart(label, reps, secs))
        variance += reps * sd * sd

    rpn = max(1.0, behaviour.reps_per_new) if count_full_learning else 1.0
    learn = speeds.for_class(LEARN)
    add("New cards", workload.new_cards * rpn, learn.pick(mode), learn.sd(mode))
    add("Learning", float(workload.learning_reps), learn.pick(mode), learn.sd(mode))

    if workload.review_cards:
        # Reviews are a mix of young and mature; weight by how many of each the
        # user actually answers rather than guessing 50/50.
        y = speeds.for_class(YOUNG)
        m = speeds.for_class(MATURE)
        total_n = y.n + m.n
        mature_share = (m.n / total_n) if total_n else 0.5
        young_share = 1.0 - mature_share
        blended = m.pick(mode) * mature_share + y.pick(mode) * young_share
        blended_sd = math.sqrt(
            m.sd(mode) ** 2 * mature_share + y.sd(mode) ** 2 * young_share
        )
        add("Reviews", float(workload.review_cards), blended, blended_sd)

        if include_lapses:
            relearn = speeds.for_class(RELEARN)
            lapse_reps = (
                workload.review_cards
                * max(0.0, min(1.0, behaviour.lapse_rate))
                * max(1.0, behaviour.reps_per_lapse)
            )
            if lapse_reps >= 0.5:
                add("Expected lapses", lapse_reps, relearn.pick(mode), relearn.sd(mode))

    total = sum(p.seconds for p in parts)
    day_swing = total * speeds.day_cv
    spread = math.sqrt(variance + day_swing * day_swing)
    return Estimate(
        seconds=total,
        seconds_slow=total + Z80 * spread,
        total_reps=sum(p.reps for p in parts),
        parts=parts,
    )


# ---------------------------------------------------------------------------
# Behaviour measurement
# ---------------------------------------------------------------------------


def measure_behaviour(
    timed: Sequence[TimedReview],
    new_card_ids: Optional[Iterable[int]] = None,
    fallback: Optional[Behaviour] = None,
) -> Behaviour:
    """Derive :class:`Behaviour` from review history.

    ``new_card_ids`` is the set of cards whose *first ever* review falls inside
    the window; only those give an honest reps-per-new-card figure, because a
    card that was already part-way through learning when the window opened
    contributes answers without contributing an introduction.
    """
    base = fallback or Behaviour()
    learn_rows = [t for t in timed if t.review.type == RT_LEARN]
    relearn_rows = [t for t in timed if t.review.type == RT_RELEARN]
    review_rows = [t for t in timed if t.review.type in (RT_REVIEW, RT_FILTERED)]

    if new_card_ids is not None:
        fresh = set(new_card_ids)
        counted = [t for t in learn_rows if t.review.cid in fresh]
        introduced = len({t.review.cid for t in counted})
    else:
        introduced = len({t.review.cid for t in learn_rows})
        counted = learn_rows
    reps_per_new = (len(counted) / introduced) if introduced >= 5 else base.reps_per_new

    lapses = [t for t in review_rows if t.review.ease == 1]
    lapse_rate = (len(lapses) / len(review_rows)) if len(review_rows) >= 20 else base.lapse_rate

    lapsed_cards = len({t.review.cid for t in relearn_rows})
    reps_per_lapse = (
        len(relearn_rows) / lapsed_cards if lapsed_cards >= 5 else base.reps_per_lapse
    )

    return Behaviour(
        reps_per_new=max(1.0, reps_per_new),
        lapse_rate=lapse_rate,
        reps_per_lapse=max(1.0, reps_per_lapse),
    )


# ---------------------------------------------------------------------------
# Done-so-far totals
# ---------------------------------------------------------------------------


@dataclass
class DoneTotals:
    reviews: int = 0
    seconds: float = 0.0
    introduced: int = 0


def totals_since(
    timed: Sequence[TimedReview],
    since_ms: int,
    first_seen: Dict[int, int],
    mode: str = "wall",
) -> DoneTotals:
    """Work completed since ``since_ms``.

    ``first_seen`` maps card id -> timestamp of its earliest review.  It only
    needs to contain cards first seen inside the window; anything missing is
    assumed to predate it, so a card counts as "introduced" in the period only
    if it was genuinely never seen before.
    """
    reviews = 0
    seconds = 0.0
    introduced = set()
    for t in timed:
        rev = t.review
        if rev.id < since_ms or classify(rev) is None:
            continue
        reviews += 1
        seconds += t.wall_s if mode == "wall" else t.answer_s
        if rev.type == RT_LEARN and first_seen.get(rev.cid, -1) >= since_ms:
            introduced.add(rev.cid)
    return DoneTotals(reviews=reviews, seconds=seconds, introduced=len(introduced))
