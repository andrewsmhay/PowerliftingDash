# PowerliftingDash

A slim, self-hosted personal health and powerlifting dashboard, designed to
run full screen on a monitor (kiosk-style).

- **Backend:** Python (FastAPI + SQLite), packaged as a slimmed-down
  multi-arch Alpine Docker image (works on a Raspberry Pi or a regular
  amd64 machine).
- **Frontend:** server-rendered dark dashboard, vanilla JS + a locally
  vendored copy of Chart.js (no CDN calls at runtime, so it works offline
  once built).
- **Data source (primary):** the **New entry** page (`/entries/new`) built
  into the app itself. You type today's numbers into a web form; everything
  derivable (remaining, competition deltas, totals, "to date" figures) is
  calculated automatically and never typed in by hand.
- **Data source (optional, dormant by default):** a Google Sheet tab you
  maintain, with one row per dated entry. This only activates once you set
  a Google Sheet ID on the **Settings** page (`/settings`) - leave it blank
  and the app runs purely from manual entries.
- **Storage:** SQLite, one `entries` row per calendar date (primary key is
  a UUID, generated once per date and kept stable across re-saves/re-syncs).
  Each row is tagged with a `source` column (`manual` or `sheet_sync`) so
  you can always tell where a given date's numbers came from.

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

## Logging your daily entry (primary workflow)

1. Open `/entries/new` (there's a **+ New entry** link on the dashboard's
   top bar).
2. The date field defaults to today, in `dd/mm/yyyy` format - change it if
   you're backfilling an earlier date. Dates are parsed with an explicit
   dd/mm/yyyy format, never guessed, so they're never silently misread.
3. Every field is pre-filled with your most recent entry's values, grouped
   by area (Goals / Status), so you usually only need to change the one or
   two numbers that actually moved.
4. Hit **Save entry**. The row is saved with `source="manual"`, and all
   derived columns (remaining, competition deltas, totals, "to date"
   figures) are recalculated for every stored date - not just the one you
   just saved - so backfilling an earlier date always keeps history
   consistent.

## Setting up the optional Google Sheet sync

Sheet sync is off by default. If you'd also like to pull dated rows in
from a spreadsheet (e.g. to bulk-load history, or keep a spreadsheet copy
in sync), fill in the Sheet ID and tab name on `/settings`:

