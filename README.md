# PowerliftingDash

A slim, self-hosted personal health and powerlifting dashboard, designed to
run full screen on a monitor (kiosk-style) and stay in sync with a Google
Sheet you update by hand.

- **Backend:** Python (FastAPI + SQLite), packaged as a slimmed-down
  multi-arch Alpine Docker image (works on a Raspberry Pi or a regular
  amd64 machine).
- **Frontend:** server-rendered dark dashboard, vanilla JS + a locally
  vendored copy of Chart.js (no CDN calls at runtime, so it works offline
  once built).
- **Data source:** a Google Sheet tab you maintain, with one row per dated
  entry. The Google Sheet ID, tab name, sync credentials and interval are
  all configured from the app's own **Settings** page (`/settings`) -
  nothing is hardcoded.
- **Storage:** SQLite, one `entries` row per calendar date (primary key is
  a UUID, generated once per date and kept stable across re-syncs).

## How the schema was built

The SQLite schema is generated from the **v1** tab of the source Google
Sheet's data dictionary (Area / Item / Description / Measurement-Type /
"Configured in Settings as Manual Input?" / "Read from New Date Entry?").
Every Item on that tab becomes one column on the `entries` table, so a
single dated row is a complete snapshot of your goals, targets, and status
metrics for that day (squat/bench/deadlift 1RM current/target/competition/
remaining/delta, total weight lifted, body weight/muscle/fat mass, body
fat %, BMI, BMR, all with target/remaining/"to date" variants).

- `schema/v1_items.csv` - a checked-in copy of the v1 tab, kept as the
  source of truth for column generation.
- `schema/generate_schema.py` - regenerates `app/schema.sql` and
  `app/schema_manifest.json` from that CSV. Re-run it if the v1 tab
  changes:
  ```bash
  python3 schema/generate_schema.py
  ```
- The sync job (`app/sync.py`) matches your sheet's header row against the
  generated column names (case/spacing/punctuation-insensitive), so your
  sheet's header text can read exactly like the Item names in the v1 tab
  ("Squat 1RM (current)", "BMI (target)", etc.) without any manual mapping.

## Setting up your Google Sheet

1. Add a tab (default name expected: `v1`, configurable in Settings) with
   a header row.
2. One column must be your date column (default header: `Date`,
   configurable in Settings), with values entered as **dd/mm/yyyy**
   (e.g. `12/08/2026`). This is parsed with an explicit dd/mm/yyyy format,
   never guessed, so dates are never silently misread.
3. Add one column per metric you want tracked, using header text that
   matches an Item name from `schema/v1_items.csv` (spelling/case/spacing
   don't need to match exactly - "squat 1rm current" and
   "Squat 1RM (current)" both map to the same column).
4. Add one row per dated entry. Columns you don't fill in are simply
   stored as empty for that date.

## Google authentication

The app talks to the Sheets API as a **service account** (the only sane
option for something running unattended on a monitor, with no browser).
Credential resolution order (see `app/auth_provider.py`):

1. A service account JSON key pasted into the Settings page.
2. `PLD_GOOGLE_SERVICE_ACCOUNT_JSON` environment variable (raw JSON).
3. `PLD_GOOGLE_SERVICE_ACCOUNT_FILE` environment variable (path to a
   mounted key file).
4. A key file dropped straight into the data volume at
   `/data/service_account.json`.

Once configured, the Settings page shows the service account's email
address - share your Google Sheet with that address (Viewer access is
enough) and you're set. The credential mechanism is intentionally
pluggable behind `auth_provider.load_credentials()`, so it's
straightforward to swap in a different approach later.

## Running it

```bash
# Build and run with Docker Compose (recommended)
docker compose up --build -d
```

Or with plain Docker, targeting a Raspberry Pi (arm64):

```bash
docker buildx build --platform linux/arm64 -t powerliftingdash:latest --load .
docker run -d --name powerliftingdash \
  -p 8080:8080 \
  -v powerliftingdash-data:/data \
  -e TZ=America/Toronto \
  powerliftingdash:latest
```

Then open `http://<host>:8080/` full screen on the monitor, and
`http://<host>:8080/settings` once to configure the Sheet ID, tab name,
and credentials.

### Multi-architecture builds

The `Dockerfile` builds cleanly for both `linux/amd64` and `linux/arm64`.
To build and push a multi-arch manifest to a registry:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t <your-registry>/powerliftingdash:latest --push .
```

## Syncing

- **Automatic:** a background thread re-pulls the sheet on the interval
  configured in Settings (default every 10 minutes), and picks up
  interval changes on its next cycle without a restart.
- **Manual:** hit "Sync now" on the Settings page, or `POST /api/sync`.
- Sync is idempotent: re-syncing the same date updates that date's row in
  place rather than creating a duplicate (matched on `entry_date`, unique
  in the schema).

## Project layout

```
app/
  main.py            FastAPI app, startup/shutdown hooks
  config.py          Environment-driven configuration
  db.py              SQLite access, upsert logic
  date_utils.py      Explicit dd/mm/yyyy + Sheets-serial date parsing
  auth_provider.py   Pluggable Google credential loading
  sheets_client.py   Google Sheets API read
  sync.py            Header-to-column mapping, sheet -> SQLite sync
  scheduler.py       Background sync loop
  metrics.py         Raw entry row -> dashboard card/chart payload
  routes/            Page routes (dashboard, settings) and JSON API
  templates/         Jinja2 templates
  static/            CSS, JS, vendored Chart.js
  schema.sql, schema_manifest.json   Generated - do not hand-edit
schema/
  v1_items.csv        Source-of-truth data dictionary (v1 tab)
  generate_schema.py   Regenerates the schema from the CSV above
tests/                 pytest unit tests (date parsing, sync mapping, DB)
Dockerfile             Multi-stage, slim Alpine, multi-arch
docker-compose.yml
```

## Tests

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
python3 -m pytest tests/ -v
```

## Notes and assumptions

- The v1 tab's "Configured in Settings as Manual Input?" / "Read from New
  Date Entry?" flags are carried through into `schema_manifest.json` as
  metadata for future UI work (e.g. grouping fields), but both flag types
  live on the same `entries` table today - whatever is in your sheet for
  a given date is what gets stored, whether the cell holds a typed number
  or a sheet formula result.
- `app_settings` (Google Sheet ID, tab name, credentials, sync interval)
  is a separate table from `entries` and is not part of the v1 schema -
  it's the app's own configuration, editable from `/settings`.
- A future v2 tab (MyFitnessPal macros, event countdown) is not yet
  wired into the schema; re-run `schema/generate_schema.py` against an
  updated `v1_items.csv` (or a new source) to extend it.
