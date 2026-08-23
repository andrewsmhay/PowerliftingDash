"""Pure calculation helpers for dashboard analytics widgets."""
import math
from datetime import date, timedelta

DOTS_COEFFICIENTS = {
    "male": {
        "a": -307.75076, "b": 24.0900756, "c": -0.1918759221,
        "d": 0.0007391293, "e": -0.000001093, "bw_min": 40.0, "bw_max": 210.0,
    },
    "female": {
        "a": -57.96288, "b": 13.6175032, "c": -0.1126655495,
        "d": 0.0005158568, "e": -0.0000010706, "bw_min": 40.0, "bw_max": 150.0,
    },
}


def compute_dots_score(total_kg, bodyweight_kg, sex):
    """Returns a DOTS value, or a reason when the inputs are incomplete."""
    if sex not in DOTS_COEFFICIENTS:
        return {"value": None, "reason": "sex_not_configured"}
    if total_kg is None or bodyweight_kg is None:
        return {"value": None, "reason": "no_data"}
    coefficients = DOTS_COEFFICIENTS[sex]
    bodyweight = max(coefficients["bw_min"], min(coefficients["bw_max"], bodyweight_kg))
    denominator = (
        coefficients["a"]
        + coefficients["b"] * bodyweight
        + coefficients["c"] * bodyweight ** 2
        + coefficients["d"] * bodyweight ** 3
        + coefficients["e"] * bodyweight ** 4
    )
    if denominator <= 0:
        return {"value": None, "reason": "no_data"}
    return {"value": round(total_kg * 500 / denominator, 1), "unit": "DOTS"}


# Wilks 2020 ("Wilks-2") coefficients. Source: https://en.wikipedia.org/wiki/Wilks_coefficient
# Normalisation constant is 600 (the original 1994 Wilks formula used 500 -
# that superseded version is not implemented here).
WILKS2_COEFFICIENTS = {
    "male": {
        "a": 47.46178854, "b": 8.472061379, "c": 0.07369410346,
        "d": -0.001395833811, "e": 7.07665973070743e-6, "f": -1.20804336482315e-8,
    },
    "female": {
        "a": -125.4255398, "b": 13.71219419, "c": -0.03307250631,
        "d": -0.001050400051, "e": 9.38773881462799e-6, "f": -2.3334613884954e-8,
    },
}


def compute_wilks2_score(total_kg, bodyweight_kg, sex):
    """Returns a Wilks-2 (2020) value, or a reason when the inputs are
    incomplete. Same shape as compute_dots_score."""
    if sex not in WILKS2_COEFFICIENTS:
        return {"value": None, "reason": "sex_not_configured"}
    if total_kg is None or bodyweight_kg is None:
        return {"value": None, "reason": "no_data"}
    coefficients = WILKS2_COEFFICIENTS[sex]
    bodyweight = bodyweight_kg
    denominator = (
        coefficients["a"]
        + coefficients["b"] * bodyweight
        + coefficients["c"] * bodyweight ** 2
        + coefficients["d"] * bodyweight ** 3
        + coefficients["e"] * bodyweight ** 4
        + coefficients["f"] * bodyweight ** 5
    )
    if denominator <= 0:
        return {"value": None, "reason": "no_data"}
    return {"value": round(total_kg * 600 / denominator, 1), "unit": "Wilks-2"}


# IPF GL Points (classic/raw, 2020 season) coefficients.
# Source: https://www.powerlifting.sport/fileadmin/ipf/data/ipf-formula/IPF_GL_Coefficients-2020.pdf
IPF_GL_COEFFICIENTS = {
    "male": {"A": 1199.72839, "B": 1025.18162, "C": 0.00921},
    "female": {"A": 610.32796, "B": 1045.59282, "C": 0.03048},
}


