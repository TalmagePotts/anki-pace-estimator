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


def panel_css(cfg) -> str:
    scale = float(cfg["display"]["font_scale"])
    compact = bool(cfg["display"]["compact"])
    pad = "10px 12px" if compact else "14px 16px"
    gap = "6px" if compact else "10px"
    value_size = round(1.45 * scale, 3)
    min_tile = 104 if compact else 118
    columns = int(cfg["display"]["columns"])
    grid = (
        "repeat(%d, minmax(0, 1fr))" % columns
        if columns
        else "repeat(auto-fit, minmax(%dpx, 1fr))" % min_tile
    )
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
  border-radius: 10px;
  font-size: {base}em;
  color: {fg};
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
}}
.{p}-head {{
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 8px; margin-bottom: {gap};
}}
.{p}-title {{
  font-weight: 600; font-size: .82em; letter-spacing: .06em;
  text-transform: uppercase; color: {subtle};
}}
.{p}-deck {{
  font-size: .78em; color: {faint}; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; max-width: 55%;
}}
.{p}-grid {{ display: grid; grid-template-columns: {grid}; gap: {gap}; }}
.{p}-tile {{
  background: {inset}; border-radius: 8px; padding: 8px 10px;
  border-left: 3px solid transparent; min-width: 0;
}}
.{p}-value {{
  font-size: {vsize}em; font-weight: 650; line-height: 1.15;
  font-variant-numeric: tabular-nums; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}}
.{p}-sub {{
  font-size: .72em; color: {subtle}; margin-top: 1px;
  font-variant-numeric: tabular-nums; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}}
.{p}-label {{
  font-size: .64em; letter-spacing: .07em; text-transform: uppercase;
  color: {faint}; margin-top: 4px;
}}
.{p}-chips {{
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: {gap};
}}
.{p}-chip {{
  font-size: .72em; padding: 3px 8px; border-radius: 999px;
  background: {inset}; color: {subtle}; font-variant-numeric: tabular-nums;
}}
.{p}-chip b {{ color: {fg}; font-weight: 600; }}
.{p}-foot {{
  margin-top: {gap}; font-size: .72em; color: {faint};
  display: flex; justify-content: space-between; gap: 8px; align-items: center;
}}
.{p}-btn {{
  cursor: pointer; color: {faint}; text-decoration: none;
  border: 1px solid transparent; border-radius: 6px; padding: 1px 6px;
  font-size: .95em; user-select: none;
}}
.{p}-btn:hover {{ color: {fg}; border-color: {border}; background: {inset}; }}
.{p}-empty {{ font-size: .82em; color: {subtle}; padding: 2px 0; }}
.{p}-new {{ border-left-color: {cnew}; }}
.{p}-learn {{ border-left-color: {clearn}; }}
.{p}-review {{ border-left-color: {creview}; }}
.{p}-accent {{ border-left-color: {accent}; }}
</style>
""".format(
        p=PREFIX,
        pad=pad,
        gap=gap,
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


def tile(value: str, label: str, sub: str = "", kind: str = "accent") -> str:
    sub_html = '<div class="%s-sub">%s</div>' % (PREFIX, esc(sub)) if sub else ""
    return (
        '<div class="{p}-tile {p}-{k}">'
        '<div class="{p}-value">{v}</div>{s}'
        '<div class="{p}-label">{l}</div>'
        "</div>"
    ).format(p=PREFIX, k=kind, v=esc(value), s=sub_html, l=esc(label))


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
        css=panel_css(cfg), p=PREFIX, head=head, grid=grid, chips=chip_html, foot=foot
    )
