import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "review_pace"))

from src import stats as S  # noqa: E402

SEC = 1000


def rev(t_offset_s, time_s, type_=S.RT_REVIEW, ivl=30, cid=1, ease=3, last_ivl=None):
    return S.Review(
        id=int(t_offset_s * SEC),
        cid=cid,
        did=1,
        ease=ease,
        ivl=ivl,
        last_ivl=ivl if last_ivl is None else last_ivl,
        time_ms=int(time_s * SEC),
        type=type_,
    )


def test_classify():
    assert S.classify(rev(0, 5, S.RT_LEARN)) == S.LEARN
    assert S.classify(rev(0, 5, S.RT_RELEARN)) == S.RELEARN
    assert S.classify(rev(0, 5, S.RT_REVIEW, ivl=5, last_ivl=5)) == S.YOUNG
    assert S.classify(rev(0, 5, S.RT_REVIEW, ivl=100, last_ivl=100)) == S.MATURE
    assert S.classify(rev(0, 0, S.RT_MANUAL)) is None
    assert S.classify(rev(0, 0, S.RT_RESCHEDULED)) is None


def test_wall_includes_between_card_time():
    # Three cards, 10s apart, each answered in 6s -> 4s of overhead each.
    rows = [rev(0, 6, cid=1), rev(10, 6, cid=2), rev(20, 6, cid=3)]
    timed = S.annotate(rows, idle_cutoff_s=60)
    assert timed[0].session_start is True
    assert timed[0].wall_s == 6  # no predecessor -> falls back to answer time
    assert timed[1].wall_s == 10
    assert timed[2].wall_s == 10
    assert timed[2].overhead_s == 4


def test_idle_gap_starts_new_session():
    rows = [rev(0, 6, cid=1), rev(600, 6, cid=2)]
    timed = S.annotate(rows, idle_cutoff_s=60)
    assert timed[1].session_start is True
    assert timed[1].wall_s == 6  # the 10 minute coffee break is not study time


def test_wall_never_below_answer_time():
    rows = [rev(0, 6, cid=1), rev(2, 6, cid=2)]  # clock skew / capped answer
    timed = S.annotate(rows, idle_cutoff_s=60)
    assert timed[1].wall_s == 6


def test_answer_time_is_capped():
    timed = S.annotate([rev(0, 500, cid=1)], max_answer_s=60)
    assert timed[0].answer_s == 60


def test_speeds_split_by_class():
    rows = []
    for i in range(30):  # mature: 5s answers, 8s wall
        rows.append(rev(i * 8, 5, S.RT_REVIEW, ivl=100, cid=100 + i))
    for i in range(30):  # learning: 15s answers, 20s wall
        rows.append(rev(1000 + i * 20, 15, S.RT_LEARN, cid=200 + i))
    sp = S.compute_speeds(S.annotate(rows))
    mature = sp.for_class(S.MATURE)
    # The typical (middle) card is a clean 8s; the mean is a shade under
    # because the session's first card has no predecessor gap to measure and
    # falls back to its 5s answer time.
    assert abs(mature.wall_typical - 8) < 0.01
    assert abs(mature.wall - 7.9) < 0.01
    assert abs(mature.answer - 5) < 0.01
    assert abs(sp.for_class(S.LEARN).wall_typical - 20) < 0.01
    assert sp.overhead_ratio > 0


def test_sparse_class_borrows_overall():
    rows = [rev(i * 8, 5, S.RT_REVIEW, ivl=100, cid=i) for i in range(40)]
    rows.append(rev(9000, 99, S.RT_RELEARN, cid=999))  # single outlier sample
    sp = S.compute_speeds(S.annotate(rows))
    assert sp.for_class(S.RELEARN) is sp.overall


