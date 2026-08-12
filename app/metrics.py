"""Turns a raw `entries` row into the grouped structure the dashboard
templates and JSON API render: lift cards, body composition cards, and
BMI/BMR cards, each with current/target/competition/remaining values and a
progress percentage where that makes sense.
"""

LIFTS = [
    {"key": "squat", "label": "Squat"},
    {"key": "bench", "label": "Bench"},
    {"key": "deadlift", "label": "Deadlift"},
]

BODY_METRICS = [
    {"key": "body_weight_mass", "label": "Body Weight", "unit": "kg"},
    {"key": "skeletal_muscle_mass", "label": "Skeletal Muscle Mass", "unit": "kg"},
    {"key": "body_fat_mass", "label": "Body Fat Mass", "unit": "kg"},
    {"key": "percent_body_fat", "label": "Body Fat", "unit": "%"},
]


def _safe(value):
    return value if isinstance(value, (int, float)) else None


def _progress_pct(current, target, competition=None):
    """0-100 progress towards target, using competition (or 0) as the
    starting baseline where available, so the bar reflects genuine progress
    rather than an arbitrary zero point.
    """
    if current is None or target is None or target == 0:
        return None
    baseline = competition if competition is not None else 0
    span = target - baseline
    if span == 0:
        return 100 if current >= target else 0
    pct = (current - baseline) / span * 100
    return max(0, min(100, round(pct, 1)))


def build_lift_cards(entry: dict | None) -> list[dict]:
    cards = []
    for lift in LIFTS:
        key = lift["key"]
        current = _safe((entry or {}).get(f"{key}_1rm_current"))
        target = _safe((entry or {}).get(f"{key}_1rm_target"))
        competition = _safe((entry or {}).get(f"{key}_1rm_competition"))
        remaining = _safe((entry or {}).get(f"{key}_1rm_remaining"))
        delta = _safe((entry or {}).get(f"{key}_1rm_competition_delta"))
        cards.append(
            {
                "label": lift["label"],
                "unit": "kg",
                "current": current,
                "target": target,
                "competition": competition,
                "remaining": remaining,
                "competition_delta": delta,
                "progress_pct": _progress_pct(current, target, competition),
            }
        )
    return cards


def build_total_card(entry: dict | None) -> dict:
    entry = entry or {}
    current = _safe(entry.get("total_weight_lifted_current"))
    target = _safe(entry.get("total_weight_lifted_target"))
    competition = _safe(entry.get("total_weight_lifted_in_competition"))
    remaining = _safe(entry.get("total_weight_lifted_remaining"))
    return {
        "label": "Total",
        "unit": "kg",
        "current": current,
        "target": target,
        "competition": competition,
        "remaining": remaining,
        "progress_pct": _progress_pct(current, target, competition),
    }


def build_body_cards(entry: dict | None) -> list[dict]:
    entry = entry or {}
    cards = []
    for metric in BODY_METRICS:
        key = metric["key"]
        current = _safe(entry.get(key))
        target = _safe(entry.get(f"{key}_target"))
        remaining = _safe(entry.get(f"{key}_remaining"))
        to_date = _safe(entry.get(f"{key}_to_date"))
        cards.append(
            {
                "label": metric["label"],
                "unit": metric["unit"],
                "current": current,
                "target": target,
                "remaining": remaining,
                "to_date": to_date,
                "progress_pct": _progress_pct(current, target),
            }
        )
    return cards


def build_index_cards(entry: dict | None) -> list[dict]:
    entry = entry or {}
    return [
        {
            "label": "BMI",
            "unit": "kg/m\u00b2",
            "current": _safe(entry.get("bmi")),
            "target": _safe(entry.get("bmi_target")),
            "to_date": _safe(entry.get("bmi_to_date")),
        },
        {
            "label": "BMR",
            "unit": "kcal",
            "current": _safe(entry.get("bmr")),
            "target": _safe(entry.get("bmr_target")),
            "to_date": _safe(entry.get("bmr_to_date")),
        },
    ]


def build_dashboard_payload(latest_entry: dict | None, history: list[dict]) -> dict:
    return {
        "latest_entry_date": (latest_entry or {}).get("entry_date"),
        "lift_cards": build_lift_cards(latest_entry),
        "total_card": build_total_card(latest_entry),
        "weight_change_since_comp": _safe((latest_entry or {}).get("weight_change_since_comp")),
        "body_cards": build_body_cards(latest_entry),
        "index_cards": build_index_cards(latest_entry),
        "history": [
            {
                "entry_date": row["entry_date"],
                "squat": row.get("squat_1rm_current"),
                "bench": row.get("bench_1rm_current"),
                "deadlift": row.get("deadlift_1rm_current"),
                "total": row.get("total_weight_lifted_current"),
                "body_weight_mass": row.get("body_weight_mass"),
                "body_fat_mass": row.get("body_fat_mass"),
                "skeletal_muscle_mass": row.get("skeletal_muscle_mass"),
                "percent_body_fat": row.get("percent_body_fat"),
                "bmi": row.get("bmi"),
                "bmr": row.get("bmr"),
            }
            for row in history
        ],
    }
