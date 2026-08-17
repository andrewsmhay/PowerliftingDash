"""Fetches a lifter's personal bests from openpowerlifting.org.

This is the one place PowerliftingDash reaches outside its own database: an
explicit, on-demand HTTP GET against a public profile page, triggered only
when a user saves or refreshes their username in Settings. There is no
background job and no scheduled polling - see README.md for the full
integration notes.

openpowerlifting.org has no public JSON API for a single lifter's summary,
so this parses the small "best lifts" table at the top of the profile page
with the standard library's `html.parser` (no third-party HTML/XML packages
are available in this project).
"""
import re
from html.parser import HTMLParser

import httpx

BASE_URL = "https://www.openpowerlifting.org/u/"
USER_AGENT = (
    "PowerliftingDash/1.0 (personal single-user dashboard; "
    "https://github.com/andrewsmhay/PowerliftingDash)"
)
TIMEOUT_SECONDS = 10


class FetchError(Exception):
    """Raised with a message that is safe to show directly to the user."""


class _BestLiftsTableParser(HTMLParser):
    """Collects the rows of the first `<table>` on the page (the "best
    lifts by equipment" summary) and separately tracks whether the `<h1>`
    reads "Lifter Disambiguation", which openpowerlifting.org shows instead
    of a profile when a username matches more than one lifter.
    """

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self.saw_disambiguation = False

        self._in_table = False
        self._table_done = False
        self._in_row = False
        self._in_cell = False
        self._current_row: list[str] = []
        self._current_cell_parts: list[str] = []

        self._in_h1 = False
        self._h1_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "table" and not self._table_done:
            self._in_table = True
        elif tag == "h1":
            self._in_h1 = True
            self._h1_parts = []
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
        elif self._in_table and self._in_row and tag == "td":
            self._in_cell = True
            self._current_cell_parts = []

    def handle_endtag(self, tag):
        if tag == "table" and self._in_table:
            self._in_table = False
            self._table_done = True
        elif tag == "h1" and self._in_h1:
            self._in_h1 = False
            text = "".join(self._h1_parts).strip().lower()
            if text == "lifter disambiguation":
                self.saw_disambiguation = True
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if self._current_row:
                self.rows.append(self._current_row)
        elif tag == "td" and self._in_cell:
            self._in_cell = False
            self._current_row.append("".join(self._current_cell_parts).strip())

    def handle_data(self, data):
        if self._in_h1:
            self._h1_parts.append(data)
        elif self._in_cell:
            self._current_cell_parts.append(data)


def _parse_float(text: str) -> float | None:
    text = (text or "").strip()
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fetch_personal_bests(username: str) -> dict:
    """Fetches and parses the best-lifts table for `username`.

    Returns a dict with keys `equip`, `squat`, `bench`, `deadlift`, `total`
    (kg, or `None` where the lifter has no result for that lift) and
    `profile_url`. Raises `FetchError` with a user-facing message on any
    failure, including an ambiguous username.
    """
    username = (username or "").strip()
    if not username:
        raise FetchError("No OpenPowerlifting username configured.")

    url = f"{BASE_URL}{username}"
    try:
        response = httpx.get(
            url,
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
    except httpx.RequestError as exc:
        raise FetchError(f"Could not reach openpowerlifting.org: {exc}") from exc

    if response.status_code == 404:
        raise FetchError(f"No openpowerlifting.org lifter found for username '{username}'.")
    if response.status_code != 200:
        raise FetchError(
            f"openpowerlifting.org returned an unexpected status ({response.status_code})."
        )

    parser = _BestLiftsTableParser()
    parser.feed(response.text)

    if parser.saw_disambiguation:
        suggestions = sorted(set(re.findall(rf'/u/({re.escape(username)}\d+)"', response.text)))
        if suggestions:
            hint = "Did you mean: " + ", ".join(suggestions) + "?"
        else:
            hint = "Try the fuller username shown on openpowerlifting.org, e.g. with a trailing number."
        raise FetchError(
            f"'{username}' matches more than one lifter on openpowerlifting.org. {hint}"
        )

    if not parser.rows:
        raise FetchError(f"Could not find a best-lifts table for '{username}' on openpowerlifting.org.")

    row = next((r for r in parser.rows if r and r[0].strip().lower() == "raw"), parser.rows[0])
    # Row shape: [Equip, Squat, Bench, Deadlift, Total, Dots]
    padded = row + [""] * (6 - len(row))

    return {
        "equip": padded[0] or None,
        "squat": _parse_float(padded[1]),
        "bench": _parse_float(padded[2]),
        "deadlift": _parse_float(padded[3]),
        "total": _parse_float(padded[4]),
        "profile_url": url,
    }
