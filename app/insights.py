"""Pure calculations behind the Meet Prep and Performance dashboard screens.

Nothing here touches the database: routes pass in entries (via the
`_history_payload` shape from metrics.py, oldest first), competitions,
countdowns and settings, and get plain dictionaries back. Every function
degrades to an explicit empty state rather than raising, so a fresh install
with no data still renders every widget.
"""
import re
from datetime import date

from .analytics import compute_rate_of_change, dots_denominator

LIFT_KEYS = ("squat", "bench", "deadlift")

# Bodyweight trend used to project weigh-in bodyweight. Shorter than the
# lift window because bodyweight responds to a cut within weeks, not months.
BODYWEIGHT_TREND_WINDOW_DAYS = 28

# A gym total logged more than this long before a meet is too stale to
# compare against the platform result.
GYM_TOTAL_MAX_AGE_DAYS = 120

# Monthly charts (lift balance, recomposition) show at most this many points.
MONTHLY_POINTS = 12


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _iso(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_weight_class(raw) -> dict | None:
    """Parses a free-text weight class such as "93", "-93 kg", "93kg" or
    "120+". Returns {"label", "limit_kg"} where limit_kg is None for an
    open (plus) class, or None when nothing numeric can be read.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    value = float(match.group(1))
    if value <= 0:
        return None
    number = match.group(1).rstrip("0").rstrip(".") if "." in match.group(1) else match.group(1)
    if "+" in text:
        return {"label": f"{number}+ kg", "limit_kg": None}
    return {"label": f"{number} kg", "limit_kg": value}


def _latest_value(history_asc: list[dict], key: str):
    for row in reversed(history_asc):
        value = _num(row.get(key))
        if value is not None:
            return value, row["entry_date"]
    return None, None


def _earliest_value(history_asc: list[dict], key: str):
    for row in history_asc:
        value = _num(row.get(key))
        if value is not None:
            return value
    return None


# ---------------------------------------------------------------------------
# Meet Prep
# ---------------------------------------------------------------------------

def find_next_meet(countdowns: list[dict], competitions_desc: list[dict], today: date) -> dict | None:
    """The soonest countdown on or after today. Its weight class comes from
    the countdown itself, falling back to the most recent logged meet's
    class so the bodyweight chart still works before a class is entered.
    """
    upcoming = []
    for countdown in countdowns or []:
        event_date = _iso(countdown.get("event_date"))
        if event_date is None or event_date < today:
            continue
        upcoming.append((event_date, countdown))
    if not upcoming:
        return None
    upcoming.sort(key=lambda item: item[0])
    event_date, countdown = upcoming[0]

    weight_class = parse_weight_class(countdown.get("weight_class"))
    source = "countdown" if weight_class else None
    if weight_class is None:
        for meet in competitions_desc or []:
            weight_class = parse_weight_class(meet.get("weight_class"))
            if weight_class:
                source = "last_meet"
                break

    location = ", ".join(
        part for part in (countdown.get("city"), countdown.get("region"), countdown.get("country")) if part
    ) or None
    return {
        "event_name": countdown.get("event_name"),
        "event_date": event_date.isoformat(),
        "days_until": (event_date - today).days,
        "location": location,
        "weight_class": weight_class,
        "weight_class_source": source,
    }


def build_meet_projection(
    history_asc: list[dict],
    dashboard_config: dict,
    rates: dict,
    next_meet: dict | None,
) -> dict:
    """Projects each lift from its latest logged value to meet day using the
    existing rate-of-change trend, and sums them into a projected total.
    A lift with no usable trend is held flat rather than guessed.
    """
    meet_date = _iso((next_meet or {}).get("event_date"))
    lifts = {}
    projected_total = 0.0
    current_total = 0.0
    target_total = 0.0
    complete = True
    targets_complete = True
    latest_dates = []
    for key in LIFT_KEYS:
        current, current_date = _latest_value(history_asc, key)
        rate = _num((rates.get(key) or {}).get("kg_per_week"))
        target = _num(dashboard_config.get(f"{key}_1rm_target"))
        projected = None
        if current is not None and meet_date is not None:
            days_ahead = max(0, (meet_date - _iso(current_date)).days)
            projected = round(current + (rate or 0) * days_ahead / 7, 1)
        lifts[key] = {
            "current": current,
            "kg_per_week": rate,
            "trend_available": rate is not None,
            "projected": projected,
            "target": target,
            "projected_vs_target": None if projected is None or target is None else round(projected - target, 1),
        }
        if current is None:
            complete = False
        else:
            current_total += current
            latest_dates.append(_iso(current_date))
        if projected is not None:
            projected_total += projected
        if target is None:
            targets_complete = False
        else:
            target_total += target

    series = [
        {"date": row["entry_date"], "total": _num(row.get("total"))}
        for row in history_asc
        if _num(row.get("total")) is not None
    ]
    projected_total_value = round(projected_total, 1) if complete and meet_date else None
    target_total_value = round(target_total, 1) if targets_complete else None
    start_date = max(latest_dates).isoformat() if latest_dates else None
    return {
        "lifts": lifts,
        "current_total": round(current_total, 1) if complete else None,
        "projected_total": projected_total_value,
        "target_total": target_total_value,
        "projected_vs_target": (
            None if projected_total_value is None or target_total_value is None
            else round(projected_total_value - target_total_value, 1)
        ),
        "projection_start_date": start_date,
        "meet_date": meet_date.isoformat() if meet_date else None,
        "series": series,
    }


def build_weight_class_status(history_asc: list[dict], next_meet: dict | None, today: date) -> dict:
    """Compares the current and projected weigh-in bodyweight with the next
    meet's class limit, including the weekly rate needed to make weight.
    """
    series = [
        {"date": row["entry_date"], "body_weight": _num(row.get("body_weight_mass"))}
        for row in history_asc
        if _num(row.get("body_weight_mass")) is not None
    ]
    current, current_date = _latest_value(history_asc, "body_weight_mass")
    trend = compute_rate_of_change(
        history_asc, "body_weight_mass", BODYWEIGHT_TREND_WINDOW_DAYS, today
    )["kg_per_week"]
    weight_class = (next_meet or {}).get("weight_class")
    limit = (weight_class or {}).get("limit_kg")
    meet_date = _iso((next_meet or {}).get("event_date"))

    projected = None
    if current is not None and meet_date is not None:
        days_ahead = max(0, (meet_date - _iso(current_date)).days)
        projected = round(current + (trend or 0) * days_ahead / 7, 1)

    margin = None if current is None or limit is None else round(limit - current, 1)
    required_per_week = None
    if margin is not None and margin < 0 and next_meet and next_meet["days_until"] > 0:
        required_per_week = round(margin / (next_meet["days_until"] / 7), 2)

    if current is None:
        state = "no_data"
    elif weight_class is None:
        state = "no_class"
    elif limit is None:
        state = "open_class"
    elif current <= limit and (projected is None or projected <= limit):
        state = "on_track"
    elif current <= limit:
        state = "drifting_over"
    elif projected is not None and projected <= limit:
        state = "cutting_on_track"
    else:
        state = "over"

    return {
        "state": state,
        "current": current,
        "limit_kg": limit,
        "class_label": (weight_class or {}).get("label"),
        "class_source": (next_meet or {}).get("weight_class_source"),
        "margin_kg": margin,
        "trend_kg_per_week": trend,
        "projected_weigh_in": projected,
        "required_kg_per_week": required_per_week,
        "meet_date": meet_date.isoformat() if meet_date else None,
        "series": series,
    }


def _score_value(compute, total, bodyweight, sex):
    if total is None or bodyweight is None:
        return None
    return compute(total, bodyweight, sex).get("value")


def build_target_progress(
    history_asc: list[dict],
    dashboard_config: dict,
    settings: dict,
    score_cards: dict,
    score_definitions: list[dict],
) -> list[dict]:
    """One row per target that has been set. Progress is measured from the
    first logged value towards the target, so it works for targets that
    should go up (lifts, scores) and down (fat mass) alike.
    """
    rows = []

    def add(label, unit, baseline, current, target):
        if target is None:
            return
        progress = None
        if current is not None and baseline is not None:
            if baseline == target:
                progress = 100.0 if current == target else None
            else:
                progress = round((current - baseline) / (target - baseline) * 100, 1)
        direction = "up" if baseline is None or target >= baseline else "down"
        met = current is not None and ((current >= target) if direction == "up" else (current <= target))
        rows.append({
            "label": label,
            "unit": unit,
            "baseline": baseline,
            "current": current,
            "target": target,
            "progress_pct": 100.0 if met and (progress is None or progress > 100) else progress,
            "remaining": None if current is None else round(target - current, 1),
            "met": met,
            "direction": direction,
        })

    for key, label in (("squat", "Squat"), ("bench", "Bench"), ("deadlift", "Deadlift")):
        add(label, "kg", _earliest_value(history_asc, key), _latest_value(history_asc, key)[0],
            _num(dashboard_config.get(f"{key}_1rm_target")))

    lift_targets = [_num(dashboard_config.get(f"{key}_1rm_target")) for key in LIFT_KEYS]
    total_target = sum(lift_targets) if all(value is not None for value in lift_targets) else None
    add("Total", "kg", _earliest_value(history_asc, "total"), _latest_value(history_asc, "total")[0], total_target)

    sex = settings.get("lifter_sex")
    first_scored = next(
        (row for row in history_asc
         if _num(row.get("total")) is not None and _num(row.get("body_weight_mass")) is not None),
        None,
    )
    for definition in score_definitions:
        card = score_cards.get(f"{definition['key']}_score") or {}
        baseline = None
        if first_scored is not None:
            baseline = _score_value(
                definition["compute"], first_scored["total"], first_scored["body_weight_mass"], sex
            )
        add(definition["label"], "", baseline, _num(card.get("value")),
            _num(dashboard_config.get(definition["target_column"])))

    for key, label, unit in (
        ("body_weight_mass", "Body weight", "kg"),
        ("skeletal_muscle_mass", "Muscle mass", "kg"),
        ("body_fat_mass", "Fat mass", "kg"),
        ("percent_body_fat", "Body fat", "%"),
    ):
        add(label, unit, _earliest_value(history_asc, key), _latest_value(history_asc, key)[0],
            _num(dashboard_config.get(f"{key}_target")))
    return rows


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

def build_strength_scatter(history_asc: list[dict], competitions_desc: list[dict], sex) -> dict:
    """Total against bodyweight for every entry and logged meet, with DOTS
    curves drawn at round levels around the lifter's current score.
    """
    entries = [
        {"date": row["entry_date"], "body_weight": row["body_weight_mass"], "total": row["total"]}
        for row in history_asc
        if _num(row.get("total")) is not None and _num(row.get("body_weight_mass")) is not None
    ]
    meets = [
        {
            "date": meet["competition_date"],
            "name": meet.get("meet_name"),
            "body_weight": meet["bodyweight_kg"],
            "total": meet["total_kg"],
        }
        for meet in reversed(competitions_desc or [])
        if _num(meet.get("total_kg")) is not None and _num(meet.get("bodyweight_kg")) is not None
    ]
    curves = []
    if sex in ("male", "female") and (entries or meets):
        bodyweights = [point["body_weight"] for point in entries + meets]
        low = max(40.0, min(bodyweights) - 4)
        high = max(bodyweights) + 4
        reference = entries[-1] if entries else meets[-1]
        denominator = dots_denominator(reference["body_weight"], sex)
        if denominator:
            current_dots = reference["total"] * 500 / denominator
            centre = round(current_dots / 25) * 25
            steps = 24
            for level in (centre - 50, centre - 25, centre, centre + 25, centre + 50):
                if level <= 0:
                    continue
                points = []
                for index in range(steps + 1):
                    bodyweight = low + (high - low) * index / steps
                    curve_denominator = dots_denominator(bodyweight, sex)
                    if curve_denominator:
                        points.append({
                            "body_weight": round(bodyweight, 2),
                            "total": round(level * curve_denominator / 500, 1),
                        })
                curves.append({"dots": level, "points": points})
    return {
        "entries": entries,
        "meets": meets,
        "dots_curves": curves,
        "sex_configured": sex in ("male", "female"),
    }


def build_gym_vs_platform(history_asc: list[dict], competitions_desc: list[dict]) -> dict:
    """Pairs each logged meet total with the most recent gym total logged on
    or before meet day (within GYM_TOTAL_MAX_AGE_DAYS).
    """
    gym_points = [
        (_iso(row["entry_date"]), row["total"])
        for row in history_asc
        if _num(row.get("total")) is not None and _iso(row.get("entry_date"))
    ]
    rows = []
    for meet in reversed(competitions_desc or []):
        meet_total = _num(meet.get("total_kg"))
        meet_date = _iso(meet.get("competition_date"))
        if meet_total is None or meet_date is None:
            continue
        gym_total = gym_date = None
        for point_date, total in gym_points:
            if point_date > meet_date:
                break
            if (meet_date - point_date).days <= GYM_TOTAL_MAX_AGE_DAYS:
                gym_total, gym_date = total, point_date
        rows.append({
            "date": meet_date.isoformat(),
            "meet_name": meet.get("meet_name"),
            "meet_total": meet_total,
            "gym_total": gym_total,
            "gym_date": gym_date.isoformat() if gym_date else None,
            "carryover_pct": None if not gym_total else round(meet_total / gym_total * 100, 1),
        })
    paired = [row["carryover_pct"] for row in rows if row["carryover_pct"] is not None]
    return {
        "meets": rows,
        "average_carryover_pct": round(sum(paired) / len(paired), 1) if paired else None,
        "paired_count": len(paired),
        "max_gym_age_days": GYM_TOTAL_MAX_AGE_DAYS,
    }


def _monthly_last(history_asc: list[dict], predicate) -> list[dict]:
    """The last qualifying entry in each calendar month, oldest first."""
    by_month = {}
    for row in history_asc:
        if predicate(row):
            by_month[row["entry_date"][:7]] = row
    return [by_month[month] for month in sorted(by_month)]


def build_lift_balance(history_asc: list[dict]) -> dict:
    """Each lift's share of the total, using the last complete entry of each
    month so day-to-day noise does not dominate.
    """
    rows = _monthly_last(
        history_asc, lambda row: all(_num(row.get(key)) is not None for key in LIFT_KEYS)
    )[-MONTHLY_POINTS:]
    months = []
    for row in rows:
        total = sum(row[key] for key in LIFT_KEYS)
        if total <= 0:
            continue
        months.append({
            "month": row["entry_date"][:7],
            "date": row["entry_date"],
            "total": round(total, 1),
            **{f"{key}_pct": round(row[key] / total * 100, 1) for key in LIFT_KEYS},
        })
    return {"months": months}


def build_recomposition(history_asc: list[dict]) -> dict:
    """Month-on-month change in lean mass against change in fat mass. Lean
    mass is bodyweight minus fat mass, matching the Lean Mass widget.
    """
    rows = _monthly_last(
        history_asc,
        lambda row: _num(row.get("body_weight_mass")) is not None and _num(row.get("body_fat_mass")) is not None,
    )
    periods = []
    for previous, current in zip(rows, rows[1:]):
        lean_change = (current["body_weight_mass"] - current["body_fat_mass"]) - (
            previous["body_weight_mass"] - previous["body_fat_mass"]
        )
        fat_change = current["body_fat_mass"] - previous["body_fat_mass"]
        if lean_change >= 0 and fat_change <= 0:
            quadrant = "recomposition"
        elif lean_change >= 0:
            quadrant = "lean_gain"
        elif fat_change <= 0:
            quadrant = "cut"
        else:
            quadrant = "regression"
        periods.append({
            "month": current["entry_date"][:7],
            "from_date": previous["entry_date"],
            "to_date": current["entry_date"],
            "lean_change": round(lean_change, 2),
            "fat_change": round(fat_change, 2),
            "quadrant": quadrant,
        })
    return {"periods": periods[-MONTHLY_POINTS:]}
