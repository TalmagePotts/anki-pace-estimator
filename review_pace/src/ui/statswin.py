"""Tools ▸ Review Pace — the detailed view."""

from __future__ import annotations

from typing import List

from aqt import mw
from aqt.qt import *  # noqa: F401,F403
from aqt.utils import restoreGeom, saveGeom
from aqt.webview import AnkiWebView

from .. import config as CFG
from .. import consts as K
from ..collector import Snapshot, build_snapshot
from ..stats import CLASS_LABELS, CLASSES
from . import home
from . import theme as T


def _table(headers: List[str], rows: List[List[str]], aligns: str = "") -> str:
    if not rows:
        return ""
    head = "".join(
        '<th style="text-align:%s">%s</th>'
        % ("right" if aligns[i : i + 1] == "r" else "left", T.esc(h))
        for i, h in enumerate(headers)
    )
    body = ""
    for row in rows:
        cells = "".join(
            '<td style="text-align:%s">%s</td>'
            % ("right" if aligns[i : i + 1] == "r" else "left", cell)
            for i, cell in enumerate(row)
        )
        body += "<tr>%s</tr>" % cells
    return '<table class="rvp-tbl"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (
        head,
        body,
    )


def _extra_css() -> str:
    return """
<style>
body {{ padding: 0 18px 24px 18px; }}
.rvp-sec {{ max-width: 720px; margin: 22px auto 0 auto; }}
.rvp-sec h2 {{
  font-size: .78em; letter-spacing: .07em; text-transform: uppercase;
  color: {subtle}; margin: 0 0 8px 0; font-weight: 600;
}}
.rvp-tbl {{
  width: 100%; border-collapse: collapse; font-size: .88em;
  font-variant-numeric: tabular-nums;
}}
.rvp-tbl th {{
  font-weight: 600; font-size: .82em; color: {faint};
  padding: 4px 8px; border-bottom: 1px solid {border};
  text-transform: uppercase; letter-spacing: .04em;
}}
.rvp-tbl td {{ padding: 5px 8px; border-bottom: 1px solid {border}; }}
.rvp-tbl tr:last-child td {{ border-bottom: none; }}
.rvp-note {{ font-size: .8em; color: {faint}; margin-top: 8px; line-height: 1.5; }}
</style>
""".format(
        subtle=T.FG_SUBTLE, faint=T.FG_FAINT, border=T.BORDER
    )


def render_report(snap: Snapshot, cfg) -> str:
    parts = [_extra_css(), home.render(snap, cfg, show_buttons=False)]

    if snap.per_deck:
        rows = []
        for line in snap.per_deck:
            total = line.review + line.new + line.learning
            rows.append(
                [
                    T.esc(line.name),
                    str(line.review),
                    str(line.new),
                    str(line.learning),
                    str(total),
                    K.fmt_duration(line.seconds),
                ]
            )
        parts.append(
            '<div class="rvp-sec"><h2>By deck</h2>%s</div>'
            % _table(
                ["Deck", "Due", "New", "Learning", "Total", "Est. time"],
                rows,
                "lrrrrr",
            )
        )

    if snap.has_speed_data:
        rows = []
        for cls in CLASSES:
            cs = snap.speeds.per_class.get(cls)
            if not cs or not cs.n:
                continue
            overhead = cs.wall - cs.answer
            rows.append(
                [
                    CLASS_LABELS[cls],
                    "{:,}".format(cs.n),
                    K.fmt_secs_per_card(cs.answer),
                    K.fmt_secs_per_card(cs.wall),
                    K.fmt_secs_per_card(cs.typical(cfg["speed"]["mode"])),
                    K.fmt_secs_per_card(overhead) if overhead > 0.05 else "--",
                    K.fmt_secs_per_card(cs.pick(cfg["speed"]["mode"], slow=True)),
                ]
            )
        overall = snap.speeds.overall
        rows.append(
            [
                "<b>All cards</b>",
                "<b>{:,}</b>".format(overall.n),
                "<b>%s</b>" % K.fmt_secs_per_card(overall.answer),
                "<b>%s</b>" % K.fmt_secs_per_card(overall.wall),
                "<b>%s</b>" % K.fmt_secs_per_card(overall.typical(cfg["speed"]["mode"])),
                "<b>%s</b>" % K.fmt_secs_per_card(max(0.0, overall.wall - overall.answer)),
                "<b>%s</b>" % K.fmt_secs_per_card(overall.pick(cfg["speed"]["mode"], slow=True)),
            ]
        )
        parts.append(
            '<div class="rvp-sec"><h2>Speed by card type — last %d days</h2>%s'
            '<div class="rvp-note">“Answer” is the time from seeing the question to '
            "pressing a button. “Wall” adds the gap before the next card appears — "
            "rendering, hesitation, and the moment between cards. “Slow” is the "
            "80th percentile of a single answer — the ETA range is built from the "
            "spread instead, which shrinks as the workload grows. “Typical” is the "
            "middle card; it is shown for interest and never multiplied by a card "
            "count.</div></div>"
            % (snap.lookback_days, _table(
                ["Card type", "Samples", "Answer", "Wall", "Typical", "Overhead", "Slow"],
                rows,
                "lrrrrrr",
            ))
        )
        parts.append(_feature_table(snap, cfg))

    est = snap.estimate
    if est.parts:
        rows = [
            [
                T.esc(part.label),
                "%.0f" % part.reps,
                K.fmt_secs_per_card(part.secs_each),
                K.fmt_duration(part.seconds),
            ]
            for part in est.parts
        ]
        rows.append(
            [
                "<b>Total</b>",
                "<b>%.0f</b>" % est.total_reps,
                "",
                "<b>%s</b>" % K.fmt_duration(est.seconds),
            ]
        )
        parts.append(
            '<div class="rvp-sec"><h2>How the estimate is built</h2>%s'
            '<div class="rvp-note">Measured from your own history: %.2f answers per '
            "new card, %.0f%% of reviews graded Again, %.2f answers per lapse. "
            "That is why this differs from “cards × seconds”.</div></div>"
            % (
                _table(["Work", "Answers", "Each", "Time"], rows, "lrrr"),
                snap.behaviour.reps_per_new,
                snap.behaviour.lapse_rate * 100,
                snap.behaviour.reps_per_lapse,
            )
        )

    rows = [
        ["Today", str(snap.today.reviews), K.fmt_duration(snap.today.seconds),
         str(snap.today.introduced)],
        ["Last 7 days", str(snap.week.reviews), K.fmt_duration(snap.week.seconds),
         str(snap.week.introduced)],
        ["Last 30 days", str(snap.month.reviews), K.fmt_duration(snap.month.seconds),
         str(snap.month.introduced)],
    ]
    if cfg["display"]["period_mode"] == "calendar":
        rows[1][0] = "This week"
        rows[2][0] = "This month"
    parts.append(
        '<div class="rvp-sec"><h2>Work done</h2>%s</div>'
        % _table(["Period", "Answers", "Time", "New learned"], rows, "lrrr")
    )
    return "".join(parts)


