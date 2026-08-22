# Customisable widget dashboard + advanced analytics widgets

Implementation spec for the coding subagent. Read this file fully before writing
any code. UK English throughout, in code comments, UI copy and docs. Do not use
em-dashes (neither `--` nor `—`) anywhere in new or edited files - use commas,
full stops or parentheses instead.

## 1. Goal

Replace the fixed-section dashboard with a widget-based grid the user can edit:

- An **Edit** button toggles edit mode. In edit mode, widgets can be dragged and
  resized, snapping to a grid. An **Add widget** tray lists every widget not
  currently on the board, grouped by category. Each widget on the board gets a
  small remove ("x") control while editing.
- **Save** persists the layout (widget ids + grid positions only, never
  rendered content) to the database so it survives reboots. **Cancel** discards
  in-progress edits and reloads the last saved layout. **Reset to default**
  clears the saved layout back to the built-in default arrangement.
- Google Health widgets (12 fields sourced from `health_metrics`, plus the new
  Activity & Recovery trend chart) only appear in the Add-widget tray, and only
  render on the board, when Google Health `client_id` **and** `client_secret`
  are both configured in Settings. If credentials are later removed, any such
  widgets already saved in a layout are skipped when rendering (not deleted
  from the saved JSON) so the user's layout isn't silently destroyed by a
  Settings change; they reappear automatically if credentials are restored.
- Add a full new tier of computed analytics widgets (always available, not
  gated on Google Health): DOTS score, strength-to-bodyweight ratio per lift,
  rate of change per lift, projected date to hit target per lift, and a PR
  timeline chart per lift. Also add the previously-recommended Activity &
  Recovery trend chart (this one *is* Google Health gated, since it needs
  resting heart rate / HRV / sleep history).

## 2. Library: GridStack.js

Vendor GridStack **v12.3.3** locally (same pattern as `chart.umd.min.js`, no
CDN dependency at runtime, pin the version, no jQuery required):

- `https://cdn.jsdelivr.net/npm/gridstack@12.3.3/dist/gridstack-all.js` -> save
  as `app/static/js/gridstack-all.js`
- `https://cdn.jsdelivr.net/npm/gridstack@12.3.3/dist/gridstack.min.css` -> save
  as `app/static/css/gridstack.min.css`

Key API used: `GridStack.init(opts, el)`, `grid.save(false, false)` (positions
only, no content), `grid.load(items)`, `grid.addWidget(...)`,
`grid.removeWidget(el)`, `grid.setStatic(true|false)` (lock dragging outside
edit mode), `grid.on('resizestop', ...)` (to call `chart.resize()` on any
Chart.js canvas inside the resized item - Chart.js with
`maintainAspectRatio: false` does not reflow on its own when a GridStack item
changes height).

## 3. Data model changes

### `app/db.py` - `_ensure_settings_columns()`

Add two columns (follow the existing pattern used for prior migrations):

- `dashboard_layout TEXT` - JSON array of `{id, x, y, w, h}`. `NULL` means "use
  the computed default layout".
- `lifter_sex TEXT` - `"male"` or `"female"`. Used only for the DOTS score.
  `NULL` means "not configured".

Add a new read helper:

```python
def get_health_metrics(limit: int = 180) -> list[dict]:
    """Most recent `limit` health_metrics rows, oldest first (chart x-axis
    order) - mirrors get_entries()."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM health_metrics ORDER BY entry_date DESC LIMIT ?", (limit,)
        ).fetchall()
    return list(reversed(rows))
```

No new write helpers are needed for the layout: reuse the existing
`update_settings(dashboard_layout=json_string)` / `get_settings()`.

### `app/config.py`

Add:

```python
# Trailing window used for the "rate of change per lift" and "projected date
# to hit target" analytics - reflects current trend, not lifetime average.
RATE_OF_CHANGE_WINDOW_DAYS = int(os.environ.get("PLD_RATE_OF_CHANGE_WINDOW_DAYS", "90"))
```

## 4. New module: `app/widgets.py`

Defines the full widget catalogue and default layout. Pure functions, no DB
access except being passed already-fetched settings.