def test_estimate_counts_learning_steps_not_cards():
    speeds = S.Speeds(overall=S.ClassSpeed(n=999, answer=10, wall=10, answer_slow=10, wall_slow=10))
    beh = S.Behaviour(reps_per_new=3.0, lapse_rate=0.0, reps_per_lapse=2.0)
    est = S.estimate(S.Workload(new_cards=10), speeds, beh, count_full_learning=True)
    assert est.total_reps == 30  # 10 cards x 3 answers each
    assert est.seconds == 300
    flat = S.estimate(S.Workload(new_cards=10), speeds, beh, count_full_learning=False)
    assert flat.total_reps == 10


def test_estimate_includes_expected_lapses():
    speeds = S.Speeds(overall=S.ClassSpeed(n=999, answer=10, wall=10, answer_slow=10, wall_slow=10))
    beh = S.Behaviour(reps_per_new=1.0, lapse_rate=0.10, reps_per_lapse=2.0)
    est = S.estimate(S.Workload(review_cards=100), speeds, beh)
    assert est.total_reps == 120  # 100 reviews + 10 lapses x 2 relearn answers
    without = S.estimate(S.Workload(review_cards=100), speeds, beh, include_lapses=False)
    assert without.total_reps == 100


def test_estimate_blends_young_and_mature_by_observed_mix():
    speeds = S.Speeds(
        per_class={
            S.YOUNG: S.ClassSpeed(n=75, answer=20, wall=20, answer_slow=20, wall_slow=20),
            S.MATURE: S.ClassSpeed(n=25, answer=4, wall=4, answer_slow=4, wall_slow=4),
        },
        overall=S.ClassSpeed(n=100, answer=16, wall=16, answer_slow=16, wall_slow=16),
    )
    beh = S.Behaviour(lapse_rate=0.0)
    est = S.estimate(S.Workload(review_cards=100), speeds, beh)
    assert abs(est.seconds - 100 * (20 * 0.75 + 4 * 0.25)) < 0.01


def test_no_spread_means_no_range():
    speeds = S.Speeds(overall=S.ClassSpeed(n=999, answer=5, wall=5))
    est = S.estimate(S.Workload(review_cards=50), speeds, S.Behaviour(lapse_rate=0.0))
    assert est.seconds_slow == est.seconds


def test_card_spread_grows_with_the_square_root_of_the_workload():
    # A single slow card cannot make a 400-card session 3x longer: over many
    # answers the slow ones are cancelled out by the fast ones.
    speeds = S.Speeds(overall=S.ClassSpeed(n=999, answer=5, wall=5, answer_sd=5, wall_sd=5))
    beh = S.Behaviour(lapse_rate=0.0)
    small = S.estimate(S.Workload(review_cards=25), speeds, beh)
    big = S.estimate(S.Workload(review_cards=400), speeds, beh)
    small_pct = small.seconds_slow / small.seconds - 1
    big_pct = big.seconds_slow / big.seconds - 1
    assert small_pct > big_pct
    # 16x the cards -> 4x the absolute spread, so a quarter of the relative one.
    assert abs(big_pct * 4 - small_pct) < 1e-6


def test_daily_form_scales_the_range_proportionally():
    speeds = S.Speeds(overall=S.ClassSpeed(n=999, answer=5, wall=5), day_cv=0.20)
    beh = S.Behaviour(lapse_rate=0.0)
    small = S.estimate(S.Workload(review_cards=25), speeds, beh)
    big = S.estimate(S.Workload(review_cards=400), speeds, beh)
    # Being tired slows the whole session, so this term does not shrink.
    assert abs(
        (small.seconds_slow / small.seconds) - (big.seconds_slow / big.seconds)
    ) < 1e-9
    assert abs(big.seconds_slow / big.seconds - (1 + S.Z80 * 0.20)) < 1e-9


