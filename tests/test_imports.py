"""Import every module against stand-in Anki modules.

Catches import-time and module-level mistakes (typos in hook names used at
import, bad ``from`` targets) without needing an Anki installation.
"""

import os
import sys
import types

ROOT = os.path.join(os.path.dirname(__file__), "..", "pace_estimator")
sys.path.insert(0, ROOT)


class _Any:
    """Stands in for any Qt/Anki symbol, in any position."""

    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return _Any()

    def __getattr__(self, name):
        return _Any()

    def __or__(self, other):
        return _Any()

    def __ror__(self, other):
        return _Any()


class _StubMeta(type):
    def __getattr__(cls, name):
        return _Any()


class _StubBase(metaclass=_StubMeta):
    """Usable as a base class, and tolerant of any attribute access."""

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return _Any()


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Any()


def _install_stubs():
    for name in (
        "aqt",
        "aqt.qt",
        "aqt.utils",
        "aqt.webview",
        "anki",
    ):
        mod = _StubModule(name)
        sys.modules[name] = mod
    sys.modules["aqt"].mw = _Any()
    sys.modules["aqt"].gui_hooks = _Any()
    # ``from aqt.qt import *`` needs concrete names to export.
    qt = sys.modules["aqt.qt"]
    for symbol in (
        "QDialog QWidget QVBoxLayout QHBoxLayout QFormLayout QLabel QLineEdit "
        "QPushButton QCheckBox QSpinBox QDoubleSpinBox QComboBox QRadioButton "
        "QGroupBox QTabWidget QTreeWidget QTreeWidgetItem QListWidget "
        "QListWidgetItem QDialogButtonBox QAbstractItemView QHeaderView Qt "
        "QKeySequence QShortcut QMessageBox QAction QToolButton "
        "QAbstractSpinBox QTimer QKeyCombination QScrollArea QFrame QSizePolicy"
    ).split():
        setattr(qt, symbol, _StubMeta(symbol, (_StubBase,), {}))
    qt.pyqtSignal = _Any()
    qt.__all__ = [s for s in dir(qt) if s.startswith("Q") or s in ("Qt", "pyqtSignal")]


def test_every_module_imports():
    _install_stubs()
    import importlib

    for name in (
        "src.consts",
        "src.config",
        "src.stats",
        "src.collector",
        "src.session",
        "src.log",
        "src.ui.theme",
        "src.ui.widgets",
        "src.ui.home",
        "src.ui.reviewer",
        "src.ui.config_dialog",
        "src.ui.statswin",
        "src.runtime",
    ):
        importlib.import_module(name)
