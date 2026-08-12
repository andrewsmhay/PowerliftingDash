"""Thin wrapper around the Google Sheets API v4 for reading the entries tab."""
from googleapiclient.discovery import build

from . import auth_provider


def fetch_tab_values(settings: dict) -> list[list]:
    """Returns the raw grid (list of rows, each a list of cell values) for
    the configured entries tab. Row 1 is expected to be a header row.
    """
    sheet_id = settings.get("google_sheet_id")
    if not sheet_id:
        raise ValueError("No Google Sheet ID configured. Set it on the Settings page.")

    tab_name = settings.get("entries_tab_name") or "v1"
    creds = auth_provider.load_credentials(settings)
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"{tab_name}!A:ZZ", valueRenderOption="UNFORMATTED_VALUE")
        .execute()
    )
    return result.get("values", [])