```python
WIDGET_CATALOG = [
    # id, label, category, kind, unit, requires_google_health
    {"id": "lift.squat", "label": "Squat", "category": "Lifts", "kind": "lift_card"},
    {"id": "lift.bench", "label": "Bench", "category": "Lifts", "kind": "lift_card"},
    {"id": "lift.deadlift", "label": "Deadlift", "category": "Lifts", "kind": "lift_card"},
    {"id": "lift.total", "label": "Total", "category": "Lifts", "kind": "lift_card"},

    {"id": "body.body_weight_mass", "label": "Body Weight", "category": "Body Composition", "kind": "body_card"},
    {"id": "body.skeletal_muscle_mass", "label": "Skeletal Muscle Mass", "category": "Body Composition", "kind": "body_card"},
    {"id": "body.body_fat_mass", "label": "Body Fat Mass", "category": "Body Composition", "kind": "body_card"},
    {"id": "body.percent_body_fat", "label": "Body Fat", "category": "Body Composition", "kind": "body_card"},
    {"id": "index.bmi", "label": "BMI", "category": "Body Composition", "kind": "index_card"},
    {"id": "index.bmr", "label": "BMR", "category": "Body Composition", "kind": "index_card"},

    {"id": "score.dots", "label": "DOTS Score", "category": "Analytics", "kind": "dots_card"},
    {"id": "ratio.squat_bw", "label": "Squat : Bodyweight", "category": "Analytics", "kind": "ratio_card"},
    {"id": "ratio.bench_bw", "label": "Bench : Bodyweight", "category": "Analytics", "kind": "ratio_card"},
    {"id": "ratio.deadlift_bw", "label": "Deadlift : Bodyweight", "category": "Analytics", "kind": "ratio_card"},
    {"id": "rate.squat", "label": "Squat Rate of Change", "category": "Analytics", "kind": "rate_card"},
    {"id": "rate.bench", "label": "Bench Rate of Change", "category": "Analytics", "kind": "rate_card"},
    {"id": "rate.deadlift", "label": "Deadlift Rate of Change", "category": "Analytics", "kind": "rate_card"},
    {"id": "projection.squat", "label": "Squat Target Projection", "category": "Analytics", "kind": "projection_card"},
    {"id": "projection.bench", "label": "Bench Target Projection", "category": "Analytics", "kind": "projection_card"},
    {"id": "projection.deadlift", "label": "Deadlift Target Projection", "category": "Analytics", "kind": "projection_card"},

    {"id": "chart.lifts", "label": "1RM Over Time", "category": "Trends", "kind": "chart"},
    {"id": "chart.body_composition", "label": "Body Composition Over Time", "category": "Trends", "kind": "chart"},
    {"id": "pr_timeline.squat", "label": "Squat PR Timeline", "category": "Trends", "kind": "pr_timeline_chart"},
    {"id": "pr_timeline.bench", "label": "Bench PR Timeline", "category": "Trends", "kind": "pr_timeline_chart"},
    {"id": "pr_timeline.deadlift", "label": "Deadlift PR Timeline", "category": "Trends", "kind": "pr_timeline_chart"},

    # Google Health gated (12 fields + 1 chart) - hidden unless client_id and
    # client_secret are both configured.
    {"id": "health.steps", "label": "Steps", "category": "Activity & Recovery", "kind": "health_card", "requires_google_health": True},
    {"id": "health.resting_heart_rate", "label": "Resting Heart Rate", "category": "Activity & Recovery", "kind": "health_card", "requires_google_health": True},
    {"id": "health.sleep_minutes", "label": "Sleep", "category": "Activity & Recovery", "kind": "health_card", "requires_google_health": True},
    {"id": "health.distance_km", "label": "Distance", "category": "Activity & Recovery", "kind": "health_card", "requires_google_health": True},
    {"id": "health.floors_climbed", "label": "Floors Climbed", "category": "Activity & Recovery", "kind": "health_card", "requires_google_health": True},
    {"id": "health.active_minutes", "label": "Active Minutes", "category": "Activity & Recovery", "kind": "health_card", "requires_google_health": True},
    {"id": "health.active_zone_minutes", "label": "Active Zone Minutes", "category": "Activity & Recovery", "kind": "health_card", "requires_google_health": True},
    {"id": "health.calories_burned", "label": "Calories Burned", "category": "Activity & Recovery", "kind": "health_card", "requires_google_health": True},
    {"id": "health.heart_rate_variability_ms", "label": "Heart Rate Variability", "category": "Activity & Recovery", "kind": "health_card", "requires_google_health": True},
    {"id": "health.vo2_max", "label": "VO2 Max", "category": "Activity & Recovery", "kind": "health_card", "requires_google_health": True},
    {"id": "health.respiratory_rate", "label": "Respiratory Rate", "category": "Activity & Recovery", "kind": "health_card", "requires_google_health": True},
    {"id": "health.oxygen_saturation_pct", "label": "Oxygen Saturation", "category": "Activity & Recovery", "kind": "health_card", "requires_google_health": True},
    {"id": "chart.activity_recovery_trend", "label": "Activity & Recovery Trends", "category": "Trends", "kind": "activity_trend_chart", "requires_google_health": True},
]
```

38 widgets total (12 Google-Health-gated, 26 always available).