1. Add a tab with a header row (the tab name is blank/unset until you
   configure it in Settings - the tab must hold dated rows, one row
   per date, not the metric catalogue/definitions layout used by this
   project's own `schema/v1_items.csv`).
2. One column must be your date column (default header: `Date`,
   configurable in Settings), with values entered as **dd/mm/yyyy**
   (e.g. `12/08/2026`).
3. Add one column per metric you want tracked, using header text that
   matches an Item name from `schema/v1_items.csv` (spelling/case/spacing
   don't need to match exactly - "squat 1rm current" and
   "Squat 1RM (current)" both map to the same column).
4. Add one row per dated entry. Columns you don't fill in are simply
   stored as empty for that date.

Rows pulled in this way are tagged `source="sheet_sync"`. Manual entries
for the same date always take precedence going forward if you later edit
that date through `/entries/new` (upsert is keyed on `entry_date`, so
whichever save happens most recently wins).

> **Not yet validated against a live sheet.** The header-matching logic
> (`app/sync.py::_normalise_header`) is unit-tested against a handful of
> synthetic header strings, not against a live sheet, because the agent
> that built this never had read access to the linked Google Sheet (a 403
> was returned even after the Google account was connected) - the schema
> was generated from an uploaded export instead. On your first real sync,
> check the Settings page's sync status message for any columns it
> couldn't map. If a header doesn't match, either rename it to match an
> Item name in `schema/v1_items.csv` or re-run `schema/generate_schema.py`
> against your actual headers.

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

Then open `http://<host>:8080/` full screen on the monitor. Log your
first entry at `http://<host>:8080/entries/new` - no other configuration
is required. Visit `http://<host>:8080/settings` only if you also want to
wire up the optional Google Sheet sync.

### Multi-architecture builds

The `Dockerfile` builds cleanly for both `linux/amd64` and `linux/arm64`.
To build and push a multi-arch manifest to a registry:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t <your-registry>/powerliftingdash:latest --push .
```

## Syncing (only relevant if Sheet sync is configured)

- Sync is dormant until a Google Sheet ID is set in Settings. With no
  Sheet ID configured, the app runs entirely on manual entries and this
  section doesn't apply.
- **Automatic:** once a Sheet ID is set, a background thread re-pulls the
  sheet on the interval configured in Settings (default every 10
  minutes), and picks up interval changes on its next cycle without a
  restart.
- **Manual:** hit "Sync now" on the Settings page, or `POST /api/sync`.
- Sync is idempotent: re-syncing the same date updates that date's row in
  place rather than creating a duplicate (matched on `entry_date`, unique
  in the schema), and tags the row `source="sheet_sync"`.
- After every sync, `derive.recompute_all()` re-derives every stored
  date's calculated columns, so a sheet backfill of earlier history
  rebaselines "to date" figures correctly.

## Project layout

```
app/
  main.py            FastAPI app, startup/shutdown hooks
  config.py          Environment-driven configuration
  db.py              SQLite access, upsert logic
  numeric.py         Shared numeric string coercion (manual form + sheet sync)
  derive.py          Computes all "read from new date entry" columns
  date_utils.py      Explicit dd/mm/yyyy + Sheets-serial date parsing
  auth_provider.py   Pluggable Google credential loading
  sheets_client.py   Google Sheets API read
  sync.py            Header-to-column mapping, sheet -> SQLite sync (dormant by default)
  scheduler.py       Background thread; only calls sync.py if a Sheet ID is set
  metrics.py         Raw entry row -> dashboard card/chart payload
  routes/            Page routes (dashboard, entries/new, settings) and JSON API
  templates/         Jinja2 templates
  static/            CSS, JS, vendored Chart.js
  schema.sql, schema_manifest.json   Generated - do not hand-edit
schema/
  v1_items.csv        Source-of-truth data dictionary (v1 tab)
  generate_schema.py   Regenerates the schema from the CSV above
tests/                 pytest unit tests (date parsing, sync mapping, DB, derive, entries route)
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

- **Manual entry is the primary and intended workflow.** Both the v1 and
  v2 tabs of the source spreadsheet turned out to be schema-definition
  catalogues (Area / Item / Description / Measurement-Type / flags), not
  dated data-entry tables, so there was never a live sheet of daily rows
  to sync against. The `/entries/new` web form is the canonical place
  numbers get logged; Sheet sync exists as an optional secondary path for
  anyone who later wants to feed rows in from a real dated-rows
  spreadsheet.
- The v1 tab's "Configured in Settings as Manual Input?" column drives
  which columns appear on the `/entries/new` form (`configured_in_settings`
  in `schema_manifest.json`). The "Read from New Date Entry?" column
  drives which columns `derive.py` computes automatically rather than
  accepting as form input - both live on the same `entries` table.
- **BMI and BMR are manual smart-scale readings**, not formulas. The
  schema has no height, age or sex fields, so BMI/BMR current and target
  are entered directly (from a smart scale) rather than derived from
  other columns.
- **Weight Change Since Comp** is derived as
  `body_weight_mass - earliest recorded body_weight_mass`, since there is
  no dedicated competition-weigh-in field in the 44-item schema. Every
  other `_to_date` column follows the same "current minus earliest
  non-null historical value" convention.
- `derive.recompute_all()` reloads every entry oldest-first and
  recomputes every derived column on every row each time it runs (after
  every manual save and after every sheet sync). This is what keeps
  "to date" baselines correct if you ever backfill an earlier date after
  later ones already exist.
- `app_settings` (Google Sheet ID, tab name, credentials, sync interval)
  is a separate table from `entries` and is not part of the v1 schema -
  it's the app's own configuration, editable from `/settings`, and the
  Sheet ID field is left blank by default (sync stays dormant).
- A future v2 tab (MyFitnessPal macros, event countdown) is not yet
  wired into the schema; re-run `schema/generate_schema.py` against an
  updated `v1_items.csv` (or a new source) to extend it.
- **Upgrading an existing database:** the `entries_tab_name` default
  changed from `'v1'` to `''` in this version. `INSERT OR IGNORE` only
  seeds that value on a brand-new `app_settings` table, so an existing
  database created before this change will still have `'v1'` stored
  (the wrong value - v1 is a catalogue tab, not a dated-rows tab) and
  Sheet sync will fail with a clear error until you either clear it from
  `/settings` or run:
  ```sql
  UPDATE app_settings SET entries_tab_name = '' WHERE entries_tab_name = 'v1';
  ```
  This has no effect on manual entries, which don't touch this setting.