def test_measure_behaviour_from_history():
    rows = []
    cid = 0
    for _ in range(10):  # 10 new cards, 3 learning answers each
        cid += 1
        for step in range(3):
            rows.append(rev(cid * 100 + step, 10, S.RT_LEARN, cid=cid))
    for i in range(100):  # 100 reviews, 20 of them failed
        rows.append(rev(5000 + i, 5, S.RT_REVIEW, cid=500 + i, ease=1 if i < 20 else 3))
    for i in range(20):  # each failure came back twice
        rows.append(rev(9000 + i, 7, S.RT_RELEARN, cid=500 + i))
        rows.append(rev(9100 + i, 7, S.RT_RELEARN, cid=500 + i))
    timed = S.annotate(rows)
    beh = S.measure_behaviour(timed, new_card_ids=range(1, 11))
    assert abs(beh.reps_per_new - 3.0) < 0.01
    assert abs(beh.lapse_rate - 0.20) < 0.01
    assert abs(beh.reps_per_lapse - 2.0) < 0.01


def test_measure_behaviour_ignores_partly_learned_cards():
    # Card 1 was introduced before the window; only 1 of its 2 steps is inside.
    rows = [rev(0, 10, S.RT_LEARN, cid=1)]
    for c in range(2, 12):
        rows += [rev(c * 100, 10, S.RT_LEARN, cid=c), rev(c * 100 + 5, 10, S.RT_LEARN, cid=c)]
    beh = S.measure_behaviour(S.annotate(rows), new_card_ids=range(2, 12))
    assert abs(beh.reps_per_new - 2.0) < 0.01


def test_measure_behaviour_falls_back_when_data_is_thin():
    beh = S.measure_behaviour(S.annotate([rev(0, 5)]), new_card_ids=[])
    assert beh == S.Behaviour()


def test_totals_since_counts_only_first_time_introductions():
    first_seen = {1: 0, 2: 10_000}
    rows = [
        rev(0, 5, S.RT_LEARN, cid=1),  # introduced before the cutoff
        rev(20, 5, S.RT_LEARN, cid=1),  # a later step of the same old card
        rev(21, 5, S.RT_LEARN, cid=2),  # genuinely new
    ]
    timed = S.annotate(rows)
    got = S.totals_since(timed, since_ms=10_000, first_seen=first_seen)
    assert got.introduced == 1
    assert got.reviews == 2


def test_percentile_matches_hand_worked_values():
    assert S.percentile([1, 2, 3, 4], 50) == 2.5
    assert S.percentile([1, 2, 3, 4, 5], 80) == 4.2
    assert S.percentile([], 50) == 0.0
    assert S.percentile([7], 99) == 7


def test_trimmed_mean_drops_outliers():
    vals = [1] * 8 + [1000, 1000]
    assert S.trimmed_mean(vals, trim_pct=10.0) < 250
    assert S.trimmed_mean([5], trim_pct=10.0) == 5


def test_totals_since_treats_unknown_cards_as_old():
    # A card missing from first_seen predates the window and must not count as
    # newly introduced.
    timed = S.annotate([rev(20, 5, S.RT_LEARN, cid=42)])
    got = S.totals_since(timed, since_ms=10_000, first_seen={})
    assert got.introduced == 0
    assert got.reviews == 1


def test_day_variation_needs_several_real_days():
    day = 86_400_000
    rows = []
    for d in range(6):
        secs = 5 if d % 2 == 0 else 9  # alternating fast and slow days
        for i in range(20):
            rows.append(
                S.Review(id=d * day + i * 20_000, cid=d * 100 + i, did=1, ease=3,
                         ivl=100, last_ivl=100, time_ms=secs * 1000, type=S.RT_REVIEW)
            )
    cv = S.day_variation(S.annotate(rows, idle_cutoff_s=5))
    assert 0.2 < cv < 0.4


def test_day_variation_ignores_thin_days():
    day = 86_400_000
    rows = [
        S.Review(id=d * day, cid=d, did=1, ease=3, ivl=100, last_ivl=100,
                 time_ms=5000, type=S.RT_REVIEW)
        for d in range(10)
    ]
    assert S.day_variation(S.annotate(rows)) == 0.0