```python
def build_catalog(google_health_configured: bool) -> list[dict]:
    """Returns the catalogue filtered to widgets the user is currently
    allowed to add. Google Health widgets are omitted entirely (not just
    disabled) when credentials are not configured - this is the
    server-side gate; the frontend must not be trusted to hide them.
    """
    return [
        w for w in WIDGET_CATALOG
        if google_health_configured or not w.get("requires_google_health")
    ]


def default_layout(google_health_configured: bool) -> list[dict]:
    """The layout rendered when app_settings.dashboard_layout is NULL - i.e.
    a brand-new install, or after a reset. Must reproduce what today's fixed
    dashboard shows: all lift/body/index/analytics/chart widgets, plus (only
    if Google Health is already configured) the three health cards that the
    previous fixed dashboard showed unconditionally (steps, resting heart
    rate, sleep) - the other 9 Google Health fields and the new trend chart
    stay opt-in even when configured, since they were never shown before.
    """
    layout = [
        {"id": "lift.squat", "x": 0, "y": 0, "w": 3, "h": 4},
        {"id": "lift.bench", "x": 3, "y": 0, "w": 3, "h": 4},
        {"id": "lift.deadlift", "x": 6, "y": 0, "w": 3, "h": 4},
        {"id": "lift.total", "x": 9, "y": 0, "w": 3, "h": 4},

        {"id": "body.body_weight_mass", "x": 0, "y": 4, "w": 3, "h": 4},
        {"id": "body.skeletal_muscle_mass", "x": 3, "y": 4, "w": 3, "h": 4},
        {"id": "body.body_fat_mass", "x": 6, "y": 4, "w": 3, "h": 4},
        {"id": "body.percent_body_fat", "x": 9, "y": 4, "w": 3, "h": 4},

        {"id": "index.bmi", "x": 0, "y": 8, "w": 3, "h": 4},
        {"id": "index.bmr", "x": 3, "y": 8, "w": 3, "h": 4},
        {"id": "score.dots", "x": 6, "y": 8, "w": 3, "h": 4},
        {"id": "ratio.squat_bw", "x": 9, "y": 8, "w": 3, "h": 4},

        {"id": "ratio.bench_bw", "x": 0, "y": 12, "w": 3, "h": 4},
        {"id": "ratio.deadlift_bw", "x": 3, "y": 12, "w": 3, "h": 4},
        {"id": "rate.squat", "x": 6, "y": 12, "w": 3, "h": 4},
        {"id": "rate.bench", "x": 9, "y": 12, "w": 3, "h": 4},

        {"id": "rate.deadlift", "x": 0, "y": 16, "w": 3, "h": 4},
        {"id": "projection.squat", "x": 3, "y": 16, "w": 3, "h": 4},
        {"id": "projection.bench", "x": 6, "y": 16, "w": 3, "h": 4},
        {"id": "projection.deadlift", "x": 9, "y": 16, "w": 3, "h": 4},

        {"id": "chart.lifts", "x": 0, "y": 20, "w": 6, "h": 8},
        {"id": "chart.body_composition", "x": 6, "y": 20, "w": 6, "h": 8},

        {"id": "pr_timeline.squat", "x": 0, "y": 28, "w": 4, "h": 8},
        {"id": "pr_timeline.bench", "x": 4, "y": 28, "w": 4, "h": 8},
        {"id": "pr_timeline.deadlift", "x": 8, "y": 28, "w": 4, "h": 8},
    ]
    if google_health_configured:
        layout += [
            {"id": "health.steps", "x": 0, "y": 36, "w": 4, "h": 4},
            {"id": "health.resting_heart_rate", "x": 4, "y": 36, "w": 4, "h": 4},
            {"id": "health.sleep_minutes", "x": 8, "y": 36, "w": 4, "h": 4},
        ]
    return layout
```

Note that `default_layout()`'s output depends on `google_health_configured`
at the moment it is called, not at install time. If the saved column is
still `NULL` and the user configures Google Health credentials later, the
next page load will include the three health cards that were not there
before. This is intended (it mirrors what the old fixed dashboard did), but
is a one-off jump at the moment credentials are first configured, not a
permanent guarantee about what `NULL` renders - do not "fix" this by
freezing the layout on first render.

The 12-column grid and the `h=4` (small card) / `h=8` (chart) convention must
match whatever `cellHeight` you choose in GridStack config - check
`dashboard.css` for today's rendered `.card` height and `.chart-canvas-wrap`
height and pick a `cellHeight` so `h=4` and `h=8` come out close to those
values. Verify visually with a screenshot at the end, not just by reading
the CSS.

## 5. New module: `app/analytics.py`

Pure functions, no DB access - callers pass in already-fetched entries/config/
settings. Add unit tests for every function (see section 10).

### 5.1 DOTS score

Verified formula and coefficients (consistent across OpenPowerlifting's
reference implementation and multiple calculator sites, Tim Konertz 2019):

```
DOTS = Total(kg) * 500 / (a + b*BW + c*BW^2 + d*BW^3 + e*BW^4)
```

| Coefficient | Men            | Women           |
|---|---|---|
| a | -307.75076      | -57.96288       |
| b | 24.0900756      | 13.6175032      |
| c | -0.1918759221   | -0.1126655495   |
| d | 0.0007391293    | 0.0005158568    |
| e | -0.000001093    | -0.0000010706   |

Valid bodyweight range: 40-210 kg (men), 40-150 kg (women). Clamp bodyweight
to the nearest edge of the range before evaluating the polynomial if it falls
outside (matches reference implementations - do not extrapolate).

