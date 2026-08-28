"""The home panel renders from plain data, so it can be checked without Anki."""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pace_estimator"))

from src import collector as CO  # noqa: E402
from src import config as C  # noqa: E402
from src import consts as K  # noqa: E402
from src import stats as S  # noqa: E402
from src.ui import home  # noqa: E402
from src.ui import reviewer as RV  # noqa: E402


def make_snapshot():
    speeds = S.Speeds(
        per_class={
            S.LEARN: S.ClassSpeed(n=300, answer=14, wall=18, answer_slow=22, wall_slow=27),
            S.YOUNG: S.ClassSpeed(n=900, answer=7, wall=9, answer_slow=12, wall_slow=15),
            S.MATURE: S.ClassSpeed(n=4000, answer=4, wall=5.5, answer_slow=7, wall_slow=9),
            S.RELEARN: S.ClassSpeed(n=200, answer=9, wall=11, answer_slow=15, wall_slow=18),
        },
        overall=S.ClassSpeed(n=5400, answer=5, wall=6.6, answer_slow=9, wall_slow=12),
        overhead_ratio=0.24,
    )
    beh = S.Behaviour(reps_per_new=2.4, lapse_rate=0.11, reps_per_lapse=1.8)
    work = S.Workload(new_cards=20, review_cards=180, learning_reps=12)
    snap = CO.Snapshot(
        deck_ids=[1, 2],
        deck_names=["Medicine", "Pharm"],
        speeds=speeds,
        behaviour=beh,
        workload=work,
        estimate=S.estimate(work, speeds, beh),
        today=S.DoneTotals(reviews=140, seconds=1020, introduced=12),
        week=S.DoneTotals(reviews=900, seconds=7000, introduced=71),
        month=S.DoneTotals(reviews=3600, seconds=28000, introduced=290),
        per_deck=[CO.DeckLine(1, "Medicine", 15, 8, 140, 900.0)],
        sample_size=5400,
        lookback_days=30,
    )
    return snap


def only(*ids):
    """A components list that is explicit about every component.

    A component missing from a stored config arrives with the state it ships
    with, so a test that wants something off has to say so.
    """
    return {"display": {"components": [
        {"id": cid, "enabled": cid in ids} for cid in K.DEFAULT_COMPONENT_ORDER]}}


def test_panel_contains_every_enabled_component():
    cfg = C.normalise({"display": {"components": [
        {"id": cid, "enabled": True} for cid in K.DEFAULT_COMPONENT_ORDER]}})
    html = home.render(make_snapshot(), cfg)
    for label in ("Time left", "Due", "New", "Learning",
                  "New learned today", "Answered today"):
        assert label in html
    assert "Mature" in html  # breakdown chips
    assert "Medicine, Pharm" in html


def test_disabled_components_are_absent():
    cfg = C.normalise(only("eta"))
    html = home.render(make_snapshot(), cfg)
    assert "Time left" in html
    assert "New learned today" not in html
    assert "Answered today" not in html


def test_panel_is_empty_when_nothing_is_enabled():
    cfg = C.normalise(only())
    assert home.render(make_snapshot(), cfg) == ""


def test_html_is_balanced_and_escaped():
    cfg = C.normalise({"display": {"title": "<script>x</script>"}})
    snap = make_snapshot()
    snap.deck_names = ['Deck "A" & <b>']
    html = home.render(snap, cfg)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert html.count("<div") == html.count("</div>")


def test_speed_mode_switches_the_headline_number():
    wall = home.render(make_snapshot(), C.normalise({"speed": {"mode": "wall"}}))
    answer = home.render(make_snapshot(), C.normalise({"speed": {"mode": "answer"}}))
    # The unit is its own span, so a long value never has to be truncated to
    # make room for it.
    assert "Wall-clock speed" in wall
    assert ">6.6<span class=\"pace-unit\">s/card</span>" in wall
    assert "Answer speed" in answer
    assert ">5.0<span class=\"pace-unit\">s/card</span>" in answer


def test_finish_time_and_range_can_be_turned_off():
    cfg = C.normalise({"display": {"show_finish_time": False, "show_eta_range": False}})
    html = home.render(make_snapshot(), cfg)
    assert "done by" not in html


def test_all_done_state():
    snap = make_snapshot()
    snap.workload = S.Workload()
    snap.estimate = S.Estimate()
    assert "All done" in home.render(snap, C.normalise({}))


def test_no_history_state():
    snap = make_snapshot()
    snap.sample_size = 0
    html = home.render(snap, C.normalise({}))
    assert "no review history yet" in html
    assert "No reviews in the last 30 days" in html


