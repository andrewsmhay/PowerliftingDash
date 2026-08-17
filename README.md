# PowerliftingDash

A slim, self-hosted personal health and powerlifting dashboard, designed to
run full screen on a monitor (kiosk-style).

- **Backend:** Python (FastAPI + SQLite), packaged as a slimmed-down
  multi-arch Alpine Docker image (works on a Raspberry Pi or a regular
  amd64 machine).
- **Frontend:** server-rendered dark dashboard, vanilla JS + a locally
  vendored copy of Chart.js (no CDN calls at runtime, so it works offline
  once built).
- **Data entry:** the **New entry** page (`/entries/new`) built into the
  app itself is the only way numbers get in - there is no external sync.
  You type today's numbers into a web form; everything derivable
  (remaining, competition deltas, totals, "to date" figures) is calculated
  automatically and never typed in by hand. Past entries can be corrected
  or removed on the **Manage entries** page (`/entries`).
- **Storage:** SQLite, one `entries` row per calendar date (primary key is
  a UUID, generated once per date and kept stable across edits).
- **Targets and competition numbers (hardcoded goals):** your 1RM targets,
  1RM competition numbers, and body-composition/BMI/BMR targets are set
  once on the **Targets** page (`/targets`), not typed in with every dated
  entry. They live as scalar columns on a single `app_settings` row rather
  than on `entries` - see "Targets vs daily entries" below.

## Screenshots

All screenshots below are running against eight weeks of made-up demo data
(a fictional powerlifter cutting body fat while building toward a target
total), seeded straight into a scratch database purely to illustrate the
layout - none of it is real training or health data.

**Dashboard** - lift progress bars, body composition, and trend charts:

![Dashboard with demo data](docs/screenshots/dashboard.png)

**New entry** - the primary way numbers get into the app:

![New entry form](docs/screenshots/entry_form.png)

**Manage entries** - review, edit or delete a past dated entry:

![Manage entries page](docs/screenshots/entries_list.png)

**Edit entry** - correct a mistake or backfill a missed value on an existing
dated entry:

![Edit entry page](docs/screenshots/entry_edit.png)

**Targets** - 1RM targets, competition numbers and body-composition goals,
set once rather than typed in with every dated entry:

![Targets page](docs/screenshots/targets.png)

**Settings** - timezone, entry count, and the danger zone:

![Settings page](docs/screenshots/settings.png)

## How the schema was built

The SQLite schema was generated from the **v1** tab of a Google Sheet data
dictionary (Area / Item / Description / Measurement-Type / "Configured in
Settings as Manual Input?" / "Read from New Date Entry?") used only as a
one-time source for column definitions - the app itself has no live
connection to that or any other spreadsheet. Every Item on that tab became
exactly one column, split across two tables by what kind of value it is:

- **`entries`** (32 columns) - anything that changes with a dated
  reading: the 9 daily manual inputs (squat/bench/deadlift 1RM current,
  body weight/muscle/fat mass, body fat %, BMI, BMR) plus the 23 columns
  `derive.py` computes from them (remaining, competition deltas, totals,
  "to date" figures).
- **`app_settings`** (12 columns) - the target and competition items,
  which describe a goal rather than a dated reading: squat/bench/deadlift
  1RM target and competition, and the target for body weight/muscle/fat
  mass, body fat %, BMI and BMR. These are set once on `/targets`, stored
  as a single scalar row, and read by `derive.py` as a snapshot applied
  uniformly across every historical entry - see "Targets vs daily
  entries" below.

`schema/generate_schema.py::is_config_item()` does this split by checking
for a strict `(target)` or `(competition)` suffix on the Item name. It
deliberately excludes `(competition delta)` and "Total Weight Lifted (in
competition)", which are derived status figures, not goals, and stay on
`entries`.

- `schema/v1_items.csv` - a checked-in copy of the v1 tab, kept as the
  source of truth for column generation.
- `schema/generate_schema.py` - regenerates `app/schema.sql` and
  `app/schema_manifest.json` from that CSV. Re-run it if the CSV changes:
  ```bash
  python3 schema/generate_schema.py
  ```

## Logging your daily entry (primary workflow)

1. Open `/entries/new` (there's a **+ New entry** link on the dashboard's
   top bar).
2. The date field defaults to today, in `dd/mm/yyyy` format - change it if
   you're backfilling an earlier date. Dates are parsed with an explicit
   dd/mm/yyyy format, never guessed, so they're never silently misread.
3. Every field is pre-filled with your most recent entry's values, grouped
   by area (Goals / Status), so you usually only need to change the one or
   two numbers that actually moved.
