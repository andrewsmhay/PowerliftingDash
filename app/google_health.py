"""Google Health OAuth and request-triggered metric synchronisation helpers.

The module intentionally uses plain HTTP calls. Tokens are refreshed only while a
user-triggered sync is already running, so the personal dashboard has no worker
or scheduled polling process.
"""
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE_URL = "https://health.googleapis.com/v4/users/me/dataTypes"
TIMEOUT_SECONDS = 20
PAGE_SIZE = 10000
TOKEN_EXPIRY_SAFETY_SECONDS = 60

SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
]

CATEGORY_TYPES = {
    "body_composition": ("weight", "body-fat", "height"),
    "activity": (
        "steps", "distance", "floors", "active-minutes", "active-zone-minutes",
        "active-energy-burned", "basal-energy-burned",
    ),
    "cardio": (
        "daily-resting-heart-rate", "daily-heart-rate-variability", "daily-vo2-max",
    ),
    "sleep": ("sleep", "daily-respiratory-rate", "daily-oxygen-saturation"),
}
SAMPLE_TYPES = {"weight", "body-fat", "height"}
INTERVAL_TYPES = {
    "steps", "distance", "floors", "active-minutes", "active-zone-minutes",
    "active-energy-burned", "basal-energy-burned",
}
DAILY_TYPES = {
    "daily-resting-heart-rate", "daily-heart-rate-variability", "daily-vo2-max",
    "daily-respiratory-rate", "daily-oxygen-saturation",
}


class FetchError(Exception):
    """Raised with a message that is safe to show directly to the user."""


def build_authorize_url(client_id: str, redirect_uri: str) -> str:
    """Builds the consent URL, requesting offline access for later manual syncs."""
    return AUTHORIZE_URL + "?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }
    )


def _token_request(data: dict) -> dict:
    try:
        response = httpx.post(TOKEN_URL, data=data, timeout=TIMEOUT_SECONDS)
    except httpx.RequestError as exc:
        raise FetchError(f"Could not reach Google's token service: {exc}") from exc
    if response.status_code != 200:
        raise FetchError("Google could not issue an access token. Check the OAuth configuration and try again.")
    try:
        return response.json()
    except ValueError as exc:
        raise FetchError("Google returned an invalid token response.") from exc


