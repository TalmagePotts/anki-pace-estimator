"""Settings dialog.

Replaces Anki's raw JSON config editor.  Every option the add-on has is
reachable here, grouped so that the two things people change often -- which
decks are tracked and what appears on the home screen -- are the first two
tabs.
"""

from __future__ import annotations

import copy
from typing import Dict, List, Optional, Tuple

from aqt import mw
from aqt.qt import *  # noqa: F401,F403
from aqt.utils import restoreGeom, saveGeom, tooltip

from .. import config as CFG
from .. import consts as K
from ..collector import all_deck_rows
from .widgets import HotkeyEdit, apply_minimum_sizes, expand_fields

GOAL_COL = 1


def _scrolled(page: QWidget) -> QScrollArea:
    """Put a tab's contents in a vertical scroll area.

    A QFormLayout given less height than its rows need does not scroll on its
    own -- it squeezes the rows until they overlap. Scrolling keeps every row
    at its proper height however small the window is.
    """
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(page)
    return area


#: Roughly how many characters of help text fit on one line at the widths this
#: dialog uses. Only used to reserve height, so it does not need to be exact.
_CHARS_PER_LINE = 74
_LINE_HEIGHT = 17


def _label(text: str, muted: bool = True) -> QLabel:
    """Explanatory text under a group of settings.

    Word-wrapped labels report their height as a function of their width, which
    layouts are notoriously bad at accounting for -- underestimate it and the
    rows above end up drawn on top of each other. Reserving a floor based on
    the text length costs nothing and removes that failure mode.
    """
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    if muted:
        font = lab.font()
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1.0))
        lab.setFont(font)
        lab.setStyleSheet("color: palette(mid);")
    lab.setMinimumHeight(estimated_label_height(text))
    lab.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
    return lab


