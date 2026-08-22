import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.widgets import WIDGET_CATALOG, build_catalog, default_layout


def test_catalog_contains_all_widgets_when_google_health_is_configured():
    assert len(WIDGET_CATALOG) == 38
    assert {widget["id"] for widget in build_catalog(True)} == {widget["id"] for widget in WIDGET_CATALOG}


def test_catalog_hides_every_google_health_widget_when_unconfigured():
    gated_ids = {widget["id"] for widget in WIDGET_CATALOG if widget.get("requires_google_health")}
    visible_ids = {widget["id"] for widget in build_catalog(False)}
    assert len(gated_ids) == 13
    assert len(visible_ids) == 25
    assert gated_ids.isdisjoint(visible_ids)


def test_default_layout_only_adds_initial_health_cards_when_configured():
    without_health = {item["id"] for item in default_layout(False)}
    with_health = {item["id"] for item in default_layout(True)}
    initial_health_ids = {"health.steps", "health.resting_heart_rate", "health.sleep_minutes"}
    assert initial_health_ids.isdisjoint(without_health)
    assert initial_health_ids.issubset(with_health)


def test_every_default_layout_widget_exists_in_the_catalogue():
    catalog_ids = {widget["id"] for widget in WIDGET_CATALOG}
    for configured in (False, True):
        assert {item["id"] for item in default_layout(configured)}.issubset(catalog_ids)
