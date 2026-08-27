"""Hook wiring: everything that makes the add-on actually appear in Anki."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from aqt import gui_hooks, mw
from aqt.qt import QAction, QKeySequence, QTimer
from aqt.utils import tooltip

from . import config as CFG
from . import consts as K
from . import log as L
from .collector import CACHE, build_snapshot, refresh_workload
from .session import SESSION
from .ui import home
from .ui import reviewer as RV

_cfg_cache: Optional[Dict[str, Any]] = None
_review_snap = None
_hud_visible = True


# ---------------------------------------------------------------------------
# Config access
# ---------------------------------------------------------------------------


def config() -> Dict[str, Any]:
    global _cfg_cache
    if _cfg_cache is None:
        _cfg_cache = CFG.normalise(mw.addonManager.getConfig(K.ADDON_PACKAGE))
        L.configure(_cfg_cache.get("debug", False))
        L.log(
            "config loaded: decks=%s goal=%s timer=%s alert=%s overlay=%s",
            _cfg_cache["decks"]["ids"] or "all",
            _cfg_cache["goal"]["enabled"],
            _cfg_cache["goal"]["show_timer"],
            _cfg_cache["goal"]["alert_style"],
            _cfg_cache["overlay"]["enabled"],
        )
    return _cfg_cache


def on_config_changed(*_args) -> None:
    global _cfg_cache, _review_snap
    _cfg_cache = None
    _review_snap = None
    CACHE.invalidate()
    _refresh_toolbar()
    try:
        if mw.state == "deckBrowser":
            mw.deckBrowser.refresh()
        elif mw.state == "overview":
            mw.overview.refresh()
    except Exception:
        pass


def _snapshot(override_decks=None, max_age: float = 20.0):
    return CACHE.get(mw.col, config(), override_decks=override_decks, max_age=max_age)


def _current_deck_ids() -> Optional[List[int]]:
    """Deck scope to use on the overview / in the reviewer."""
    cfg = config()
    if not cfg["decks"]["follow_current_deck"]:
        return None
    try:
        return [int(mw.col.decks.get_current_id())]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Home screen
# ---------------------------------------------------------------------------


@L.guard("deck browser")
def _on_deck_browser(deck_browser, content) -> None:
    cfg = config()
    if not cfg["display"]["show_on_deck_browser"]:
        return
    html = home.render(_snapshot(), cfg)
    if html:
        content.stats += html


@L.guard("overview")
def _on_overview(overview, content) -> None:
    cfg = config()
    if not cfg["display"]["show_on_overview"]:
        return
    html = home.render(_snapshot(override_decks=_current_deck_ids()), cfg)
    if html:
        content.table += html


def _on_js_message(handled, message: str, context):
    if not isinstance(message, str) or not message.startswith("rvp:"):
        return handled
    cmd = message[4:]
    if cmd == "config":
        from .ui.config_dialog import open_config

        open_config()
    elif cmd == "stats":
        from .ui.statswin import open_stats

        open_stats()
    return (True, None)


# ---------------------------------------------------------------------------
# Toolbar
# ---------------------------------------------------------------------------


def _toolbar_text(cfg) -> Optional[str]:
    snap = _snapshot()
    if cfg["toolbar"]["hide_when_empty"] and not snap.total_cards:
        return None
    fields = {
        "eta": K.fmt_duration(snap.estimate.seconds),
        "eta_slow": K.fmt_duration(snap.estimate.seconds_slow),
        "cards": snap.total_cards,
        "due": snap.workload.review_cards,
        "new": snap.workload.new_cards,
        "learn": snap.workload.learning_reps,
        "speed": K.fmt_secs_per_card(snap.speeds.overall.pick(cfg["speed"]["mode"])),
        "done": snap.today.reviews,
        "finish": K.fmt_clock(snap.finish_epoch, cfg["display"]["clock_24h"]),
    }
    try:
        return cfg["toolbar"]["template"].format(**fields)
    except (KeyError, IndexError, ValueError):
        return fields["eta"]


@L.guard("toolbar")
def _on_toolbar_links(links: List[str], toolbar) -> None:
    cfg = config()
    if not cfg["toolbar"]["enabled"]:
        return
    text = _toolbar_text(cfg)
    if not text:
        return
    links.append(
        toolbar.create_link(
            "rvp_toolbar",
            text,
            _on_toolbar_click,
            tip="%s — click for details" % K.ADDON_NAME,
            id="rvp_toolbar",
        )
    )


def _on_toolbar_click() -> None:
    action = config()["toolbar"]["click_action"]
    if action == "stats":
        from .ui.statswin import open_stats

        open_stats()
    elif action == "config":
        from .ui.config_dialog import open_config

        open_config()


def _refresh_toolbar() -> None:
    try:
        mw.toolbar.redraw()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------


def _goal_seconds_for_card(card) -> Optional[float]:
    cfg = config()
    if not cfg["goal"]["enabled"]:
        L.log("goal: turned off in settings")
        return None
    did = int(getattr(card, "odid", 0) or card.did)
    secs = CFG.goal_seconds_for(cfg, did)
    L.log("goal: deck %s -> %.1fs", did, secs)
    return secs


@L.guard("inject")
def _inject(card=None) -> None:
    cfg = config()
    global _review_snap
    if _review_snap is None:
        _review_snap = build_snapshot(mw.col, cfg, _current_deck_ids())
    else:
        refresh_workload(_review_snap, mw.col, cfg)
    goal_seconds = _goal_seconds_for_card(card) if card is not None else None
    payload = RV.build_payload(_review_snap, cfg, SESSION, goal_seconds, _hud_visible)
    L.log(
        "inject: goal=%s hud=%s",
        payload["goal"]["seconds"] if payload["goal"] else None,
        bool(payload["hud"]),
    )
    web = getattr(mw.reviewer, "web", None)
    if web is None:
        L.log("inject: no reviewer webview")
        return
    web.eval(RV.script(payload))


@L.guard("show question")
def _on_show_question(card) -> None:
    _stamp_card_start()
    if config()["goal"]["start_on"] == "answer":
        # Draw the HUD now, but hold the badge back: passing no card means no
        # goal in the payload, which hides the badge until the answer is shown.
        _inject(None)
        return
    _inject(card)


@L.guard("show answer")
def _on_show_answer(card) -> None:
    if config()["goal"]["start_on"] == "answer":
        _stamp_card_start()
        _inject(card)


def _stamp_card_start() -> None:
    """Mark the moment the card appeared, before any slow work happens."""
    web = getattr(mw.reviewer, "web", None)
    if web is not None:
        web.eval(RV.stamp_script())


@L.guard("answer card")
def _on_answer_card(reviewer, card, ease) -> None:
    SESSION.record(int(card.time_taken()))
    L.log(
        "answered: %dms, session %d cards at %.1fs",
        card.time_taken(),
        SESSION.answers,
        SESSION.wall_per_card,
    )


@L.guard("state change")
def _on_state_change(new_state: str, old_state: str) -> None:
    global _review_snap, _hud_visible
    if new_state == "review" and old_state != "review":
        cfg = config()
        SESSION.reset(idle_cutoff_s=float(cfg["speed"]["idle_cutoff_s"]))
        _review_snap = None
        _hud_visible = True
    elif old_state == "review" and new_state != "review":
        _review_snap = None


@L.guard("reviewer end")
def _on_reviewer_end() -> None:
    global _review_snap
    _review_snap = None
    web = getattr(mw.reviewer, "web", None)
    if web is not None:
        web.eval(RV.clear_script())


def _toggle_hud() -> None:
    global _hud_visible
    _hud_visible = not _hud_visible
    _inject(getattr(mw.reviewer, "card", None))
    tooltip("Review Pace HUD %s" % ("shown" if _hud_visible else "hidden"), period=900)


@L.guard("shortcuts")
def _on_shortcuts(state: str, shortcuts: List) -> None:
    if state != "review":
        return
    key = config()["overlay"]["hotkey"]
    if key:
        shortcuts.append((key, _toggle_hud))


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------


@L.guard("install menu")
def _install_menu() -> None:
    action = QAction("%s…" % K.ADDON_NAME, mw)
    action.setShortcut(QKeySequence("Ctrl+Shift+P"))
    action.triggered.connect(lambda: _open_stats())
    mw.form.menuTools.addAction(action)


def _open_stats() -> None:
    from .ui.statswin import open_stats

    open_stats()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def install() -> None:
    mw.addonManager.setConfigAction(K.ADDON_PACKAGE, _open_config_action)
    mw.addonManager.setConfigUpdatedAction(K.ADDON_PACKAGE, on_config_changed)

    gui_hooks.deck_browser_will_render_content.append(_on_deck_browser)
    gui_hooks.overview_will_render_content.append(_on_overview)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
    gui_hooks.top_toolbar_did_init_links.append(_on_toolbar_links)

    gui_hooks.reviewer_did_show_question.append(_on_show_question)
    gui_hooks.reviewer_did_show_answer.append(_on_show_answer)
    gui_hooks.reviewer_did_answer_card.append(_on_answer_card)
    gui_hooks.reviewer_will_end.append(_on_reviewer_end)
    gui_hooks.state_did_change.append(_on_state_change)
    gui_hooks.state_shortcuts_will_change.append(_on_shortcuts)

    gui_hooks.profile_did_open.append(_on_profile_open)
    if getattr(mw, "form", None) is not None:
        _install_menu()
    else:
        gui_hooks.main_window_did_init.append(_install_menu)
    L.log("installed")


def _on_profile_open() -> None:
    on_config_changed()


PREVIEW_SECONDS = 3.0
PREVIEW_CLEAR_MS = 9000


def preview_goal(cfg: Dict[str, Any]) -> None:
    """Show the timer and warning on the current screen for a few seconds.

    Sitting on a card waiting for it to time out is a slow way to check a
    setting, so the preview shortens the goal and clears itself.
    """
    web = getattr(mw, "web", None)
    if web is None:
        return
    preview = CFG.normalise(cfg)
    preview["goal"]["enabled"] = True
    seconds = min(PREVIEW_SECONDS, float(preview["goal"]["seconds_per_card"]))
    payload = RV.build_payload(None, preview, SESSION, seconds, False)
    web.eval(RV.script(payload))
    L.log("preview: %.1fs goal on the main window", seconds)
    QTimer.singleShot(PREVIEW_CLEAR_MS, lambda: _clear_preview(web))
    tooltip(
        "Previewing a %.0f second card — the warning fires in %.0f seconds."
        % (seconds, seconds),
        period=int(PREVIEW_CLEAR_MS),
    )


def _clear_preview(web) -> None:
    try:
        web.eval(RV.clear_script())
    except Exception:
        pass


def _open_config_action() -> None:
    from .ui.config_dialog import open_config

    open_config()
