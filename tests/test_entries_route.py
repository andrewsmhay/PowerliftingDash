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
    from app.routes import entries, pages, targets

    importlib.reload(derive)
    importlib.reload(entries)
    importlib.reload(pages)
    importlib.reload(targets)

    import app.main as main_module

    importlib.reload(main_module)

    from fastapi.testclient import TestClient

    db.init_db()
    return TestClient(main_module.app)


def test_save_entry_computes_derived_fields(monkeypatch):
    client = make_client(monkeypatch)

    targets_resp = client.post(
        "/api/targets",
        json={"values": {"squat_1rm_target": "170", "squat_1rm_competition": "150"}},
    )
    assert targets_resp.status_code == 200

    resp = client.post(
        "/api/entries",
        json={
            "entry_date": "05/08/2026",
            "values": {
                "squat_1rm_current": "161",
                "body_weight_mass": "88",
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["entry_date_ddmmyyyy"] == "05/08/2026"
    assert body["entry"]["squat_1rm_remaining"] == 9.0
    assert body["entry"]["squat_1rm_competition_delta"] == 11.0
    assert body["entry"]["body_weight_mass_to_date"] == 0.0


def test_save_entry_rejects_unknown_field(monkeypatch):
    client = make_client(monkeypatch)

    resp = client.post(
        "/api/entries",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_remaining": "9"}},
    )
    assert resp.status_code == 400


def test_save_entry_rejects_target_and_competition_fields(monkeypatch):
    """Target/competition are configured on /targets, not per date - the
    entry endpoint must reject them with a message pointing there, rather
    than silently accepting or lumping them in with a generic unknown-field
    error."""
    client = make_client(monkeypatch)

    resp = client.post(
        "/api/entries",
        json={
            "entry_date": "05/08/2026",
            "values": {"squat_1rm_current": "161", "squat_1rm_target": "170"},
        },
    )
    assert resp.status_code == 400
    assert "/targets" in resp.json()["detail"]


def test_save_entry_rejects_bad_date(monkeypatch):
    client = make_client(monkeypatch)

    resp = client.post(
        "/api/entries",
        json={"entry_date": "2026-08-05", "values": {"squat_1rm_current": "161"}},
    )
    assert resp.status_code == 400


def test_save_entry_rejects_empty_values(monkeypatch):
    """Neither section filled in at all - nothing to save."""
    client = make_client(monkeypatch)

    resp = client.post(
        "/api/entries",
        json={"entry_date": "05/08/2026", "values": {}},
    )
    assert resp.status_code == 400
    assert "at least one" in resp.json()["detail"].lower()


def test_save_entry_accepts_lifts_only(monkeypatch):
    client = make_client(monkeypatch)

    resp = client.post(
        "/api/entries",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "161"}},
    )
    assert resp.status_code == 200


def test_save_entry_accepts_body_composition_only(monkeypatch):
    client = make_client(monkeypatch)

    resp = client.post(
        "/api/entries",
        json={"entry_date": "05/08/2026", "values": {"body_weight_mass": "88"}},
    )
    assert resp.status_code == 200


def test_new_entry_page_renders(monkeypatch):
    client = make_client(monkeypatch)

    resp = client.get("/entries/new")
    assert resp.status_code == 200
    assert "New entry" in resp.text
    assert "Squat 1RM (current)" in resp.text


def test_entries_list_page_renders(monkeypatch):
    client = make_client(monkeypatch)

    client.post(
        "/api/entries",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "161"}},
    )

    resp = client.get("/entries")
    assert resp.status_code == 200
    assert "05/08/2026" in resp.text


def test_edit_entry_page_renders(monkeypatch):
    client = make_client(monkeypatch)

    save_resp = client.post(
        "/api/entries",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "161"}},
    )
    entry_id = save_resp.json()["id"]

    resp = client.get(f"/entries/{entry_id}/edit")
    assert resp.status_code == 200
    assert "05/08/2026" in resp.text


def test_edit_entry_page_missing_returns_404(monkeypatch):
    client = make_client(monkeypatch)

    resp = client.get("/entries/does-not-exist/edit")
    assert resp.status_code == 404


def test_update_entry_changes_values(monkeypatch):
    client = make_client(monkeypatch)

    save_resp = client.post(
        "/api/entries",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "161"}},
    )
    entry_id = save_resp.json()["id"]

    resp = client.put(
        f"/api/entries/{entry_id}",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "165"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["entry"]["squat_1rm_current"] == 165.0


def test_update_entry_can_clear_a_field(monkeypatch):
    """Edit is full-state, not a partial patch - omitting a field on save
    should clear it, unlike the create endpoint which leaves it untouched."""
    client = make_client(monkeypatch)

    save_resp = client.post(
        "/api/entries",
        json={
            "entry_date": "05/08/2026",
            "values": {"squat_1rm_current": "161", "body_weight_mass": "88"},
        },
    )
    entry_id = save_resp.json()["id"]

    resp = client.put(
        f"/api/entries/{entry_id}",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "165"}},
    )
    assert resp.status_code == 200
    assert resp.json()["entry"]["body_weight_mass"] is None


def test_update_entry_rejects_when_no_values_remain(monkeypatch):
    client = make_client(monkeypatch)

    save_resp = client.post(
        "/api/entries",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "161"}},
    )
    entry_id = save_resp.json()["id"]

    resp = client.put(
        f"/api/entries/{entry_id}",
        json={"entry_date": "05/08/2026", "values": {}},
    )
    assert resp.status_code == 400


def test_update_entry_missing_returns_404(monkeypatch):
    client = make_client(monkeypatch)

    resp = client.put(
        "/api/entries/does-not-exist",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "165"}},
    )
    assert resp.status_code == 404


def test_update_entry_rejects_date_collision(monkeypatch):
    client = make_client(monkeypatch)

    client.post(
        "/api/entries",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "161"}},
    )
    second = client.post(
        "/api/entries",
        json={"entry_date": "06/08/2026", "values": {"squat_1rm_current": "162"}},
    )
    second_id = second.json()["id"]

    resp = client.put(
        f"/api/entries/{second_id}",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "162"}},
    )
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"]


def test_delete_single_entry(monkeypatch):
    client = make_client(monkeypatch)

    save_resp = client.post(
        "/api/entries",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "161"}},
    )
    entry_id = save_resp.json()["id"]

    resp = client.delete(f"/api/entries/{entry_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp = client.get(f"/entries/{entry_id}/edit")
    assert resp.status_code == 404


def test_delete_single_entry_missing_returns_404(monkeypatch):
    client = make_client(monkeypatch)

    resp = client.delete("/api/entries/does-not-exist")
    assert resp.status_code == 404


def test_delete_all_requires_confirmation(monkeypatch):
    client = make_client(monkeypatch)

    client.post(
        "/api/entries",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "161"}},
    )

    resp = client.post("/api/entries/delete-all", json={})
    assert resp.status_code == 400

    resp = client.get("/entries")
    assert "05/08/2026" in resp.text


def test_delete_all_removes_every_entry(monkeypatch):
    client = make_client(monkeypatch)

    client.post(
        "/api/entries",
        json={"entry_date": "05/08/2026", "values": {"squat_1rm_current": "161"}},
    )
    client.post(
        "/api/entries",
        json={"entry_date": "06/08/2026", "values": {"squat_1rm_current": "162"}},
    )

    resp = client.post("/api/entries/delete-all", json={"confirm": True})
    assert resp.status_code == 200
    assert resp.json()["removed"] == 2

    resp = client.get("/entries")
    assert "05/08/2026" not in resp.text
    assert "06/08/2026" not in resp.text