def test_reviewer_payload_and_script():
    cfg = C.normalise({"goal": {"enabled": True, "seconds_per_card": 12}})
    from src.session import LiveSession

    sess = LiveSession()
    sess.reset()
    for _ in range(5):
        sess.record(6000)
    payload = RV.build_payload(make_snapshot(), cfg, sess, 12.0, True)
    assert payload["goal"]["seconds"] == 12.0
    assert payload["goal"]["show_timer"] is False   # ships off
    assert payload["goal"]["alert_style"] == "exclamation"
    assert "eta" in payload["hud"]["html"]
    js = RV.script(payload)
    assert js.count("(") == js.count(")")
    assert "%(payload)s" not in js and "%%" not in js


def test_hud_hidden_when_toggled_off():
    cfg = C.normalise({"goal": {"enabled": True}})
    from src.session import LiveSession

    payload = RV.build_payload(make_snapshot(), cfg, LiveSession(), 10.0, False)
    assert payload["hud"] is None
    assert payload["goal"] is not None


def test_goal_absent_when_disabled():
    cfg = C.normalise({"goal": {"enabled": False}})
    from src.session import LiveSession

    payload = RV.build_payload(make_snapshot(), cfg, LiveSession(), 10.0, True)
    assert payload["goal"] is None


def test_css_braces_are_balanced():
    css = home.T.panel_css(C.normalise({}))
    assert css.count("{") == css.count("}")
    assert "{p}" not in css and "{gap}" not in css


def test_warning_only_mode_has_no_timer():
    cfg = C.normalise({"goal": {"enabled": True, "show_timer": False,
                                "alert_style": "exclamation", "alert_text": "!"}})
    from src.session import LiveSession

    payload = RV.build_payload(None, cfg, LiveSession(), 15.0, False)
    assert payload["goal"]["show_timer"] is False
    assert payload["goal"]["alert_style"] == "exclamation"
    js = RV.script(payload)
    assert "pace-alert" in js


def test_alert_position_reaches_the_script():
    for position, css_top in (("bottom", '"6vh"'), ("lower-half", '"50%"'),
                              ("upper-half", '"0"'), ("center", '"0"'),
                              ("top", '"6vh"')):
        cfg = C.normalise({"goal": {"enabled": True, "alert_style": "exclamation",
                                    "alert_position": position}})
        from src.session import LiveSession

        payload = RV.build_payload(None, cfg, LiveSession(), 10.0, False)
        assert payload["goal"]["alert_position"] == position
        assert css_top in RV.script(payload)


def test_script_has_no_leftover_format_markers():
    from src.session import LiveSession

    cfg = C.normalise({"goal": {"enabled": True, "alert_style": "both"}})
    js = RV.script(RV.build_payload(make_snapshot(), cfg, LiveSession(), 10.0, True))
    assert "%(" not in js
    assert "%%" not in js
    assert js.count("{") == js.count("}")


def test_column_count_is_chosen_to_fill_the_last_row():
    auto = home.T.auto_columns
    assert auto(6) == 3   # two full rows, not 4 + 2
    assert auto(4) == 4   # one full row
    assert auto(3) == 3
    assert auto(2) == 2
    assert auto(1) == 1   # one tile is one column, not a lone cell in a row
    assert auto(8) == 4
    assert auto(9) == 3
    assert auto(7) == 4   # nothing divides 7; 4 + 3 wastes the least
    assert auto(5) == 3   # 3 + 2 beats 4 + 1
    assert auto(0) == 1


def test_layout_adapts_to_the_tiles_actually_shown():
    snap = make_snapshot()
    seven = home.render(snap, C.normalise({}))
    assert seven.count('class="pace-tile') == 7
    assert "repeat(4, minmax(0, 1fr))" in seven

    snap.workload = S.Workload(new_cards=20, review_cards=180, learning_reps=0)
    six = home.render(snap, C.normalise({}))
    assert six.count('class="pace-tile') == 6
    assert "repeat(3, minmax(0, 1fr))" in six


def test_explicit_column_setting_wins():
    html = home.render(make_snapshot(), C.normalise({"display": {"columns": 2}}))
    assert "repeat(2, minmax(0, 1fr))" in html


def test_labels_and_values_never_wrap():
    css = home.T.panel_css(C.normalise({}))
    for block in ("pace-label", "pace-value", "pace-sub"):
        section = css.split("." + block + " {")[1].split("}")[0]
        assert "white-space: nowrap" in section, block
        assert "text-overflow: ellipsis" in section, block


