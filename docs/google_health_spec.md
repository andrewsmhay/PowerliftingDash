# Google Health integration — implementation spec

## Context (read first)
This is an existing FastAPI + SQLite project at `/home/user/workspace/PowerliftingDash`
(git repo `andrewsmhay/PowerliftingDash`, private, branch `main`). Read these files
before writing any code, to follow existing conventions exactly:
- `app/db.py` — SQLite access layer, `_ensure_settings_columns()` migration pattern,
  `upsert_entry()`, `update_settings()`, `update_computed_columns()`
- `app/config.py` — env-driven config
- `app/openpowerlifting.py` — the existing "reach outside the app" integration:
  on-demand HTTP fetch, triggered only by explicit user action (save/refresh button),
  NO background thread, NO scheduled polling. `app/routes/api.py` shows how it's wired
  (`_refresh_opl_bests`, `/api/openpowerlifting/refresh`).
- `app/schema.sql` / `app/schema_manifest.json` — the manifest-driven entries table
  (Goals/Status target-tracking triples). Google Health data does NOT go through the
  manifest system — it's a separate concern (see "Storage design" below).
- `app/routes/pages.py`, `app/templates/settings.html`, `app/static/settings.js` —
  existing Settings page structure to extend.
- `README.md` — update with a new section documenting this feature, same style as the
  existing OpenPowerlifting section.

## House style (non-negotiable)
- UK English throughout (colour, behaviour, licence, organise, etc.) in all new code
  comments, docstrings, README text, and UI copy.
- NEVER use em-dashes (`—`) or `--` as a dash in any text. Use commas, parentheses, or
  full stops instead.
- Follow the existing docstring/comment style (explain *why*, not just *what*, as seen
  in `openpowerlifting.py` and `db.py`).
- Run the existing test suite (`pytest`) and `pyflakes app/` before declaring done; all
  72 existing tests must still pass, and add new tests for the new modules following
  the existing `tests/test_*.py` patterns (e.g. `tests/test_openpowerlifting.py`,
  `tests/test_settings_route.py`).

## What to build: Google Health API integration
Google's new Google Health API (`health.googleapis.com`, launched 2026, successor to
the Fitbit Web API) is the data source. Full technical facts already verified, do not
re-research these:

- OAuth 2.0 is the standard Google flow: authorize at
  `https://accounts.google.com/o/oauth2/v2/auth`, token exchange/refresh at
  `https://oauth2.googleapis.com/token`. Use `access_type=offline&prompt=consent` on
  the first authorize request to guarantee a refresh token.
- Required scopes (space-separated in the `scope` param):
  `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`
  `https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly`
  `https://www.googleapis.com/auth/googlehealth.sleep.readonly`
- All these scopes are Google-classified "Restricted". For a single personal user this
  is fine as long as the OAuth consent screen stays in "Testing" publishing status with
  Andrew's own Google account added as a test user — no Google security review needed
  at that scale. Note this in the README setup instructions; do not build any
  verification/CASA flow.
- Base API path: `https://health.googleapis.com/v4/users/me/dataTypes/{data_type}/dataPoints`
  (GET, query params: `filter`, `pageSize` up to 10000, `pageToken` for pagination).
  Literal `me` is valid and always refers to the authenticated user, no identity
  lookup call needed.
- Response ordering is descending by interval/sample start time; always follow
  `nextPageToken` until exhausted for a requested range.
- Filter syntax (AIP-160), the field name depends on the data type's category:
  - Sample types (weight, body-fat, height): `{type}.sample_time.civil_time >= "YYYY-MM-DD" AND {type}.sample_time.civil_time < "YYYY-MM-DD"`
  - Interval types (steps, distance, floors, active-minutes, active-zone-minutes,
    active-energy-burned, basal-energy-burned): `{type}.interval.civil_start_time >= "YYYY-MM-DD" AND {type}.interval.civil_start_time < "YYYY-MM-DD"`
  - Daily types (daily-resting-heart-rate, daily-heart-rate-variability,
    daily-vo2-max, daily-respiratory-rate, daily-oxygen-saturation): `{type_with_underscores}.date >= "YYYY-MM-DD" AND {type_with_underscores}.date < "YYYY-MM-DD"`
    (note: daily type filter field uses underscores, e.g. `daily_resting_heart_rate.date`,
    even though the data type path segment uses hyphens, e.g. `daily-resting-heart-rate`)
  - Sleep (session type, special case): filter on end time, e.g.
    `sleep.interval.civil_end_time >= "YYYY-MM-DD" AND sleep.interval.civil_end_time < "YYYY-MM-DD"`
    (bucket a sleep session under the date the person woke up)
