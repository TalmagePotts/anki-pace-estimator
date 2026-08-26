"""The home panel renders from plain data, so it can be checked without Anki."""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "review_pace"))

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


def test_panel_contains_every_enabled_component():
    cfg = C.normalise({"display": {"components": [
        {"id": cid, "enabled": True} for cid in K.DEFAULT_COMPONENT_ORDER]}})
    html = home.render(make_snapshot(), cfg)
    for label in ("Time remaining", "Due", "New", "Learning",
                  "New learned today", "Answered today"):
        assert label in html
    assert "Mature" in html  # breakdown chips
    assert "Medicine, Pharm" in html


def test_disabled_components_are_absent():
    cfg = C.normalise({"display": {"components": [{"id": "eta", "enabled": True}]}})
    html = home.render(make_snapshot(), cfg)
    assert "Time remaining" in html
    assert "New learned today" not in html
    assert "Answered today" not in html


def test_panel_is_empty_when_nothing_is_enabled():
    cfg = C.normalise({"display": {"components": []}})
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
    assert "Wall-clock speed" in wall and "6.6s/card" in wall
    assert "Answer speed" in answer and "5.0s/card" in answer


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