def _token_expiry(token_data: dict) -> str:
    try:
        seconds = int(token_data.get("expires_in", 3600))
    except (TypeError, ValueError):
        seconds = 3600
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def exchange_authorization_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """Exchanges an OAuth callback code for values ready for app_settings."""
    token_data = _token_request(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    )
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    if not access_token or not refresh_token:
        raise FetchError("Google did not return the offline access needed to sync Health data.")
    return {
        "google_health_access_token": access_token,
        "google_health_refresh_token": refresh_token,
        "google_health_token_expiry": _token_expiry(token_data),
    }


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Refreshes a stored Google token without starting a new browser flow."""
    token_data = _token_request(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    )
    access_token = token_data.get("access_token")
    if not access_token:
        raise FetchError("Google did not return a refreshed access token. Reconnect Google Health and try again.")
    updates = {
        "google_health_access_token": access_token,
        "google_health_token_expiry": _token_expiry(token_data),
    }
    if token_data.get("refresh_token"):
        updates["google_health_refresh_token"] = token_data["refresh_token"]
    return updates


def _is_expiring(expiry: str | None) -> bool:
    if not expiry:
        return True
    try:
        parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= datetime.now(timezone.utc) + timedelta(seconds=TOKEN_EXPIRY_SAFETY_SECONDS)


def get_valid_access_token(settings: dict) -> tuple[str, dict]:
    """Returns a usable token and any app_settings updates from an inline refresh."""
    access_token = settings.get("google_health_access_token")
    if access_token and not _is_expiring(settings.get("google_health_token_expiry")):
        return access_token, {}
    client_id = settings.get("google_health_client_id")
    client_secret = settings.get("google_health_client_secret")
    refresh_token = settings.get("google_health_refresh_token")
    if not client_id or not client_secret or not refresh_token:
        raise FetchError("Google Health is not connected. Connect it from Settings first.")
    updates = refresh_access_token(client_id, client_secret, refresh_token)
    return updates["google_health_access_token"], updates


def _as_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def iter_month_windows(start_date: date | str, end_date: date | str):
    """Yields half-open calendar-month windows to avoid oversized API filters."""
    start = _as_date(start_date)
    end = _as_date(end_date)
    current = start
    while current < end:
        first_next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        window_end = min(first_next_month, end)
        yield current, window_end
        current = window_end


def build_filter(data_type: str, start_date: date | str, end_date: date | str) -> str:
    """Returns the documented AIP-160 filter for one half-open date window."""
    start = _as_date(start_date).isoformat()
    end = _as_date(end_date).isoformat()
    if data_type in SAMPLE_TYPES:
        field = f"{data_type}.sample_time.civil_time"
    elif data_type in INTERVAL_TYPES:
        field = f"{data_type}.interval.civil_start_time"
    elif data_type in DAILY_TYPES:
        field = f"{data_type.replace('-', '_')}.date"
    elif data_type == "sleep":
        field = "sleep.interval.civil_end_time"
    else:
        raise ValueError(f"Unsupported Google Health data type: {data_type}")
    return f'{field} >= "{start}" AND {field} < "{end}"'


def fetch_data_points(access_token: str, data_type: str, start_date: date | str, end_date: date | str) -> list[dict]:
    """Fetches every page for each calendar-month window of one data type."""
    points: list[dict] = []
    headers = {"Authorization": f"Bearer {access_token}"}
    for window_start, window_end in iter_month_windows(start_date, end_date):
        params = {"filter": build_filter(data_type, window_start, window_end), "pageSize": PAGE_SIZE}
        while True:
            try:
                response = httpx.get(
                    f"{API_BASE_URL}/{data_type}/dataPoints",
                    headers=headers,
                    params=params,
                    timeout=TIMEOUT_SECONDS,
                )
            except httpx.RequestError as exc:
                raise FetchError(f"Could not reach Google Health: {exc}") from exc
            if response.status_code != 200:
                raise FetchError(f"Google Health returned an unexpected status ({response.status_code}).")
            try:
                payload = response.json()
            except ValueError as exc:
                raise FetchError("Google Health returned an invalid data response.") from exc
            points.extend(payload.get("dataPoints") or [])
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
            params["pageToken"] = page_token
    return points


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_from_object(value: dict | None) -> str | None:
    if not isinstance(value, dict):
        return None
    if "date" in value:
        value = value["date"]
    try:
        return date(int(value["year"]), int(value["month"]), int(value["day"])).isoformat()
    except (KeyError, TypeError, ValueError):
        return None


def _date_from_time(value: dict | None, fallback: str | None = None) -> str | None:
    civil_date = _date_from_object(value)
    if civil_date:
        return civil_date
    if not fallback:
        return None
    try:
        return datetime.fromisoformat(fallback.replace("Z", "+00:00")).date().isoformat()
    except (TypeError, ValueError):
        return None


def _sample_date(payload: dict) -> str | None:
    sample_time = payload.get("sampleTime") or {}
    return _date_from_time(sample_time.get("civilTime"), sample_time.get("physicalTime"))


def _interval_date(payload: dict, use_end: bool = False) -> str | None:
    interval = payload.get("interval") or {}
    civil_key = "civilEndTime" if use_end else "civilStartTime"
    physical_key = "endTime" if use_end else "startTime"
    return _date_from_time(interval.get(civil_key), interval.get(physical_key))


def _merge_value(rows: dict, entry_date: str | None, column: str, value, add: bool = False) -> None:
    number = _number(value)
    if not entry_date or number is None:
        return
    row = rows.setdefault(entry_date, {})
    if add:
        row[column] = (row.get(column) or 0) + number
    elif column not in row:
        row[column] = number


def fetch_body_composition(access_token: str, start_date: date | str, end_date: date | str) -> dict:
    """Normalises body samples for the dated gap-fill fields and saved height."""
    entry_fields: dict[str, dict] = {}
    latest_height: tuple[str, float] | None = None
    for point in fetch_data_points(access_token, "weight", start_date, end_date):
        payload = point.get("weight") or {}
        value = _number(payload.get("weightGrams"))
        day = _sample_date(payload)
        if day and value is not None and "body_weight_mass" not in entry_fields.setdefault(day, {}):
            entry_fields[day]["body_weight_mass"] = value / 1000
    for point in fetch_data_points(access_token, "body-fat", start_date, end_date):
        payload = point.get("bodyFat") or {}
        day = _sample_date(payload)
        value = _number(payload.get("percentage"))
        if day and value is not None and "percent_body_fat" not in entry_fields.setdefault(day, {}):
            entry_fields[day]["percent_body_fat"] = value
    for point in fetch_data_points(access_token, "height", start_date, end_date):
        payload = point.get("height") or {}
        day = _sample_date(payload)
        value = _number(payload.get("heightMillimeters"))
        if day and value is not None and (latest_height is None or day > latest_height[0]):
            latest_height = (day, value / 10)
    return {"entry_fields": entry_fields, "height_cm": latest_height[1] if latest_height else None, "metrics": {}}


def fetch_activity(access_token: str, start_date: date | str, end_date: date | str) -> dict:
    """Normalises interval activity types into additive daily summaries."""
    rows: dict[str, dict] = {}
    simple_types = {
        "steps": ("steps", "count", 1),
        "distance": ("distance_km", "millimeters", 1 / 1_000_000),
        "floors": ("floors_climbed", "count", 1),
        "active-zone-minutes": ("active_zone_minutes", "activeZoneMinutes", 1),
        "active-energy-burned": ("calories_burned", "kcal", 1),
        "basal-energy-burned": ("calories_burned", "kcal", 1),
    }
    for data_type, (column, field, multiplier) in simple_types.items():
        payload_key = {
            "active-zone-minutes": "activeZoneMinutes",
            "active-energy-burned": "activeEnergyBurned",
            "basal-energy-burned": "basalEnergyBurned",
        }.get(data_type, data_type)
        for point in fetch_data_points(access_token, data_type, start_date, end_date):
            payload = point.get(payload_key) or {}
            value = _number(payload.get(field))
            _merge_value(rows, _interval_date(payload), column, value * multiplier if value is not None else None, add=True)
    for point in fetch_data_points(access_token, "active-minutes", start_date, end_date):
        payload = point.get("activeMinutes") or {}
        total = sum(
            value for item in payload.get("activeMinutesByActivityLevel") or []
            if (value := _number(item.get("activeMinutes"))) is not None
        )
        _merge_value(rows, _interval_date(payload), "active_minutes", total, add=True)
    return {"entry_fields": {}, "height_cm": None, "metrics": rows}


def fetch_cardio(access_token: str, start_date: date | str, end_date: date | str) -> dict:
    """Normalises daily cardio values, preferring the documented average HRV."""
    rows: dict[str, dict] = {}
    mappings = {
        "daily-resting-heart-rate": ("dailyRestingHeartRate", "resting_heart_rate", "beatsPerMinute"),
        "daily-heart-rate-variability": (
            "dailyHeartRateVariability", "heart_rate_variability_ms", "averageHeartRateVariabilityMilliseconds",
        ),
        "daily-vo2-max": ("dailyVo2Max", "vo2_max", "vo2Max"),
    }
    for data_type, (payload_key, column, field) in mappings.items():
        for point in fetch_data_points(access_token, data_type, start_date, end_date):
            payload = point.get(payload_key) or {}
            _merge_value(rows, _date_from_object(payload.get("date")), column, payload.get(field))
    return {"entry_fields": {}, "height_cm": None, "metrics": rows}


def fetch_sleep(access_token: str, start_date: date | str, end_date: date | str) -> dict:
    """Buckets sleep by wake date, then adds daily respiratory and oxygen values."""
    rows: dict[str, dict] = {}
    for point in fetch_data_points(access_token, "sleep", start_date, end_date):
        payload = point.get("sleep") or {}
        summary = payload.get("summary") or {}
        _merge_value(rows, _interval_date(payload, use_end=True), "sleep_minutes", summary.get("minutesAsleep"), add=True)
    mappings = {
        "daily-respiratory-rate": ("dailyRespiratoryRate", "respiratory_rate", "breathsPerMinute"),
        "daily-oxygen-saturation": ("dailyOxygenSaturation", "oxygen_saturation_pct", "averagePercentage"),
    }
    for data_type, (payload_key, column, field) in mappings.items():
        for point in fetch_data_points(access_token, data_type, start_date, end_date):
            payload = point.get(payload_key) or {}
            _merge_value(rows, _date_from_object(payload.get("date")), column, payload.get(field))
    return {"entry_fields": {}, "height_cm": None, "metrics": rows}
