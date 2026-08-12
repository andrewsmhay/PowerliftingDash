"""Computes every `read_from_new_date_entry=True` column in schema_manifest.json
from the manually entered columns on the same row, plus (for the "to date"
family) the earliest historical value recorded for that column.

Formula conventions
--------------------
- "remaining"          = target - current                       (signed)
- "competition delta"  = current - competition                  (signed)
- "total" (Goals)      = squat + bench + deadlift, per variant   (current/target/competition)
- "to date"            = current - baseline, where baseline is the value of
                          the same column on the earliest entry_date that has
                          a non-null value for it (i.e. "since I started
                          tracking this")

Documented assumptions (see README for the full explanation)
--------------------------------------------------------------
- BMI and BMR (including their targets) are manual smart-scale readings, not
  formula outputs - there is no height/age/sex anywhere in the 44-item
  schema to derive them from, and the source spreadsheet's own "current" /
  "target" split for every other metric is manual, so the same pattern is
  applied here.
- "Weight Change Since Comp" has no dedicated "competition weigh-in" field in
  the 44-item schema, so it is computed with the same "to date" convention:
  current body weight minus the earliest recorded body weight. If Andrew
  wants it anchored to a specific competition date instead, that needs a new
  manual field.

Recomputation strategy: rather than track baselines incrementally (which
would go stale the moment an earlier date is backfilled), `recompute_all()`
reloads every entry, recomputes every derived column for every row, and
writes them all back. The dataset is a personal daily log, so this is cheap
and removes an entire class of staleness bugs.
"""
from . import db

# Manual columns that participate in a "to date" (baseline-relative) derived
# column, mapped to the derived column name.
_TO_DATE_COLUMNS = {
    "body_weight_mass": "body_weight_mass_to_date",
    "skeletal_muscle_mass": "skeletal_muscle_mass_to_date",
    "body_fat_mass": "body_fat_mass_to_date",
    "percent_body_fat": "percent_body_fat_to_date",
    "bmi": "bmi_to_date",
    "bmr": "bmr_to_date",
}

# Manual current/target pairs that participate in a plain "remaining" derived
# column (remaining = target - current).
_REMAINING_PAIRS = {
    "squat_1rm_remaining": ("squat_1rm_target", "squat_1rm_current"),
    "bench_1rm_remaining": ("bench_1rm_target", "bench_1rm_current"),
    "deadlift_1rm_remaining": ("deadlift_1rm_target", "deadlift_1rm_current"),
    "body_weight_mass_remaining": ("body_weight_mass_target", "body_weight_mass"),
    "skeletal_muscle_mass_remaining": ("skeletal_muscle_mass_target", "skeletal_muscle_mass"),
    "body_fat_mass_remaining": ("body_fat_mass_target", "body_fat_mass"),
    "percent_body_fat_remaining": ("percent_body_fat_target", "percent_body_fat"),
    "bmi_remaining": ("bmi_target", "bmi"),
    "bmr_remaining": ("bmr_target", "bmr"),
}

# Competition deltas (delta = current - competition).
_COMPETITION_DELTA_PAIRS = {
    "squat_1rm_competition_delta": ("squat_1rm_current", "squat_1rm_competition"),
    "bench_1rm_competition_delta": ("bench_1rm_current", "bench_1rm_competition"),
    "deadlift_1rm_competition_delta": ("deadlift_1rm_current", "deadlift_1rm_competition"),
}

ALL_DERIVED_COLUMNS = (
    set(_REMAINING_PAIRS)
    | set(_COMPETITION_DELTA_PAIRS)
    | set(_TO_DATE_COLUMNS.values())
    | {
        "total_weight_lifted_target",
        "total_weight_lifted_in_competition",
        "total_weight_lifted_current",
        "total_weight_lifted_remaining",
        "weight_change_since_comp",
    }
)


def _sub(a, b):
    if a is None or b is None:
        return None
    return a - b


def _sum(*values):
    if any(v is None for v in values):
        return None
    return sum(values)


def compute_row_derived(row: dict, baselines: dict) -> dict:
    """Computes every derived column for a single row.

    `row` is the full entry dict (manual columns already populated).
    `baselines` maps manual column name -> its earliest recorded value
    across the whole history (see `_compute_baselines`).
    """
    out: dict = {}

    for derived_col, (target_col, current_col) in _REMAINING_PAIRS.items():
        out[derived_col] = _sub(row.get(target_col), row.get(current_col))

    for derived_col, (current_col, competition_col) in _COMPETITION_DELTA_PAIRS.items():
        out[derived_col] = _sub(row.get(current_col), row.get(competition_col))

    out["total_weight_lifted_target"] = _sum(
        row.get("squat_1rm_target"), row.get("bench_1rm_target"), row.get("deadlift_1rm_target")
    ) if all(
        row.get(c) is not None
        for c in ("squat_1rm_target", "bench_1rm_target", "deadlift_1rm_target")
    ) else None
    out["total_weight_lifted_in_competition"] = _sum(
        row.get("squat_1rm_competition"),
        row.get("bench_1rm_competition"),
        row.get("deadlift_1rm_competition"),
    ) if all(
        row.get(c) is not None
        for c in ("squat_1rm_competition", "bench_1rm_competition", "deadlift_1rm_competition")
    ) else None
    out["total_weight_lifted_current"] = _sum(
        row.get("squat_1rm_current"), row.get("bench_1rm_current"), row.get("deadlift_1rm_current")
    ) if all(
        row.get(c) is not None
        for c in ("squat_1rm_current", "bench_1rm_current", "deadlift_1rm_current")
    ) else None
    out["total_weight_lifted_remaining"] = _sub(
        out["total_weight_lifted_target"], out["total_weight_lifted_current"]
    )

    # Weight Change Since Comp: see module docstring for the baseline assumption.
    out["weight_change_since_comp"] = _sub(
        row.get("body_weight_mass"), baselines.get("body_weight_mass")
    )

    for manual_col, derived_col in _TO_DATE_COLUMNS.items():
        out[derived_col] = _sub(row.get(manual_col), baselines.get(manual_col))

    return out


def _compute_baselines(entries_asc: list[dict]) -> dict:
    """Earliest non-null value per manual column that feeds a 'to date'
    derived column, scanning entries oldest-first.
    """
    baselines: dict = {}
    for column in _TO_DATE_COLUMNS:
        for row in entries_asc:
            value = row.get(column)
            if value is not None:
                baselines[column] = value
                break
    return baselines


def recompute_all() -> int:
    """Recomputes and persists derived columns for every entry. Returns the
    number of rows updated.
    """
    entries_asc = db.get_all_entries_asc()
    if not entries_asc:
        return 0

    baselines = _compute_baselines(entries_asc)

    updated = 0
    for row in entries_asc:
        derived = compute_row_derived(row, baselines)
        db.update_computed_columns(row["id"], derived)
        updated += 1
    return updated
