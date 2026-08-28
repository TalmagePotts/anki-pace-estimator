"""Cards pulled into a filtered deck still belong to their home deck."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pace_estimator"))

from src.collector import classify_filtered  # noqa: E402

TODAY = 500          # Anki's day number
NOW = 1_700_000_000  # epoch seconds


def test_new_cards_are_counted_whenever_they_appear():
    assert classify_filtered([(0, 0, 0), (0, 99, 0)], TODAY, NOW) == (2, 0, 0)


def test_reviews_count_only_once_due():
    rows = [(2, TODAY - 1, 0), (2, TODAY, 0), (2, TODAY + 1, 0)]
    assert classify_filtered(rows, TODAY, NOW) == (0, 2, 0)


def test_intraday_learning_uses_the_clock_not_the_day_number():
    # A queue-1 card's due is an epoch timestamp; comparing it against the day
    # number would make every one of them look due.
    rows = [(1, NOW - 60, 2), (1, NOW + 600, 2)]
    assert classify_filtered(rows, TODAY, NOW) == (0, 0, 2)


def test_day_learning_uses_the_day_number():
    rows = [(3, TODAY, 3), (3, TODAY + 2, 3)]
    assert classify_filtered(rows, TODAY, NOW) == (0, 0, 3)


def test_learning_cards_owe_their_remaining_steps():
    assert classify_filtered([(1, NOW - 1, 3)], TODAY, NOW) == (0, 0, 3)
    assert classify_filtered([(1, NOW - 1, 1003)], TODAY, NOW) == (0, 0, 3)
    assert classify_filtered([(1, NOW - 1, 0)], TODAY, NOW) == (0, 0, 1)
    assert classify_filtered([(1, NOW - 1, None)], TODAY, NOW) == (0, 0, 1)


def test_preview_cards_are_one_answer_each():
    rows = [(4, NOW - 1, 0), (4, NOW + 999, 0)]
    assert classify_filtered(rows, TODAY, NOW) == (0, 0, 1)


def test_suspended_and_buried_cards_are_ignored():
    # Negative queues are suspended (-1) and buried (-2, -3).
    rows = [(-1, TODAY, 0), (-2, TODAY, 0), (-3, TODAY, 0)]
    assert classify_filtered(rows, TODAY, NOW) == (0, 0, 0)


def test_a_mixed_filtered_deck():
    rows = [
        (0, 0, 0),               # a new card gathered into the deck
        (2, TODAY - 3, 0),       # an overdue review
        (2, TODAY + 5, 0),       # not due yet
        (1, NOW - 5, 2),         # mid-learning, two steps left
        (4, NOW - 5, 0),         # a preview card
    ]
    assert classify_filtered(rows, TODAY, NOW) == (1, 1, 3)


def test_nothing_in_a_filtered_deck():
    assert classify_filtered([], TODAY, NOW) == (0, 0, 0)
