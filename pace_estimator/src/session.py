"""Tracking of the study session currently in progress.

History-based speed tells you how fast you *usually* are.  When you are in the
middle of a session, how fast you are *right now* is a better predictor, so the
reviewer overlay blends the two: it leans on history until the session has
enough answers of its own to speak for itself.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from . import stats as S

#: Answers needed before the live session speed is trusted on its own.
FULL_TRUST_AT = 25


@dataclass
class LiveSession:
    started_at: float = 0.0
    answers: int = 0
    #: Wall-clock seconds actually spent studying (idle gaps excluded).
    active_seconds: float = 0.0
    answer_seconds: float = 0.0
    last_answer_at: Optional[float] = None
    #: ``(wall_seconds, answer_seconds)`` per answer, so an undo can be undone.
    per_card: List[tuple] = field(default_factory=list)
    #: Cards seen for the very first time during this session.
    introduced: set = field(default_factory=set)
    idle_cutoff_s: float = 60.0
    #: Answers already done when the session opened, used for the progress bar.
    initial_total: int = 0

    def reset(self, idle_cutoff_s: float = 60.0, initial_total: int = 0) -> None:
        self.started_at = time.time()
        self.answers = 0
        self.active_seconds = 0.0
        self.answer_seconds = 0.0
        self.last_answer_at = None
        self.per_card = []
        self.introduced = set()
        self.idle_cutoff_s = idle_cutoff_s
        self.initial_total = initial_total

    def record(self, answer_ms: int) -> None:
        now = time.time()
        answer_s = max(0.0, answer_ms / 1000.0)
        if self.last_answer_at is None:
            wall = answer_s
        else:
            gap = now - self.last_answer_at
            wall = answer_s if gap <= 0 or gap > self.idle_cutoff_s else max(gap, answer_s)
        self.last_answer_at = now
        self.answers += 1
        self.active_seconds += wall
        self.answer_seconds += answer_s
        self.per_card.append((wall, answer_s))

    def note_introduced(self, card_id: int) -> None:
        """Record a card being seen for the first time."""
        self.introduced.add(int(card_id))

    def undo_last(self) -> bool:
        """Remove the most recent answer.

        Undoing in Anki puts the card back, so leaving it counted would quietly
        inflate the session's card count and drag its pace.
        """
        if not self.per_card:
            return False
        wall, answer = self.per_card.pop()
        self.answers = max(0, self.answers - 1)
        self.active_seconds = max(0.0, self.active_seconds - wall)
        self.answer_seconds = max(0.0, self.answer_seconds - answer)
        # The next answer has no trustworthy predecessor now, so treat it as
        # opening a fresh stretch rather than measuring a gap across the undo.
        self.last_answer_at = None
        return True

    @property
    def wall_per_card(self) -> float:
        return self.active_seconds / self.answers if self.answers else 0.0

    @property
    def answer_per_card(self) -> float:
        return self.answer_seconds / self.answers if self.answers else 0.0

    def per_card_for(self, mode: str) -> float:
        return self.answer_per_card if mode == "answer" else self.wall_per_card

    def blended_speed(self, historical: float, mode: str) -> float:
        """Session speed weighted in gradually as evidence accumulates."""
        live = self.per_card_for(mode)
        if not live:
            return historical
        if not historical:
            return live
        weight = min(1.0, self.answers / float(FULL_TRUST_AT))
        return live * weight + historical * (1.0 - weight)

    def pace_ratio(self, goal_seconds: float, mode: str) -> Optional[float]:
        """How the session compares to a per-card goal. >1 means too slow."""
        if not self.answers or goal_seconds <= 0:
            return None
        return self.per_card_for(mode) / goal_seconds


@dataclass
class SessionSummary:
    """What a finished session amounted to, kept for the congratulations screen."""

    answers: int = 0
    seconds: float = 0.0
    introduced: int = 0
    ended_at: float = 0.0
    #: Seconds per card for the session, in whichever mode was configured.
    per_card: float = 0.0
    #: The historical figure it is being compared against, or 0 if unknown.
    usual_per_card: float = 0.0

    @property
    def has_comparison(self) -> bool:
        return self.per_card > 0 and self.usual_per_card > 0

    @property
    def pct_vs_usual(self) -> float:
        """Negative is faster than usual, positive is slower."""
        if not self.has_comparison:
            return 0.0
        return (self.per_card / self.usual_per_card - 1.0) * 100.0

    def is_fresh(self, within_seconds: float) -> bool:
        return bool(self.answers) and (time.time() - self.ended_at) <= within_seconds


def summarise(session: LiveSession, mode: str, usual: float) -> SessionSummary:
    return SessionSummary(
        answers=session.answers,
        seconds=session.active_seconds
        if mode != "answer"
        else session.answer_seconds,
        introduced=len(session.introduced),
        ended_at=time.time(),
        per_card=session.per_card_for(mode),
        usual_per_card=usual,
    )


SESSION = LiveSession()

#: The most recently finished session, shown on the congratulations screen.
LAST_SESSION = SessionSummary()


def remaining_estimate(snap, cfg, session: LiveSession) -> S.Estimate:
    """Re-run the ETA using the live session speed where it is meaningful."""
    mode = cfg["speed"]["mode"]
    speeds = snap.speeds
    live = session.per_card_for(mode)
    if live and session.answers:
        weight = min(1.0, session.answers / float(FULL_TRUST_AT))
        scale = 1.0
        base = speeds.overall.pick(mode)
        if base > 0:
            scale = (live * weight + base * (1.0 - weight)) / base
        speeds = _scaled(speeds, scale)
    return S.estimate(
        snap.workload,
        speeds,
        snap.behaviour,
        mode=mode,
        count_full_learning=cfg["speed"]["count_full_learning"],
        include_lapses=cfg["speed"]["include_lapses"],
    )


def _scaled(speeds: S.Speeds, factor: float) -> S.Speeds:
    """Speeds nudged by a factor, preserving the relative cost of each class."""
    if abs(factor - 1.0) < 1e-6:
        return speeds

    def scale(cs: S.ClassSpeed) -> S.ClassSpeed:
        return S.ClassSpeed(
            n=cs.n,
            answer=cs.answer * factor,
            wall=cs.wall * factor,
            answer_slow=cs.answer_slow * factor,
            wall_slow=cs.wall_slow * factor,
            answer_sd=cs.answer_sd * factor,
            wall_sd=cs.wall_sd * factor,
        )

    return S.Speeds(
        per_class={k: scale(v) for k, v in speeds.per_class.items()},
        overall=scale(speeds.overall),
        overhead_ratio=speeds.overhead_ratio,
        day_cv=speeds.day_cv,
    )
