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
    from app.routes import competitions, entries, pages, targets

    importlib.reload(derive)
    importlib.reload(entries)
    importlib.reload(pages)
    importlib.reload(targets)
    importlib.reload(competitions)

    import app.main as main_module

    importlib.reload(main_module)

    from fastapi.testclient import TestClient

    db.init_db()
    return TestClient(main_module.app), db


def test_create_competition_persists_and_returns_ddmmyyyy(monkeypatch):
    client, db = make_client(monkeypatch)

    resp = client.post(
        "/api/competitions",
        json={
            "competition_date": "15/06/2026",
            "values": {
                "meet_name": "Ontario Provincials",
                "federation": "CPU",
                "placing": "1st",
                "bodyweight_kg": "92.4",
                "squat_kg": "220",
                "bench_kg": "150",
                "deadlift_kg": "250",
                "total_kg": "620",
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["competition_date_ddmmyyyy"] == "15/06/2026"
    assert body["competition"]["meet_name"] == "Ontario Provincials"
    assert db.count_competitions() == 1


def test_create_competition_requires_a_valid_date(monkeypatch):
    client, _ = make_client(monkeypatch)

    resp = client.post(
        "/api/competitions",
        json={"competition_date": "not-a-date", "values": {"meet_name": "Club Meet"}},
    )
    assert resp.status_code == 400


def test_create_competition_rejects_a_completely_blank_submission(monkeypatch):
    client, _ = make_client(monkeypatch)

    resp = client.post(
        "/api/competitions",
        json={"competition_date": "15/06/2026", "values": {}},
    )
    assert resp.status_code == 400


def test_create_competition_rejects_unknown_fields(monkeypatch):
    client, _ = make_client(monkeypatch)

    resp = client.post(
        "/api/competitions",
        json={"competition_date": "15/06/2026", "values": {"not_a_real_field": "x"}},
    )
    assert resp.status_code == 400


def test_update_competition_overwrites_and_clears_omitted_fields(monkeypatch):
    client, db = make_client(monkeypatch)

    create_resp = client.post(
        "/api/competitions",
        json={
            "competition_date": "15/06/2026",
            "values": {"meet_name": "Club Meet", "federation": "CPU", "total_kg": "500"},
        },
    )
    competition_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/competitions/{competition_id}",
        json={
            "competition_date": "16/06/2026",
            "values": {"meet_name": "Club Meet (corrected)", "total_kg": "510"},
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["competition"]
    assert updated["meet_name"] == "Club Meet (corrected)"
    assert updated["total_kg"] == 510.0
    assert updated["federation"] is None

    saved = db.get_competition_by_id(competition_id)
    assert saved["competition_date"] == "2026-06-16"


def test_update_competition_returns_404_for_unknown_id(monkeypatch):
    client, _ = make_client(monkeypatch)

    resp = client.put(
        "/api/competitions/does-not-exist",
        json={"competition_date": "15/06/2026", "values": {"meet_name": "x"}},
    )
    assert resp.status_code == 404


def test_delete_competition_removes_it(monkeypatch):
    client, db = make_client(monkeypatch)

    create_resp = client.post(
        "/api/competitions",
        json={"competition_date": "15/06/2026", "values": {"meet_name": "Club Meet"}},
    )
    competition_id = create_resp.json()["id"]

    delete_resp = client.delete(f"/api/competitions/{competition_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["ok"] is True
    assert db.count_competitions() == 0


def test_delete_competition_returns_404_for_unknown_id(monkeypatch):
    client, _ = make_client(monkeypatch)
    resp = client.delete("/api/competitions/does-not-exist")
    assert resp.status_code == 404


def test_competitions_list_page_renders_with_and_without_data(monkeypatch):
    client, _ = make_client(monkeypatch)

    empty_resp = client.get("/competitions")
    assert empty_resp.status_code == 200
    assert "No competitions logged yet" in empty_resp.text

    client.post(
        "/api/competitions",
        json={
            "competition_date": "15/06/2026",
            "values": {"meet_name": "Ontario Provincials", "total_kg": "620"},
        },
    )
    filled_resp = client.get("/competitions")
    assert filled_resp.status_code == 200
    assert "Ontario Provincials" in filled_resp.text


def test_new_and_edit_competition_pages_render(monkeypatch):
    client, _ = make_client(monkeypatch)

    new_resp = client.get("/competitions/new")
    assert new_resp.status_code == 200
    assert "Log a competition" in new_resp.text

    create_resp = client.post(
        "/api/competitions",
        json={"competition_date": "15/06/2026", "values": {"meet_name": "Club Meet"}},
    )
    competition_id = create_resp.json()["id"]

    edit_resp = client.get(f"/competitions/{competition_id}/edit")
    assert edit_resp.status_code == 200
    assert "Club Meet" in edit_resp.text
    assert "15/06/2026" in edit_resp.text


def test_edit_competition_page_returns_404_for_unknown_id(monkeypatch):
    client, _ = make_client(monkeypatch)
    resp = client.get("/competitions/does-not-exist/edit")
    assert resp.status_code == 404


def test_dashboard_page_links_to_competitions(monkeypatch):
    client, _ = make_client(monkeypatch)
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'href="/competitions"' in resp.text


def test_sync_openpowerlifting_requires_a_configured_username(monkeypatch):
    client, _ = make_client(monkeypatch)
    resp = client.post("/api/competitions/sync-openpowerlifting")
    assert resp.status_code == 400


def test_sync_openpowerlifting_returns_502_on_fetch_error(monkeypatch):
    client, db = make_client(monkeypatch)
    db.update_settings(openpowerlifting_username="someone")

    from app.openpowerlifting import FetchError
    from app.routes import competitions

    def _raise(_username):
        raise FetchError("No openpowerlifting.org lifter found for username 'someone'.")

    monkeypatch.setattr(competitions, "fetch_competition_history", _raise)

    resp = client.post("/api/competitions/sync-openpowerlifting")
    assert resp.status_code == 502
    assert "someone" in resp.json()["detail"]


def test_sync_openpowerlifting_imports_new_meets_and_skips_duplicates(monkeypatch):
    client, db = make_client(monkeypatch)
    db.update_settings(openpowerlifting_username="someone")

    # Already logged manually - same date/name/total as one of the fetched
    # meets below, so it should be recognised as a duplicate and skipped.
    client.post(
        "/api/competitions",
        json={
            "competition_date": "14/03/2026",
            "values": {"meet_name": "Provincials", "total_kg": "620", "notes": "My own notes"},
        },
    )

    from app.routes import competitions

    fetched = [
        {
            "competition_date_iso": "2026-03-14",
            "meet_name": "Provincials",
            "federation": "CPU",
            "location": "Canada",
            "weight_class": "93",
            "placing": "1st",
            "bodyweight_kg": 91.4,
            "squat_kg": 220.0,
            "bench_kg": 150.0,
            "deadlift_kg": 250.0,
            "total_kg": 620.0,
            "notes": "Imported from OpenPowerlifting.",
        },
        {
            "competition_date_iso": "2025-11-01",
            "meet_name": "Fall Classic",
            "federation": "CPU",
            "location": "Canada",
            "weight_class": "93",
            "placing": "2nd",
            "bodyweight_kg": 92.0,
            "squat_kg": 200.0,
            "bench_kg": 130.0,
            "deadlift_kg": 220.0,
            "total_kg": 550.0,
            "notes": "Imported from OpenPowerlifting.",
        },
    ]
    monkeypatch.setattr(competitions, "fetch_competition_history", lambda username: fetched)

    resp = client.post("/api/competitions/sync-openpowerlifting")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["imported"] == 1
    assert body["skipped"] == 1
    assert body["imported_meets"] == ["Fall Classic"]

    assert db.count_competitions() == 2
    provincials = next(m for m in db.get_all_competitions_desc() if m["meet_name"] == "Provincials")
    # The manually entered row - and its notes - must be untouched by sync.
    assert provincials["notes"] == "My own notes"


def test_sync_openpowerlifting_collapses_same_meet_reported_in_two_divisions(monkeypatch):
    client, db = make_client(monkeypatch)
    db.update_settings(openpowerlifting_username="someone")

    from app.routes import competitions

    def _meet(division):
        return {
            "competition_date_iso": "2024-03-02",
            "meet_name": "Classic and Equipped National Championships",
            "federation": "USVIPF",
            "location": "US Virgin Islands",
            "weight_class": "76",
            "placing": "1st",
            "bodyweight_kg": 75.5,
            "squat_kg": 177.5,
            "bench_kg": 110.0,
            "deadlift_kg": 240.0,
            "total_kg": 527.5,
            "notes": f"Imported from OpenPowerlifting ({division}).",
        }

    fetched = [_meet("Masters 1"), _meet("Open")]
    monkeypatch.setattr(competitions, "fetch_competition_history", lambda username: fetched)

    resp = client.post("/api/competitions/sync-openpowerlifting")
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 1
    assert body["skipped"] == 1
    assert db.count_competitions() == 1
