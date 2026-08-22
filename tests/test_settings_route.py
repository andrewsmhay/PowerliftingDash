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

    from app import derive, formatting, openpowerlifting
    from app.routes import api, entries, pages, targets

    importlib.reload(derive)
    importlib.reload(formatting)
    importlib.reload(openpowerlifting)
    importlib.reload(entries)
    importlib.reload(pages)
    importlib.reload(targets)
    importlib.reload(api)

    import app.main as main_module

    importlib.reload(main_module)

    from fastapi.testclient import TestClient

    db.init_db()
    return TestClient(main_module.app), api


def test_save_settings_accepts_name_dob_and_username(monkeypatch):
    client, api = make_client(monkeypatch)
    monkeypatch.setattr(
        api, "fetch_personal_bests", lambda username: (_ for _ in ()).throw(AssertionError("should not be called"))
    )

    resp = client.post(
        "/api/settings",
        json={"display_name": "Andrew", "date_of_birth": "24/02/1979"},
    )
    assert resp.status_code == 200

    from app import db

    settings = db.get_settings()
    assert settings["display_name"] == "Andrew"
    assert settings["date_of_birth"] == "1979-02-24"


def test_save_settings_rejects_bad_date_of_birth(monkeypatch):
    client, _api = make_client(monkeypatch)

    resp = client.post("/api/settings", json={"date_of_birth": "not-a-date"})
    assert resp.status_code == 400


def test_save_settings_validates_manual_height(monkeypatch):
    client, _api = make_client(monkeypatch)

    valid = client.post("/api/settings", json={"height_cm": "182.5"})
    assert valid.status_code == 200

    from app import db

    assert db.get_settings()["height_cm"] == 182.5
    assert client.post("/api/settings", json={"height_cm": "tall"}).status_code == 400
    assert client.post("/api/settings", json={"height_cm": "0"}).status_code == 400
    assert client.post("/api/settings", json={"height_cm": "301"}).status_code == 400


def test_save_settings_rejects_fast_dashboard_rotation(monkeypatch):
    client, _api = make_client(monkeypatch)

    assert client.post("/api/settings", json={"dashboard_rotation_seconds": "4"}).status_code == 400
    assert client.post("/api/settings", json={"dashboard_rotation_seconds": "5"}).status_code == 200

    from app import db

    assert db.get_settings()["dashboard_rotation_seconds"] == 5


def test_save_settings_triggers_opl_fetch_on_new_username(monkeypatch):
    client, api = make_client(monkeypatch)
    calls = []

    def fake_fetch(username):
        calls.append(username)
        return {"equip": "Raw", "squat": 100.0, "bench": 60.0, "deadlift": 120.0, "total": 280.0}

    monkeypatch.setattr(api, "fetch_personal_bests", fake_fetch)

    resp = client.post("/api/settings", json={"openpowerlifting_username": "andrewhay"})
    assert resp.status_code == 200
    assert calls == ["andrewhay"]

    from app import db

    settings = db.get_settings()
    assert settings["opl_best_squat"] == 100.0
    assert settings["opl_best_total"] == 280.0
    assert settings["opl_fetch_error"] is None


def test_save_settings_does_not_refetch_when_username_unchanged(monkeypatch):
    client, api = make_client(monkeypatch)
    calls = []
    monkeypatch.setattr(api, "fetch_personal_bests", lambda username: calls.append(username) or {
        "equip": "Raw", "squat": 100.0, "bench": 60.0, "deadlift": 120.0, "total": 280.0
    })

    client.post("/api/settings", json={"openpowerlifting_username": "andrewhay"})
    assert len(calls) == 1

    client.post("/api/settings", json={"timezone": "Europe/Dublin"})
    assert len(calls) == 1  # unchanged username, no refetch


def test_save_settings_surfaces_opl_warning_on_fetch_failure(monkeypatch):
    client, api = make_client(monkeypatch)
    from app.openpowerlifting import FetchError

    monkeypatch.setattr(
        api, "fetch_personal_bests", lambda username: (_ for _ in ()).throw(FetchError("no such lifter"))
    )

    resp = client.post("/api/settings", json={"openpowerlifting_username": "nobody"})
    assert resp.status_code == 200  # settings still saved
    body = resp.json()
    assert "no such lifter" in body["openpowerlifting_warning"]

    from app import db

    settings = db.get_settings()
    assert settings["opl_fetch_error"] == "no such lifter"


def test_refresh_endpoint_requires_configured_username(monkeypatch):
    client, _api = make_client(monkeypatch)

    resp = client.post("/api/openpowerlifting/refresh")
    assert resp.status_code == 400


def test_refresh_endpoint_returns_bests_on_success(monkeypatch):
    client, api = make_client(monkeypatch)
    client.post("/api/settings", json={"timezone": "Europe/Dublin"})

    from app import db

    db.update_settings(openpowerlifting_username="andrewhay")

    monkeypatch.setattr(
        api,
        "fetch_personal_bests",
        lambda username: {"equip": "Raw", "squat": 150.0, "bench": 100.0, "deadlift": 180.0, "total": 430.0},
    )

    resp = client.post("/api/openpowerlifting/refresh")
    assert resp.status_code == 200
    assert resp.json()["bests"]["total"] == 430.0


def test_save_settings_accepts_google_health_setup_without_returning_secret(monkeypatch):
    client, _api = make_client(monkeypatch)

    response = client.post(
        "/api/settings",
        json={
            "google_health_client_id": "client-id",
            "google_health_client_secret": "very-secret",
            "google_health_enabled_categories": '["activity", "sleep"]',
        },
    )
    assert response.status_code == 200

    response = client.get("/api/settings")
    body = response.json()
    assert body["google_health_client_id"] == "client-id"
    assert body["google_health_client_secret_set"] is True
    assert "google_health_client_secret" not in body


def test_google_health_sync_route_uses_shared_synchroniser(monkeypatch):
    client, api = make_client(monkeypatch)
    from app.routes import google_health as google_health_routes

    monkeypatch.setattr(google_health_routes, "synchronise_google_health", lambda: {"ok": True, "metrics_dates": 2})
    response = client.post("/api/google-health/sync")
    assert response.status_code == 200
    assert response.json()["metrics_dates"] == 2
    assert api is not None
