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


def test_lean_mass_card_is_bodyweight_minus_fat_mass():
    entry = {"body_weight_mass": 82.0, "body_fat_mass": 15.5}
    cards = build_body_cards(entry, config={})
    lean_mass = next(c for c in cards if c["id"] == "body.lean_mass")
    assert lean_mass["label"] == "Lean Mass"
    assert lean_mass["unit"] == "kg"
    assert lean_mass["current"] == 66.5
    assert lean_mass["target"] is None
    assert lean_mass["to_date"] is None


def test_lean_mass_card_none_when_inputs_missing():
    cards = build_body_cards({"body_weight_mass": 82.0}, config={})
    lean_mass = next(c for c in cards if c["id"] == "body.lean_mass")
    assert lean_mass["current"] is None


def test_lean_mass_to_date_uses_earliest_entry_with_both_inputs():
    history = [
        {"entry_date": "2026-06-01", "body_weight_mass": 90.0},
        {"entry_date": "2026-06-08", "body_weight_mass": 88.0, "body_fat_mass": 20.0},
        {"entry_date": "2026-06-15", "body_weight_mass": 84.0, "body_fat_mass": 15.0},
    ]
    entry = {"body_weight_mass": 82.0, "body_fat_mass": 14.0}
    cards = build_body_cards(entry, config={}, history_asc=history)
    lean_mass = next(c for c in cards if c["id"] == "body.lean_mass")
    # current lean mass 68.0, baseline is the first row with both fields (88.0 - 20.0 = 68.0)
    assert lean_mass["current"] == 68.0
    assert lean_mass["to_date"] == 0.0


def test_lean_mass_to_date_none_without_history():
    entry = {"body_weight_mass": 82.0, "body_fat_mass": 14.0}
    cards = build_body_cards(entry, config={})
    lean_mass = next(c for c in cards if c["id"] == "body.lean_mass")
    assert lean_mass["to_date"] is None


def test_body_card_target_attainment_pct_is_unclamped():
    entry = {"body_weight_mass": 82.0}
    config = {"body_weight_mass_target": 80.0}
    cards = build_body_cards(entry, config)
    weight = next(c for c in cards if c["label"] == "Body Weight")
    assert weight["progress_pct"] == 100.0
    assert weight["target_attainment_pct"] == 102.5


def test_body_card_target_attainment_pct_none_without_target():
    entry = {"body_weight_mass": 82.0}
    cards = build_body_cards(entry, config={})
    weight = next(c for c in cards if c["label"] == "Body Weight")
    assert weight["target_attainment_pct"] is None


def test_lean_mass_card_has_no_target_attainment_pct():
    entry = {"body_weight_mass": 82.0, "body_fat_mass": 15.5}
    cards = build_body_cards(entry, config={})
    lean_mass = next(c for c in cards if c["id"] == "body.lean_mass")
    assert lean_mass["target_attainment_pct"] is None


def test_index_cards_expose_target_attainment_pct():
    from app.metrics import build_index_cards

    entry = {"bmi": 24.0, "bmr": 1800.0}
    config = {"bmi_target": 24.0, "bmr_target": 2000.0}
    cards = build_index_cards(entry, config)
    bmi = next(c for c in cards if c["id"] == "index.bmi")
    bmr = next(c for c in cards if c["id"] == "index.bmr")
    assert bmi["target_attainment_pct"] == 100.0
    assert bmr["target_attainment_pct"] == 90.0


def test_index_card_target_attainment_pct_none_without_target():
    from app.metrics import build_index_cards

    cards = build_index_cards({"bmi": 24.0}, config={})
    bmi = next(c for c in cards if c["id"] == "index.bmi")
    assert bmi["target_attainment_pct"] is None


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
        "body.body_weight_mass", "body.skeletal_muscle_mass", "body.body_fat_mass", "body.percent_body_fat",
        "body.lean_mass",
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
    assert payload["wilks2_score"]["value"] is not None
    assert payload["ipf_gl_score"]["value"] is not None
    assert payload["ratios"]["squat"] == {"value": 1.78}
    assert payload["rate_of_change"]["bench"] == {"kg_per_week": 5.0}
    assert payload["projected_dates"]["deadlift"]["state"] == "projected"
    # No full_history_asc was passed, so pr_intervals falls back to the windowed
    # history - one genuine PR (160 after the 150 baseline), so no average yet.
    assert payload["pr_intervals"]["squat"]["pr_count"] == 1
    assert payload["pr_intervals"]["squat"]["avg_days_between_prs"] is None


