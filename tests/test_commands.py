"""The home-screen buttons and the handler that receives their clicks.

These two live in different files and are joined only by a string. When the
add-on was renamed, the prefix changed length, the handler kept slicing a
hardcoded four characters, and both buttons silently stopped working -- the
click was swallowed rather than erroring. This ties the two ends together.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pace_estimator"))

import test_imports  # noqa: E402


def load():
    test_imports._install_stubs()
    import importlib

    runtime = importlib.import_module("src.runtime")
    config_dialog = importlib.import_module("src.ui.config_dialog")
    statswin = importlib.import_module("src.ui.statswin")
    calls = []
    config_dialog.open_config = lambda *a, **k: calls.append("config")
    statswin.open_stats = lambda *a, **k: calls.append("stats")
    return runtime, calls


def rendered_commands():
    """Every pycmd string the home panel actually emits."""
    from src import config as C
    from src.ui import home

    import test_render

    html = home.render(test_render.make_snapshot(), C.normalise({}))
    return re.findall(r"pycmd\('([^']+)'\)", html)


def test_the_panel_emits_commands():
    assert rendered_commands(), "the panel rendered no buttons at all"


def test_every_button_the_panel_draws_is_handled():
    runtime, calls = load()
    commands = rendered_commands()
    for command in commands:
        result = runtime._on_js_message(False, command, None)
        assert result == (True, None), "unhandled button: %r" % command
    assert len(calls) == len(commands)
    assert set(calls) == {"config", "stats"}


def test_commands_use_the_declared_prefix():
    runtime, _ = load()
    for command in rendered_commands():
        assert command.startswith(runtime.CMD_PREFIX)


def test_other_addons_messages_pass_straight_through():
    runtime, calls = load()
    for message in ("deckBrowser", "study", "", "paceX", "pace"):
        assert runtime._on_js_message(False, message, None) is False
        assert runtime._on_js_message(True, message, None) is True
    assert calls == []


def test_an_unknown_command_of_ours_is_not_swallowed():
    # Better to let Anki report an unhandled message than to absorb it.
    runtime, calls = load()
    assert runtime._on_js_message(False, "pace:nonsense", None) is False
    assert calls == []


def test_non_string_messages_are_ignored():
    runtime, _ = load()
    assert runtime._on_js_message(False, None, None) is False
    assert runtime._on_js_message(False, 42, None) is False