def test_label_comes_before_the_value():
    # Every tile lines up only if the label is the first row of each one.
    html = home.render(make_snapshot(), C.normalise({}))
    tile = html.split('class="pace-tile')[1]
    assert tile.index("pace-label") < tile.index("pace-value")


def test_speed_tile_reports_the_mean_matching_answered_today():
    # The headline speed and today's seconds-per-card are now the same kind of
    # number, so they can be compared without them disagreeing.
    snap = make_snapshot()
    snap.today = S.DoneTotals(reviews=100, seconds=660, introduced=4)
    html = home.render(snap, C.normalise({"speed": {"mode": "wall"}}))
    assert ">6.6<" in html          # 30-day mean
    assert "6.6s each" in html      # today: 660s / 100 cards


def test_speed_display_choices():
    snap = make_snapshot()
    snap.speeds.overall = S.ClassSpeed(
        n=5400, answer=5, wall=6.6, answer_typical=3, wall_typical=4.1
    )
    mean = home.render(snap, C.normalise({"display": {"speed_display": "mean"}}))
    typical = home.render(snap, C.normalise({"display": {"speed_display": "typical"}}))
    both = home.render(snap, C.normalise({"display": {"speed_display": "both"}}))

    assert ">6.6<" in mean and "typical" not in mean
    assert ">4.1<" in typical and "typical card" in typical.lower()
    assert "average 6.6s" in typical
    assert ">6.6<" in both and "typical card 4.1s" in both


def test_feature_buckets_reach_the_estimate_through_the_config():
    from src import collector as CO2  # noqa: F401

    cfg = C.normalise({"speed": {"features": ["ease"]}})
    assert cfg["speed"]["features"] == ["ease"]
    speeds = S.Speeds(
        per_class={S.MATURE: S.ClassSpeed(n=200, answer=10, wall=10)},
        overall=S.ClassSpeed(n=200, answer=10, wall=10),
        per_key={(S.MATURE, "hard"): S.ClassSpeed(n=100, answer=30, wall=30)},
        features=("ease",),
    )
    work = S.Workload(review_cards=10, review_buckets={(S.MATURE, "hard"): 10})
    est = S.estimate(work, speeds, S.Behaviour(lapse_rate=0.0),
                     count_full_learning=cfg["speed"]["count_full_learning"])
    assert est.seconds == 300
    assert "Hard" in est.parts[0].label or "hard" in est.parts[0].label


def test_session_summary_appears_then_expires():
    import time as _t

    from src import session as SESS

    cfg = C.normalise(only("session"))
    SESS.LAST_SESSION = SESS.SessionSummary(
        answers=68, seconds=1440, introduced=14, ended_at=_t.time(),
        per_card=21.0, usual_per_card=24.0,
    )
    html = home.render(make_snapshot(), cfg)
    assert "Just finished" in html and ">68<" in html
    assert "24m" in html and "21.0s each" in html and "14 new" in html
    assert "12% faster than usual" in html

    SESS.LAST_SESSION.ended_at = _t.time() - 3 * 3600
    assert home.render(make_snapshot(), cfg) == ""
    SESS.LAST_SESSION = SESS.SessionSummary()


def test_session_summary_can_be_turned_off_entirely():
    import time as _t

    from src import session as SESS

    SESS.LAST_SESSION = SESS.SessionSummary(
        answers=10, seconds=100, ended_at=_t.time(), per_card=10.0, usual_per_card=10.0
    )
    cfg = C.normalise(dict(only("session"), **{"display": {
        "components": [{"id": cid, "enabled": cid == "session"}
                       for cid in K.DEFAULT_COMPONENT_ORDER],
        "session_summary_minutes": 0}}))
    assert home.render(make_snapshot(), cfg) == ""
    SESS.LAST_SESSION = SESS.SessionSummary()


def test_pace_versus_usual_appears_in_the_hud():
    from src.session import LiveSession

    cfg = C.normalise({})
    sess = LiveSession()
    sess.reset(idle_cutoff_s=60)
    snap = make_snapshot()
    snap.speeds.overall = S.ClassSpeed(n=500, answer=10, wall=10)
    for _ in range(6):
        sess.record(20_000)  # twice the usual pace
    html = RV.build_hud_html(snap, C.normalise({"speed": {"mode": "answer"}}), sess)
    assert "vs usual" in html and "+100%" in html


def test_pace_versus_usual_waits_for_enough_answers():
    from src.session import LiveSession

    sess = LiveSession()
    sess.reset(idle_cutoff_s=60)
    sess.record(20_000)
    snap = make_snapshot()
    snap.speeds.overall = S.ClassSpeed(n=500, answer=10, wall=10)
    assert "vs usual" not in RV.build_hud_html(snap, C.normalise({}), sess)