```python
DOTS_COEFFICIENTS = {
    "male": {"a": -307.75076, "b": 24.0900756, "c": -0.1918759221, "d": 0.0007391293, "e": -0.000001093, "bw_min": 40.0, "bw_max": 210.0},
    "female": {"a": -57.96288, "b": 13.6175032, "c": -0.1126655495, "d": 0.0005158568, "e": -0.0000010706, "bw_min": 40.0, "bw_max": 150.0},
}


def compute_dots_score(total_kg, bodyweight_kg, sex):
    """Returns {"value": float, "unit": "DOTS"} or {"value": None, "reason": "..."}."""
    if sex not in DOTS_COEFFICIENTS:
        return {"value": None, "reason": "sex_not_configured"}
    if total_kg is None or bodyweight_kg is None:
        return {"value": None, "reason": "no_data"}
    c = DOTS_COEFFICIENTS[sex]
    bw = max(c["bw_min"], min(c["bw_max"], bodyweight_kg))
    denominator = c["a"] + c["b"] * bw + c["c"] * bw**2 + c["d"] * bw**3 + c["e"] * bw**4
    if denominator <= 0:
        return {"value": None, "reason": "no_data"}
    return {"value": round(total_kg * 500 / denominator, 1), "unit": "DOTS"}
```

### 5.2 Strength-to-bodyweight ratio

```python
def compute_ratio(lift_1rm_kg, bodyweight_kg):
    """Returns {"value": float} (e.g. 1.85 meaning 1.85x bodyweight) or
    {"value": None} if either input is missing or bodyweight is zero."""
    if lift_1rm_kg is None or not bodyweight_kg:
        return {"value": None}
    return {"value": round(lift_1rm_kg / bodyweight_kg, 2)}
```

One call per lift (squat/bench/deadlift), using the latest entry's
`{lift}_1rm_current` and `body_weight_mass`.

### 5.3 Rate of change per lift

Ordinary least squares over `(day_offset, value)` pairs, using entries from
the trailing `config.RATE_OF_CHANGE_WINDOW_DAYS` days (default 90) that have a
non-null value for that lift. Needs at least 2 distinct dates.

```python
def compute_rate_of_change(history_asc: list[dict], key: str, window_days: int, today: date):
    """`history_asc` is oldest-first, each item has 'entry_date' (ISO date
    string) and `key` (e.g. 'squat'). Returns {"kg_per_week": float} or
    {"kg_per_week": None} if there isn't enough recent data.

    The cutoff is anchored to `today` (the real current date, passed in by
    the caller), not to the most recent entry's date. If logging has
    lapsed for months, the window must correctly end up empty (or near-
    empty) rather than silently reusing a stale window ending at the last
    logged entry - a stale window would let `compute_projected_date` project
    a target date from dead data.
    """
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
    x0 = points[0][0]
    xs = [(p[0] - x0).days for p in points]
    ys = [p[1] for p in points]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var = sum((x - mean_x) ** 2 for x in xs)
    if var == 0:
        return {"kg_per_week": None}
    slope_per_day = cov / var
    return {"kg_per_week": round(slope_per_day * 7, 2)}
```

### 5.4 Projected date to hit target

```python
def compute_projected_date(current, target, kg_per_week, today: date):
    """Returns one of:
      {"state": "target_met"}
      {"state": "no_data"}
      {"state": "not_on_track"}                      # rate <= 0, current < target
      {"state": "too_far", "years": float}           # projected > 10 years out
      {"state": "projected", "date": "YYYY-MM-DD"}
    """
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
```

### 5.5 PR timeline

No backend computation needed - `history` (already sent to the frontend,
oldest-first) has everything required. The frontend computes, per lift, a
running maximum over the ascending series and flags any point that is a new
all-time high (first non-null point always counts) as `is_pr: true`. Do this
client-side in `dashboard.js`, not in Python.

## 6. `app/metrics.py` changes

- Add a stable `"id"` field to every card dict already produced:
  - `build_lift_cards`: `"id": f"lift.{key}"` for each of squat/bench/deadlift.
  - `build_total_card`: `"id": "lift.total"`.
  - `build_body_cards`: `"id": f"body.{key}"` for each `BODY_METRICS` entry.
  - `build_index_cards`: `"id": "index.bmi"` and `"id": "index.bmr"`.
- Add `build_analytics_payload(entry, config, settings, history_asc)` that
  returns:

```python
{
    "dots_score": compute_dots_score(entry.total_weight_lifted_current, entry.body_weight_mass, settings.lifter_sex),
    "ratios": {
        "squat": compute_ratio(entry.squat_1rm_current, entry.body_weight_mass),
        "bench": compute_ratio(entry.bench_1rm_current, entry.body_weight_mass),
        "deadlift": compute_ratio(entry.deadlift_1rm_current, entry.body_weight_mass),
    },
    "rate_of_change": {
        "squat": compute_rate_of_change(history_asc_with_squat_key, "squat", config.RATE_OF_CHANGE_WINDOW_DAYS),
        "bench": ...,
        "deadlift": ...,
    },
    "projected_dates": {
        "squat": compute_projected_date(current_squat, target_squat, rate_of_change.squat.kg_per_week, today),
        "bench": ...,
        "deadlift": ...,
    },
}
```

  Reuse the existing `history` list already built in `build_dashboard_payload`
  (it already has `squat`/`bench`/`deadlift` keys per row) as the input to
  `compute_rate_of_change`, so there is exactly one history query, no
  duplicated data. Pass `today = datetime.now(timezone.utc).date()` (or the
  configured local date, whichever pattern the rest of the module already
  uses) into `compute_rate_of_change` - never derive the cutoff from the
  data itself.
