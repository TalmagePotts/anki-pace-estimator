"""Shared look-and-feel for every surface the add-on draws.

All colours are taken from Anki's own CSS custom properties so the panel
follows the active theme (including custom themes) without the add-on ever
needing to know whether night mode is on.  Every ``var()`` carries a literal
fallback so an older or unusual theme degrades gracefully instead of rendering
invisible text.
"""

from __future__ import annotations

from typing import List, Optional

PREFIX = "rvp"

FG = "var(--fg, #2c2c2c)"
FG_SUBTLE = "var(--fg-subtle, #777)"
FG_FAINT = "var(--fg-faint, #999)"
CANVAS = "var(--canvas-elevated, var(--canvas, #f5f5f5))"
CANVAS_INSET = "var(--canvas-inset, rgba(127,127,127,.10))"
BORDER = "var(--border-subtle, var(--border, rgba(127,127,127,.28)))"
ACCENT = "var(--accent-card, #3a7bd5)"
C_NEW = "var(--state-new, #2496dc)"
C_LEARN = "var(--state-learn, #d34848)"
C_REVIEW = "var(--state-review, #46a35c)"


def accent_for(cfg) -> str:
    custom = (cfg["display"].get("accent") or "").strip()
    return custom or ACCENT


#: Column counts worth considering. One is excluded deliberately: a single
#: column always divides evenly and would otherwise win every tie.
CANDIDATE_COLUMNS = (4, 3, 2)


def auto_columns(tile_count: int) -> int:
    """Pick a column count that leaves the fewest empty cells in the last row.

    Auto-fitting to the panel width gave whatever happened to fit, which left a
    single orphan tile stranded on its own row. Choosing the count from the
    number of tiles keeps every row full where the arithmetic allows it, and
    prefers wider tiles when several counts tie.
    """
    if tile_count <= 1:
        return 1

    def waste(columns: int) -> tuple:
        remainder = tile_count % columns
        empty = 0 if remainder == 0 else columns - remainder
        # Fewest empty cells wins; ties go to the wider layout.
        return (empty, -columns)

    return min(CANDIDATE_COLUMNS, key=waste)


def panel_css(cfg, tile_count: int = 0) -> str:
    scale = float(cfg["display"]["font_scale"])
    compact = bool(cfg["display"]["compact"])
    pad = "10px 12px" if compact else "14px 16px"
    gap = "6px" if compact else "9px"
    tile_pad = "7px 10px" if compact else "9px 12px"
    value_size = round(1.5 * scale, 3)
    columns = int(cfg["display"]["columns"]) or auto_columns(tile_count)
    grid = "repeat(%d, minmax(0, 1fr))" % columns
    return """
<style>
.{p}-panel {{
  box-sizing: border-box;
  max-width: 720px;
  margin: 14px auto 6px auto;
  padding: {pad};
  text-align: left;
  background: {canvas};
  border: 1px solid {border};
  border-radius: 12px;
  font-size: {base}em;
  color: {fg};
}}
.{p}-head {{
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 8px; margin-bottom: {gap};
}}
.{p}-title {{
  font-weight: 600; font-size: .78em; letter-spacing: .08em;
  text-transform: uppercase; color: {subtle};
}}
.{p}-deck {{
  font-size: .78em; color: {faint}; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; max-width: 55%;
}}
.{p}-grid {{
  display: grid; grid-template-columns: {grid}; gap: {gap};
  align-items: stretch;
}}
.{p}-tile {{
  display: flex; flex-direction: column; gap: 1px;
  background: {inset}; border-radius: 9px; padding: {tpad};
  min-width: 0;
}}
.{p}-label {{
  font-size: .64em; letter-spacing: .08em; text-transform: uppercase;
  color: {faint}; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; font-weight: 600;
}}
.{p}-value {{
  font-size: {vsize}em; font-weight: 650; line-height: 1.2;
  font-variant-numeric: tabular-nums; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}}
.{p}-unit {{ font-size: .56em; font-weight: 500; color: {subtle}; }}
.{p}-sub {{
  font-size: .7em; color: {subtle};
  font-variant-numeric: tabular-nums; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}}
.{p}-chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: {gap}; }}
.{p}-chip {{
  font-size: .7em; padding: 3px 9px; border-radius: 999px;
  background: {inset}; color: {subtle}; font-variant-numeric: tabular-nums;
  white-space: nowrap;
}}
.{p}-chip b {{ color: {fg}; font-weight: 600; }}
.{p}-foot {{
  margin-top: {gap}; font-size: .7em; color: {faint};
  display: flex; justify-content: space-between; gap: 8px; align-items: center;
}}
.{p}-btn {{
  cursor: pointer; color: {faint}; text-decoration: none;
  border-radius: 6px; padding: 2px 6px; user-select: none;
}}
.{p}-btn:hover {{ color: {fg}; background: {inset}; }}
.{p}-new .{p}-label {{ color: {cnew}; }}
.{p}-learn .{p}-label {{ color: {clearn}; }}
.{p}-review .{p}-label {{ color: {creview}; }}
.{p}-accent .{p}-label {{ color: {accent}; }}
</style>
""".format(
        p=PREFIX,
        pad=pad,
        gap=gap,
        tpad=tile_pad,
        grid=grid,
        base=round(scale, 3),
        vsize=value_size,
        canvas=CANVAS,
        border=BORDER,
        inset=CANVAS_INSET,
        fg=FG,
        subtle=FG_SUBTLE,
        faint=FG_FAINT,
        accent=accent_for(cfg),
        cnew=C_NEW,
        clearn=C_LEARN,
        creview=C_REVIEW,
    )


