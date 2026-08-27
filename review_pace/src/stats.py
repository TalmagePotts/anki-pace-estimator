"""Pure statistics core for Review Pace.

This module deliberately imports nothing from ``anki`` or ``aqt`` so that every
number the add-on displays can be unit-tested without launching Anki.  The
Anki-facing code lives in ``collector.py`` and is responsible for turning the
collection into the plain dataclasses defined here.
"""

from __future__ import annotations

import math
import time
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
    #: The card's ease factor going into this review, in permille (2500 = 250%).
    #: Zero when Anki did not record one, which is normal for learning cards.
    factor: int = 0


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
# Optional feature buckets
# ---------------------------------------------------------------------------

FEATURE_EASE = "ease"
FEATURE_INTERVAL = "interval"

ALL_FEATURES = (FEATURE_EASE, FEATURE_INTERVAL)

FEATURE_LABELS = {
    FEATURE_EASE: "Ease factor",
    FEATURE_INTERVAL: "Interval",
}

#: Ease factor is stored in permille. The splits sit either side of Anki's
#: 250% starting factor, so a card only lands in "hard" or "easy" once its own
#: history has actually moved it there.
EASE_BUCKETS = (("hard", 2200), ("normal", 2700), ("easy", 10 ** 9))

INTERVAL_BUCKETS = (("<1w", 7), ("1-4w", 30), ("1-6m", 180), ("6m+", 10 ** 9))


def ease_bucket(factor: int) -> str:
    if not factor:
        return "n/a"
    for name, upper in EASE_BUCKETS:
        if factor < upper:
            return name
    return EASE_BUCKETS[-1][0]


def interval_bucket(days: int) -> str:
    if days <= 0:
        return "new"
    for name, upper in INTERVAL_BUCKETS:
        if days <= upper:
            return name
    return INTERVAL_BUCKETS[-1][0]


def bucket_key(cls: str, factor: int, ivl: int, features: Sequence[str]) -> tuple:
    """The key a review is averaged under.

    Always starts with the card class, so a bucket that turns out to be too
    thin can fall back to its class without losing the most important split.
    """
    key = [cls]
    for feature in features:
        if feature == FEATURE_EASE:
            key.append(ease_bucket(factor))
        elif feature == FEATURE_INTERVAL:
            key.append(interval_bucket(ivl))
    return tuple(key)


def review_key(review: "Review", features: Sequence[str]) -> Optional[tuple]:
    cls = classify(review)
    if cls is None:
        return None
    ivl = review.last_ivl if review.last_ivl > 0 else review.ivl
    return bucket_key(cls, review.factor, ivl, features)


def describe_key(key: tuple) -> str:
    return " · ".join([CLASS_LABELS.get(key[0], key[0])] + list(key[1:]))


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
    if method == "median":
        return percentile(values, 50.0)
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
    #: Speeds for the optional finer buckets, keyed by :func:`bucket_key`.
    #: Empty unless extra features are switched on.
    per_key: Dict[tuple, ClassSpeed] = field(default_factory=dict)
    features: Tuple[str, ...] = ()
    #: Speed measured in each hour of the day, for the analysis view. Always
    #: populated; it is only *used* when hour factors are switched on.
    hour_speeds: Dict[int, ClassSpeed] = field(default_factory=dict)
    #: How many *distinct days* each hour was studied on. An hour seen on one
    #: long day is that day, not that hour.
    hour_days: Dict[int, int] = field(default_factory=dict)
    #: Multipliers applied to the estimate per hour. Empty when switched off.
    hour_factors: Dict[int, float] = field(default_factory=dict)
    #: Speed per ``(deck id, card class)``, where the deck id is the deck the
    #: review happened in *or any of its parents*, so a thin subdeck can fall
    #: back up its own tree. A ``None`` class holds the deck's overall speed.
    per_deck: Dict[tuple, ClassSpeed] = field(default_factory=dict)

    def for_class(self, cls: str) -> ClassSpeed:
        """Speed for a class, falling back to the overall figure when a class
        has too little history of its own to be trustworthy."""
        cs = self.per_class.get(cls)
        if cs is None or cs.n < MIN_SAMPLES:
            return self.overall
        return cs

    def secs(self, cls: str, mode: str, slow: bool = False) -> float:
        return self.for_class(cls).pick(mode, slow)

    def for_deck(self, ancestors: Sequence[int], cls: Optional[str]) -> Optional[ClassSpeed]:
        """Speed for a deck, walking up its parents until the data is enough.

        Decks differ far more than card types do -- a vocabulary deck and an
        image-heavy one are not the same activity -- so a deck is priced from
        its own history where it has one, its parent's where it does not, and
        the whole selection only as a last resort.
        """
        for deck_id in ancestors:
            cs = self.per_deck.get((deck_id, cls))
            if cs is not None and cs.n >= MIN_SAMPLES:
                return cs
        return None

    def deck_view(self, ancestors: Sequence[int]) -> "Speeds":
        """A copy of these speeds priced for one deck."""
        if not self.per_deck or not ancestors:
            return self
        per_class = {}
        for cls in CLASSES:
            cs = self.for_deck(ancestors, cls)
            if cs is not None:
                per_class[cls] = cs
        overall = self.for_deck(ancestors, None) or self.overall
        return Speeds(
            per_class=per_class or self.per_class,
            overall=overall,
            overhead_ratio=self.overhead_ratio,
            day_cv=self.day_cv,
            per_key=self.per_key,
            features=self.features,
            hour_speeds=self.hour_speeds,
            hour_days=self.hour_days,
            hour_factors=self.hour_factors,
            per_deck=self.per_deck,
        )

    def for_key(self, key: tuple) -> ClassSpeed:
        """Speed for a feature bucket, falling back to its card class.

        A finer split is only worth using when it has enough evidence of its
        own; otherwise it is noise dressed up as precision.
        """
        cs = self.per_key.get(key)
        if cs is not None and cs.n >= MIN_SAMPLES:
            return cs
        return self.for_class(key[0] if key else "")


