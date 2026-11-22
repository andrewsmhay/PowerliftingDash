import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import insights
from app.analytics import compute_dots_score
from app.metrics import SCORES, build_dashboard_payload

TODAY = date(2026, 11, 22)


def entry(entry_date, squat=None, bench=None, deadlift=None, bw=None, fat=None, **extra):
    total = None
    if None not in (squat, bench, deadlift):
        total = squat + bench + deadlift
    return {
        "entry_date": entry_date, "squat": squat, "bench": bench, "deadlift": deadlift,
        "total": total, "body_weight_mass": bw, "body_fat_mass": fat, **extra,
    }


def test_parse_weight_class_handles_common_formats():
    assert insights.parse_weight_class("93") == {"label": "93 kg", "limit_kg": 93.0}
    assert insights.parse_weight_class("-105kg") == {"label": "105 kg", "limit_kg": 105.0}
    assert insights.parse_weight_class("120+") == {"label": "120+ kg", "limit_kg": None}
    assert insights.parse_weight_class("52.5") == {"label": "52.5 kg", "limit_kg": 52.5}
    assert insights.parse_weight_class("SHW") is None
    assert insights.parse_weight_class("") is None
    assert insights.parse_weight_class(None) is None


def test_next_meet_is_soonest_upcoming_with_last_meet_class_fallback():
    countdowns = [
        {"event_date": "2026-11-01", "event_name": "Past"},
        {"event_date": "2027-03-01", "event_name": "Later"},
        {"event_date": "2027-01-10", "event_name": "Provincials", "city": "Ottawa", "country": "Canada"},
    ]
    competitions = [{"weight_class": "105"}, {"weight_class": "93"}]
    meet = insights.find_next_meet(countdowns, competitions, TODAY)
    assert meet["event_name"] == "Provincials"
    assert meet["days_until"] == 49
    assert meet["location"] == "Ottawa, Canada"
    assert meet["weight_class"]["limit_kg"] == 105.0
    assert meet["weight_class_source"] == "last_meet"


def test_next_meet_prefers_countdown_class_and_handles_none():
    countdowns = [{"event_date": "2027-01-10", "event_name": "Nats", "weight_class": "93"}]
    meet = insights.find_next_meet(countdowns, [{"weight_class": "105"}], TODAY)
    assert meet["weight_class"]["limit_kg"] == 93.0
    assert meet["weight_class_source"] == "countdown"
    assert insights.find_next_meet([], [], TODAY) is None


def test_meet_projection_extends_each_lift_trend_to_meet_day():
    history = [entry("2026-11-15", 200, 140, 250)]
    rates = {"squat": {"kg_per_week": 1.0}, "bench": {"kg_per_week": 0.5}, "deadlift": {"kg_per_week": None}}
    config = {"squat_1rm_target": 210, "bench_1rm_target": 145, "deadlift_1rm_target": 260}
    meet = {"event_date": "2027-01-10"}  # 8 weeks after the latest entry
    result = insights.build_meet_projection(history, config, rates, meet)
    assert result["lifts"]["squat"]["projected"] == 208.0
    assert result["lifts"]["bench"]["projected"] == 144.0
    assert result["lifts"]["deadlift"]["projected"] == 250.0  # no trend, held flat
    assert result["lifts"]["deadlift"]["trend_available"] is False
    assert result["projected_total"] == 602.0
    assert result["target_total"] == 615.0
    assert result["projected_vs_target"] == -13.0


def test_meet_projection_without_meet_still_returns_series():
    history = [entry("2026-11-15", 200, 140, 250)]
    result = insights.build_meet_projection(history, {}, {}, None)
    assert result["projected_total"] is None
    assert result["series"] == [{"date": "2026-11-15", "total": 590}]


def test_weight_class_status_flags_cut_needed():
    history = [entry("2026-10-25", bw=97.0), entry("2026-11-22", bw=96.0)]
    meet = {"event_date": "2027-01-17", "days_until": 56, "weight_class": {"label": "93 kg", "limit_kg": 93.0},
            "weight_class_source": "countdown"}
    status = insights.build_weight_class_status(history, meet, TODAY)
    assert status["margin_kg"] == -3.0
    assert status["required_kg_per_week"] == -0.38
    assert status["trend_kg_per_week"] == -0.25
    assert status["projected_weigh_in"] == 94.0
    assert status["state"] == "over"


def test_weight_class_status_states():
    history = [entry("2026-11-22", bw=90.0)]
    open_meet = {"event_date": "2027-01-17", "days_until": 56,
                 "weight_class": {"label": "120+ kg", "limit_kg": None}}
    assert insights.build_weight_class_status(history, open_meet, TODAY)["state"] == "open_class"
    assert insights.build_weight_class_status(history, None, TODAY)["state"] == "no_class"
    assert insights.build_weight_class_status([], None, TODAY)["state"] == "no_data"
    under = dict(open_meet, weight_class={"label": "93 kg", "limit_kg": 93.0})
    assert insights.build_weight_class_status(history, under, TODAY)["state"] == "on_track"


