"""Widget catalogue and the built-in dashboard arrangement."""

WIDGET_CATALOG = [
    {"id": "lift.squat", "label": "Squat", "category": "Lifts", "kind": "lift_card"},
    {"id": "lift.bench", "label": "Bench", "category": "Lifts", "kind": "lift_card"},
    {"id": "lift.deadlift", "label": "Deadlift", "category": "Lifts", "kind": "lift_card"},
    {"id": "lift.total", "label": "Total", "category": "Lifts", "kind": "lift_card"},
    {"id": "body.body_weight_mass", "label": "Body Weight", "category": "Body Composition", "kind": "body_card"},
    {"id": "body.skeletal_muscle_mass", "label": "Skeletal Muscle Mass", "category": "Body Composition", "kind": "body_card"},
    {"id": "body.body_fat_mass", "label": "Body Fat Mass", "category": "Body Composition", "kind": "body_card"},
    {"id": "body.percent_body_fat", "label": "Body Fat", "category": "Body Composition", "kind": "body_card"},
    {"id": "body.lean_mass", "label": "Lean Mass", "category": "Body Composition", "kind": "body_card"},
    {"id": "index.bmi", "label": "BMI", "category": "Body Composition", "kind": "index_card"},
    {"id": "index.bmr", "label": "BMR", "category": "Body Composition", "kind": "index_card"},
    {"id": "score.dots", "label": "DOTS Score", "category": "Analytics", "kind": "score_card"},
    {"id": "score.wilks2", "label": "Wilks-2 Score", "category": "Analytics", "kind": "score_card"},
    {"id": "score.ipf_gl", "label": "IPF GL Points", "category": "Analytics", "kind": "score_card"},
    {"id": "ratio.squat_bw", "label": "Squat : Bodyweight", "category": "Analytics", "kind": "ratio_card"},
    {"id": "ratio.bench_bw", "label": "Bench : Bodyweight", "category": "Analytics", "kind": "ratio_card"},
    {"id": "ratio.deadlift_bw", "label": "Deadlift : Bodyweight", "category": "Analytics", "kind": "ratio_card"},
    {"id": "rate.squat", "label": "Squat Rate of Change", "category": "Analytics", "kind": "rate_card"},
    {"id": "rate.bench", "label": "Bench Rate of Change", "category": "Analytics", "kind": "rate_card"},
    {"id": "rate.deadlift", "label": "Deadlift Rate of Change", "category": "Analytics", "kind": "rate_card"},
    {"id": "pr_interval.squat", "label": "Squat PR Pace", "category": "Analytics", "kind": "pr_interval_card"},
    {"id": "pr_interval.bench", "label": "Bench PR Pace", "category": "Analytics", "kind": "pr_interval_card"},
    {"id": "pr_interval.deadlift", "label": "Deadlift PR Pace", "category": "Analytics", "kind": "pr_interval_card"},
    {"id": "chart.lifts", "label": "1RM Over Time", "category": "Trends", "kind": "chart"},
    {"id": "chart.body_composition", "label": "Body Composition Over Time", "category": "Trends", "kind": "chart"},
    {"id": "pr_timeline.squat", "label": "Squat PR Timeline", "category": "Trends", "kind": "pr_timeline_chart"},
    {"id": "pr_timeline.bench", "label": "Bench PR Timeline", "category": "Trends", "kind": "pr_timeline_chart"},
    {"id": "pr_timeline.deadlift", "label": "Deadlift PR Timeline", "category": "Trends", "kind": "pr_timeline_chart"},
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


def build_catalog(google_health_configured: bool) -> list[dict]:
    """Returns only widgets that may be added in the current configuration."""
    return [
        widget for widget in WIDGET_CATALOG
        if google_health_configured or not widget.get("requires_google_health")
    ]


def default_screens(google_health_configured: bool) -> list[dict]:
    """Returns the default multi-screen layout for the current Health setup."""
    screens = [
        {
            "id": "screen-lifts-body",
            "name": "Lifts & Body",
            "widgets": [
                {"id": "lift.squat", "x": 0, "y": 0, "w": 3, "h": 6},
                {"id": "lift.bench", "x": 3, "y": 0, "w": 3, "h": 6},
                {"id": "lift.deadlift", "x": 6, "y": 0, "w": 3, "h": 6},
                {"id": "lift.total", "x": 9, "y": 0, "w": 3, "h": 6},
                {"id": "body.body_weight_mass", "x": 0, "y": 6, "w": 3, "h": 4},
                {"id": "body.skeletal_muscle_mass", "x": 3, "y": 6, "w": 3, "h": 4},
                {"id": "body.body_fat_mass", "x": 6, "y": 6, "w": 3, "h": 4},
                {"id": "body.percent_body_fat", "x": 9, "y": 6, "w": 3, "h": 4},
                {"id": "index.bmi", "x": 0, "y": 10, "w": 3, "h": 4},
                {"id": "index.bmr", "x": 3, "y": 10, "w": 3, "h": 4},
                {"id": "body.lean_mass", "x": 6, "y": 10, "w": 3, "h": 4},
            ],
        },
        {
            "id": "screen-analytics",
            "name": "Analytics",
            "widgets": [
                {"id": "score.dots", "x": 0, "y": 0, "w": 4, "h": 4},
                {"id": "score.wilks2", "x": 4, "y": 0, "w": 4, "h": 4},
                {"id": "score.ipf_gl", "x": 8, "y": 0, "w": 4, "h": 4},
                {"id": "ratio.squat_bw", "x": 0, "y": 4, "w": 4, "h": 4},
                {"id": "ratio.bench_bw", "x": 4, "y": 4, "w": 4, "h": 4},
                {"id": "ratio.deadlift_bw", "x": 8, "y": 4, "w": 4, "h": 4},
                {"id": "rate.squat", "x": 0, "y": 8, "w": 4, "h": 4},
                {"id": "rate.bench", "x": 4, "y": 8, "w": 4, "h": 4},
                {"id": "rate.deadlift", "x": 8, "y": 8, "w": 4, "h": 4},
                {"id": "pr_interval.squat", "x": 0, "y": 12, "w": 4, "h": 4},
                {"id": "pr_interval.bench", "x": 4, "y": 12, "w": 4, "h": 4},
                {"id": "pr_interval.deadlift", "x": 8, "y": 12, "w": 4, "h": 4},
            ],
        },
        {
            "id": "screen-trends",
            "name": "Trends",
            "widgets": [
                {"id": "chart.lifts", "x": 0, "y": 0, "w": 6, "h": 8},
                {"id": "chart.body_composition", "x": 6, "y": 0, "w": 6, "h": 8},
                {"id": "pr_timeline.squat", "x": 0, "y": 8, "w": 4, "h": 8},
                {"id": "pr_timeline.bench", "x": 4, "y": 8, "w": 4, "h": 8},
                {"id": "pr_timeline.deadlift", "x": 8, "y": 8, "w": 4, "h": 8},
            ],
        },
    ]
    if google_health_configured:
        screens.append({
            "id": "screen-activity-recovery",
            "name": "Activity & Recovery",
            "widgets": [
                {"id": "health.steps", "x": 0, "y": 0, "w": 4, "h": 4},
                {"id": "health.resting_heart_rate", "x": 4, "y": 0, "w": 4, "h": 4},
                {"id": "health.sleep_minutes", "x": 8, "y": 0, "w": 4, "h": 4},
                {"id": "chart.activity_recovery_trend", "x": 0, "y": 4, "w": 12, "h": 8},
            ],
        })
    return screens