- `build_dashboard_payload` must also add:
  - `"health_history": [...]` - ascending list of
    `{entry_date, resting_heart_rate, heart_rate_variability_ms, sleep_minutes}`
    from `db.get_health_metrics(limit=180)`, for the new Activity & Recovery
    trend chart. Convert `sleep_minutes` to hours in the frontend, not here
    (keep raw units in the payload, consistent with `history`).
  - `"google_health_configured": bool(settings.get("google_health_client_id")) and bool(settings.get("google_health_client_secret"))`.
    Note this is deliberately *not* the same as "connected" (which checks
    `google_health_refresh_token` in `routes/api.py`'s dashboard endpoint) -
    widget gating is about configuration, not completed OAuth.
  - the analytics payload from above, merged in.

## 7. `app/routes/api.py` changes

- Extend `dashboard_data()` to pass the extra fields through
  `build_dashboard_payload` (already covered by the metrics.py change above -
  no extra plumbing needed there beyond passing `db.get_health_metrics()` and
  `db.get_settings()` in).
- New endpoints:

```python
from .. import widgets as widget_catalog

@router.get("/widgets/catalog")
def widgets_catalog():
    settings = db.get_settings()
    configured = bool(settings.get("google_health_client_id")) and bool(settings.get("google_health_client_secret"))
    return {"widgets": widget_catalog.build_catalog(configured)}


@router.get("/dashboard/layout")
def get_dashboard_layout():
    settings = db.get_settings()
    configured = bool(settings.get("google_health_client_id")) and bool(settings.get("google_health_client_secret"))
    raw = settings.get("dashboard_layout")
    if raw:
        try:
            return {"widgets": json.loads(raw), "is_default": False}
        except (TypeError, ValueError):
            pass
    return {"widgets": widget_catalog.default_layout(configured), "is_default": True}


@router.post("/dashboard/layout")
def save_dashboard_layout(payload: dict):
    items = payload.get("widgets")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="widgets must be a list")
    catalog_ids = {w["id"] for w in widget_catalog.WIDGET_CATALOG}
    cleaned = []
    for item in items:
        if not isinstance(item, dict) or item.get("id") not in catalog_ids:
            continue
        try:
            cleaned.append({
                "id": item["id"],
                "x": int(item["x"]), "y": int(item["y"]),
                "w": int(item["w"]), "h": int(item["h"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    db.update_settings(dashboard_layout=json.dumps(cleaned))
    return {"ok": True}


@router.post("/dashboard/layout/reset")
def reset_dashboard_layout():
    db.update_settings(dashboard_layout=None)
    return {"ok": True}
```

  Note the `POST /api/dashboard/layout` handler validates against the *full*
  catalog (`widget_catalog.WIDGET_CATALOG`, not the filtered `build_catalog`
  result) - this is what makes "skip render, keep in JSON" work: a Google
  Health widget id already in a saved layout must still validate even if
  credentials are currently unconfigured, so it is never stripped out by a
  save that happens while disconnected.

- `save_settings()`: add `"lifter_sex"` to both the `allowed` and `clearable`
  sets. Validate it is one of `"male"`/`"female"` (or `None`/empty to clear)
  before calling `db.update_settings`, mirroring the existing
  `google_health_enabled_categories` validation style - raise
  `HTTPException(400, ...)` on an invalid value.
- `get_settings()`: no change needed - `lifter_sex` is not a secret, it can
  pass straight through.

## 8. `app/routes/pages.py` changes

- `settings_page()`: no special handling needed for `lifter_sex` beyond it
  already being present in the `settings` dict passed to the template (same
  as `display_name`).
- `dashboard()`: no change needed - the dashboard template no longer needs
  server-rendered card markup; everything is fetched from
  `/api/dashboard`, `/api/widgets/catalog` and `/api/dashboard/layout` by
  `dashboard.js` on load.

## 9. Frontend

### 9.1 `app/templates/settings.html`

Add a "Sex (for DOTS score)" field near the existing `display_name`/
`date_of_birth` fields: a `<select name="lifter_sex">` with an empty/
"Not set" option, "Male", "Female", pre-selected from
`settings.lifter_sex`. Follow the existing label/input markup pattern used
for the other fields in this file. Explain in a short help line under the
field that it is only used to calculate the DOTS score.

### 9.2 `app/templates/dashboard.html`

Restructure to:

```html
<div class="top-bar">
  <div>...</div>
  <div class="status-cluster">
    ...existing nav links...
    <button id="edit-dashboard-btn" class="nav-link">Edit dashboard</button>
    <button id="save-dashboard-btn" class="nav-link" hidden>Save</button>
    <button id="cancel-dashboard-btn" class="nav-link" hidden>Cancel</button>
    <button id="reset-dashboard-btn" class="nav-link" hidden>Reset to default</button>
    <a class="gear-link" href="/settings" title="Settings">&#9881;</a>
  </div>
</div>

{% if not data.latest_entry_date %}...unchanged empty state...{% endif %}

<div id="widget-tray" class="widget-tray" hidden></div>

<div class="grid-stack" id="dashboard-grid"></div>
```

Remove the old fixed `#lift-cards` / `#body-cards` / `#health-cards` /
`.charts-grid` markup entirely - it is all now generated by `dashboard.js`
into GridStack items. Keep the `chart.umd.min.js` script tag, and add the
GridStack CSS/JS tags before `dashboard.js`:

```html
<link rel="stylesheet" href="/static/css/gridstack.min.css">
...
<script src="/static/js/gridstack-all.js"></script>
<script src="/static/js/chart.umd.min.js"></script>
<script src="/static/js/dashboard.js"></script>
```

### 9.3 `app/static/js/dashboard.js` - rewrite

Keep all existing formatting helpers (`fmt`, `valueHtml`) and existing card/
chart renderers, but restructure around a widget registry and GridStack:

1. **State**: `let grid; let editing = false; let catalog = []; let savedLayout = []; let currentWidgetIds = []; let skippedLayoutItems = []; let dashboardData = null; let charts = {};` (a map from widget id to Chart.js instance, replacing the two module-level `liftChart`/`bodyChart` variables). `skippedLayoutItems` holds the `{id, x, y, w, h}` entries from the last-loaded layout that were **not** rendered onto the board (Google-Health-gated ids while unconfigured) - see points 4 and 5, this is what stops Save from silently dropping them.
2. **Renderer registry** keyed by `kind` from the catalogue, each a function
   `(widgetId, dashboardData) -> innerHTML string` for card kinds, or
   `(widgetId, containerEl, dashboardData) -> void` for chart kinds (charts
   need a live canvas element, so they cannot be pure innerHTML like cards):
   - `lift_card`: find the matching item in `dashboardData.lift_cards` (or
     `dashboardData.total_card` for `lift.total`) by its `id` field, reuse
     `liftCardHtml`. For `lift.total`, keep the existing behaviour of
     zeroing out `competition_delta`/`competition_attainment_pct`.
   - `body_card`: find in `dashboardData.body_cards` by `id`, reuse `bodyCardHtml`.
   - `index_card`: find in `dashboardData.index_cards` by `id`, reuse `indexCardHtml`.
   - `health_card`: map widget id suffix (after `health.`) to the matching
     `dashboardData.latest_health_metric` field; reuse/extend the existing
     per-field rendering used by `healthCardsHtml`, generalised to any one of
     the 12 fields with correct unit/decimals (steps: no unit, integer;
     resting_heart_rate: " bpm"; sleep_minutes: convert to hours, " hrs", 1
     decimal; distance_km: " km", 2 decimals; floors_climbed: no unit,
     integer; active_minutes / active_zone_minutes: " min", integer;
     calories_burned: " kcal", integer; heart_rate_variability_ms: " ms",
     integer; vo2_max: " ml/kg/min", 1 decimal; respiratory_rate: " br/min",
     1 decimal; oxygen_saturation_pct: "%", 1 decimal).
   - `dots_card`: from `dashboardData.dots_score`. If `value` is `None`, show
     the existing "No data" empty state and, when `reason === "sex_not_configured"`,
     a small line "Configure sex in Settings to calculate this."
   - `ratio_card`: from `dashboardData.ratios[lift]`, format as e.g. `1.85x`
     bodyweight.
   - `rate_card`: from `dashboardData.rate_of_change[lift].kg_per_week`,
     format as `+1.2 kg/week` (or negative, or "No data" if null). Colour
     positive green (`var(--success)`), negative red (`var(--error)`), same
     convention as the existing `.delta-pill` classes.
   - `projection_card`: from `dashboardData.projected_dates[lift]`, switch on
     `state`: `target_met` -> "Target already met"; `no_data` -> "No data";
     `not_on_track` -> "Not on track at current rate"; `too_far` -> "More
     than 10 years away at current rate"; `projected` -> show the date,
     formatted `DD/MM/YYYY` (UK format, reuse `date_utils`-equivalent
     formatting already used elsewhere in the frontend if present, otherwise
     format directly in JS).
   - `chart` (kind for `chart.lifts` / `chart.body_composition`): reuse the
     existing `renderCharts`-style logic but scoped to one canvas per widget
     id, created inside the GridStack item's container the first time it is
     rendered, and updated (not recreated) on subsequent refreshes. Store the
     Chart.js instance in the `charts` map.
   - `pr_timeline_chart`: one per lift. Build from `dashboardData.history`
     (ascending). Compute running max client-side: iterate ascending,
     `isPr = value !== null && value > runningMax` (update `runningMax` after
     each non-null point; the first non-null point is always a PR). Render a
     single-line Chart.js line chart for that lift's 1RM, with
     `pointRadius`/`pointBackgroundColor` arrays: default small neutral point,
     larger gold (`#ffc553`) point at every `isPr` index. Add two flat dashed
     reference datasets if target/competition are configured for that lift
     (reuse the same target/competition values already in `lift_cards`),
     styled distinctly (dashed border, no points) so they read as reference
     lines rather than data series.
   - `activity_trend_chart`: from `dashboardData.health_history` (ascending).
     Three-series line chart: Resting Heart Rate (bpm), Heart Rate
     Variability (ms), Sleep (hours, converted from `sleep_minutes / 60`).
     Use a second Chart.js y-axis (`y1`) for sleep hours since its scale
     differs from bpm/ms, following Chart.js's standard dual-axis
     configuration (`scales: { y: {...}, y1: { position: 'right', ... } }`
     and setting `yAxisID` per dataset).
3. **GridStack init**: `cellHeight` chosen per section 4's note,
   `column: 12`, `margin: 10`, `float: true`. Start with `grid.setStatic(true)`
   (locked) until edit mode is entered.
4. **Loading a layout**: on page load, `fetch('/api/widgets/catalog')` and
   `fetch('/api/dashboard/layout')` in parallel, then `fetch('/api/dashboard')`.
   For each `{id, x, y, w, h}` in the layout: if the widget id is in the
   *catalogue response* (i.e. currently allowed - this is the "skip render,
   keep in JSON" behaviour, since the layout response itself may still
   contain a Google-Health widget id that the catalogue no longer lists),
   render it as a GridStack item at that position via `grid.addWidget({id,
   x, y, w, h, content: ''})` (or the equivalent `grid.load([...])` call) -
   **the `id` field must always be passed through explicitly**, because
   GridStack only populates `el.gridstackNode.id` (used later for chart
   lookups and Save) when the caller sets `id` on the node at creation; it
   is never inferred. If the widget id is not in the catalogue response,
   skip it entirely: do not add a placeholder, and push its `{id, x, y, w,
   h}` entry into `skippedLayoutItems` instead of discarding it, so it can
   be merged back into the next Save payload (point 5) rather than being
   silently dropped the moment the user saves while disconnected.
5. **Edit mode**:
   - "Edit dashboard" button: show Save/Cancel/Reset buttons, hide itself,
     call `grid.setStatic(false)`, show the widget tray, freeze the 60-second
     poll loop (skip `refresh()` while `editing === true` so drags aren't
     fought by a data refresh), add a small remove control to every existing
     grid item (an "x" button absolutely positioned top-right of each
     `.grid-stack-item-content`), and populate the tray with every catalogue
     widget **not** currently on the board, grouped by `category`, each with
     an "Add" button that calls `grid.addWidget({id, w: <sensible default>,
     h: <sensible default>, content: '' })` then renders that widget's
     content into the new item and removes it from the tray.
   - "Save" button: call `grid.save(false, false)` to get positions only
     (`[{id, x, y, w, h}]`, no `content`) for widgets currently on the
     board, then **merge in `skippedLayoutItems`** (any id already present
     in the `grid.save()` result wins; otherwise append the skipped entry
     unchanged) before `POST /api/dashboard/layout`. Without this merge,
     `grid.save()` only reports the items it currently knows about, so any
     gated widget that was skipped at load time would be silently dropped
     from the layout on the very next save - defeating the "skip render,
     keep in JSON" guarantee. After the successful POST, re-enable the poll
     loop, `grid.setStatic(true)`, hide Save/Cancel/Reset/tray, show "Edit
     dashboard" again.
   - "Cancel" button: discard current grid state, re-fetch
     `/api/dashboard/layout` and rebuild the grid from the last saved (or
     default) layout, then do the same UI teardown as Save.
   - "Reset to default" button: `POST /api/dashboard/layout/reset`, then
     behave like Cancel's rebuild step (re-fetch, which will now return the
     default layout with `is_default: true`).