#: Below this many samples a class borrows the overall average instead.
MIN_SAMPLES = 20

#: Percentile used for the pessimistic end of the ETA range.
SLOW_PCT = 80.0

#: Pulls a thinly-sampled hour back toward "no effect". An hour needs about
#: this many reviews before half of its apparent difference is believed.
DEFAULT_HOUR_SHRINKAGE = 50

#: An hour must have been studied on at least this many separate days before it
#: is allowed to move an estimate.
#:
#: This guard matters more than the shrinkage does. Hourly averages look
#: dramatic -- on the collection this was tuned against, 5pm appeared 85%
#: slower than midnight -- but most of that gap is *which days* those hours
#: happened to fall on, not the hours themselves. Comparing hours only against
#: other hours of the same day shrinks the spread from 85% to about 10%.
#: Without this requirement, applying hourly factors made estimates worse
#: (28.3% average error against 26.7% for ignoring the clock entirely); with
#: it, they improve slightly (26.2%) and the bias roughly halves.
DEFAULT_HOUR_MIN_DAYS = 5


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


def compute_deck_speeds(
    timed: Sequence[TimedReview],
    method: str,
    ancestors_of: Dict[int, Sequence[int]],
) -> Dict[tuple, ClassSpeed]:
    """Speeds per deck and per parent deck.

    Each review is counted into its own deck *and* every deck above it, so a
    parent always has at least as much evidence as its children combined.
    """
    buckets: Dict[tuple, List[TimedReview]] = {}
    for t in timed:
        cls = classify(t.review)
        if cls is None:
            continue
        for deck_id in ancestors_of.get(t.review.did, (t.review.did,)):
            buckets.setdefault((deck_id, cls), []).append(t)
            buckets.setdefault((deck_id, None), []).append(t)
    return {k: _class_speed(v, method) for k, v in buckets.items()}