def test_target_progress_measures_from_first_entry_in_both_directions():
    history = [
        entry("2026-01-01", 180, 120, 220, bw=100.0, fat=25.0),
        entry("2026-11-01", 195, 130, 240, bw=98.0, fat=20.0),
    ]
    config = {"squat_1rm_target": 200, "body_fat_mass_target": 15}
    rows = insights.build_target_progress(history, config, {}, {}, SCORES)
    by_label = {row["label"]: row for row in rows}
    assert set(by_label) == {"Squat", "Fat mass"}
    assert by_label["Squat"]["progress_pct"] == 75.0
    assert by_label["Fat mass"]["progress_pct"] == 50.0
    assert by_label["Fat mass"]["direction"] == "down"
    assert by_label["Squat"]["met"] is False


def test_target_progress_caps_met_targets_at_one_hundred():
    history = [entry("2026-01-01", 180, 120, 220), entry("2026-11-01", 210, 125, 230)]
    rows = insights.build_target_progress(history, {"squat_1rm_target": 200}, {}, {}, SCORES)
    assert rows[0]["met"] is True
    assert rows[0]["progress_pct"] == 100.0


def test_strength_scatter_curves_match_dots_formula():
    history = [entry("2026-11-01", 200, 140, 250, bw=95.0)]
    result = insights.build_strength_scatter(history, [], "male")
    assert len(result["dots_curves"]) == 5
    curve = result["dots_curves"][2]
    point = curve["points"][len(curve["points"]) // 2]
    score = compute_dots_score(point["total"], point["body_weight"], "male")["value"]
    assert abs(score - curve["dots"]) < 0.2


def test_strength_scatter_without_sex_has_no_curves():
    history = [entry("2026-11-01", 200, 140, 250, bw=95.0)]
    result = insights.build_strength_scatter(history, [], None)
    assert result["dots_curves"] == []
    assert result["sex_configured"] is False
    assert len(result["entries"]) == 1


def test_gym_vs_platform_pairs_latest_recent_gym_total():
    history = [
        entry("2026-01-01", 180, 120, 220),
        entry("2026-05-20", 200, 130, 240),
        entry("2026-06-10", 205, 135, 250),
    ]
    competitions = [
        {"competition_date": "2026-06-01", "meet_name": "Summer Open", "total_kg": 555},
        {"competition_date": "2025-06-01", "meet_name": "Too early", "total_kg": 500},
    ]
    result = insights.build_gym_vs_platform(history, competitions)
    assert [row["meet_name"] for row in result["meets"]] == ["Too early", "Summer Open"]
    assert result["meets"][0]["gym_total"] is None
    assert result["meets"][1]["gym_total"] == 570
    assert result["meets"][1]["carryover_pct"] == 97.4
    assert result["average_carryover_pct"] == 97.4
    assert result["paired_count"] == 1


def test_lift_balance_uses_last_complete_entry_per_month():
    history = [
        entry("2026-09-02", 100, 100, 100),
        entry("2026-09-28", 200, 100, 200),
        entry("2026-10-15", 200, None, 200),
    ]
    months = insights.build_lift_balance(history)["months"]
    assert len(months) == 1
    assert months[0]["month"] == "2026-09"
    assert months[0]["squat_pct"] == 40.0
    assert months[0]["bench_pct"] == 20.0


def test_recomposition_classifies_quadrants():
    history = [
        entry("2026-08-30", bw=100.0, fat=25.0),
        entry("2026-09-30", bw=100.0, fat=23.0),  # lean +2, fat -2
        entry("2026-10-30", bw=102.0, fat=24.0),  # lean +1, fat +1
        entry("2026-11-20", bw=99.0, fat=23.0),   # lean -2, fat -1
    ]
    periods = insights.build_recomposition(history)["periods"]
    assert [period["quadrant"] for period in periods] == ["recomposition", "lean_gain", "cut"]
    assert periods[0]["lean_change"] == 2.0
    assert periods[0]["fat_change"] == -2.0


def test_dashboard_payload_includes_meet_prep_and_performance_with_no_data():
    payload = build_dashboard_payload(None, [], {}, {}, [], full_history=[])
    assert payload["meet_prep"]["next_meet"] is None
    assert payload["meet_prep"]["target_progress"] == []
    assert payload["meet_prep"]["weight_class"]["state"] == "no_data"
    assert payload["performance"]["gym_vs_platform"]["meets"] == []
    assert payload["performance"]["lift_balance"]["months"] == []
