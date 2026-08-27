"""Small custom widgets for the settings dialog."""

from __future__ import annotations

from typing import Optional, Set

from aqt.qt import *  # noqa: F401,F403

#: Keys that only ever act as part of a combination.
_MODIFIER_KEYS: Set[int] = set()


def _modifier_keys() -> Set[int]:
    global _MODIFIER_KEYS
    if not _MODIFIER_KEYS:
        _MODIFIER_KEYS = {
            int(Qt.Key.Key_Shift),
            int(Qt.Key.Key_Control),
            int(Qt.Key.Key_Alt),
            int(Qt.Key.Key_Meta),
            int(Qt.Key.Key_AltGr),
            int(Qt.Key.Key_CapsLock),
            int(Qt.Key.Key_NumLock),
            int(Qt.Key.Key_ScrollLock),
        }
    return _MODIFIER_KEYS


class HotkeyEdit(QWidget):
    """Click to record a shortcut, press the keys, let go.

    Qt's own ``QKeySequenceEdit`` behaves like a text field that quietly
    accumulates up to four chords and never tells you which state it is in.
    This records exactly one chord: press the combination you want and it is
    taken the moment you release everything, with an ✕ to clear it.
    """

    changed = pyqtSignal()

    PLACEHOLDER = "Not set"
    PROMPT = "Press keys…"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._sequence = QKeySequence()
        self._capturing = False
        self._pending: Optional[QKeySequence] = None
        self._down: Set[int] = set()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.button = QPushButton(self.PLACEHOLDER)
        self.button.setCheckable(True)
        self.button.setAutoDefault(False)
        self.button.setMinimumHeight(28)
        self.button.setMinimumWidth(150)
        self.button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.button.clicked.connect(self._on_button)
        layout.addWidget(self.button, 1)

        self.clear_button = QToolButton()
        self.clear_button.setText("✕")
        self.clear_button.setAutoRaise(True)
        self.clear_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clear_button.setToolTip("Clear this shortcut")
        self.clear_button.setFixedSize(28, 28)
        self.clear_button.clicked.connect(self.clear)
        layout.addWidget(self.clear_button, 0)

        self.setFocusProxy(self.button)
        self._refresh()

    # -- public API, mirroring QKeySequenceEdit --------------------------
    def keySequence(self) -> QKeySequence:
        return self._sequence

    def setKeySequence(self, sequence) -> None:
        if isinstance(sequence, str):
            sequence = QKeySequence(sequence)
        self._sequence = sequence or QKeySequence()
        self._stop_capture()
        self._refresh()

    def clear(self) -> None:
        self._sequence = QKeySequence()
        self._stop_capture()
        self._refresh()
        self.changed.emit()

    # -- capture ---------------------------------------------------------
    def _on_button(self) -> None:
        if self.button.isChecked():
            self._start_capture()
        else:
            self._stop_capture()
            self._refresh()

    def _start_capture(self) -> None:
        self._capturing = True
        self._pending = None
        self._down = set()
        self.button.setChecked(True)
        self.button.setText(self.PROMPT)
        self.button.setFocus(Qt.FocusReason.MouseFocusReason)
        self.grabKeyboard()

    def _stop_capture(self) -> None:
        if self._capturing:
            self.releaseKeyboard()
        self._capturing = False
        self._pending = None
        self._down = set()
        self.button.setChecked(False)

    def _commit(self) -> None:
        pending = self._pending
        self._stop_capture()
        if pending is not None and not pending.isEmpty():
            self._sequence = pending
            self._refresh()
            self.changed.emit()
        else:
            # Released without a real key -- modifiers alone are not a shortcut.
            self._refresh()

    def _refresh(self) -> None:
        if self._sequence.isEmpty():
            self.button.setText(self.PLACEHOLDER)
            self.button.setToolTip("Click, then press the keys you want")
        else:
            self.button.setText(
                self._sequence.toString(QKeySequence.SequenceFormat.NativeText)
            )
            self.button.setToolTip("Click to record a different shortcut")
        self.clear_button.setEnabled(not self._sequence.isEmpty())

    # -- events ----------------------------------------------------------
    def keyPressEvent(self, event) -> None:
        if not self._capturing or event.isAutoRepeat():
            super().keyPressEvent(event)
            return
        key = int(event.key())
        self._down.add(key)

        if key == int(Qt.Key.Key_Escape) and not self._has_modifier(event):
            self._stop_capture()
            self._refresh()
            event.accept()
            return
        if key in (int(Qt.Key.Key_Backspace), int(Qt.Key.Key_Delete)) and not self._has_modifier(
            event
        ):
            self.clear()
            event.accept()
            return
        if key in _modifier_keys():
            self.button.setText(self._preview(event))
            event.accept()
            return

        self._pending = self._sequence_for(event)
        self.button.setText(
            self._pending.toString(QKeySequence.SequenceFormat.NativeText)
        )
        event.accept()

    def keyReleaseEvent(self, event) -> None:
        if not self._capturing or event.isAutoRepeat():
            super().keyReleaseEvent(event)
            return
        self._down.discard(int(event.key()))
        if not self._down:
            self._commit()
        event.accept()

    def focusOutEvent(self, event) -> None:
        if self._capturing:
            self._stop_capture()
            self._refresh()
        super().focusOutEvent(event)

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _is_set(mods, flag) -> bool:
        """Whether a modifier flag is held.

        PyQt has returned both flag objects and plain ints from ``&`` over the
        years, so the result is reduced to a number before being tested.
        """
        combined = mods & flag
        try:
            return bool(combined.value)
        except AttributeError:
            return bool(combined)

    @classmethod
    def _has_modifier(cls, event) -> bool:
        mods = event.modifiers()
        return any(
            cls._is_set(mods, flag)
            for flag in (
                Qt.KeyboardModifier.ControlModifier,
                Qt.KeyboardModifier.AltModifier,
                Qt.KeyboardModifier.MetaModifier,
                Qt.KeyboardModifier.ShiftModifier,
            )
        )

    @staticmethod
    def _sequence_for(event) -> QKeySequence:
        """Build a one-chord sequence from a key event.

        ``keyCombination()`` is the supported route on Qt 6; the integer
        fallback keeps this working if that ever goes missing.
        """
        try:
            return QKeySequence(event.keyCombination())
        except (AttributeError, TypeError):
            try:
                return QKeySequence(int(event.modifiers().value) | int(event.key()))
            except Exception:
                return QKeySequence()

    def _preview(self, event) -> str:
        """Show the modifiers held so far, so the widget feels responsive."""
        names = []
        mods = event.modifiers()
        for flag, name in (
            (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
            (Qt.KeyboardModifier.AltModifier, "Alt"),
            (Qt.KeyboardModifier.ShiftModifier, "Shift"),
            (Qt.KeyboardModifier.MetaModifier, "Meta"),
        ):
            if self._is_set(mods, flag):
                names.append(name)
        return ("+".join(names) + "+…") if names else self.PROMPT


# ---------------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------------

MIN_HEIGHT = 28
MIN_TEXT_WIDTH = 240
MIN_NUMBER_WIDTH = 130


def apply_minimum_sizes(root: QWidget) -> None:
    """Give every input in a dialog a workable size.

    Qt sizes fields to their content by default, which leaves spin boxes and
    drop-downs too narrow to read comfortably.
    """
    for widget in root.findChildren(QAbstractSpinBox):
        widget.setMinimumHeight(MIN_HEIGHT)
        widget.setMinimumWidth(MIN_NUMBER_WIDTH)
    for widget in root.findChildren(QComboBox):
        widget.setMinimumHeight(MIN_HEIGHT)
        widget.setMinimumWidth(MIN_TEXT_WIDTH)
    for widget in root.findChildren(QLineEdit):
        if widget.parent() is not None and isinstance(widget.parent(), QAbstractSpinBox):
            continue  # the spin box's own editor is sized by the spin box
        widget.setMinimumHeight(MIN_HEIGHT)
        widget.setMinimumWidth(MIN_TEXT_WIDTH)
    for widget in root.findChildren(QPushButton):
        widget.setMinimumHeight(MIN_HEIGHT)


def expand_fields(form: QFormLayout) -> None:
    """Let fields use the width available instead of hugging their content."""
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    form.setHorizontalSpacing(12)
    form.setVerticalSpacing(8)