6. **Refresh loop**: `refresh()` (the existing `fetch('/api/dashboard')`
   poll) must re-render only the *contents* of existing widgets (update
   card innerHTML, update chart `.data`/`.update()`) - never touch grid
   positions - and must be a no-op while `editing === true`.
7. **Chart resize**: `grid.on('resizestop', (event, el) => { const canvas =
   el.querySelector('canvas'); const chart = charts[el.gridstackNode.id]; if
   (chart) chart.resize(); })`.

### 9.4 CSS (`app/static/css/dashboard.css`)

- Remove/replace `.card-grid` / `.charts-grid` fixed-grid rules (no longer
  used) but keep `.card`, `.card-label`, `.card-value`, `.progress-track`,
  `.delta-pill`, `.chart-card`, `.chart-canvas-wrap` etc. as-is - they are
  reused inside GridStack items.
- Add GridStack item styling consistent with the existing dark theme
  (`--surface`, `--border` tokens): `.grid-stack-item-content` should look
  like today's `.card`/`.chart-card` (or wrap the existing markup unchanged
  and just let GridStack position the outer `.grid-stack-item` div).
- Edit-mode affordances: dashed `--border`-coloured outline on
  `.grid-stack-item-content` while editing, a small circular remove button
  (reuse `--error` colour) top-right of each item, visible only in edit mode.