4. Fill in the Lifts section, the Body composition section, or both - a
   section left blank is simply not recorded for that date rather than
   rejected, so a gym day and a weigh-in day don't have to be the same
   day. At least one value somewhere on the form is required.
5. Hit **Save entry**. All derived columns (remaining, competition deltas,
   totals, "to date" figures) are recalculated for every stored date - not
   just the one you just saved - so backfilling an earlier date always
   keeps history consistent.

Target and competition fields do not appear on this form, and posting
one to `/api/entries` is rejected with a `400` pointing you to `/targets`
instead - see the next section.

## Managing past entries

Open `/entries` (there's an **Entries** link on the dashboard's top bar,
and a link from `/settings`) to see every stored date, newest first.

- **Edit** an entry to open it in the same form used for new entries, with
  its existing values pre-filled. Saving an edit replaces that entry's
  full set of values - clearing a field and saving removes that value from
  the entry rather than leaving the old number in place. At least one
  value must remain, and changing the date to one that already has an
  entry is rejected with a `400` telling you to edit that entry instead.
- **Delete** a single entry from its edit page.
- **Delete every entry** from the danger zone on `/settings` - this
  requires ticking an "I understand" confirmation checkbox before the
  button is enabled, and cannot be undone. Targets and competition
  numbers are untouched, since they live on a separate `app_settings` row.

## Setting your targets and competition numbers

Your 1RM targets, 1RM competition numbers, and body-composition/BMI/BMR
targets are goals, not daily readings, so they live on their own page
rather than on `/entries/new`:

1. Open `/targets` (there's a **Targets** link on the dashboard's top bar
   and on `/settings`).
2. Fields are grouped by area and pre-filled with whatever you last
   saved. Leave a field blank to leave it unset.
3. Hit **Save targets**. This writes to a single `app_settings` row (via
   `db.update_config()`), then calls `derive.recompute_all()`, so every
   stored entry's remaining/delta figures update immediately to reflect
   the new goal - not just entries you save from now on.

Because they're config rather than per-date data, target and competition
values are intentionally excluded from `/entries/new`: posting one there
returns a `400` telling you to use `/targets` instead.

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
is required.

### Multi-architecture builds

The `Dockerfile` builds cleanly for both `linux/amd64` and `linux/arm64`.
To build and push a multi-arch manifest to a registry:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t <your-registry>/powerliftingdash:latest --push .
```

## Project layout

```
app/
  main.py            FastAPI app, startup/shutdown hooks
  config.py          Environment-driven configuration
  db.py              SQLite access, upsert/edit/delete logic, app_settings config
  numeric.py         Shared numeric string coercion for the manual entry form
  derive.py          Computes all "read from new date entry" columns from a config snapshot
  date_utils.py      Explicit dd/mm/yyyy date parsing
  metrics.py         Raw entry row + config -> dashboard card/chart payload
  routes/            Page routes (dashboard, entries, targets, settings) and JSON API
  templates/         Jinja2 templates (dashboard, entry_form, entries_list, targets, settings)
  static/            CSS, JS, vendored Chart.js
  schema.sql, schema_manifest.json   Generated - do not hand-edit
schema/
  v1_items.csv        Source-of-truth data dictionary
  generate_schema.py   Regenerates the schema from the CSV above; splits entries vs app_settings
tests/                 pytest unit tests (date parsing, DB, derive, entries route, targets route)
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

- **Manual entry is the only workflow.** The `/entries/new` web form is
  the sole place numbers get logged; there is no external data source or
  background job of any kind.
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
  every manual save, edit or delete). This is what keeps "to date"
  baselines correct if you ever backfill, edit or remove an earlier date
  after later ones already exist.
- A future v2 metric set (MyFitnessPal macros, event countdown) is not yet
  wired into the schema; extend `schema/v1_items.csv` and re-run
  `schema/generate_schema.py` to add it.
- **Upgrading an existing database for the `/targets` split:** older
  databases stored target/competition values as columns on `entries`.
  `db.init_db()` runs two migration steps automatically on startup, so
  nothing manual is required on your Pi:
  1. `_ensure_config_columns()` - idempotent `ALTER TABLE app_settings ADD
     COLUMN` for each of the 12 target/competition columns, safe to run
     on every startup (it checks the existing column list first).
  2. `_backfill_config_from_latest_entry()` - a one-time seed: if
     `app_settings`'s target/competition columns are still `NULL` and
     your old `entries` table still has legacy target/competition
     columns, it copies the values from your most recent entry into
     `app_settings` so your existing goals aren't lost. It's a no-op on
     fresh installs and on any database that's already migrated.

  After upgrading, open `/targets` once to confirm your goals carried
  over correctly, and adjust anything that didn't.