def estimated_label_height(text: str) -> int:
    """A lower bound on the height wrapped ``text`` will need."""
    lines = 0
    for paragraph in text.split("\n"):
        lines += max(1, -(-len(paragraph) // _CHARS_PER_LINE))
    return lines * _LINE_HEIGHT


class DeckTree(QTreeWidget):
    """Deck hierarchy with a checkbox per deck and an editable goal column."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Deck", "Card goal (s)"])
        self.setColumnCount(2)
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # Fixed and generous: this column is typed into, so it has to stay wide
        # enough to use even when every deck leaves it blank.
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, 130)
        self.setStyleSheet("QTreeWidget::item { height: 26px; } "
                           "QTreeWidget { font-size: 13px; }")
        self._items: Dict[int, QTreeWidgetItem] = {}

    def populate(self, rows: List[Tuple[int, str]], checked: List[int],
                 goals: Dict[str, float]) -> None:
        self.clear()
        self._items = {}
        checked_set = set(checked)
        nodes: Dict[str, QTreeWidgetItem] = {}
        for did, name in sorted(rows, key=lambda r: r[1].lower()):
            parts = name.split("::")
            path = ""
            parent: Optional[QTreeWidgetItem] = None
            for depth, part in enumerate(parts):
                path = part if not path else path + "::" + part
                node = nodes.get(path)
                if node is None:
                    node = QTreeWidgetItem([part, ""])
                    node.setFlags(
                        node.flags()
                        | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsEditable
                    )
                    node.setCheckState(0, Qt.CheckState.Unchecked)
                    if parent is None:
                        self.addTopLevelItem(node)
                    else:
                        parent.addChild(node)
                    nodes[path] = node
                if depth == len(parts) - 1:
                    node.setData(0, Qt.ItemDataRole.UserRole, did)
                    if did in checked_set:
                        node.setCheckState(0, Qt.CheckState.Checked)
                    goal = goals.get(str(did))
                    if goal:
                        node.setText(GOAL_COL, "%g" % float(goal))
                    self._items[did] = node
                parent = node
        self.expandToDepth(0)

    def checked_ids(self) -> List[int]:
        out: List[int] = []
        for did, item in self._items.items():
            if item.checkState(0) == Qt.CheckState.Checked:
                out.append(did)
        return sorted(out)

    def goals(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for did, item in self._items.items():
            raw = item.text(GOAL_COL).strip()
            if not raw:
                continue
            try:
                val = float(raw)
            except ValueError:
                continue
            if val > 0:
                out[str(did)] = val
        return out

    def set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for item in self._items.values():
            item.setCheckState(0, state)

    def filter(self, needle: str) -> None:
        needle = needle.strip().lower()

        def visit(item: QTreeWidgetItem) -> bool:
            match = needle in item.text(0).lower() if needle else True
            child_match = False
            for i in range(item.childCount()):
                child_match = visit(item.child(i)) or child_match
            item.setHidden(not (match or child_match))
            return match or child_match

        for i in range(self.topLevelItemCount()):
            visit(self.topLevelItem(i))


class ConfigDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent or mw)
        self.setWindowTitle("%s — settings" % K.ADDON_NAME)
        self.setMinimumSize(720, 620)
        self.cfg = CFG.normalise(mw.addonManager.getConfig(K.ADDON_PACKAGE))
        self._original = copy.deepcopy(self.cfg)
        self._build()
        self._load()
        restoreGeom(self, "pace_config")

    # -- construction ----------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        self.tabs = QTabWidget()
        # Only the deck tab is unscrolled: it is short, and it holds a tree
        # that does its own scrolling. The rest are taller than the dialog on
        # a small screen, and without a scroll area Qt compresses their rows
        # past the minimum size and they draw on top of each other.
        self.tabs.addTab(self._decks_tab(), "Decks")
        self.tabs.addTab(_scrolled(self._display_tab()), "Home screen")
        self.tabs.addTab(_scrolled(self._speed_tab()), "Speed && accuracy")
        self.tabs.addTab(_scrolled(self._reviewer_tab()), "While reviewing")
        self.tabs.addTab(_scrolled(self._toolbar_tab()), "Toolbar")
        outer.addWidget(self.tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self._restore_defaults
        )
        outer.addWidget(buttons)

        # Applied once, at the end, so every input on every tab is covered --
        # including ones added later.
        for form in self.findChildren(QFormLayout):
            expand_fields(form)
        apply_minimum_sizes(self)

    def _decks_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(
            _label(
                "Tick the decks you want tracked. With nothing ticked the add-on "
                "reports on your whole collection."
            )
        )
        search_row = QHBoxLayout()
        self.deck_search = QLineEdit()
        self.deck_search.setPlaceholderText("Filter decks…")
        self.deck_search.setClearButtonEnabled(True)
        search_row.addWidget(self.deck_search)
        for text, slot in (
            ("All", lambda: self.deck_tree.set_all(True)),
            ("None", lambda: self.deck_tree.set_all(False)),
            ("Current", self._select_current_deck),
        ):
            btn = QPushButton(text)
            btn.setAutoDefault(False)
            btn.clicked.connect(slot)
            search_row.addWidget(btn)
        lay.addLayout(search_row)

        self.deck_tree = DeckTree()
        self.deck_search.textChanged.connect(self.deck_tree.filter)
        lay.addWidget(self.deck_tree, 1)

        self.include_subdecks = QCheckBox("Include subdecks of ticked decks")
        self.follow_current = QCheckBox(
            "While reviewing, measure the deck I am actually in"
        )
        lay.addWidget(self.include_subdecks)
        lay.addWidget(self.follow_current)
        lay.addWidget(
            _label(
                "The second column sets a per-card time goal for that deck, "
                "overriding the global goal on the “While reviewing” tab. "
                "Leave it blank to use the global value."
            )
        )
        return page

    def _display_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(
            _label("Tick what you want shown, and drag to reorder.")
        )
        row = QHBoxLayout()
        self.comp_list = QListWidget()
        self.comp_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.comp_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.comp_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.comp_list.setMinimumHeight(150)
        row.addWidget(self.comp_list, 1)
        side = QVBoxLayout()
        up = QPushButton("↑")
        down = QPushButton("↓")
        for btn, delta in ((up, -1), (down, 1)):
            btn.setFixedWidth(34)
            btn.setAutoDefault(False)
            btn.clicked.connect(lambda _=False, d=delta: self._move_component(d))
            side.addWidget(btn)
        side.addStretch(1)
        row.addLayout(side)
        lay.addLayout(row)

        form = QFormLayout()
        self.show_deck_browser = QCheckBox("Show on the deck list")
        self.show_overview = QCheckBox("Show on a deck's study screen")
        self.show_title = QCheckBox("Show the panel heading")
        self.panel_title = QLineEdit()
        self.show_range = QCheckBox("Show the ETA as a range")
        self.show_finish = QCheckBox("Show the clock time you finish at")
        self.clock_24h = QCheckBox("Use 24-hour times")
        self.compact = QCheckBox("Compact spacing")
        self.columns = QSpinBox()
        self.columns.setRange(0, 6)
        self.columns.setSpecialValueText("Auto")
        self.font_scale = QDoubleSpinBox()
        self.font_scale.setRange(0.7, 2.0)
        self.font_scale.setSingleStep(0.05)
        self.speed_display = QComboBox()
        self.speed_display.addItem("Average per card", "mean")
        self.speed_display.addItem("Typical card (median)", "typical")
        self.speed_display.addItem("Average, with the typical card underneath", "both")
        self.session_minutes = QSpinBox()
        self.session_minutes.setRange(0, 1440)
        self.session_minutes.setSuffix(" min")
        self.session_minutes.setSpecialValueText("Never show it")
        self.period_mode = QComboBox()
        self.period_mode.addItem("Rolling (last 7 / 30 days)", "rolling")
        self.period_mode.addItem("Calendar (this week / this month)", "calendar")
        self.accent = QLineEdit()
        self.accent.setPlaceholderText("Follow Anki's theme — or e.g. #3a7bd5")

        for widget in (self.show_deck_browser, self.show_overview, self.show_title):
            form.addRow("", widget)
        form.addRow("Heading text", self.panel_title)
        form.addRow("", self.show_range)
        form.addRow("", self.show_finish)
        form.addRow("", self.clock_24h)
        form.addRow("", self.compact)
        form.addRow("Columns", self.columns)
        form.addRow("Text size", self.font_scale)
        form.addRow("Show speed as", self.speed_display)
        form.addRow("Keep the session summary for", self.session_minutes)
        form.addRow("Week / month", self.period_mode)
        form.addRow("Accent colour", self.accent)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def _speed_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)

        mode_box = QGroupBox("Which speed drives the estimate")
        mode_lay = QVBoxLayout(mode_box)
        self.mode_wall = QRadioButton("Wall-clock — time on the card plus the gap to the next one")
        self.mode_answer = QRadioButton("Answer only — question shown until you press a button")
        mode_lay.addWidget(self.mode_wall)
        mode_lay.addWidget(self.mode_answer)
        mode_lay.addWidget(
            _label(
                "Wall-clock is the honest one: it includes rendering, your pause "
                "before flipping the card, and the moment between cards. Both "
                "numbers are always shown; this only picks which one the ETA uses."
            )
        )
        lay.addWidget(mode_box)

        acc_box = QGroupBox("Accuracy")
        form = QFormLayout(acc_box)
        self.per_class = QCheckBox("Measure new, young, mature and relearning cards separately")
        self.per_deck_speeds = QCheckBox("Measure each deck separately")
        self.full_learning = QCheckBox("Count every learning step, not one answer per new card")
        self.include_lapses = QCheckBox("Allow for reviews you will fail and see again today")
        self.estimator = QComboBox()
        self.estimator.addItem("Average — unbiased for totals (recommended)", "mean")
        self.estimator.addItem("Average, ignoring your slowest 10%", "trimmed")
        self.estimator.addItem("Median — reads low, underestimates totals", "median")
        self.lookback = QSpinBox()
        self.lookback.setRange(1, 3650)
        self.lookback.setSuffix(" days")
        self.idle_cutoff = QSpinBox()
        self.idle_cutoff.setRange(5, 3600)
        self.idle_cutoff.setSuffix(" s")
        self.max_answer = QSpinBox()
        self.max_answer.setRange(5, 600)
        self.max_answer.setSuffix(" s")
        self.max_rows = QSpinBox()
        self.max_rows.setRange(500, 1000000)
        self.max_rows.setSingleStep(5000)
        self.max_rows.setGroupSeparatorShown(True)

        form.addRow("", self.per_class)
        form.addRow("", self.per_deck_speeds)
        form.addRow("", self.full_learning)
        form.addRow("", self.include_lapses)
        form.addRow("Estimates built from", self.estimator)

        self.time_of_day = QCheckBox("Adjust the estimate for the time of day")
        self.tod_min_days = QSpinBox()
        self.tod_min_days.setRange(1, 365)
        self.tod_min_days.setSuffix(" days")
        self.tod_shrinkage = QSpinBox()
        self.tod_shrinkage.setRange(0, 10000)
        self.tod_shrinkage.setSingleStep(10)
        self.feature_ease = QCheckBox("Ease factor (hard / normal / easy cards)")
        self.feature_interval = QCheckBox("Interval (how far apart the card is scheduled)")
        form.addRow("", self.time_of_day)
        form.addRow("An hour must span", self.tod_min_days)
        form.addRow("Samples before an hour is believed", self.tod_shrinkage)
        form.addRow("Also split speeds by", self.feature_ease)
        form.addRow("", self.feature_interval)
        form.addRow("Look back over", self.lookback)
        form.addRow("Treat a gap longer than", self.idle_cutoff)
        form.addRow("Cap a single answer at", self.max_answer)
        form.addRow("Reviews to scan at most", self.max_rows)
        lay.addWidget(acc_box)
        lay.addWidget(
            _label(
                "A gap longer than the cutoff counts as a break, not study time, so "
                "walking away mid-session no longer wrecks your average.\n\n"
                "On the collection this was tested against, the median ran 43% short "
                "of real session times, because the slowest tenth of cards used 38% "
                "of the time and a median discards that tail. The extra splits above "
                "changed accuracy by well under a point — day-to-day variation "
                "dominates — so they are off by default. A split falls back to its "
                "card type until it has enough samples to stand on its own.\n\n"
                "Measuring each deck separately is the single biggest thing on this "
                "tab: decks differ far more than card types do. A deck with too "
                "little history of its own is priced from the deck above it.\n\n"
                "Time of day is worth a little, but only with the guard above: "
                "hourly averages are mostly a record of which days you studied in "
                "which hours, so an hour has to appear on several separate days "
                "before it may move an estimate. Tools ▸ Pace Estimator shows every "
                "hour and whether it qualified."
            )
        )
        lay.addStretch(1)
        return page

    def _reviewer_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)

        hud = QGroupBox("Heads-up display")
        hform = QFormLayout(hud)
        self.overlay_enabled = QCheckBox("Show while reviewing")
        self.overlay_remaining = QCheckBox("Cards left")
        self.overlay_eta = QCheckBox("Time remaining")
        self.overlay_speed = QCheckBox("This session's pace")
        self.overlay_elapsed = QCheckBox("Time spent this session")
        self.overlay_vs_normal = QCheckBox("How today compares to your usual pace")
        self.overlay_bar = QCheckBox("Progress bar")
        self.overlay_pos = QComboBox()
        for pos in K.OVERLAY_POSITIONS:
            self.overlay_pos.addItem(pos.replace("-", " ").title(), pos)
        self.overlay_opacity = QDoubleSpinBox()
        self.overlay_opacity.setRange(0.2, 1.0)
        self.overlay_opacity.setSingleStep(0.05)
        self.overlay_scale = QDoubleSpinBox()
        self.overlay_scale.setRange(0.6, 2.0)
        self.overlay_scale.setSingleStep(0.05)
        self.overlay_hotkey = HotkeyEdit()

        hform.addRow("", self.overlay_enabled)
        hform.addRow("Show", self.overlay_remaining)
        hform.addRow("", self.overlay_eta)
        hform.addRow("", self.overlay_speed)
        hform.addRow("", self.overlay_elapsed)
        hform.addRow("", self.overlay_vs_normal)
        hform.addRow("", self.overlay_bar)
        hform.addRow("Corner", self.overlay_pos)
        hform.addRow("Opacity", self.overlay_opacity)
        hform.addRow("Size", self.overlay_scale)
        hform.addRow("Toggle with", self.overlay_hotkey)
        lay.addWidget(hud)

        goal = QGroupBox("Per-card time goal")
        gform = QFormLayout(goal)
        self.goal_enabled = QCheckBox("Keep an eye on how long each card takes")
        self.goal_seconds = QDoubleSpinBox()
        self.goal_seconds.setRange(1.0, 600.0)
        self.goal_seconds.setSuffix(" s")
        self.goal_seconds.setDecimals(1)
        self.timer_phase = QComboBox()
        self.timer_phase.addItem("One clock for the whole card", "whole_card")
        self.timer_phase.addItem("Only while the question is showing", "question")
        self.timer_phase.addItem("Only once I reveal the answer", "answer")
        self.timer_phase.addItem("A separate clock for the answer", "separate")
        self.answer_seconds = QDoubleSpinBox()
        self.answer_seconds.setRange(1.0, 600.0)
        self.answer_seconds.setSuffix(" s")
        self.answer_seconds.setDecimals(1)
        self.alert_phase = QComboBox()
        self.alert_phase.addItem("Either side of the card", "always")
        self.alert_phase.addItem("Only while the question is showing", "question")
        self.alert_phase.addItem("Only once I reveal the answer", "answer")

        self.goal_show_timer = QCheckBox("Show a running timer on every card")
        self.goal_countdown = QCheckBox("Count down to zero (rather than up)")
        self.goal_pos = QComboBox()
        for pos in K.OVERLAY_POSITIONS:
            self.goal_pos.addItem(pos.replace("-", " ").title(), pos)
        self.goal_scale = QDoubleSpinBox()
        self.goal_scale.setRange(0.6, 2.0)
        self.goal_scale.setSingleStep(0.05)

        self.alert_style = QComboBox()
        self.alert_style.addItem("Nothing", "none")
        self.alert_style.addItem("Turn the timer red", "badge")
        self.alert_style.addItem("Big symbol over the card", "exclamation")
        self.alert_style.addItem("Both", "both")
        self.alert_text = QLineEdit()
        self.alert_text.setMaxLength(8)
        self.alert_text.setPlaceholderText("!")
        self.alert_pos = QComboBox()
        self.alert_pos.addItem("Bottom middle", "bottom")
        self.alert_pos.addItem("Lower half", "lower-half")
        self.alert_pos.addItem("Middle of the screen", "center")
        self.alert_pos.addItem("Upper half", "upper-half")
        self.alert_pos.addItem("Top middle", "top")
        self.alert_scale = QDoubleSpinBox()
        self.alert_scale.setRange(0.5, 4.0)
        self.alert_scale.setSingleStep(0.1)
        self.goal_pulse = QCheckBox("Pulse the warning")
        self.goal_sound = QCheckBox("Play a short chime when time is up")

        gform.addRow("", self.goal_enabled)
        gform.addRow("Time per card", self.goal_seconds)
        gform.addRow("Clock runs", self.timer_phase)
        gform.addRow("Time for the answer", self.answer_seconds)
        gform.addRow("Warn me on", self.alert_phase)
        gform.addRow("", self.goal_show_timer)
        gform.addRow("", self.goal_countdown)
        gform.addRow("Timer corner", self.goal_pos)
        gform.addRow("Timer size", self.goal_scale)
        gform.addRow("When time is up", self.alert_style)
        gform.addRow("Symbol", self.alert_text)
        gform.addRow("Symbol position", self.alert_pos)
        gform.addRow("Symbol size", self.alert_scale)
        gform.addRow("", self.goal_pulse)
        gform.addRow("", self.goal_sound)

        preview = QPushButton("Preview it here")
        preview.setAutoDefault(False)
        preview.clicked.connect(self._preview_goal)
        gform.addRow("", preview)
        lay.addWidget(goal)
        lay.addWidget(
            _label(
                "The warning fires at exactly the time you set above — there is no "
                "early stage. Turn the timer off and pick “Big symbol” if you would "
                "rather see nothing at all until you are out of time. Per-deck times "
                "are set on the Decks tab.\n\n"
                "“Clock runs” and “Warn me on” are independent: you can time the "
                "whole card but only be warned once the answer is showing, or give "
                "the answer its own separate allowance. “Time for the answer” "
                "applies only to the separate clock.\n\n"
                "It is drawn by the add-on, so it works on every card in every note "
                "type — nothing to add to your templates."
            )
        )
        lay.addStretch(1)

        for widget in (self.goal_enabled, self.goal_show_timer):
            widget.toggled.connect(self._sync_goal_enabled)
        for combo in (self.alert_style, self.timer_phase):
            combo.currentIndexChanged.connect(self._sync_goal_enabled)
        return page

    def _toolbar_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        form = QFormLayout()
        self.toolbar_enabled = QCheckBox("Show an item in the top toolbar")
        self.toolbar_template = QLineEdit()
        self.toolbar_hide_empty = QCheckBox("Hide it when nothing is waiting")
        self.toolbar_click = QComboBox()
        self.toolbar_click.addItem("Open the stats window", "stats")
        self.toolbar_click.addItem("Open these settings", "config")
        self.toolbar_click.addItem("Do nothing", "none")
        form.addRow("", self.toolbar_enabled)
        form.addRow("Text", self.toolbar_template)
        form.addRow("", self.toolbar_hide_empty)
        form.addRow("Clicking it", self.toolbar_click)
        lay.addLayout(form)
        lay.addWidget(
            _label(
                "Placeholders: {eta} time remaining · {eta_slow} the slow end of "
                "the range · {cards} cards waiting · {due} · {new} · {learn} · "
                "{speed} seconds per card · {done} answered today · {finish} finish time."
            )
        )

        trouble = QGroupBox("Troubleshooting")
        tlay = QVBoxLayout(trouble)
        self.debug = QCheckBox("Write a debug log")
        tlay.addWidget(self.debug)
        log_btn = QPushButton("Show recent activity…")
        log_btn.setAutoDefault(False)
        log_btn.clicked.connect(self._show_log)
        tlay.addWidget(log_btn)
        lay.addWidget(trouble)
        lay.addStretch(1)
        return page

    def _show_log(self) -> None:
        from .. import log as L

        text = L.recent() or "Nothing recorded yet."
        if L.path():
            text += "\n\nFull log: %s" % L.path()
        box = QMessageBox(self)
        box.setWindowTitle("%s — recent activity" % K.ADDON_NAME)
        box.setText("What the add-on has been doing:")
        box.setDetailedText(text)
        box.exec()

    def _sync_goal_enabled(self) -> None:
        on = self.goal_enabled.isChecked()
        timer = on and self.goal_show_timer.isChecked()
        style = self.alert_style.currentData()
        symbol = on and style in ("exclamation", "both")
        for widget in (
            self.goal_seconds, self.timer_phase, self.alert_phase,
            self.goal_show_timer, self.alert_style, self.goal_pulse, self.goal_sound,
        ):
            widget.setEnabled(on)
        self.answer_seconds.setEnabled(
            on and self.timer_phase.currentData() == "separate"
        )
        for widget in (self.goal_countdown, self.goal_pos, self.goal_scale):
            widget.setEnabled(timer)
        for widget in (self.alert_text, self.alert_pos, self.alert_scale):
            widget.setEnabled(symbol)

    def _preview_goal(self) -> None:
        """Run the badge and warning on this dialog's parent window.

        Waiting for a card to time out is a slow way to check a setting, so the
        preview uses a two second goal against whatever is on screen now.
        """
        from .. import runtime

        cfg = self._collect()
        runtime.preview_goal(cfg)

    # -- load / save -----------------------------------------------------
    def _load(self) -> None:
        cfg = self.cfg
        self.deck_tree.populate(
            all_deck_rows(mw.col), cfg["decks"]["ids"], cfg["goal"]["per_deck_seconds"]
        )
        self.include_subdecks.setChecked(cfg["decks"]["include_subdecks"])
        self.follow_current.setChecked(cfg["decks"]["follow_current_deck"])

        self.comp_list.clear()
        for entry in cfg["display"]["components"]:
            item = QListWidgetItem(K.COMPONENT_LABELS.get(entry["id"], entry["id"]))
            item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if entry["enabled"] else Qt.CheckState.Unchecked
            )
            item.setToolTip(K.COMPONENT_HELP.get(entry["id"], ""))
            self.comp_list.addItem(item)

        d = cfg["display"]
        self.show_deck_browser.setChecked(d["show_on_deck_browser"])
        self.show_overview.setChecked(d["show_on_overview"])
        self.show_title.setChecked(d["show_title"])
        self.panel_title.setText(d["title"])
        self.show_range.setChecked(d["show_eta_range"])
        self.show_finish.setChecked(d["show_finish_time"])
        self.clock_24h.setChecked(d["clock_24h"])
        self.compact.setChecked(d["compact"])
        self.columns.setValue(d["columns"])
        self.font_scale.setValue(d["font_scale"])
        self.accent.setText(d["accent"])
        self._set_combo(self.speed_display, d["speed_display"])
        self.session_minutes.setValue(d["session_summary_minutes"])
        self._set_combo(self.period_mode, d["period_mode"])

        s = cfg["speed"]
        self.mode_wall.setChecked(s["mode"] == K.SPEED_MODE_WALL)
        self.mode_answer.setChecked(s["mode"] != K.SPEED_MODE_WALL)
        self.per_class.setChecked(s["per_card_class"])
        self.per_deck_speeds.setChecked(s["per_deck_speeds"])
        self.full_learning.setChecked(s["count_full_learning"])
        self.include_lapses.setChecked(s["include_lapses"])
        self._set_combo(self.estimator, s["estimator"])
        self.time_of_day.setChecked(s["time_of_day"])
        self.tod_min_days.setValue(s["time_of_day_min_days"])
        self.tod_shrinkage.setValue(s["time_of_day_shrinkage"])
        self.feature_ease.setChecked("ease" in s["features"])
        self.feature_interval.setChecked("interval" in s["features"])
        self.lookback.setValue(s["lookback_days"])
        self.idle_cutoff.setValue(s["idle_cutoff_s"])
        self.max_answer.setValue(s["max_answer_s"])
        self.max_rows.setValue(s["max_rows"])

        o = cfg["overlay"]
        self.overlay_enabled.setChecked(o["enabled"])
        self.overlay_remaining.setChecked(o["show_remaining"])
        self.overlay_eta.setChecked(o["show_eta"])
        self.overlay_speed.setChecked(o["show_session_speed"])
        self.overlay_elapsed.setChecked(o["show_elapsed"])
        self.overlay_vs_normal.setChecked(o["show_pace_vs_normal"])
        self.overlay_bar.setChecked(o["show_progress_bar"])
        self._set_combo(self.overlay_pos, o["position"])
        self.overlay_opacity.setValue(o["opacity"])
        self.overlay_scale.setValue(o["scale"])
        self.overlay_hotkey.setKeySequence(o["hotkey"])

        g = cfg["goal"]
        self.goal_enabled.setChecked(g["enabled"])
        self.goal_seconds.setValue(g["seconds_per_card"])
        self.goal_show_timer.setChecked(g["show_timer"])
        self.goal_countdown.setChecked(g["count_down"])
        self._set_combo(self.goal_pos, g["badge_position"])
        self.goal_scale.setValue(g["scale"])
        self._set_combo(self.alert_style, g["alert_style"])
        self.alert_text.setText(g["alert_text"])
        self._set_combo(self.alert_pos, g["alert_position"])
        self.alert_scale.setValue(g["alert_scale"])
        self.goal_pulse.setChecked(g["pulse_when_over"])
        self.goal_sound.setChecked(g["sound"])
        self._set_combo(self.timer_phase, g["timer_phase"])
        self.answer_seconds.setValue(g["answer_seconds"])
        self._set_combo(self.alert_phase, g["alert_phase"])
        self.debug.setChecked(cfg.get("debug", False))
        self._sync_goal_enabled()

        t = cfg["toolbar"]
        self.toolbar_enabled.setChecked(t["enabled"])
        self.toolbar_template.setText(t["template"])
        self.toolbar_hide_empty.setChecked(t["hide_when_empty"])
        self._set_combo(self.toolbar_click, t["click_action"])

    def _collect(self) -> Dict:
        cfg = copy.deepcopy(self.cfg)
        cfg["decks"]["ids"] = self.deck_tree.checked_ids()
        cfg["decks"]["include_subdecks"] = self.include_subdecks.isChecked()
        cfg["decks"]["follow_current_deck"] = self.follow_current.isChecked()

        components = []
        for i in range(self.comp_list.count()):
            item = self.comp_list.item(i)
            components.append(
                {
                    "id": item.data(Qt.ItemDataRole.UserRole),
                    "enabled": item.checkState() == Qt.CheckState.Checked,
                }
            )
        cfg["display"].update(
            {
                "components": components,
                "show_on_deck_browser": self.show_deck_browser.isChecked(),
                "show_on_overview": self.show_overview.isChecked(),
                "show_title": self.show_title.isChecked(),
                "title": self.panel_title.text().strip() or K.ADDON_NAME,
                "show_eta_range": self.show_range.isChecked(),
                "show_finish_time": self.show_finish.isChecked(),
                "clock_24h": self.clock_24h.isChecked(),
                "compact": self.compact.isChecked(),
                "columns": self.columns.value(),
                "font_scale": self.font_scale.value(),
                "accent": self.accent.text().strip(),
                "speed_display": self.speed_display.currentData(),
                "session_summary_minutes": self.session_minutes.value(),
                "period_mode": self.period_mode.currentData(),
            }
        )
        cfg["speed"].update(
            {
                "mode": K.SPEED_MODE_WALL if self.mode_wall.isChecked() else K.SPEED_MODE_ANSWER,
                "per_card_class": self.per_class.isChecked(),
                "per_deck_speeds": self.per_deck_speeds.isChecked(),
                "count_full_learning": self.full_learning.isChecked(),
                "include_lapses": self.include_lapses.isChecked(),
                "estimator": self.estimator.currentData(),
                "time_of_day": self.time_of_day.isChecked(),
                "time_of_day_min_days": self.tod_min_days.value(),
                "time_of_day_shrinkage": self.tod_shrinkage.value(),
                "features": [
                    name
                    for name, box in (
                        ("ease", self.feature_ease),
                        ("interval", self.feature_interval),
                    )
                    if box.isChecked()
                ],
                "lookback_days": self.lookback.value(),
                "idle_cutoff_s": self.idle_cutoff.value(),
                "max_answer_s": self.max_answer.value(),
                "max_rows": self.max_rows.value(),
            }
        )
        cfg["overlay"].update(
            {
                "enabled": self.overlay_enabled.isChecked(),
                "show_remaining": self.overlay_remaining.isChecked(),
                "show_eta": self.overlay_eta.isChecked(),
                "show_session_speed": self.overlay_speed.isChecked(),
                "show_elapsed": self.overlay_elapsed.isChecked(),
                "show_pace_vs_normal": self.overlay_vs_normal.isChecked(),
                "show_progress_bar": self.overlay_bar.isChecked(),
                "position": self.overlay_pos.currentData(),
                "opacity": self.overlay_opacity.value(),
                "scale": self.overlay_scale.value(),
                "hotkey": self.overlay_hotkey.keySequence().toString(),
            }
        )
        cfg["goal"].update(
            {
                "enabled": self.goal_enabled.isChecked(),
                "seconds_per_card": self.goal_seconds.value(),
                "show_timer": self.goal_show_timer.isChecked(),
                "count_down": self.goal_countdown.isChecked(),
                "badge_position": self.goal_pos.currentData(),
                "scale": self.goal_scale.value(),
                "alert_style": self.alert_style.currentData(),
                "alert_text": self.alert_text.text().strip() or "!",
                "alert_position": self.alert_pos.currentData(),
                "alert_scale": self.alert_scale.value(),
                "pulse_when_over": self.goal_pulse.isChecked(),
                "sound": self.goal_sound.isChecked(),
                "timer_phase": self.timer_phase.currentData(),
                "answer_seconds": self.answer_seconds.value(),
                "alert_phase": self.alert_phase.currentData(),
                "per_deck_seconds": self.deck_tree.goals(),
            }
        )
        cfg["debug"] = self.debug.isChecked()
        cfg["toolbar"].update(
            {
                "enabled": self.toolbar_enabled.isChecked(),
                "template": self.toolbar_template.text(),
                "hide_when_empty": self.toolbar_hide_empty.isChecked(),
                "click_action": self.toolbar_click.currentData(),
            }
        )
        return CFG.normalise(cfg)

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _set_combo(combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _move_component(self, delta: int) -> None:
        row = self.comp_list.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < self.comp_list.count()):
            return
        item = self.comp_list.takeItem(row)
        self.comp_list.insertItem(target, item)
        self.comp_list.setCurrentRow(target)

    def _select_current_deck(self) -> None:
        try:
            did = int(mw.col.decks.get_current_id())
        except Exception:
            return
        self.deck_tree.set_all(False)
        item = self.deck_tree._items.get(did)
        if item:
            item.setCheckState(0, Qt.CheckState.Checked)
            self.deck_tree.scrollToItem(item)

    def _restore_defaults(self) -> None:
        if (
            QMessageBox.question(
                self,
                K.ADDON_NAME,
                "Reset every Pace Estimator setting to its default?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.cfg = CFG.normalise({})
        self._load()

    # -- dialog ----------------------------------------------------------
    def accept(self) -> None:
        cfg = self._collect()
        mw.addonManager.writeConfig(K.ADDON_PACKAGE, cfg)
        saveGeom(self, "pace_config")
        from .. import runtime

        runtime.on_config_changed()
        tooltip("Pace Estimator settings saved", parent=mw)
        super().accept()

    def reject(self) -> None:
        saveGeom(self, "pace_config")
        super().reject()


def open_config(parent=None) -> None:
    dlg = ConfigDialog(parent)
    dlg.exec()