- Widget tray: a collapsible panel (reuse `--surface-alt`/`--border`) listing
  available widgets grouped by category with small "Add" buttons, hidden
  outside edit mode.
- New small-card variants for `dots_card`/`ratio_card`/`rate_card`/
  `projection_card` can reuse the existing `.card` styles directly - no new
  layout classes should be needed, only new colour classes for
  positive/negative rate deltas (reuse `.delta-pill.positive`/`.negative`
  already defined for lift cards).

## 10. Testing

Keep the existing 80 tests passing. Add:

- `tests/test_analytics.py`: unit tests for `compute_dots_score` (male and
  female, including the bodyweight clamp at both range edges, and the
  `sex_not_configured` / `no_data` branches), `compute_ratio`,
  `compute_rate_of_change` (enough points, not enough points, all points
  outside the window), `compute_projected_date` (all five states).
- `tests/test_widgets.py`: `build_catalog(True)` includes all 38 ids,
  `build_catalog(False)` excludes exactly the 12 `requires_google_health`
  ids, `default_layout(False)` excludes the three health cards,
  `default_layout(True)` includes them, and every id referenced in either
  default layout exists in `WIDGET_CATALOG`.
- `tests/test_dashboard_layout_route.py` (or add to `test_entries_route.py`
  if there is an existing FastAPI TestClient fixture to reuse): `GET
  /api/dashboard/layout` returns the default when unset; `POST` then `GET`
  round-trips a layout; `POST` with an unknown widget id drops that item
  silently rather than erroring the whole request; `POST` with a Google
  Health widget id succeeds and round-trips even when Google Health is not
  configured (proves "skip render, keep in JSON" on the backend); `POST
  /api/dashboard/layout/reset` clears back to default. The backend route
  test alone cannot prove the frontend honours the same guarantee - when
  manually verifying the built feature, also run the save/reload/save
  cycle described at the end of section 9.3 point 5 (a Google-Health
  widget on the board, credentials cleared, Save, reload, Save again) and
  confirm the widget id is still present in `dashboard_layout` afterwards.