def compute_speeds(
    timed: Sequence[TimedReview],
    method: str = "mean",
    features: Sequence[str] = (),
    hour_shrinkage: Optional[float] = None,
    hour_min_days: int = DEFAULT_HOUR_MIN_DAYS,
    ancestors_of: Optional[Dict[int, Sequence[int]]] = None,
) -> Speeds:
    features = tuple(f for f in features if f in ALL_FEATURES)
    buckets: Dict[str, List[TimedReview]] = {c: [] for c in CLASSES}
    keyed: Dict[tuple, List[TimedReview]] = {}
    usable: List[TimedReview] = []
    for t in timed:
        cls = classify(t.review)
        if cls is None:
            continue
        buckets[cls].append(t)
        usable.append(t)
        if features:
            key = review_key(t.review, features)
            if key is not None:
                keyed.setdefault(key, []).append(t)
    speeds = Speeds(
        per_class={c: _class_speed(v, method) for c, v in buckets.items()},
        overall=_class_speed(usable, method),
        per_key={k: _class_speed(v, method) for k, v in keyed.items()},
        features=features,
    )
    total_wall = sum(t.wall_s for t in usable)
    if total_wall > 0:
        speeds.overhead_ratio = sum(t.overhead_s for t in usable) / total_wall
    speeds.day_cv = day_variation(usable)
    if ancestors_of:
        speeds.per_deck = compute_deck_speeds(usable, method, ancestors_of)
    speeds.hour_speeds, speeds.hour_days = compute_hour_speeds(usable, method)
    if hour_shrinkage is not None:
        speeds.hour_factors = hour_factors_from(
            speeds.hour_speeds,
            speeds.overall,
            "wall",
            hour_shrinkage,
            speeds.hour_days,
            hour_min_days,
        )
    return speeds


# ---------------------------------------------------------------------------
# Time of day
# ---------------------------------------------------------------------------

def local_hour(epoch_ms_or_s: float, milliseconds: bool = True) -> int:
    seconds = epoch_ms_or_s / 1000.0 if milliseconds else epoch_ms_or_s
    return time.localtime(seconds).tm_hour