def test_build_analytics_payload_pr_intervals_use_full_history_when_provided():
    from datetime import date
    from app.metrics import build_analytics_payload

    windowed_history = [
        {"entry_date": "2026-08-01", "squat": 150.0},
        {"entry_date": "2026-08-15", "squat": 160.0},
    ]
    full_history = [
        {"entry_date": "2026-01-01", "squat": 100.0},
        {"entry_date": "2026-03-01", "squat": 130.0},
    ] + windowed_history

    payload = build_analytics_payload(
        {},
        {},
        {},
        windowed_history,
        full_history_asc=full_history,
        today=date(2026, 8, 22),
    )
    # Full history has 3 genuine PRs (130, 150, 160) vs. just 1 in the window.
    assert payload["pr_intervals"]["squat"]["pr_count"] == 3
    assert payload["pr_intervals"]["squat"]["avg_days_between_prs"] is not None


def test_build_analytics_payload_with_no_data():
    from datetime import date
    from app.metrics import build_analytics_payload

    payload = build_analytics_payload({}, {}, {}, [], today=date(2026, 8, 22))
    assert payload["dots_score"]["value"] is None
    assert payload["dots_score"]["reason"] == "sex_not_configured"
    assert payload["wilks2_score"]["value"] is None
    assert payload["wilks2_score"]["reason"] == "sex_not_configured"
    assert payload["ipf_gl_score"]["value"] is None
    assert payload["ipf_gl_score"]["reason"] == "sex_not_configured"
    assert payload["ratios"]["squat"] == {"value": None}
    assert payload["rate_of_change"]["squat"] == {"kg_per_week": None}
    assert payload["projected_dates"]["squat"] == {"state": "no_data"}


def test_build_analytics_payload_score_cards_include_target_remaining_and_delta():
    from datetime import date
    from app.metrics import build_analytics_payload

    history = [
        {"entry_date": "2026-08-01", "total": 400.0, "body_weight_mass": 90.0},
        {"entry_date": "2026-08-15", "total": 450.0, "body_weight_mass": 90.0},
    ]
    entry = {"total_weight_lifted_current": 450.0, "body_weight_mass": 90.0}
    payload = build_analytics_payload(
        entry,
        {"dots_score_target": 400.0, "wilks2_score_target": 500.0, "ipf_gl_points_target": 90.0},
        {"lifter_sex": "male"},
        history,
        today=date(2026, 8, 22),
    )
    for key, target in (
        ("dots_score", 400.0), ("wilks2_score", 500.0), ("ipf_gl_score", 90.0),
    ):
        card = payload[key]
        assert card["target"] == target
        assert card["value"] is not None
        assert card["remaining"] == round(target - card["value"], 1)
        # The most recent history row before the current entry lifted less
        # at the same bodyweight, so every score should have increased.
        assert card["delta_from_last_entry"] is not None
        assert card["delta_from_last_entry"] > 0


def test_build_analytics_payload_score_delta_is_none_without_previous_entry():
    from datetime import date
    from app.metrics import build_analytics_payload

    entry = {"total_weight_lifted_current": 450.0, "body_weight_mass": 90.0}
    payload = build_analytics_payload(
        entry, {}, {"lifter_sex": "male"},
        [{"entry_date": "2026-08-22", "total": 450.0, "body_weight_mass": 90.0}],
        today=date(2026, 8, 22),
    )
    assert payload["dots_score"]["delta_from_last_entry"] is None
    assert payload["wilks2_score"]["delta_from_last_entry"] is None
    assert payload["ipf_gl_score"]["delta_from_last_entry"] is None
