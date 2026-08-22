"""Pure calculation helpers for dashboard analytics widgets."""
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
