import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.widgets import WIDGET_CATALOG, build_catalog, default_screens


def test_catalog_contains_all_widgets_when_google_health_is_configured():
    assert len(WIDGET_CATALOG) == 38
    assert {widget["id"] for widget in build_catalog(True)} == {widget["id"] for widget in WIDGET_CATALOG}


def test_catalog_hides_every_google_health_widget_when_unconfigured():
    gated_ids = {widget["id"] for widget in WIDGET_CATALOG if widget.get("requires_google_health")}
    visible_ids = {widget["id"] for widget in build_catalog(False)}
    assert len(gated_ids) == 13
    assert len(visible_ids) == 25
    assert gated_ids.isdisjoint(visible_ids)


def test_default_screens_only_add_activity_recovery_when_configured():
    without_health = default_screens(False)
    with_health = default_screens(True)
    without_health_ids = {item["id"] for screen in without_health for item in screen["widgets"]}
    with_health_ids = {item["id"] for screen in with_health for item in screen["widgets"]}
    initial_health_ids = {"health.steps", "health.resting_heart_rate", "health.sleep_minutes"}
    assert len(without_health) == 3
    assert len(with_health) == 4
    assert initial_health_ids.isdisjoint(without_health_ids)
    assert initial_health_ids.issubset(with_health_ids)


def test_every_default_screen_widget_exists_in_the_catalogue():
    catalog_ids = {widget["id"] for widget in WIDGET_CATALOG}
    for configured in (False, True):
        widget_ids = {item["id"] for screen in default_screens(configured) for item in screen["widgets"]}
        assert widget_ids.issubset(catalog_ids)