def _feature_table(snap: Snapshot, cfg) -> str:
    """Speeds for the optional finer splits, when they are switched on."""
    speeds = snap.speeds
    if not speeds.features or not speeds.per_key:
        return ""
    from ..stats import FEATURE_LABELS, MIN_SAMPLES, describe_key

    mode = cfg["speed"]["mode"]
    rows = []
    for key in sorted(speeds.per_key):
        cs = speeds.per_key[key]
        if not cs.n:
            continue
        used = cs.n >= MIN_SAMPLES
        rows.append(
            [
                T.esc(describe_key(key)),
                "{:,}".format(cs.n),
                K.fmt_secs_per_card(cs.pick(mode)),
                "yes" if used else "falls back to card type",
            ]
        )
    if not rows:
        return ""
    names = ", ".join(FEATURE_LABELS[f].lower() for f in speeds.features)
    return (
        '<div class="rvp-sec"><h2>Split by %s</h2>%s'
        '<div class="rvp-note">A split is only used once it has %d samples of its '
        "own; below that it falls back to the card type, so a rarely-seen "
        "combination cannot swing the estimate.</div></div>"
        % (names, _table(["Bucket", "Samples", "Speed", "Used"], rows, "lrrl"), MIN_SAMPLES)
    )


class StatsWindow(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent or mw)
        self.setWindowTitle(K.ADDON_NAME)
        self.setMinimumSize(700, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.web = AnkiWebView(title="review_pace_stats")
        self.web.set_bridge_command(self._on_cmd, self)
        lay.addWidget(self.web, 1)

        bar = QHBoxLayout()
        bar.setContentsMargins(10, 6, 10, 10)
        self.scope = QLabel("")
        bar.addWidget(self.scope, 1)
        for text, slot in (("Refresh", self.refresh), ("Settings…", self._open_config)):
            btn = QPushButton(text)
            btn.setAutoDefault(False)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        close = QPushButton("Close")
        close.setAutoDefault(True)
        close.clicked.connect(self.reject)
        bar.addWidget(close)
        lay.addLayout(bar)

        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.refresh)
        restoreGeom(self, "rvp_stats")
        self.refresh()

    def _on_cmd(self, cmd: str):
        if cmd == "rvp:config":
            self._open_config()
        return None

    def _open_config(self) -> None:
        from .config_dialog import open_config

        open_config(self)
        self.refresh()

    def refresh(self) -> None:
        cfg = CFG.normalise(mw.addonManager.getConfig(K.ADDON_PACKAGE))
        snap = build_snapshot(mw.col, cfg)
        self.scope.setText("Scope: %s" % snap.deck_label(limit=4))
        self.web.stdHtml(render_report(snap, cfg), context=self)

    def reject(self) -> None:
        saveGeom(self, "rvp_stats")
        self.web.cleanup()
        super().reject()


_window = None


def open_stats(parent=None) -> None:
    global _window
    if _window is not None:
        try:
            _window.close()
        except Exception:
            pass
    _window = StatsWindow(parent)
    _window.show()
    _window.raise_()
    _window.activateWindow()
