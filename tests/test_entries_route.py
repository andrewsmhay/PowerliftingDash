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

    from app import derive, scheduler
    from app.routes import entries, pages, targets

    importlib.reload(derive)
    importlib.reload(entries)
    importlib.reload(pages)
    importlib.reload(targets)

    import app.main as main_module

    importlib.reload(main_module)

    from fastapi.testclient import TestClient

    monkeypatch.setattr(scheduler, "start", lambda: None)
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


def test_new_entry_page_renders(monkeypatch):
    client = make_client(monkeypatch)

    resp = client.get("/entries/new")
    assert resp.status_code == 200
    assert "New entry" in resp.text
    assert "Squat 1RM (current)" in resp.text