def compute_ipf_gl_score(total_kg, bodyweight_kg, sex):
    """Returns an IPF GL Points value, or a reason when the inputs are
    incomplete. Same shape as compute_dots_score."""
    if sex not in IPF_GL_COEFFICIENTS:
        return {"value": None, "reason": "sex_not_configured"}
    if total_kg is None or bodyweight_kg is None:
        return {"value": None, "reason": "no_data"}
    coefficients = IPF_GL_COEFFICIENTS[sex]
    denominator = coefficients["A"] - coefficients["B"] * math.exp(-coefficients["C"] * bodyweight_kg)
    if denominator <= 0:
        return {"value": None, "reason": "no_data"}
    return {"value": round(total_kg * 100 / denominator, 1), "unit": "GL Points"}


def compute_ratio(lift_1rm_kg, bodyweight_kg):
    """Returns a lift to bodyweight ratio when both values are usable."""
    if lift_1rm_kg is None or not bodyweight_kg:
        return {"value": None}
    return {"value": round(lift_1rm_kg / bodyweight_kg, 2)}


def compute_rate_of_change(history_asc: list[dict], key: str, window_days: int, today: date):
    """Calculates an ordinary least squares lift trend over the recent window."""
    if not history_asc:
        return {"kg_per_week": None}
    cutoff = today - timedelta(days=window_days)
    points = [
        (date.fromisoformat(row["entry_date"]), row[key])
        for row in history_asc
        if row.get(key) is not None and date.fromisoformat(row["entry_date"]) >= cutoff
    ]
    if len(points) < 2:
        return {"kg_per_week": None}
    first_date = points[0][0]
    offsets = [(point_date - first_date).days for point_date, _value in points]
    values = [value for _point_date, value in points]
    count = len(offsets)
    mean_offset = sum(offsets) / count
    mean_value = sum(values) / count
    covariance = sum(
        (offset - mean_offset) * (value - mean_value)
        for offset, value in zip(offsets, values)
    )
    variance = sum((offset - mean_offset) ** 2 for offset in offsets)
    if variance == 0:
        return {"kg_per_week": None}
    return {"kg_per_week": round(covariance / variance * 7, 2)}


def compute_pr_intervals(history_asc: list[dict], key: str, today: date):
    """Measures how often genuine breakthroughs happen for one lift.

    The first recorded value is treated as a baseline, not a PR - only
    strict increases after it count as a PR event, matching the pr_timeline
    chart's `> runningMax` strictness for every point after the first (the
    chart also highlights the first point itself as a visual starting
    marker, which this deliberately does not count, so a history that opens
    on a high number doesn't inflate the average pace with a trivial "PR").

    Returns pr_count (genuine PR events after the baseline),
    avg_days_between_prs (None until at least two genuine PRs exist),
    days_since_last_pr, last_pr_date (ISO) and last_pr_value.
    """
    empty = {
        "pr_count": 0, "avg_days_between_prs": None, "days_since_last_pr": None,
        "last_pr_date": None, "last_pr_value": None,
    }
    points = [
        (date.fromisoformat(row["entry_date"]), row[key])
        for row in history_asc
        if row.get(key) is not None
    ]
    if not points:
        return dict(empty)

    running_max = points[0][1]
    pr_dates = []
    pr_values = []
    for point_date, value in points[1:]:
        if value > running_max:
            pr_dates.append(point_date)
            pr_values.append(value)
            running_max = value

    if not pr_dates:
        return dict(empty)

    avg_days_between_prs = None
    if len(pr_dates) >= 2:
        span_days = (pr_dates[-1] - pr_dates[0]).days
        avg_days_between_prs = round(span_days / (len(pr_dates) - 1), 1)

    return {
        "pr_count": len(pr_dates),
        "avg_days_between_prs": avg_days_between_prs,
        "days_since_last_pr": (today - pr_dates[-1]).days,
        "last_pr_date": pr_dates[-1].isoformat(),
        "last_pr_value": pr_values[-1],
    }


def compute_projected_date(current, target, kg_per_week, today: date):
    """Returns the target projection state for a current lift and trend."""
    if current is None or target is None:
        return {"state": "no_data"}
    if current >= target:
        return {"state": "target_met"}
    if kg_per_week is None or kg_per_week <= 0:
        return {"state": "not_on_track"}
    days = (target - current) / (kg_per_week / 7)
    if days > 3650:
        return {"state": "too_far", "years": round(days / 365, 1)}
    return {"state": "projected", "date": (today + timedelta(days=days)).isoformat()}