def test_stdev():
    assert S.stdev([]) == 0.0
    assert S.stdev([4]) == 0.0
    assert abs(S.stdev([2, 4, 4, 4, 5, 5, 7, 9]) - 2.13809) < 0.0001


def test_speed_used_for_estimates_is_a_mean_not_a_median():
    # Nine quick cards and one slow one: the median says 5s, but ten cards
    # really do take 95s, so an ETA built on the median would be 45% short.
    rows = [rev(i * 8, 5, S.RT_REVIEW, ivl=100, cid=i) for i in range(9)]
    rows.append(rev(9 * 8, 50, S.RT_REVIEW, ivl=100, cid=9))
    sp = S.compute_speeds(S.annotate(rows, idle_cutoff_s=1))
    cs = sp.for_class(S.MATURE)
    assert abs(cs.answer_typical - 5) < 0.01
    assert abs(cs.answer - 9.5) < 0.01
    assert abs(cs.answer * 10 - sum(r.time_ms for r in rows) / 1000) < 0.01


def test_trimmed_option_discards_the_slow_tail():
    rows = [rev(i * 8, 5, S.RT_REVIEW, ivl=100, cid=i) for i in range(18)]
    rows += [rev(200 + i, 60, S.RT_REVIEW, ivl=100, cid=100 + i) for i in range(2)]
    timed = S.annotate(rows, idle_cutoff_s=1)
    plain = S.compute_speeds(timed, "mean").for_class(S.MATURE).answer
    trimmed = S.compute_speeds(timed, "trimmed").for_class(S.MATURE).answer
    assert trimmed < plain


def test_every_estimator_is_available():
    vals = [1, 2, 30]
    assert S.aggregate(vals, "mean") == 11
    assert S.aggregate(vals, "median") == 2
    assert S.aggregate(vals, "trimmed") == 11  # too few values to trim
    assert S.aggregate(vals, "nonsense") == 11  # unknown falls back to the mean
    assert S.aggregate([], "mean") == 0.0


# ---------------------------------------------------------------------------
# Optional feature buckets
# ---------------------------------------------------------------------------


def test_ease_and_interval_bucketing():
    assert S.ease_bucket(0) == "n/a"
    assert S.ease_bucket(1900) == "hard"
    assert S.ease_bucket(2500) == "normal"
    assert S.ease_bucket(3100) == "easy"
    assert S.interval_bucket(0) == "new"
    assert S.interval_bucket(3) == "<1w"
    assert S.interval_bucket(20) == "1-4w"
    assert S.interval_bucket(90) == "1-6m"
    assert S.interval_bucket(400) == "6m+"


def test_bucket_key_always_leads_with_the_card_class():
    key = S.bucket_key(S.MATURE, 1900, 200, ["ease", "interval"])
    assert key == (S.MATURE, "hard", "6m+")
    assert S.bucket_key(S.MATURE, 1900, 200, []) == (S.MATURE,)
    assert S.describe_key(key).startswith("Mature")


def test_features_are_off_unless_asked_for():
    rows = [rev(i * 8, 5, S.RT_REVIEW, ivl=100, cid=i) for i in range(30)]
    assert S.compute_speeds(S.annotate(rows)).per_key == {}


def test_feature_buckets_get_their_own_speeds():
    rows = []
    for i in range(40):  # hard cards: slow
        rows.append(S.Review(i * 20_000, i, 1, 3, 100, 100, 18_000, S.RT_REVIEW, 1900))
    for i in range(40):  # easy cards: quick
        rows.append(S.Review(10 ** 6 + i * 20_000, 100 + i, 1, 3, 100, 100, 4_000,
                             S.RT_REVIEW, 3000))
    sp = S.compute_speeds(S.annotate(rows), "mean", ["ease"])
    assert abs(sp.for_key((S.MATURE, "hard")).answer - 18) < 0.1
    assert abs(sp.for_key((S.MATURE, "easy")).answer - 4) < 0.1


