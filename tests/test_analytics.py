import math
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.analytics import (
    DOTS_COEFFICIENTS,
    IPF_GL_COEFFICIENTS,
    WILKS2_COEFFICIENTS,
    compute_dots_score,
    compute_ipf_gl_score,
    compute_projected_date,
    compute_rate_of_change,
    compute_ratio,
    compute_wilks2_score,
)


def expected_dots(total, bodyweight, sex):
    coefficients = DOTS_COEFFICIENTS[sex]
    clamped = max(coefficients["bw_min"], min(coefficients["bw_max"], bodyweight))
    denominator = (
        coefficients["a"] + coefficients["b"] * clamped + coefficients["c"] * clamped ** 2
        + coefficients["d"] * clamped ** 3 + coefficients["e"] * clamped ** 4
    )
    return round(total * 500 / denominator, 1)


def test_compute_dots_score_for_male_and_female():
    assert compute_dots_score(600, 100, "male") == {"value": expected_dots(600, 100, "male"), "unit": "DOTS"}
    assert compute_dots_score(400, 65, "female") == {"value": expected_dots(400, 65, "female"), "unit": "DOTS"}


def test_compute_dots_score_clamps_at_each_bodyweight_edge():
    assert compute_dots_score(500, 20, "male")["value"] == expected_dots(500, 40, "male")
    assert compute_dots_score(500, 260, "male")["value"] == expected_dots(500, 210, "male")
    assert compute_dots_score(300, 20, "female")["value"] == expected_dots(300, 40, "female")
    assert compute_dots_score(300, 180, "female")["value"] == expected_dots(300, 150, "female")


def test_compute_dots_score_returns_reasons_for_missing_inputs():
    assert compute_dots_score(500, 90, None) == {"value": None, "reason": "sex_not_configured"}
    assert compute_dots_score(None, 90, "male") == {"value": None, "reason": "no_data"}
    assert compute_dots_score(500, None, "female") == {"value": None, "reason": "no_data"}


def expected_wilks2(total, bodyweight, sex):
    coefficients = WILKS2_COEFFICIENTS[sex]
    denominator = (
        coefficients["a"] + coefficients["b"] * bodyweight + coefficients["c"] * bodyweight ** 2
        + coefficients["d"] * bodyweight ** 3 + coefficients["e"] * bodyweight ** 4
        + coefficients["f"] * bodyweight ** 5
    )
    return round(total * 600 / denominator, 1)


def expected_ipf_gl(total, bodyweight, sex):
    coefficients = IPF_GL_COEFFICIENTS[sex]
    denominator = coefficients["A"] - coefficients["B"] * math.exp(-coefficients["C"] * bodyweight)
    return round(total * 100 / denominator, 1)


def test_compute_wilks2_score_for_male_and_female():
    assert compute_wilks2_score(600, 100, "male") == {"value": expected_wilks2(600, 100, "male"), "unit": "Wilks-2"}
    assert compute_wilks2_score(400, 65, "female") == {"value": expected_wilks2(400, 65, "female"), "unit": "Wilks-2"}


def test_compute_wilks2_score_returns_reasons_for_missing_inputs():
    assert compute_wilks2_score(500, 90, None) == {"value": None, "reason": "sex_not_configured"}
    assert compute_wilks2_score(None, 90, "male") == {"value": None, "reason": "no_data"}
    assert compute_wilks2_score(500, None, "female") == {"value": None, "reason": "no_data"}


def test_compute_ipf_gl_score_for_male_and_female():
    assert compute_ipf_gl_score(600, 100, "male") == {"value": expected_ipf_gl(600, 100, "male"), "unit": "GL Points"}
    assert compute_ipf_gl_score(400, 65, "female") == {"value": expected_ipf_gl(400, 65, "female"), "unit": "GL Points"}


def test_compute_ipf_gl_score_returns_reasons_for_missing_inputs():
    assert compute_ipf_gl_score(500, 90, None) == {"value": None, "reason": "sex_not_configured"}
    assert compute_ipf_gl_score(None, 90, "male") == {"value": None, "reason": "no_data"}
    assert compute_ipf_gl_score(500, None, "female") == {"value": None, "reason": "no_data"}


def test_compute_ratio_handles_valid_and_missing_values():
    assert compute_ratio(185, 100) == {"value": 1.85}
    assert compute_ratio(None, 100) == {"value": None}
    assert compute_ratio(185, 0) == {"value": None}


def test_compute_rate_of_change_uses_current_date_window():
    today = date(2026, 8, 22)
    history = [
        {"entry_date": "2026-08-01", "squat": 100},
        {"entry_date": "2026-08-15", "squat": 110},
        {"entry_date": "2026-08-22", "squat": 115},
    ]
    assert compute_rate_of_change(history, "squat", 90, today) == {"kg_per_week": 5.0}


def test_compute_rate_of_change_requires_two_recent_dates():
    today = date(2026, 8, 22)
    assert compute_rate_of_change([
        {"entry_date": "2026-08-20", "squat": 100},
        {"entry_date": "2026-08-20", "squat": 105},
    ], "squat", 90, today) == {"kg_per_week": None}


def test_compute_rate_of_change_drops_stale_history_using_today_anchor():
    today = date(2026, 8, 22)
    stale_history = [
        {"entry_date": "2026-01-01", "squat": 100},
        {"entry_date": "2026-01-15", "squat": 110},
    ]
    assert compute_rate_of_change(stale_history, "squat", 90, today) == {"kg_per_week": None}


def test_compute_projected_date_returns_all_states():
    today = date(2026, 8, 22)
    assert compute_projected_date(150, 140, 1, today) == {"state": "target_met"}
    assert compute_projected_date(None, 160, 1, today) == {"state": "no_data"}
    assert compute_projected_date(150, 160, 0, today) == {"state": "not_on_track"}
    assert compute_projected_date(150, 160, -1, today) == {"state": "not_on_track"}
    assert compute_projected_date(150, 160, 0.01, today) == {"state": "too_far", "years": 19.2}
    assert compute_projected_date(150, 160, 5, today) == {"state": "projected", "date": "2026-09-05"}
