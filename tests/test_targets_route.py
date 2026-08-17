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


def test_targets_page_renders(monkeypatch):
    client = make_client(monkeypatch)

    resp = client.get("/targets")
    assert resp.status_code == 200
    assert "Targets" in resp.text
    assert "targets-form" in resp.text


def test_save_targets_updates_config_and_recomputes(monkeypatch):
    client = make_client(monkeypatch)
    from app import db

    db.upsert_entry("2026-08-05", None, {"squat_1rm_current": 150.0}, source="manual")

    resp = client.post(
        "/api/targets",
        json={"values": {"squat_1rm_target": "170", "squat_1rm_competition": "140"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["config"]["squat_1rm_target"] == 170.0
    assert body["config"]["squat_1rm_competition"] == 140.0

    entry = db.get_entry_by_date("2026-08-05")
    assert entry["squat_1rm_remaining"] == 20.0
    assert entry["squat_1rm_competition_delta"] == 10.0


def test_save_targets_rejects_unknown_field(monkeypatch):
    client = make_client(monkeypatch)

    resp = client.post(
        "/api/targets",
        json={"values": {"not_a_real_config_field": "1"}},
    )
    assert resp.status_code == 400


def test_save_targets_rejects_daily_entry_field(monkeypatch):
    """The config endpoint must only accept config-scoped columns - a daily
    reading like squat_1rm_current belongs on /entries/new, not here."""
    client = make_client(monkeypatch)

    resp = client.post(
        "/api/targets",
        json={"values": {"squat_1rm_current": "161"}},
    )
    assert resp.status_code == 400
