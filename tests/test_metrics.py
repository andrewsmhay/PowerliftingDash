import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.metrics import build_lift_cards, build_body_cards, build_total_card


def test_lift_progress_is_plain_current_over_target():
    """Progress bars must reflect current/target directly. Regression test
    for a bug where the bar used the competition value as its baseline: a
    lifter sitting exactly at their competition number (no change since the
    meet) saw a 0% bar even when very close to their target, which
    contradicted the "remaining" figure shown next to it.

    Target/competition are config, current/remaining/delta are entry-row.
    """
    entry = {
        "squat_1rm_current": 161.0,
        "squat_1rm_remaining": 9.0,
        "squat_1rm_competition_delta": 0.0,
    }
    config = {
        "squat_1rm_target": 170.0,
        "squat_1rm_competition": 161.0,  # same as current: no change since comp
    }
    cards = build_lift_cards(entry, config)
    squat = next(c for c in cards if c["label"] == "Squat")
    assert squat["progress_pct"] == 94.7


def test_lift_progress_ignores_competition_value_entirely():
    """Two lifters with the same current/target but different competition
    numbers must get the same progress percentage."""
    entry = {
        "squat_1rm_current": 150.0,
        "squat_1rm_remaining": 0.0,
        "squat_1rm_competition_delta": 0.0,
    }
    low_comp_config = {"squat_1rm_target": 150.0, "squat_1rm_competition": 100.0}
    high_comp_config = {"squat_1rm_target": 150.0, "squat_1rm_competition": 149.0}
    pct_low = next(c for c in build_lift_cards(entry, low_comp_config) if c["label"] == "Squat")["progress_pct"]
    pct_high = next(c for c in build_lift_cards(entry, high_comp_config) if c["label"] == "Squat")["progress_pct"]
    assert pct_low == pct_high == 100.0


def test_total_card_progress_is_plain_ratio():
    entry = {
        "total_weight_lifted_current": 441.0,
        "total_weight_lifted_target": 480.0,
        "total_weight_lifted_in_competition": 441.0,
        "total_weight_lifted_remaining": 39.0,
    }
    total = build_total_card(entry)
    assert total["progress_pct"] == 91.9


def test_body_card_progress_unaffected():
    entry = {"body_weight_mass": 82.0}
    config = {"body_weight_mass_target": 80.0}
    cards = build_body_cards(entry, config)
    weight = next(c for c in cards if c["label"] == "Body Weight")
    assert weight["progress_pct"] == 100.0


def test_progress_pct_none_when_missing_current_or_target():
    config = {"squat_1rm_target": 170.0}
    cards = build_lift_cards(entry=None, config=config)  # current missing
    squat = next(c for c in cards if c["label"] == "Squat")
    assert squat["progress_pct"] is None


def test_lift_card_attainment_percentages_are_unclamped():
    """Unlike progress_pct (clamped 0-100 for the bar), the attainment
    percentages shown as text may exceed 100% - overachievement should be
    visible, not hidden.
    """
    entry = {"squat_1rm_current": 171.0}
    config = {"squat_1rm_target": 170.0, "squat_1rm_competition": 160.0}
    cards = build_lift_cards(entry, config)
    squat = next(c for c in cards if c["label"] == "Squat")
    assert squat["target_attainment_pct"] == 100.6
    assert squat["competition_attainment_pct"] == 106.9


def test_lift_card_attainment_percentages_none_when_inputs_missing():
    cards = build_lift_cards(entry=None, config={})
    squat = next(c for c in cards if c["label"] == "Squat")
    assert squat["target_attainment_pct"] is None
    assert squat["competition_attainment_pct"] is None


def test_lift_card_personal_best_from_settings():
    entry = {"squat_1rm_current": 150.0}
    settings = {"opl_best_squat": 172.5, "opl_best_bench": None}
    cards = build_lift_cards(entry, config={}, settings=settings)
    squat = next(c for c in cards if c["label"] == "Squat")
    bench = next(c for c in cards if c["label"] == "Bench")
    assert squat["personal_best"] == 172.5
    assert bench["personal_best"] is None


def test_total_card_has_target_attainment_but_not_competition_attainment():
    """The Total widget excludes the competition-attainment percentage per
    the product requirement - only per-lift cards compare against the last
    competition result.
    """
    entry = {
        "total_weight_lifted_current": 441.0,
        "total_weight_lifted_target": 480.0,
        "total_weight_lifted_in_competition": 400.0,
        "total_weight_lifted_remaining": 39.0,
    }
    total = build_total_card(entry, settings={"opl_best_total": 500.0})
    assert total["target_attainment_pct"] == 91.9
    assert "competition_attainment_pct" not in total
    assert total["personal_best"] == 500.0


def test_dashboard_cards_have_stable_widget_ids():
    from app.metrics import build_index_cards

    lift_ids = {card["id"] for card in build_lift_cards({}, {})}
    body_ids = {card["id"] for card in build_body_cards({}, {})}
    index_ids = {card["id"] for card in build_index_cards({}, {})}
    assert lift_ids == {"lift.squat", "lift.bench", "lift.deadlift"}
    assert build_total_card({})["id"] == "lift.total"
    assert body_ids == {
        "body.body_weight_mass", "body.skeletal_muscle_mass", "body.body_fat_mass", "body.percent_body_fat"
    }
    assert index_ids == {"index.bmi", "index.bmr"}


def test_build_analytics_payload_with_full_data():
    from datetime import date
    from app.metrics import build_analytics_payload

    entry = {
        "total_weight_lifted_current": 450.0,
        "body_weight_mass": 90.0,
        "squat_1rm_current": 160.0,
        "bench_1rm_current": 110.0,
        "deadlift_1rm_current": 180.0,
    }
    history = [
        {"entry_date": "2026-08-01", "squat": 150.0, "bench": 100.0, "deadlift": 170.0},
        {"entry_date": "2026-08-15", "squat": 160.0, "bench": 110.0, "deadlift": 180.0},
    ]
    payload = build_analytics_payload(
        entry,
        {"squat_1rm_target": 170.0, "bench_1rm_target": 120.0, "deadlift_1rm_target": 190.0},
        {"lifter_sex": "male"},
        history,
        today=date(2026, 8, 22),
    )
    assert payload["dots_score"]["value"] is not None
    assert payload["ratios"]["squat"] == {"value": 1.78}
    assert payload["rate_of_change"]["bench"] == {"kg_per_week": 5.0}
    assert payload["projected_dates"]["deadlift"]["state"] == "projected"


def test_build_analytics_payload_with_no_data():
    from datetime import date
    from app.metrics import build_analytics_payload

    payload = build_analytics_payload({}, {}, {}, [], today=date(2026, 8, 22))
    assert payload["dots_score"] == {"value": None, "reason": "sex_not_configured"}
    assert payload["ratios"]["squat"] == {"value": None}
    assert payload["rate_of_change"]["squat"] == {"kg_per_week": None}
    assert payload["projected_dates"]["squat"] == {"state": "no_data"}