def test_thin_bucket_falls_back_to_its_card_class():
    rows = [S.Review(i * 20_000, i, 1, 3, 100, 100, 5_000, S.RT_REVIEW, 2500)
            for i in range(40)]
    rows.append(S.Review(10 ** 6, 999, 1, 3, 100, 100, 55_000, S.RT_REVIEW, 1500))
    sp = S.compute_speeds(S.annotate(rows), "mean", ["ease"])
    # One "hard" sample is not evidence; it must not price the whole bucket.
    assert sp.for_key((S.MATURE, "hard")) is sp.for_class(S.MATURE)


def test_estimate_prices_each_bucket_separately():
    speeds = S.Speeds(
        per_class={S.MATURE: S.ClassSpeed(n=200, answer=10, wall=10)},
        overall=S.ClassSpeed(n=200, answer=10, wall=10),
        per_key={
            (S.MATURE, "hard"): S.ClassSpeed(n=100, answer=20, wall=20),
            (S.MATURE, "easy"): S.ClassSpeed(n=100, answer=5, wall=5),
        },
        features=("ease",),
    )
    work = S.Workload(
        review_cards=100,
        review_buckets={(S.MATURE, "hard"): 40, (S.MATURE, "easy"): 60},
    )
    est = S.estimate(work, speeds, S.Behaviour(lapse_rate=0.0))
    assert est.seconds == 40 * 20 + 60 * 5
    assert {p.reps for p in est.parts} == {40.0, 60.0}


def test_estimate_ignores_buckets_when_features_are_off():
    speeds = S.Speeds(
        per_class={S.MATURE: S.ClassSpeed(n=200, answer=10, wall=10)},
        overall=S.ClassSpeed(n=200, answer=10, wall=10),
        per_key={(S.MATURE, "hard"): S.ClassSpeed(n=100, answer=20, wall=20)},
        features=(),
    )
    work = S.Workload(review_cards=100, review_buckets={(S.MATURE, "hard"): 100})
    assert S.estimate(work, speeds, S.Behaviour(lapse_rate=0.0)).seconds == 1000


def test_unknown_features_are_ignored():
    rows = [rev(i * 8, 5, S.RT_REVIEW, ivl=100, cid=i) for i in range(30)]
    sp = S.compute_speeds(S.annotate(rows), "mean", ["ease", "astrology"])
    assert sp.features == ("ease",)


# ---------------------------------------------------------------------------
# Time of day
# ---------------------------------------------------------------------------

HOUR_MS = 3_600_000
DAY_MS = 86_400_000


def at(day, hour, secs, cid):
    """A review on a given day and hour, taking ``secs``."""
    # Days are counted from the epoch, whose local hour offset does not matter
    # here because every helper goes through the same conversion.
    base = day * DAY_MS + hour * HOUR_MS
    return S.Review(base + cid * 1000, cid, 1, 3, 100, 100, int(secs * 1000),
                    S.RT_REVIEW, 2500)


def test_hour_speeds_count_distinct_days():
    rows = [at(5, 9, 10, i) for i in range(30)] + [at(6, 9, 10, 100 + i) for i in range(30)]
    speeds, days = S.compute_hour_speeds(S.annotate(rows, idle_cutoff_s=0.5), "mean")
    hour = S.local_hour(rows[0].id)
    assert speeds[hour].n == 60
    assert days[hour] == 2


def test_an_hour_seen_on_too_few_days_is_not_used():
    # One very long session is a day, not an hour, and must not move anything.
    hour_speeds = {3: S.ClassSpeed(n=500, answer=30, wall=30)}
    overall = S.ClassSpeed(n=1000, answer=10, wall=10)
    assert S.hour_factors_from(hour_speeds, overall, "wall", 50, {3: 1}, min_days=5) == {}
    used = S.hour_factors_from(hour_speeds, overall, "wall", 50, {3: 20}, min_days=5)
    assert used and used[3] > 1


