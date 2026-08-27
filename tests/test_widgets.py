"""Logic checks for the custom shortcut widget, with Qt stubbed out.

The widget itself needs a running Qt application, but its decision-making --
which keys count as modifiers, how a held combination is previewed, how a flag
is tested -- is plain Python and worth pinning down.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))

import test_imports  # noqa: E402


class FakeFlag:
    """Stands in for a PyQt flag that exposes ``.value``."""

    def __init__(self, value):
        self.value = value

    def __and__(self, other):
        return FakeFlag(self.value & other.value)


class PlainIntFlag(int):
    """Stands in for the older PyQt behaviour of returning a bare int."""

    def __and__(self, other):
        return PlainIntFlag(int(self) & int(other))


def hotkey_class():
    test_imports._install_stubs()
    import importlib

    return importlib.import_module("src.ui.widgets").HotkeyEdit


def test_flag_test_handles_objects_with_value():
    HotkeyEdit = hotkey_class()
    assert HotkeyEdit._is_set(FakeFlag(0b110), FakeFlag(0b010)) is True
    assert HotkeyEdit._is_set(FakeFlag(0b100), FakeFlag(0b010)) is False


def test_flag_test_handles_plain_ints():
    HotkeyEdit = hotkey_class()
    assert HotkeyEdit._is_set(PlainIntFlag(0b110), PlainIntFlag(0b010)) is True
    assert HotkeyEdit._is_set(PlainIntFlag(0b001), PlainIntFlag(0b010)) is False


def test_widget_exposes_the_qkeysequenceedit_api():
    HotkeyEdit = hotkey_class()
    for name in ("keySequence", "setKeySequence", "clear", "changed"):
        assert hasattr(HotkeyEdit, name), name


def test_sizing_constants_are_usable():
    test_imports._install_stubs()
    import importlib

    w = importlib.import_module("src.ui.widgets")
    assert w.MIN_HEIGHT >= 24
    assert w.MIN_TEXT_WIDTH >= 200
    assert w.MIN_NUMBER_WIDTH >= 100


def config_module():
    test_imports._install_stubs()
    import importlib

    return importlib.import_module("src.ui.config_dialog")


def test_label_height_grows_with_the_text():
    height = config_module().estimated_label_height
    one_line = height("Short note.")
    long_line = height("x" * 300)
    assert one_line > 0
    assert long_line >= one_line * 4


def test_label_height_counts_explicit_paragraphs():
    height = config_module().estimated_label_height
    assert height("a\n\nb") > height("a")


def test_every_tab_but_the_deck_list_scrolls():
    # The deck tab scrolls itself via its tree; the others are taller than the
    # dialog on a small screen and must not be allowed to compress.
    import inspect

    source = inspect.getsource(config_module().ConfigDialog._build)
    assert source.count("_scrolled(") == 4
    assert "_scrolled(self._decks_tab())" not in source