- `GET /api/widgets/catalog` returns 26 widgets when Google Health is
  unconfigured and 38 when both `google_health_client_id` and
  `google_health_client_secret` are set.
- `test_metrics.py`: extend for the new `id` fields on lift/body/index
  cards, and for `build_analytics_payload` (or wherever the merged analytics
  fields land) covering at least one full-data case and one no-data case.

Run `pyflakes app/` and `node --check app/static/js/dashboard.js` (and any
other new/modified `.js` file) before considering the work done, exactly as
in prior sessions. Do **not** run `node --check` against the vendored
`gridstack-all.js` - only against files you wrote or edited.

## 11. Manual verification

After implementation, start the server against the demo-seeded database used
in earlier sessions (`/tmp/seed_demo.py`) and take fresh screenshots
(`/tmp/screenshot_pld.py` pattern) of:

1. The dashboard in its default (view) state, showing the new Analytics and
   PR timeline widgets alongside the existing cards.
2. The dashboard in edit mode, with the widget tray open, at least one
   Google-Health-gated widget visible in the tray (seed/set
   `google_health_client_id` + `google_health_client_secret` in the demo DB
   first so this is testable), and the remove ("x") controls visible on
   existing widgets.
3. The Settings page showing the new "Sex (for DOTS score)" field.

Check every screenshot closely for overlapping grid items, squashed charts
after any resize, and truncated card text before sharing - a known failure
mode in this project is charts not reflowing after a GridStack resize (see
section 9.3 point 7).

## 12. File change manifest

New files:
- `app/widgets.py`
- `app/analytics.py`
- `app/static/js/gridstack-all.js` (vendored)
- `app/static/css/gridstack.min.css` (vendored)
- `tests/test_analytics.py`
- `tests/test_widgets.py`
- `tests/test_dashboard_layout_route.py` (or merged into an existing route
  test file, agent's judgement)
- `docs/dashboard_customization_spec.md` (this file - already present)

Modified files:
- `app/db.py` (`_ensure_settings_columns`, new `get_health_metrics`)
- `app/config.py` (`RATE_OF_CHANGE_WINDOW_DAYS`)
- `app/metrics.py` (card `id` fields, `build_analytics_payload`, extended
  `build_dashboard_payload`)
- `app/routes/api.py` (new endpoints, extended `save_settings` allowed/
  clearable fields, extended `dashboard_data`)
- `app/templates/settings.html` (sex field)
- `app/templates/dashboard.html` (grid container, edit/save/cancel/reset
  buttons, widget tray, new script/style tags)
- `app/static/js/dashboard.js` (full rewrite per section 9.3)
- `app/static/css/dashboard.css` (GridStack + edit-mode styling)
- `tests/test_metrics.py` (extended)

## 13. Style constraints (non-negotiable)

- UK English in all UI copy, code comments and docs (e.g. "colour" not
  "color" in comments/copy - CSS property names stay `color` since that is
  the CSS spec, but do not introduce new UK/US inconsistency anywhere it can
  be avoided in prose).
- No em-dashes anywhere in new or edited files. Use a comma, colon, or full
  stop instead.
- Reuse existing CSS variables (`--bg`, `--surface`, `--surface-alt`,
  `--border`, `--text`, `--text-muted`, `--text-faint`, `--primary`,
  `--primary-hover`, `--success`, `--warning`, `--error`) - do not invent new
  colour tokens.
- Match the existing code style (no framework beyond what is already vendored,
  vanilla JS, FastAPI route/handler patterns already used elsewhere in the
  file).
