import importlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_client(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    from app import config

    monkeypatch.setattr(config, "DATA_DIR", Path(tmpdir))
    monkeypatch.setattr(config, "DB_PATH", Path(tmpdir) / "test.sqlite3")
    from app import db

    importlib.reload(db)
    from app.routes import api, entries, pages, targets

    importlib.reload(api)
    importlib.reload(entries)
    importlib.reload(pages)
    importlib.reload(targets)
    import app.main as main_module

    importlib.reload(main_module)
    from fastapi.testclient import TestClient

    db.init_db()
    return TestClient(main_module.app), db


def test_layout_returns_default_screens_when_unset(monkeypatch):
    client, _db = make_client(monkeypatch)
    response = client.get("/api/dashboard/layout")
    body = response.json()
    assert response.status_code == 200
    assert body["is_default"] is True
    assert len(body["screens"]) == 4
    assert body["screens"][0]["name"] == "Lifts & Body"
    assert body["rotation_seconds"] == 30


def test_legacy_flat_list_loads_as_one_screen(monkeypatch):
    client, db = make_client(monkeypatch)
    widgets = [{"id": "lift.squat", "x": 1, "y": 2, "w": 3, "h": 4}]
    db.update_settings(dashboard_layout=json.dumps(widgets))

    body = client.get("/api/dashboard/layout").json()

    assert body["is_default"] is False
    assert body["screens"] == [{
        "id": "legacy-dashboard",
        "name": "Dashboard",
        "widgets": widgets,
    }]


def test_layout_post_round_trips_multiple_screens(monkeypatch):
    client, _db = make_client(monkeypatch)
    screens = [
        {
            "id": "screen-lifts",
            "name": "Lifts",
            "widgets": [{"id": "lift.squat", "x": 1, "y": 2, "w": 3, "h": 4}],
        },
        {
            "id": "screen-trends",
            "name": "Trends",
            "widgets": [{"id": "chart.lifts", "x": 0, "y": 0, "w": 6, "h": 8}],
        },
    ]
    assert client.post("/api/dashboard/layout", json={"screens": screens}).status_code == 200
    body = client.get("/api/dashboard/layout").json()
    assert body["screens"] == screens
    assert body["is_default"] is False


def test_layout_post_discards_unknown_widgets_but_keeps_request_successful(monkeypatch):
    client, _db = make_client(monkeypatch)
    response = client.post("/api/dashboard/layout", json={"screens": [{
        "id": "screen-one",
        "name": "One",
        "widgets": [
            {"id": "unknown.widget", "x": 0, "y": 0, "w": 3, "h": 4},
            {"id": "lift.bench", "x": 3, "y": 0, "w": 3, "h": 4},
        ],
    }]})
    assert response.status_code == 200
    assert client.get("/api/dashboard/layout").json()["screens"][0]["widgets"] == [
        {"id": "lift.bench", "x": 3, "y": 0, "w": 3, "h": 4}
    ]


def test_layout_keeps_gated_widget_when_google_health_is_unconfigured(monkeypatch):
    client, _db = make_client(monkeypatch)
    widget = {"id": "health.steps", "x": 0, "y": 0, "w": 3, "h": 4}
    payload = {"screens": [{"id": "screen-health", "name": "Health", "widgets": [widget]}]}
    assert client.post("/api/dashboard/layout", json=payload).status_code == 200
    assert client.get("/api/dashboard/layout").json()["screens"][0]["widgets"] == [widget]


def test_screen_add_remove_and_rename_payload_shape(monkeypatch):
    client, _db = make_client(monkeypatch)
    initial = {"screens": [
        {"id": "screen-one", "name": "Original", "widgets": []},
        {"id": "screen-two", "name": "New screen", "widgets": [{"id": "lift.total", "x": 0, "y": 0, "w": 3, "h": 6}]},
    ]}
    assert client.post("/api/dashboard/layout", json=initial).status_code == 200

    updated = {"screens": [
        {"id": "screen-two", "name": "Competition", "widgets": [{"id": "lift.total", "x": 0, "y": 0, "w": 3, "h": 6}]},
    ]}
    assert client.post("/api/dashboard/layout", json=updated).status_code == 200
    assert client.get("/api/dashboard/layout").json()["screens"] == updated["screens"]


def test_layout_reset_returns_to_default(monkeypatch):
    client, db = make_client(monkeypatch)
    client.post("/api/dashboard/layout", json={"screens": [{
        "id": "screen-one",
        "name": "One",
        "widgets": [{"id": "lift.squat", "x": 0, "y": 0, "w": 3, "h": 4}],
    }]})
    assert client.post("/api/dashboard/layout/reset").status_code == 200
    assert db.get_settings()["dashboard_layout"] is None
    assert client.get("/api/dashboard/layout").json()["is_default"] is True


def test_widget_catalog_is_gated_by_google_health_credentials(monkeypatch):
    client, db = make_client(monkeypatch)
    assert len(client.get("/api/widgets/catalog").json()["widgets"]) == 29
    db.update_settings(google_health_client_id="client", google_health_client_secret="secret")
    assert len(client.get("/api/widgets/catalog").json()["widgets"]) == 42