- Chunk requests by month (not the whole history range in one filter) to keep filter
  strings simple and avoid any server-side range limits; loop until the full requested
  window (see "History window" below) is covered.
- DataPoint JSON shape: the response's `dataPoints[]` array has objects with the
  request's data type as a key holding the typed payload, e.g. for `weight`:
  `{"weight": {"weightGrams": 82500.0, "sampleTime": {...}}}`. Exact field names and
  units per type (all confirmed from the live discovery document, use exactly these):
  - `weight.weightGrams` (double, grams) → convert to kg for storage (÷1000)
  - `bodyFat.percentage` (double, 0-100, already a percentage)
  - `height.heightMillimeters` (int64-as-string) → convert to cm (÷10)
  - `steps.count` (int64-as-string), `steps.interval` (start/end)
  - `distance` interval type: has a distance value in metres (confirm exact field name
    from `GET https://health.googleapis.com/$discovery/rest?version=v4` schemas.Distance
    if unsure, it's already downloaded at
    `/home/user/workspace/google_health_discovery.json`, read it directly for any field
    you're unsure of instead of guessing)
  - `floors`, `activeMinutes`, `activeZoneMinutes`, `activeEnergyBurned`,
    `basalEnergyBurned`: read exact field names from the same discovery JSON file
    (schemas: Floors, ActiveMinutes, ActiveZoneMinutes, ActiveEnergyBurned,
    BasalEnergyBurned) rather than guessing
  - Daily types (`DailyRestingHeartRate`, `DailyHeartRateVariability`, `DailyVO2Max`,
    `DailyRespiratoryRate`, `DailyOxygenSaturation`): read exact field/value names from
    the discovery JSON, they are simple date + value objects
  - `sleep.interval` (start/end) and `sleep.summary` (duration etc.): read the `Sleep`
    and `SleepSummary` schemas in the discovery JSON for the exact duration field name
- The discovery JSON at `/home/user/workspace/google_health_discovery.json` is the
  ground truth for every field name and type. Always check it rather than inventing a
  field name. If a field genuinely cannot be found there, add a defensive `.get()` with
  a sensible fallback and log/skip that data point rather than crashing the sync.

## Data types to sync (exactly these, matching the 4 categories Andrew selected)
1. Body composition: `weight`, `body-fat`, `height`
2. Activity & steps: `steps`, `distance`, `floors`, `active-minutes`,
   `active-zone-minutes`, `active-energy-burned`, `basal-energy-burned`
3. Heart & cardio: `daily-resting-heart-rate`, `daily-heart-rate-variability`,
   `daily-vo2-max`
4. Sleep & recovery: `sleep`, `daily-respiratory-rate`, `daily-oxygen-saturation`

Do NOT implement: blood glucose, ECG, irregular rhythm notifications, moods, symptoms,
menstrual/reproductive health, nutrition, hydration, mindfulness. Out of scope, not
requested.

BMR is explicitly NOT available in the Google Health API yet (verified against the
live discovery document, not just the marketing page). Do not attempt to sync it. It
must stay a manual smart-scale entry as it already is. Note this clearly in the README
and, ideally, in the Settings UI copy near the Google Health section so it's not a
surprise.

## Storage design
Add a new table `health_metrics`, one row per `entry_date` (ISO YYYY-MM-DD), separate
from the existing manifest-driven `entries` table (which is a Goals/Status
target-tracking model that these activity/cardio/sleep metrics don't fit):

```sql
CREATE TABLE IF NOT EXISTS health_metrics (
    entry_date TEXT PRIMARY KEY,
    steps INTEGER,
    distance_km REAL,
    floors_climbed REAL,
    active_minutes REAL,
    active_zone_minutes REAL,
    calories_burned REAL,           -- active + basal energy burned, kcal
    resting_heart_rate REAL,        -- bpm
    heart_rate_variability_ms REAL,
    vo2_max REAL,
    sleep_minutes REAL,
    respiratory_rate REAL,
    oxygen_saturation_pct REAL,
    source TEXT NOT NULL DEFAULT 'google_health',
    synced_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_health_metrics_date ON health_metrics(entry_date);
```
Create this via the same idempotent `CREATE TABLE IF NOT EXISTS` + migration pattern
already used in `db.py`'s `init_db()`.

Weight and body-fat DO map onto existing tracked fields, so gap-fill them directly into
`entries.body_weight_mass` (kg) and `entries.percent_body_fat` (%) (and derive
`entries.body_fat_mass` = weight_kg * pct/100 when both are present and that column is
still NULL). **Gap-fill only, per Andrew's explicit decision**: a synced value must
NEVER overwrite a value that already exists for that date, whether it arrived from a
manual entry or an earlier sync. Do not reuse `upsert_entry()` as-is for this (it always
overwrites provided columns) — write a new `db.gap_fill_entry_fields(entry_date_iso,
values: dict, source_label: str)` that:
- Inserts a new row (via the same shape as `upsert_entry`, `source=source_label`) if no
  row exists for that date yet.
- If a row exists, only includes a column in the UPDATE if the *current* value for that
  column on that row is NULL. Leaves the row's existing `source` and `updated_at`
  untouched (don't relabel a manual row as `google_health` just because one gap was
  filled).
Height has no natural per-day entries column (it barely changes) — store the latest
synced value on `app_settings.google_health_height_cm` instead (informational display
only, not part of the Goals/Status model).

## New app_settings columns
Add via the same `_ensure_settings_columns()`-style idempotent migration:
```
google_health_client_id TEXT
google_health_client_secret TEXT
google_health_access_token TEXT
google_health_refresh_token TEXT
google_health_token_expiry TEXT        -- ISO 8601 UTC
google_health_connected_at TEXT        -- ISO 8601 UTC, first successful OAuth
google_health_last_sync_at TEXT        -- ISO 8601 UTC
google_health_last_sync_error TEXT
google_health_history_days INTEGER DEFAULT 730   -- how far back the first sync reaches
google_health_height_cm REAL
google_health_enabled_categories TEXT  -- JSON array, e.g. ["body_composition","activity","cardio","sleep"]
```
Client secret: store as plain text in SQLite for now (this app has no other secrets
encryption layer and the DB file is already the trust boundary for this single-user
app) but never log it, never echo it back in any API JSON response (mask it, e.g.
return `"google_health_client_secret_set": true/false` instead of the value itself).

## Redirect URI / public base URL
Add `PLD_PUBLIC_BASE_URL` to `app/config.py` (default `f"http://localhost:{PORT}"`,
same env-var-driven pattern as everything else in that file). The OAuth redirect_uri is
`f"{config.PUBLIC_BASE_URL}/google-health/oauth/callback"`. Do not make Caddy/HTTPS a
prerequisite, plain HTTP localhost works fine for the OAuth redirect during
development; document in the README that production/public deployments should set
`PLD_PUBLIC_BASE_URL` to the real HTTPS URL once one exists.

## New module: app/google_health.py
Client for the Google Health API: OAuth URL building, token exchange, token refresh
(refresh automatically whenever the stored token is expired or about to expire before
making a request, matching the "triggered, not backgrounded" pattern, i.e. refresh
happens inline within the sync call, never a background thread), and one function per
data-type category that fetches + normalises a date range into the shapes needed for
`health_metrics` rows / gap-fill values. Raise a `FetchError` (mirroring
`openpowerlifting.py`'s `FetchError`) with a user-facing message on any failure.

## New routes: app/routes/google_health.py
- `GET /google-health/connect` — requires `google_health_client_id`/`_secret` already
  saved; builds the Google authorize URL and redirects.
- `GET /google-health/oauth/callback` — exchanges `code` for tokens, saves them, sets
  `google_health_connected_at`, then runs the **historical backfill** synchronously
  (full `google_health_history_days` window) before redirecting to `/settings` with a
  success or error flash message via query param.
- `POST /api/google-health/sync` — manual "Sync now": incremental sync from
  `google_health_last_sync_at` (or the full history window if never synced) to now.
  Updates `google_health_last_sync_at` / `google_health_last_sync_error`.
- `POST /api/google-health/disconnect` — clears all `google_health_*` token/connection
  columns (keeps `client_id`/`client_secret` and `enabled_categories` so reconnecting is
  a one-click "Connect" again, not a full re-setup).
Register the new router in `app/main.py` alongside the existing routers.

Also add a **lightweight auto-sync trigger**: on `GET /api/dashboard` (in
`app/routes/api.py`), if Google Health is connected and
`now - google_health_last_sync_at > 1 hour` (reuse a similar cadence idea to
`PLD_DASHBOARD_POLL_SECONDS`, e.g. a new `PLD_GOOGLE_HEALTH_SYNC_INTERVAL_SECONDS` env
var defaulting to 3600), trigger the same incremental sync inline before building the
payload. Still request-triggered, never a background thread, consistent with the
OpenPowerlifting pattern and the project's existing "no scheduled polling" design note.

## Settings UI (app/templates/settings.html + app/static/settings.js)
Add a new "Google Health" section, in the same visual style as the existing
OpenPowerlifting section:
- If no client ID/secret saved: two inputs (Client ID, Client Secret) + a "Save and
  connect" button that POSTs to `/api/settings` then navigates to
  `/google-health/connect`.
- If saved but not connected: "Connect Google Health" button.
- If connected: green "Connected" status, "Last synced: {relative time}" (or the error
  message if `google_health_last_sync_error` is set), a "Sync now" button (calls
  `/api/google-health/sync`), a "Disconnect" button, and four checkboxes for the
  category toggles (Body composition / Activity & steps / Heart & cardio / Sleep &
  recovery) all checked by default, wired to `google_health_enabled_categories`.
- A short note: "Weight and body composition only fill in dates with no existing
  manual entry, so your smart-scale readings are never overwritten. BMR is not yet
  available from Google Health and must stay a manual entry."
- Extend `POST /api/settings` in `app/routes/api.py` to accept
  `google_health_client_id`, `google_health_client_secret`, and
  `google_health_enabled_categories` (as a JSON-encoded list) as allowed/clearable
  fields, following the exact pattern already used for `openpowerlifting_username`.

## Dashboard display (optional but nice, keep small)
If time allows, add a small "Activity & recovery" card to the dashboard showing the
latest `health_metrics` row's steps, resting heart rate, and sleep hours, styled
consistently with existing dashboard cards (check `app/templates/dashboard.html` and
`app/static/dashboard.js`/CSS tokens). Do not let this expand scope, if it needs new
metrics/derived-value plumbing to fit the existing `metrics.py` payload cleanly, do the
minimal version and document what's deferred instead of over-building.

## Dependencies
Add to `requirements.txt`: nothing new is strictly required, `httpx` is already there
and is sufficient for both the OAuth token exchange and the Health API REST calls
(same approach as `openpowerlifting.py`). Do not add `google-auth`/`google-api-python-client`,
plain `httpx` keeps this consistent with the rest of the codebase.

## Tests to add
- `tests/test_google_health.py`: unit tests for the client module (mock `httpx`
  responses) covering token refresh, unit conversions (grams→kg, mm→cm), and the
  filter-string builders for each category (sample/interval/daily/session).
- `tests/test_db_migration.py` (extend): new columns/table appear on a fresh DB and on
  an upgraded existing DB.
- A test for `db.gap_fill_entry_fields`: confirms it never overwrites an existing
  non-NULL value and does insert into a genuinely empty date.
- A route test for `/api/google-health/sync` and the settings extension, following
  `tests/test_settings_route.py`'s pattern (mock the Google Health client, don't hit
  the real network).

## When done
Run `pytest` (all existing + new tests green) and `pyflakes app/` (clean) before
reporting back. Report: files changed/added, test results, and any field names you had
to infer because the discovery JSON was ambiguous (call these out explicitly so they
can be verified against a real account later).
