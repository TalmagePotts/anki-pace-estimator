"""Review Pace — accurate study-speed measurement and ETAs for Anki."""

from __future__ import annotations


def _boot() -> None:
    from aqt import mw

    if mw is None:  # running outside the GUI (tests, tooling)
        return
    from .src.runtime import install

    install()


try:
    _boot()
except Exception:  # pragma: no cover - never take Anki down with us
    import traceback

    print("Review Pace failed to start:\n" + traceback.format_exc())
