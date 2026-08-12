"""Pluggable Google credential loading.

Default strategy is a service account, which is the only sane option for an
unattended kiosk container (no browser, no refresh token dance). Resolution
order:

  1. Service account JSON pasted into the Settings page (stored in the
     app_settings.service_account_json DB column).
  2. PLD_GOOGLE_SERVICE_ACCOUNT_JSON environment variable (raw JSON string).
  3. PLD_GOOGLE_SERVICE_ACCOUNT_FILE environment variable (path to a
     mounted JSON key file).
  4. /data/service_account.json, if someone drops a key file straight into
     the data volume.

Swap in a different mechanism later (OAuth, workload identity, etc.) by
replacing `load_credentials()` below with your own implementation that
still returns a `google.auth.credentials.Credentials` instance -- nothing
else in the codebase needs to change.
"""
import json

from google.oauth2 import service_account

from . import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class CredentialsNotConfigured(RuntimeError):
    pass


def _from_json_string(raw_json: str):
    info = json.loads(raw_json)
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def load_credentials(settings: dict):
    pasted = (settings or {}).get("service_account_json")
    if pasted:
        return _from_json_string(pasted)

    if config.ENV_SERVICE_ACCOUNT_JSON:
        return _from_json_string(config.ENV_SERVICE_ACCOUNT_JSON)

    if config.ENV_SERVICE_ACCOUNT_FILE:
        return service_account.Credentials.from_service_account_file(
            config.ENV_SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )

    if config.DEFAULT_SERVICE_ACCOUNT_FILE.exists():
        return service_account.Credentials.from_service_account_file(
            str(config.DEFAULT_SERVICE_ACCOUNT_FILE), scopes=SCOPES
        )

    raise CredentialsNotConfigured(
        "No Google service account credentials configured. Paste one into "
        "Settings, or set PLD_GOOGLE_SERVICE_ACCOUNT_JSON / "
        "PLD_GOOGLE_SERVICE_ACCOUNT_FILE, or mount a key at /data/service_account.json."
    )


def service_account_email(settings: dict) -> str | None:
    """Returns the client_email from whichever credential source is active,
    so the UI can tell the user which address to share their Sheet with.
    """
    try:
        creds = load_credentials(settings)
        return getattr(creds, "service_account_email", None)
    except CredentialsNotConfigured:
        return None
