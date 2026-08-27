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

    from app import derive
    from app.routes import competitions, countdowns, entries, pages, targets

    importlib.reload(derive)
    importlib.reload(entries)
    importlib.reload(pages)
    importlib.reload(targets)
    importlib.reload(competitions)
    importlib.reload(countdowns)

    import app.main as main_module

    importlib.reload(main_module)

    from fastapi.testclient import TestClient

    db.init_db()
    return TestClient(main_module.app), db


def test_create_countdown_persists_and_returns_ddmmyyyy(monkeypatch):
    client, db = make_client(monkeypatch)

    resp = client.post(
        "/api/countdowns",
        json={
            "event_date": "15/06/2030",
            "values": {"event_name": "Provincial Championships"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["event_date_ddmmyyyy"] == "15/06/2030"
    assert body["countdown"]["event_name"] == "Provincial Championships"
    assert db.count_countdowns() == 1


def test_create_countdown_requires_event_name(monkeypatch):
    client, _ = make_client(monkeypatch)

    resp = client.post(
        "/api/countdowns",
        json={"event_date": "15/06/2030", "values": {}},
    )
    assert resp.status_code == 400


def test_create_countdown_requires_a_valid_date(monkeypatch):
    client, _ = make_client(monkeypatch)

    resp = client.post(
        "/api/countdowns",
        json={"event_date": "not-a-date", "values": {"event_name": "Club Meet"}},
    )
    assert resp.status_code == 400


def test_create_countdown_rejects_unknown_fields(monkeypatch):
    client, _ = make_client(monkeypatch)

    resp = client.post(
        "/api/countdowns",
        json={
            "event_date": "15/06/2030",
            "values": {"event_name": "Club Meet", "not_a_real_field": "x"},
        },
    )
    assert resp.status_code == 400


def test_create_countdown_with_location(monkeypatch):
    client, db = make_client(monkeypatch)

    resp = client.post(
        "/api/countdowns",
        json={
            "event_date": "15/06/2030",
            "values": {
                "event_name": "Nationals",
                "country": "Canada",
                "region": "Ontario",
                "city": "Ottawa",
            },
        },
    )
    assert resp.status_code == 200
    countdown = resp.json()["countdown"]
    assert countdown["country"] == "Canada"
    assert countdown["region"] == "Ontario"
    assert countdown["city"] == "Ottawa"


def test_update_countdown_overwrites_and_clears_omitted_fields(monkeypatch):
    client, db = make_client(monkeypatch)

    create_resp = client.post(
        "/api/countdowns",
        json={
            "event_date": "15/06/2030",
            "values": {"event_name": "Club Meet", "country": "Canada"},
        },
    )
    countdown_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/countdowns/{countdown_id}",
        json={
            "event_date": "16/06/2030",
            "values": {"event_name": "Club Meet (corrected)"},
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["countdown"]
    assert updated["event_name"] == "Club Meet (corrected)"
    assert updated["country"] is None

    saved = db.get_countdown_by_id(countdown_id)
    assert saved["event_date"] == "2030-06-16"


def test_update_countdown_returns_404_for_unknown_id(monkeypatch):
    client, _ = make_client(monkeypatch)

    resp = client.put(
        "/api/countdowns/does-not-exist",
        json={"event_date": "15/06/2030", "values": {"event_name": "x"}},
    )
    assert resp.status_code == 404


def test_delete_countdown_removes_it(monkeypatch):
    client, db = make_client(monkeypatch)

    create_resp = client.post(
        "/api/countdowns",
        json={"event_date": "15/06/2030", "values": {"event_name": "Club Meet"}},
    )
    countdown_id = create_resp.json()["id"]

    delete_resp = client.delete(f"/api/countdowns/{countdown_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["ok"] is True
    assert db.count_countdowns() == 0


def test_delete_countdown_returns_404_for_unknown_id(monkeypatch):
    client, _ = make_client(monkeypatch)
    resp = client.delete("/api/countdowns/does-not-exist")
    assert resp.status_code == 404


def test_add_countdown_location_dedupes_case_insensitively(monkeypatch):
    client, db = make_client(monkeypatch)

    first = client.post("/api/countdowns/locations", json={"kind": "country", "value": "Canada"})
    assert first.status_code == 200
    assert first.json()["created"] is True

    second = client.post("/api/countdowns/locations", json={"kind": "country", "value": "canada"})
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["id"] == first.json()["id"]

    locations = db.get_all_countdown_locations()
    assert len(locations["country"]) == 1


def test_add_countdown_location_rejects_unknown_kind(monkeypatch):
    client, _ = make_client(monkeypatch)
    resp = client.post("/api/countdowns/locations", json={"kind": "planet", "value": "Mars"})
    assert resp.status_code == 400


def test_add_countdown_location_requires_a_value(monkeypatch):
    client, _ = make_client(monkeypatch)
    resp = client.post("/api/countdowns/locations", json={"kind": "country", "value": "  "})
    assert resp.status_code == 400


def test_delete_countdown_location_removes_it(monkeypatch):
    client, db = make_client(monkeypatch)
    created = client.post("/api/countdowns/locations", json={"kind": "city", "value": "Ottawa"}).json()

    delete_resp = client.delete(f"/api/countdowns/locations/{created['id']}")
    assert delete_resp.status_code == 200
    assert db.get_all_countdown_locations()["city"] == []


def test_delete_countdown_location_returns_404_for_unknown_id(monkeypatch):
    client, _ = make_client(monkeypatch)
    resp = client.delete("/api/countdowns/locations/does-not-exist")
    assert resp.status_code == 404


def test_competitions_page_renders_countdown_section(monkeypatch):
    client, _ = make_client(monkeypatch)

    empty_resp = client.get("/competitions")
    assert empty_resp.status_code == 200
    assert "No countdowns added yet" in empty_resp.text

    client.post(
        "/api/countdowns",
        json={"event_date": "15/06/2030", "values": {"event_name": "Future Meet"}},
    )
    filled_resp = client.get("/competitions")
    assert filled_resp.status_code == 200
    assert "Future Meet" in filled_resp.text


def test_competitions_page_splits_upcoming_and_past_countdowns(monkeypatch):
    client, _ = make_client(monkeypatch)

    client.post(
        "/api/countdowns",
        json={"event_date": "15/06/2020", "values": {"event_name": "Old Meet"}},
    )
    client.post(
        "/api/countdowns",
        json={"event_date": "15/06/2099", "values": {"event_name": "Future Meet"}},
    )

    resp = client.get("/competitions")
    assert resp.status_code == 200
    # Both rows render regardless of section - just confirm the page renders
    # both without erroring on the days_until/time_until computation.
    assert "Old Meet" in resp.text
    assert "Future Meet" in resp.text
    assert "ago" in resp.text  # the past event's "N days ago" label
    assert "In " in resp.text  # the future event's "In N days" label


def test_dashboard_payload_includes_upcoming_countdowns(monkeypatch):
    client, _ = make_client(monkeypatch)

    client.post(
        "/api/countdowns",
        json={"event_date": "15/06/2020", "values": {"event_name": "Old Meet"}},
    )
    client.post(
        "/api/countdowns",
        json={"event_date": "15/06/2099", "values": {"event_name": "Future Meet"}},
    )

    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    block = resp.json()["countdowns_upcoming"]
    assert block["total"] == 1
    assert block["items"][0]["event_name"] == "Future Meet"


def test_countdowns_widget_is_in_catalog(monkeypatch):
    client, _ = make_client(monkeypatch)
    resp = client.get("/api/widgets/catalog")
    assert resp.status_code == 200
    ids = [w["id"] for w in resp.json()["widgets"]]
    assert "countdown.list" in ids
