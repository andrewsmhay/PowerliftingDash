import importlib
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


def test_layout_returns_default_when_unset(monkeypatch):
    client, _db = make_client(monkeypatch)
    response = client.get("/api/dashboard/layout")
    assert response.status_code == 200
    assert response.json()["is_default"] is True
    assert response.json()["widgets"]


def test_layout_post_round_trips_valid_items(monkeypatch):
    client, _db = make_client(monkeypatch)
    widgets = [{"id": "lift.squat", "x": 1, "y": 2, "w": 3, "h": 4}]
    assert client.post("/api/dashboard/layout", json={"widgets": widgets}).status_code == 200
    response = client.get("/api/dashboard/layout")
    assert response.json() == {"widgets": widgets, "is_default": False}


def test_layout_post_discards_unknown_widgets_but_keeps_request_successful(monkeypatch):
    client, _db = make_client(monkeypatch)
    response = client.post("/api/dashboard/layout", json={"widgets": [
        {"id": "unknown.widget", "x": 0, "y": 0, "w": 3, "h": 4},
        {"id": "lift.bench", "x": 3, "y": 0, "w": 3, "h": 4},
    ]})
    assert response.status_code == 200
    assert client.get("/api/dashboard/layout").json()["widgets"] == [
        {"id": "lift.bench", "x": 3, "y": 0, "w": 3, "h": 4}
    ]


def test_layout_keeps_gated_widget_when_google_health_is_unconfigured(monkeypatch):
    client, _db = make_client(monkeypatch)
    widget = {"id": "health.steps", "x": 0, "y": 0, "w": 3, "h": 4}
    assert client.post("/api/dashboard/layout", json={"widgets": [widget]}).status_code == 200
    assert client.get("/api/dashboard/layout").json()["widgets"] == [widget]


def test_layout_reset_returns_to_default(monkeypatch):
    client, db = make_client(monkeypatch)
    client.post("/api/dashboard/layout", json={"widgets": [{"id": "lift.squat", "x": 0, "y": 0, "w": 3, "h": 4}]})
    assert client.post("/api/dashboard/layout/reset").status_code == 200
    assert db.get_settings()["dashboard_layout"] is None
    assert client.get("/api/dashboard/layout").json()["is_default"] is True


def test_widget_catalog_is_gated_by_google_health_credentials(monkeypatch):
    client, db = make_client(monkeypatch)
    assert len(client.get("/api/widgets/catalog").json()["widgets"]) == 25
    db.update_settings(google_health_client_id="client", google_health_client_secret="secret")
    assert len(client.get("/api/widgets/catalog").json()["widgets"]) == 38
