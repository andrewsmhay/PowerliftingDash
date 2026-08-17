"""Turns a raw `entries` row into the grouped structure the dashboard
templates and JSON API render: lift cards, body composition cards, and
BMI/BMR cards, each with current/target/competition/remaining values and a
progress percentage where that makes sense.

Current values (and every derived remaining/delta/to-date figure) come from
the entry row. Target and competition values are hardcoded goals from the
/targets screen, so they come from a `config` dict (`db.get_config()`)
instead - the same config snapshot applies regardless of which entry is
being shown.
"""

from .formatting import dashboard_title

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


def _pct(current, base):
    """Unclamped percentage of `current` against `base`, one decimal place.

    Distinct from `_progress_pct`, which is clamped 0-100 and drives the
    progress bar's width only. Attainment percentages shown as text (e.g.
    "106.7% of last competition") are allowed to run past 100% - clamping
    them would hide genuine overachievement.
    """
    if current is None or base is None or base == 0:
        return None
    return round(current / base * 100, 1)


def _progress_pct(current, target):
    """0-100 progress towards target, as a plain current/target ratio.

    Kept deliberately simple and consistent across every card type: the
    bar always answers "how close to the target am I", while any
    comparison to a competition lift is shown separately via the
    competition/competition_delta fields rather than folded into the bar.
    An earlier version used the competition value as the bar's baseline,
    which meant a lifter sitting right at their competition number (i.e.
    no change since the meet) saw an empty bar even when close to target -
    contradicting the "Remaining" figure shown alongside it.
    """
    if current is None or target is None or target == 0:
        return None
    pct = current / target * 100
    return max(0, min(100, round(pct, 1)))


def build_lift_cards(
    entry: dict | None, config: dict | None = None, settings: dict | None = None
) -> list[dict]:
    config = config or {}
    settings = settings or {}
    cards = []
    for lift in LIFTS:
        key = lift["key"]
        current = _safe((entry or {}).get(f"{key}_1rm_current"))
        target = _safe(config.get(f"{key}_1rm_target"))
        competition = _safe(config.get(f"{key}_1rm_competition"))
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
                "progress_pct": _progress_pct(current, target),
                "target_attainment_pct": _pct(current, target),
                "competition_attainment_pct": _pct(current, competition),
                "personal_best": _safe(settings.get(f"opl_best_{key}")),
            }
        )
    return cards


def build_total_card(entry: dict | None, settings: dict | None = None) -> dict:
    entry = entry or {}
    settings = settings or {}
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
        "progress_pct": _progress_pct(current, target),
        "target_attainment_pct": _pct(current, target),
        "personal_best": _safe(settings.get("opl_best_total")),
    }


def build_body_cards(entry: dict | None, config: dict | None = None) -> list[dict]:
    entry = entry or {}
    config = config or {}
    cards = []
    for metric in BODY_METRICS:
        key = metric["key"]
        current = _safe(entry.get(key))
        target = _safe(config.get(f"{key}_target"))
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


def build_index_cards(entry: dict | None, config: dict | None = None) -> list[dict]:
    entry = entry or {}
    config = config or {}
    return [
        {
            "label": "BMI",
            "unit": "kg/m\u00b2",
            "current": _safe(entry.get("bmi")),
            "target": _safe(config.get("bmi_target")),
            "to_date": _safe(entry.get("bmi_to_date")),
        },
        {
            "label": "BMR",
            "unit": "kcal",
            "current": _safe(entry.get("bmr")),
            "target": _safe(config.get("bmr_target")),
            "to_date": _safe(entry.get("bmr_to_date")),
        },
    ]


def build_dashboard_payload(
    latest_entry: dict | None,
    history: list[dict],
    config: dict | None = None,
    settings: dict | None = None,
) -> dict:
    config = config or {}
    settings = settings or {}
    return {
        "latest_entry_date": (latest_entry or {}).get("entry_date"),
        "lifter_name": settings.get("display_name"),
        "dashboard_title": dashboard_title(settings.get("display_name")),
        "lift_cards": build_lift_cards(latest_entry, config, settings),
        "total_card": build_total_card(latest_entry, settings),
        "weight_change_since_comp": _safe((latest_entry or {}).get("weight_change_since_comp")),
        "body_cards": build_body_cards(latest_entry, config),
        "index_cards": build_index_cards(latest_entry, config),
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