def esc(text) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def tile(value: str, label: str, sub: str = "", kind: str = "accent",
         unit: str = "") -> str:
    """One statistic.

    The label sits above the value so that every tile lines up regardless of
    whether it has a sub-line, and the unit is a separate, smaller span so a
    long value never has to be truncated to fit its unit in.
    """
    sub_html = '<div class="%s-sub">%s</div>' % (PREFIX, esc(sub)) if sub else ""
    unit_html = '<span class="%s-unit">%s</span>' % (PREFIX, esc(unit)) if unit else ""
    return (
        '<div class="{p}-tile {p}-{k}">'
        '<div class="{p}-label">{l}</div>'
        '<div class="{p}-value">{v}{u}</div>{s}'
        "</div>"
    ).format(p=PREFIX, k=kind, v=esc(value), u=unit_html, s=sub_html, l=esc(label))


def chip(label: str, value: str) -> str:
    return '<span class="{p}-chip">{l} <b>{v}</b></span>'.format(
        p=PREFIX, l=esc(label), v=esc(value)
    )


def panel(cfg, tiles: List[str], chips: Optional[List[str]] = None,
          footer_left: str = "", footer_right: str = "", deck_label: str = "") -> str:
    """Assemble the outer panel. Returns "" when there is nothing to show."""
    if not tiles and not chips:
        return ""
    head = ""
    if cfg["display"]["show_title"]:
        head = (
            '<div class="{p}-head"><div class="{p}-title">{t}</div>'
            '<div class="{p}-deck">{d}</div></div>'
        ).format(p=PREFIX, t=esc(cfg["display"]["title"]), d=esc(deck_label))
    grid = (
        '<div class="{p}-grid">{tiles}</div>'.format(p=PREFIX, tiles="".join(tiles))
        if tiles
        else ""
    )
    chip_html = (
        '<div class="{p}-chips">{c}</div>'.format(p=PREFIX, c="".join(chips)) if chips else ""
    )
    foot = ""
    if footer_left or footer_right:
        foot = (
            '<div class="{p}-foot"><div>{l}</div><div>{r}</div></div>'
        ).format(p=PREFIX, l=footer_left, r=footer_right)
    return '{css}<div class="{p}-panel">{head}{grid}{chips}{foot}</div>'.format(
        css=panel_css(cfg, len(tiles)),
        p=PREFIX,
        head=head,
        grid=grid,
        chips=chip_html,
        foot=foot,
    )
