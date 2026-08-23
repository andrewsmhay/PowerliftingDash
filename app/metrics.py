"""Builds the data structures used by dashboard cards and JSON responses."""
from datetime import datetime, timezone

from . import config as runtime_config
from .analytics import (
    compute_dots_score,
    compute_ipf_gl_score,
    compute_pr_intervals,
    compute_projected_date,
    compute_rate_of_change,
    compute_ratio,
    compute_wilks2_score,
)
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
    """Returns an unclamped attainment percentage for textual display."""
    if current is None or base is None or base == 0:
        return None
    return round(current / base * 100, 1)


def _progress_pct(current, target):
    """Returns a 0 to 100 percentage for the visible progress bar."""
    if current is None or target is None or target == 0:
        return None
    return max(0, min(100, round(current / target * 100, 1)))


def build_lift_cards(
    entry: dict | None, config: dict | None = None, settings: dict | None = None
) -> list[dict]:
    """Returns cards for the three competition lifts."""
    config = config or {}
    settings = settings or {}
    cards = []
    for lift in LIFTS:
        key = lift["key"]
        current = _safe((entry or {}).get(f"{key}_1rm_current"))
        target = _safe(config.get(f"{key}_1rm_target"))
        competition = _safe(config.get(f"{key}_1rm_competition"))
        cards.append({
            "id": f"lift.{key}",
            "label": lift["label"],
            "unit": "kg",
            "current": current,
            "target": target,
            "competition": competition,
            "remaining": _safe((entry or {}).get(f"{key}_1rm_remaining")),
            "competition_delta": _safe((entry or {}).get(f"{key}_1rm_competition_delta")),
            "progress_pct": _progress_pct(current, target),
            "target_attainment_pct": _pct(current, target),
            "competition_attainment_pct": _pct(current, competition),
            "personal_best": _safe(settings.get(f"opl_best_{key}")),
        })
    return cards


def build_total_card(entry: dict | None, settings: dict | None = None) -> dict:
    """Returns the combined total card."""
    entry = entry or {}
    settings = settings or {}
    current = _safe(entry.get("total_weight_lifted_current"))
    target = _safe(entry.get("total_weight_lifted_target"))
    return {
        "id": "lift.total",
        "label": "Total",
        "unit": "kg",
        "current": current,
        "target": target,
        "competition": _safe(entry.get("total_weight_lifted_in_competition")),
        "remaining": _safe(entry.get("total_weight_lifted_remaining")),
        "progress_pct": _progress_pct(current, target),
        "target_attainment_pct": _pct(current, target),
        "personal_best": _safe(settings.get("opl_best_total")),
    }


def _lean_mass(row: dict) -> float | None:
    body_weight = _safe(row.get("body_weight_mass"))
    body_fat = _safe(row.get("body_fat_mass"))
    if body_weight is None or body_fat is None:
        return None
    return round(body_weight - body_fat, 2)


def _lean_mass_card(entry: dict, history_asc: list[dict] | None = None) -> dict:
    """Lean mass (bodyweight minus fat mass) is calculated on the fly from
    the two manual smart-scale readings rather than stored on the entry -
    it is not part of Andrew's original 44-field schema, so it has no
    target of its own. "To date" follows the same baseline convention as
    every other body card: current minus the value on the earliest entry
    that has both inputs recorded.
    """
    current = _lean_mass(entry)
    to_date = None
    if current is not None:
        for row in history_asc or []:
            baseline = _lean_mass(row)
            if baseline is not None:
                to_date = round(current - baseline, 2)
                break
    return {
        "id": "body.lean_mass",
        "label": "Lean Mass",
        "unit": "kg",
        "current": current,
        "target": None,
        "remaining": None,
        "to_date": to_date,
        "progress_pct": None,
        "target_attainment_pct": None,
    }