def test_shrinkage_pulls_a_thin_hour_toward_no_effect():
    overall = S.ClassSpeed(n=1000, answer=10, wall=10)
    thin = {1: S.ClassSpeed(n=10, answer=20, wall=20)}     # looks twice as slow
    thick = {1: S.ClassSpeed(n=5000, answer=20, wall=20)}  # same, far more data
    days = {1: 30}
    thin_f = S.hour_factors_from(thin, overall, "wall", 50, days, 5)[1]
    thick_f = S.hour_factors_from(thick, overall, "wall", 50, days, 5)[1]
    assert 1.0 < thin_f < thick_f <= 2.0
    assert abs(thick_f - 2.0) < 0.05     # believed almost entirely
    assert abs(thin_f - 1.17) < 0.05     # barely believed at all


def test_no_shrinkage_means_the_raw_ratio():
    overall = S.ClassSpeed(n=1000, answer=10, wall=10)
    hours = {1: S.ClassSpeed(n=10, answer=20, wall=20)}
    assert S.hour_factors_from(hours, overall, "wall", 0, {1: 9}, 5)[1] == 2.0


def test_hour_factors_need_a_baseline():
    assert S.hour_factors_from({1: S.ClassSpeed(n=99, wall=5)}, S.ClassSpeed(), "wall") == {}


def test_stretch_spreads_work_across_hour_boundaries():
    import time as _t

    # Start exactly on the hour so the arithmetic is checkable by hand.
    start = _t.mktime((2026, 6, 1, 10, 0, 0, 0, 0, -1))
    # An hour of work at 2x, then the next hour is normal: the first 30 minutes
    # of nominal work fills the whole 10:00 hour.
    factors = {10: 2.0, 11: 1.0}
    assert abs(S.stretch_over_hours(1800, start, factors) - 3600) < 1
    # Half that work fits inside the slow hour and simply doubles.
    assert abs(S.stretch_over_hours(900, start, factors) - 1800) < 1
    # More than the slow hour can absorb spills into the normal one.
    assert abs(S.stretch_over_hours(2400, start, factors) - (3600 + 600)) < 1


def test_stretch_is_a_no_op_without_factors():
    assert S.stretch_over_hours(500, 0, {}) == 500
    assert S.stretch_over_hours(0, 0, {5: 2.0}) == 0


def test_estimate_applies_hour_factors_only_when_given_a_clock():
    import time as _t

    start = _t.mktime((2026, 6, 1, 10, 0, 0, 0, 0, -1))
    speeds = S.Speeds(overall=S.ClassSpeed(n=999, answer=10, wall=10))
    work = S.Workload(review_cards=60)  # 600 nominal seconds
    beh = S.Behaviour(lapse_rate=0.0)
    assert S.estimate(work, speeds, beh, start_epoch=start).seconds == 600

    speeds.hour_factors = {10: 2.0, 11: 2.0}
    assert S.estimate(work, speeds, beh).seconds == 600  # no clock, no effect
    assert abs(S.estimate(work, speeds, beh, start_epoch=start).seconds - 1200) < 1


# ---------------------------------------------------------------------------
# Per-deck speeds
# ---------------------------------------------------------------------------

# 10 is the parent of 11 and 12.
ANCESTORS = {10: [10], 11: [11, 10], 12: [12, 10]}


def deck_rev(did, secs, cid, offset=0):
    return S.Review(offset + cid * 20_000, cid, did, 3, 100, 100,
                    int(secs * 1000), S.RT_REVIEW, 2500)


def test_a_review_counts_toward_its_deck_and_every_parent():
    rows = [deck_rev(11, 5, i) for i in range(30)]
    speeds = S.compute_speeds(S.annotate(rows, idle_cutoff_s=1), "mean",
                              ancestors_of=ANCESTORS)
    assert speeds.per_deck[(11, S.MATURE)].n == 30
    assert speeds.per_deck[(10, S.MATURE)].n == 30   # the parent sees it too
    assert speeds.per_deck[(11, None)].n == 30       # and the deck's overall


