"""Runtime configuration. Values come from environment variables so the
container can be configured at `docker run` / compose time; anything not
set here falls back to defaults stored in the app_settings DB row, which is
editable from the web UI's Settings page.
"""
import os
from pathlib import Path

# All persistent state (SQLite DB, cached credentials) lives under /data,
# which should be mounted as a volume so it survives container restarts.
DATA_DIR = Path(os.environ.get("PLD_DATA_DIR", "/data"))
DB_PATH = DATA_DIR / os.environ.get("PLD_DB_FILENAME", "powerlifting_dash.sqlite3")

APP_DIR = Path(__file__).resolve().parent
SCHEMA_SQL_PATH = APP_DIR / "schema.sql"
SCHEMA_MANIFEST_PATH = APP_DIR / "schema_manifest.json"

# Fallback credential sources, checked in this order by auth_provider.py if
# no service account JSON has been pasted into Settings:
#   1. PLD_GOOGLE_SERVICE_ACCOUNT_JSON  - the raw JSON key as a string
#   2. PLD_GOOGLE_SERVICE_ACCOUNT_FILE  - path to a mounted JSON key file
#   3. /data/service_account.json       - a file dropped into the data volume
ENV_SERVICE_ACCOUNT_JSON = os.environ.get("PLD_GOOGLE_SERVICE_ACCOUNT_JSON")
ENV_SERVICE_ACCOUNT_FILE = os.environ.get("PLD_GOOGLE_SERVICE_ACCOUNT_FILE")
DEFAULT_SERVICE_ACCOUNT_FILE = DATA_DIR / "service_account.json"

HOST = os.environ.get("PLD_HOST", "0.0.0.0")
PORT = int(os.environ.get("PLD_PORT", "8080"))

# How often the dashboard page itself polls the API for fresh data (seconds).
# Independent of the background Google Sheets sync interval, which is
# configured in Settings and stored in the DB.
DASHBOARD_POLL_SECONDS = int(os.environ.get("PLD_DASHBOARD_POLL_SECONDS", "60"))

DEFAULT_SYNC_INTERVAL_MINUTES = int(os.environ.get("PLD_DEFAULT_SYNC_INTERVAL_MINUTES", "10"))