def build_body_cards(
    entry: dict | None, config: dict | None = None, history_asc: list[dict] | None = None
) -> list[dict]:
    """Returns cards for body composition readings."""
    entry = entry or {}
    config = config or {}
    cards = []
    for metric in BODY_METRICS:
        key = metric["key"]
        current = _safe(entry.get(key))
        target = _safe(config.get(f"{key}_target"))
        cards.append({
            "id": f"body.{key}",
            "label": metric["label"],
            "unit": metric["unit"],
            "current": current,
            "target": target,
            "remaining": _safe(entry.get(f"{key}_remaining")),
            "to_date": _safe(entry.get(f"{key}_to_date")),
            "progress_pct": _progress_pct(current, target),
            "target_attainment_pct": _pct(current, target),
        })
    cards.append(_lean_mass_card(entry, history_asc))
    return cards


def build_index_cards(entry: dict | None, config: dict | None = None) -> list[dict]:
    """Returns BMI and BMR cards."""
    entry = entry or {}
    config = config or {}
    return [
        {
            "id": "index.bmi",
            "label": "BMI",
            "unit": "kg/m²",
            "current": _safe(entry.get("bmi")),
            "target": _safe(config.get("bmi_target")),
            "to_date": _safe(entry.get("bmi_to_date")),
            "target_attainment_pct": _pct(_safe(entry.get("bmi")), _safe(config.get("bmi_target"))),
        },
        {
            "id": "index.bmr",
            "label": "BMR",
            "unit": "kcal",
            "current": _safe(entry.get("bmr")),
            "target": _safe(config.get("bmr_target")),
            "to_date": _safe(entry.get("bmr_to_date")),
            "target_attainment_pct": _pct(_safe(entry.get("bmr")), _safe(config.get("bmr_target"))),
        },
    ]


# Score widgets (DOTS, Wilks-2, IPF GL Points) all share the same shape -
# a formula fed by the latest total and bodyweight, a one-off target from
# /targets, and a delta against the previous entry.
SCORES = [
    {"key": "dots", "label": "DOTS", "target_column": "dots_score_target", "compute": compute_dots_score},
    {"key": "wilks2", "label": "Wilks-2", "target_column": "wilks2_score_target", "compute": compute_wilks2_score},
    {
        "key": "ipf_gl", "label": "IPF GL Points", "target_column": "ipf_gl_points_target",
        "compute": compute_ipf_gl_score,
    },
]


def _previous_totals(history_asc: list[dict] | None) -> tuple[float | None, float | None]:
    """Total and bodyweight from the entry immediately before the latest
    one, used to show increase/decrease on the score widgets. history_asc
    is oldest-first with the latest entry last, so the previous entry is
    the second-to-last row."""
    if not history_asc or len(history_asc) < 2:
        return None, None
    previous = history_asc[-2]
    return _safe(previous.get("total")), _safe(previous.get("body_weight_mass"))


def _score_card(
    score_id: str, label: str, result: dict, target: float | None, delta: float | None
) -> dict:
    value = result.get("value")
    return {
        "id": score_id,
        "label": label,
        "unit": result.get("unit", ""),
        "value": value,
        "reason": result.get("reason"),
        "target": target,
        "remaining": None if value is None or target is None else round(target - value, 1),
        "target_attainment_pct": _pct(value, target),
        "progress_pct": _progress_pct(value, target),
        "delta_from_last_entry": delta,
    }


def _build_score_cards(
    total_current: float | None, bodyweight: float | None, sex, dashboard_config: dict, history_asc: list[dict]
) -> dict:
    prev_total, prev_bodyweight = _previous_totals(history_asc)
    cards = {}
    for score in SCORES:
        compute = score["compute"]
        result = compute(total_current, bodyweight, sex)
        delta = None
        if result.get("value") is not None and prev_total is not None and prev_bodyweight is not None:
            previous_result = compute(prev_total, prev_bodyweight, sex)
            if previous_result.get("value") is not None:
                delta = round(result["value"] - previous_result["value"], 1)
        cards[f"{score['key']}_score"] = _score_card(
            f"score.{score['key']}", score["label"], result,
            _safe(dashboard_config.get(score["target_column"])), delta,
        )
    return cards


def _history_payload(history: list[dict]) -> list[dict]:
    return [
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
    ]


