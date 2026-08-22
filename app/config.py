"""Runtime configuration. Values come from environment variables, so the
app is configured the same way whether it runs in Docker (`docker run -e`
/ compose `environment:`) or natively on a Linux host (systemd
`Environment=` / `EnvironmentFile=` - see deploy/systemd/). Anything not
set here falls back to defaults stored in the app_settings DB row, which is
editable from the web UI's Settings page.
"""
import os
from pathlib import Path

# All persistent state (SQLite DB) lives here. The Docker image defaults
# this to /data (mounted as a volume so it survives container restarts);
# native/systemd deployments should set PLD_DATA_DIR to a proper FHS path
# such as /var/lib/powerliftingdash - see deploy/systemd/.
DATA_DIR = Path(os.environ.get("PLD_DATA_DIR", "/data"))
DB_PATH = DATA_DIR / os.environ.get("PLD_DB_FILENAME", "powerlifting_dash.sqlite3")

APP_DIR = Path(__file__).resolve().parent
SCHEMA_SQL_PATH = APP_DIR / "schema.sql"
SCHEMA_MANIFEST_PATH = APP_DIR / "schema_manifest.json"

HOST = os.environ.get("PLD_HOST", "0.0.0.0")
PORT = int(os.environ.get("PLD_PORT", "8080"))

# How often the dashboard page itself polls the API for fresh data (seconds).
DASHBOARD_POLL_SECONDS = int(os.environ.get("PLD_DASHBOARD_POLL_SECONDS", "60"))

# Google sends OAuth callbacks to this public address. Local development can
# use the default HTTP address, while public deployments should configure HTTPS.
PUBLIC_BASE_URL = os.environ.get("PLD_PUBLIC_BASE_URL", f"http://localhost:{PORT}").rstrip("/")

# Health API work remains request-triggered. This only limits how often a
# dashboard request may refresh data that has already been connected.
GOOGLE_HEALTH_SYNC_INTERVAL_SECONDS = int(
    os.environ.get("PLD_GOOGLE_HEALTH_SYNC_INTERVAL_SECONDS", "3600")
)

# Trailing window for current lift trends and target projections.
RATE_OF_CHANGE_WINDOW_DAYS = int(os.environ.get("PLD_RATE_OF_CHANGE_WINDOW_DAYS", "90"))
