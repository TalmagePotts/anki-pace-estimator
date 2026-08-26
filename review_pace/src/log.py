"""Diagnostics.

Add-on failures inside Anki are easy to miss: a hook that raises can leave a
surface silently blank.  Everything interesting goes to a log file next to the
collection so problems can be read back after the fact, and to stdout when
Anki is started from a terminal.
"""

from __future__ import annotations

import os
import time
import traceback
from typing import Any, Optional

_enabled = False
_path: Optional[str] = None
_lines: list = []
MAX_MEMORY_LINES = 400


def configure(enabled: bool) -> None:
    global _enabled, _path
    _enabled = bool(enabled)
    if _path is None:
        _path = _default_path()


def _default_path() -> Optional[str]:
    try:
        from aqt import mw

        base = mw.pm.addonFolder() if mw and mw.pm else None
        if base:
            return os.path.join(base, "review_pace_debug.log")
    except Exception:
        pass
    return None


def recent() -> str:
    """The in-memory tail, for showing inside Anki."""
    return "\n".join(_lines)


def path() -> Optional[str]:
    return _path


def log(message: str, *args: Any) -> None:
    if args:
        try:
            message = message % args
        except Exception:
            message = "%s %r" % (message, args)
    line = "%s  %s" % (time.strftime("%H:%M:%S"), message)
    _lines.append(line)
    if len(_lines) > MAX_MEMORY_LINES:
        del _lines[: len(_lines) - MAX_MEMORY_LINES]
    if not _enabled:
        return
    print("[Review Pace] " + line)
    if _path:
        try:
            with open(_path, "a", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%d ") + line + "\n")
        except Exception:
            pass


def exception(context: str) -> None:
    """Record a traceback without letting it escape into Anki's error dialog."""
    log("ERROR in %s\n%s", context, traceback.format_exc())


def guard(context: str):
    """Decorator: log and swallow anything a hook raises.

    A hook that throws can break the screen it is attached to, so every hook
    this add-on registers is wrapped.
    """

    def wrap(func):
        def inner(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                exception(context)
                return None

        inner.__name__ = getattr(func, "__name__", "inner")
        inner.__doc__ = func.__doc__
        return inner

    return wrap