def build_analytics_payload(
    entry: dict | None,
    dashboard_config: dict | None,
    settings: dict | None,
    history_asc: list[dict],
    full_history_asc: list[dict] | None = None,
    today=None,
) -> dict:
    """Builds analytics data from an entry, configured goals, and one history
    list. `full_history_asc` feeds `pr_intervals`: unlike the rate-of-change
    and chart figures, which intentionally look at the recent
    `history_asc` window, PR pace needs the athlete's entire logged history
    to measure genuine long-horizon breakthroughs. Callers that only have
    the windowed history (e.g. existing tests) may omit it, in which case
    the window is reused and PR pace is simply computed over less data.
    """
    entry = entry or {}
    dashboard_config = dashboard_config or {}
    settings = settings or {}
    today = today or datetime.now(timezone.utc).date()
    full_history_asc = history_asc if full_history_asc is None else full_history_asc
    bodyweight = _safe(entry.get("body_weight_mass"))
    rates = {
        lift["key"]: compute_rate_of_change(
            history_asc,
            lift["key"],
            runtime_config.RATE_OF_CHANGE_WINDOW_DAYS,
            today,
        )
        for lift in LIFTS
    }
    pr_intervals = {
        lift["key"]: compute_pr_intervals(full_history_asc, lift["key"], today)
        for lift in LIFTS
    }
    score_cards = _build_score_cards(
        _safe(entry.get("total_weight_lifted_current")),
        bodyweight,
        settings.get("lifter_sex"),
        dashboard_config,
        history_asc,
    )
    return {
        **score_cards,
        "ratios": {
            lift["key"]: compute_ratio(
                _safe(entry.get(f"{lift['key']}_1rm_current")), bodyweight
            )
            for lift in LIFTS
        },
        "rate_of_change": rates,
        "projected_dates": {
            lift["key"]: compute_projected_date(
                _safe(entry.get(f"{lift['key']}_1rm_current")),
                _safe(dashboard_config.get(f"{lift['key']}_1rm_target")),
                rates[lift["key"]]["kg_per_week"],
                today,
            )
            for lift in LIFTS
        },
        "pr_intervals": pr_intervals,
    }


def build_dashboard_payload(
    latest_entry: dict | None,
    history: list[dict],
    dashboard_config: dict | None = None,
    settings: dict | None = None,
    health_metrics: list[dict] | None = None,
    full_history: list[dict] | None = None,
) -> dict:
    """Returns all dynamic dashboard values without doing database access.

    `full_history` should be every entry ever logged (oldest first), not
    just the `history` window, so PR pace reflects the athlete's whole
    logged career. Routes must pass it explicitly - see routes/pages.py
    and routes/api.py, which both fetch it via db.get_all_entries_asc().
    """
    dashboard_config = dashboard_config or {}
    settings = settings or {}
    history_payload = _history_payload(history)
    full_history_payload = _history_payload(full_history) if full_history is not None else None
    health_metrics = health_metrics or []
    analytics = build_analytics_payload(
        latest_entry, dashboard_config, settings, history_payload, full_history_payload
    )
    return {
        "latest_entry_date": (latest_entry or {}).get("entry_date"),
        "lifter_name": settings.get("display_name"),
        "dashboard_title": dashboard_title(settings.get("display_name")),
        "lift_cards": build_lift_cards(latest_entry, dashboard_config, settings),
        "total_card": build_total_card(latest_entry, settings),
        "weight_change_since_comp": _safe((latest_entry or {}).get("weight_change_since_comp")),
        "body_cards": build_body_cards(latest_entry, dashboard_config, history),
        "index_cards": build_index_cards(latest_entry, dashboard_config),
        "history": history_payload,
        "health_history": [
            {
                "entry_date": row["entry_date"],
                "resting_heart_rate": row.get("resting_heart_rate"),
                "heart_rate_variability_ms": row.get("heart_rate_variability_ms"),
                "sleep_minutes": row.get("sleep_minutes"),
            }
            for row in health_metrics
        ],
        "google_health_configured": bool(settings.get("google_health_client_id"))
        and bool(settings.get("google_health_client_secret")),
        **analytics,
    }
