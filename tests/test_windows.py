"""The review window: speeds use a short one, totals need a month.

The two were the same window once, so "new cards learned this month" was
silently capped at the speed lookback and reported the same number as the
weekly figure.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pace_estimator"))

from src import collector as CO  # noqa: E402
from src import config as C  # noqa: E402

DAY_MS = 86_400_000
CUTOFF = 1_700_000_000  # day_cutoff, epoch seconds


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.cutoffs = []

    def all(self, sql, *args):
        if "from revlog r join cards" in sql:
            self.cutoffs.append(args[0])
            return [r for r in self.rows if r[0] >= args[0]][::-1]
        if "min(id)" in sql:
            return []
        return []

    def list(self, sql, *args):
        return []


class FakeSched:
    day_cutoff = CUTOFF
    today = 500


class FakeCol:
    def __init__(self, rows):
        self.db = FakeDB(rows)
        self.sched = FakeSched()


def review_row(days_ago, cid):
    ts = int((CUTOFF - days_ago * 86400) * 1000)
    return (ts, cid, 1, 3, 100, 100, 5000, 1, 2500)


def fetch(lookback, rows):
    cfg = C.normalise({"speed": {"lookback_days": lookback, "min_sample": 0}})
    col = FakeCol(rows)
    result = CO.fetch_reviews(col, cfg, set())
    return col, result


def test_a_short_speed_window_still_fetches_a_full_month():
    col, (reviews, _, _, speed_cutoff) = fetch(
        14, [review_row(d, d) for d in range(0, 40)]
    )
    requested_days = (CUTOFF - col.db.cutoffs[0] / 1000) / 86400
    assert round(requested_days) == CO.TOTALS_DAYS
    # A card reviewed 25 days ago is outside the speed window but inside the
    # month, so it must still be fetched.
    assert any(r.id < speed_cutoff for r in reviews)


def test_the_speed_cutoff_tracks_the_lookback_setting():
    _, (_, _, _, speed_cutoff) = fetch(14, [review_row(d, d) for d in range(0, 40)])
    assert round((CUTOFF - speed_cutoff / 1000) / 86400) == 14


def test_a_long_lookback_widens_the_fetch_rather_than_narrowing_it():
    col, _ = fetch(90, [review_row(d, d) for d in range(0, 100)])
    assert round((CUTOFF - col.db.cutoffs[0] / 1000) / 86400) == 90


def test_the_totals_window_covers_a_calendar_month():
    # 30 would truncate the last day of a 31-day month.
    assert CO.TOTALS_DAYS >= 31