def compute_hour_speeds(
    timed: Sequence[TimedReview], method: str
) -> Tuple[Dict[int, ClassSpeed], Dict[int, int]]:
    """Speed in each hour of the day, and how many days each hour spans."""
    buckets: Dict[int, List[TimedReview]] = {}
    days: Dict[int, set] = {}
    for t in timed:
        if classify(t.review) is None:
            continue
        hour = local_hour(t.review.id)
        buckets.setdefault(hour, []).append(t)
        days.setdefault(hour, set()).add(t.review.id // 86_400_000)
    return (
        {h: _class_speed(v, method) for h, v in buckets.items()},
        {h: len(v) for h, v in days.items()},
    )


def hour_factors_from(
    hour_speeds: Dict[int, ClassSpeed],
    overall: ClassSpeed,
    mode: str,
    shrinkage: float = DEFAULT_HOUR_SHRINKAGE,
    hour_days: Optional[Dict[int, int]] = None,
    min_days: int = DEFAULT_HOUR_MIN_DAYS,
) -> Dict[int, float]:
    """Per-hour multipliers, pulled toward 1 in proportion to the evidence.

    Twenty-four buckets is a lot to carve a review history into, and an hour
    you have studied in twice should not be allowed to move an estimate. The
    shrinkage term is what stops that: an hour with ``shrinkage`` samples gets
    half the difference it appears to have, and one with far more gets nearly
    all of it.
    """
    base = overall.pick(mode)
    if base <= 0:
        return {}
    factors = {}
    for hour, cs in hour_speeds.items():
        if not cs.n:
            continue
        if min_days and (hour_days or {}).get(hour, 0) < min_days:
            continue  # one long night is a day, not an hour
        raw = cs.pick(mode) / base
        weight = cs.n / (cs.n + shrinkage) if (cs.n + shrinkage) else 0.0
        factors[hour] = 1.0 + (raw - 1.0) * weight
    return factors


def stretch_over_hours(
    seconds: float, start_epoch: float, factors: Dict[int, float]
) -> float:
    """Spread a workload forward from ``start_epoch``, hour by hour.

    A long session runs through hours you are quicker or slower in, so the
    work is walked forward across hour boundaries rather than priced entirely
    at the hour it began in.
    """
    if seconds <= 0 or not factors:
        return seconds
    remaining = seconds
    clock = float(start_epoch)
    elapsed = 0.0
    # A session cannot sensibly run past a day; the guard also bounds the loop.
    for _ in range(48):
        factor = max(0.1, factors.get(local_hour(clock, milliseconds=False), 1.0))
        lt = time.localtime(clock)
        to_boundary = 3600 - (lt.tm_min * 60 + lt.tm_sec)
        capacity = to_boundary / factor  # nominal work this hour can absorb
        if remaining <= capacity:
            return elapsed + remaining * factor
        remaining -= capacity
        elapsed += to_boundary
        clock += to_boundary
    return elapsed + remaining


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
    #: How ``review_cards`` splits across feature buckets. Only populated when
    #: extra features are switched on; the counts sum to ``review_cards``.
    review_buckets: Dict[tuple, float] = field(default_factory=dict)


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


def _build_parts(
    workload: Workload,
    speeds: Speeds,
    behaviour: Behaviour,
    mode: str,
    count_full_learning: bool,
    include_lapses: bool,
    prefix: str = "",
) -> Tuple[List[EtaPart], float]:
    """Price one workload, returning its parts and their combined variance."""
    parts: List[EtaPart] = []
    variance = 0.0

    def add(label: str, reps: float, secs: float, sd: float) -> None:
        nonlocal variance
        if reps <= 0 or secs <= 0:
            return
        parts.append(EtaPart(prefix + label if prefix else label, reps, secs))
        variance += reps * sd * sd

    rpn = max(1.0, behaviour.reps_per_new) if count_full_learning else 1.0
    learn = speeds.for_class(LEARN)
    add("New cards", workload.new_cards * rpn, learn.pick(mode), learn.sd(mode))
    add("Learning", float(workload.learning_reps), learn.pick(mode), learn.sd(mode))

    if workload.review_cards:
        if speeds.features and workload.review_buckets:
            # Each bucket of due cards priced at its own measured speed.
            for key, count in sorted(workload.review_buckets.items()):
                if count <= 0:
                    continue
                cs = speeds.for_key(key)
                add(describe_key(key), float(count), cs.pick(mode), cs.sd(mode))
        else:
            # Reviews are a mix of young and mature; weight by how many of each
            # the user actually answers rather than guessing 50/50.
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

    return parts, variance


@dataclass
class DeckWork:
    """One deck's workload, priced with that deck's own speeds."""

    label: str
    workload: Workload
    speeds: Speeds


def estimate_many(
    entries: Sequence[DeckWork],
    behaviour: Behaviour,
    mode: str = "wall",
    count_full_learning: bool = True,
    include_lapses: bool = True,
    start_epoch: Optional[float] = None,
    day_cv: float = 0.0,
    hour_factors: Optional[Dict[int, float]] = None,
) -> Estimate:
    """Combine several separately-priced workloads into one estimate.

    Variances add, standard deviations do not, so the decks are combined here
    rather than by summing their individual upper bounds -- which would imply
    every deck runs slow at once.
    """
    parts: List[EtaPart] = []
    variance = 0.0
    for entry in entries:
        got, var = _build_parts(
            entry.workload,
            entry.speeds,
            behaviour,
            mode,
            count_full_learning,
            include_lapses,
            prefix="%s: " % entry.label if entry.label else "",
        )
        parts.extend(got)
        variance += var

    total = sum(p.seconds for p in parts)
    day_swing = total * day_cv
    spread = math.sqrt(variance + day_swing * day_swing)
    slow = total + Z80 * spread
    if hour_factors and start_epoch is not None:
        total = stretch_over_hours(total, start_epoch, hour_factors)
        slow = stretch_over_hours(slow, start_epoch, hour_factors)
    return Estimate(
        seconds=total,
        seconds_slow=slow,
        total_reps=sum(p.reps for p in parts),
        parts=parts,
    )


def estimate(
    workload: Workload,
    speeds: Speeds,
    behaviour: Behaviour,
    mode: str = "wall",
    count_full_learning: bool = True,
    include_lapses: bool = True,
    start_epoch: Optional[float] = None,
) -> Estimate:
    """Turn a single workload into an ETA.

    The accuracy of this function comes from four places that a flat
    "seconds x cards" estimate misses:

    * a new card is not one answer -- it is ``reps_per_new`` answers, measured
      from your own history rather than assumed from the deck preset;
    * cards mid-way through learning still owe their remaining steps;
    * a share of today's reviews will be failed and come back as relearning
      answers within the same session;
    * decks and card types are priced separately, because they are not the
      same activity.

    The upper bound is *not* "every card takes as long as your slowest cards".
    Over hundreds of answers the slow ones are cancelled out by the fast ones,
    so per-card spread is propagated as a variance -- it grows with the square
    root of the workload, not linearly.  What does move a whole session
    together is your own day-to-day form, so that is added as a separate,
    proportional term.
    """
    return estimate_many(
        [DeckWork("", workload, speeds)],
        behaviour,
        mode,
        count_full_learning,
        include_lapses,
        start_epoch,
        day_cv=speeds.day_cv,
        hour_factors=speeds.hour_factors,
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