def test_each_deck_is_priced_from_its_own_history():
    rows = [deck_rev(11, 4, i) for i in range(30)]
    rows += [deck_rev(12, 24, 100 + i, offset=10 ** 7) for i in range(30)]
    speeds = S.compute_speeds(S.annotate(rows, idle_cutoff_s=1), "mean",
                              ancestors_of=ANCESTORS)
    assert abs(speeds.deck_view([11, 10]).overall.wall - 4) < 0.2
    assert abs(speeds.deck_view([12, 10]).overall.wall - 24) < 0.2
    # The parent sees both, so it lands between them.
    assert 4 < speeds.deck_view([10]).overall.wall < 24


def test_a_thin_deck_falls_back_to_its_parent():
    rows = [deck_rev(11, 4, i) for i in range(40)]
    rows += [deck_rev(12, 30, 500, offset=10 ** 7)]  # one card only
    speeds = S.compute_speeds(S.annotate(rows, idle_cutoff_s=1), "mean",
                              ancestors_of=ANCESTORS)
    thin = speeds.for_deck([12, 10], S.MATURE)
    parent = speeds.per_deck[(10, S.MATURE)]
    assert thin is parent            # not priced off a single card
    assert speeds.for_deck([999], S.MATURE) is None   # unknown deck: no opinion


def test_deck_view_is_a_no_op_without_deck_data():
    rows = [deck_rev(11, 5, i) for i in range(30)]
    speeds = S.compute_speeds(S.annotate(rows, idle_cutoff_s=1), "mean")
    assert speeds.deck_view([11, 10]) is speeds
    assert speeds.deck_view([]) is speeds


def test_deck_view_keeps_the_shared_adjustments():
    rows = [deck_rev(11, 5, i) for i in range(30)]
    speeds = S.compute_speeds(S.annotate(rows, idle_cutoff_s=1), "mean",
                              ancestors_of=ANCESTORS)
    speeds.day_cv = 0.3
    speeds.hour_factors = {4: 1.5}
    view = speeds.deck_view([11, 10])
    assert view.day_cv == 0.3
    assert view.hour_factors == {4: 1.5}


def test_combining_decks_adds_variances_not_upper_bounds():
    # Two decks that each might run slow are unlikely to both run slow at once,
    # so the combined range must be tighter than the sum of their ranges.
    speeds = S.Speeds(
        per_class={S.MATURE: S.ClassSpeed(n=200, answer=10, wall=10, wall_sd=6)},
        overall=S.ClassSpeed(n=200, answer=10, wall=10, wall_sd=6),
    )
    beh = S.Behaviour(lapse_rate=0.0)
    one = S.estimate(S.Workload(review_cards=50), speeds, beh)
    both = S.estimate_many(
        [S.DeckWork("A", S.Workload(review_cards=50), speeds),
         S.DeckWork("B", S.Workload(review_cards=50), speeds)],
        beh,
    )
    assert both.seconds == one.seconds * 2
    assert both.seconds_slow < one.seconds_slow * 2
    spread_one = one.seconds_slow - one.seconds
    spread_both = both.seconds_slow - both.seconds
    assert abs(spread_both - spread_one * math.sqrt(2)) < 1e-6


def test_combined_parts_are_labelled_by_deck():
    speeds = S.Speeds(overall=S.ClassSpeed(n=200, answer=10, wall=10))
    est = S.estimate_many(
        [S.DeckWork("Spanish", S.Workload(review_cards=10), speeds),
         S.DeckWork("Pharm", S.Workload(review_cards=10), speeds)],
        S.Behaviour(lapse_rate=0.0),
    )
    labels = [p.label for p in est.parts]
    assert "Spanish: Reviews" in labels and "Pharm: Reviews" in labels
