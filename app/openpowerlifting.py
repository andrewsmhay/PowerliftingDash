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


class _MeetResultsTableParser(HTMLParser):
    """Collects the rows of the second `<table>` on a lifter's profile page
    (the meet-by-meet "Competition Results" history, below the best-lifts
    summary parsed by `_BestLiftsTableParser`).

    openpowerlifting.org tags every Squat/Bench/Deadlift attempt cell with a
    matching `class="squat"`/`"bench"`/`"deadlift"` attribute, so attempts
    are grouped by that class rather than by position - this copes with
    federations that show fewer than four attempts. Every other cell in a
    row is collected, in order, into `others`.
    """

    _TARGET_TABLE_INDEX = 2
    _ATTEMPT_CLASSES = ("squat", "bench", "deadlift")

    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []

        self._table_count = 0
        self._in_target_table = False
        self._table_done = False
        self._in_row = False
        self._in_cell = False
        self._cell_class = None
        self._current_cell_parts: list[str] = []
        self._current_others: list[str] = []
        self._current_attempts: dict[str, list[str]] = {}

    def handle_starttag(self, tag, attrs):
        if tag == "table" and not self._table_done:
            self._table_count += 1
            self._in_target_table = self._table_count == self._TARGET_TABLE_INDEX
        elif self._in_target_table and tag == "tr":
            self._in_row = True
            self._current_others = []
            self._current_attempts = {cls: [] for cls in self._ATTEMPT_CLASSES}
        elif self._in_target_table and self._in_row and tag == "td":
            self._in_cell = True
            self._current_cell_parts = []
            self._cell_class = dict(attrs).get("class")

    def handle_endtag(self, tag):
        if tag == "table" and self._in_target_table:
            self._in_target_table = False
            self._table_done = True
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if self._current_others or any(self._current_attempts.values()):
                self.rows.append(
                    {"others": self._current_others, "attempts": self._current_attempts}
                )
        elif tag == "td" and self._in_cell:
            self._in_cell = False
            text = "".join(self._current_cell_parts).strip()
            if self._cell_class in self._ATTEMPT_CLASSES:
                self._current_attempts[self._cell_class].append(text)
            else:
                self._current_others.append(text)

    def handle_data(self, data):
        if self._in_cell:
            self._current_cell_parts.append(data)


def _ordinal(text: str) -> str:
    """Formats a bare integer placing such as "1" as "1st". Anything that
    is not a plain integer (e.g. "DQ", "G", a guest-lifter marker) is
    returned unchanged.
    """
    text = (text or "").strip()
    if not re.fullmatch(r"\d+", text):
        return text
    n = int(text)
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _best_attempt(values: list[str]) -> float | None:
    """Returns the heaviest successful attempt from a list of raw
    attempt-cell strings (openpowerlifting.org records failed attempts as
    negative numbers), or `None` if every attempt was blank or failed.
    """
    best = None
    for raw in values:
        parsed = _parse_float(raw)
        if parsed is not None and parsed > 0 and (best is None or parsed > best):
            best = parsed
    return best


# Fixed column order of the non-attempt cells in a Competition Results row:
# Place, Fed, Date, Location, Competition, Division, Age, Equip, Class,
# Weight, Total, Dots.
_OTHERS_COUNT = 12


def _row_to_meet(others: list[str], attempts: dict[str, list[str]]) -> dict | None:
    """Maps one parsed table row to a competitions-table-shaped dict, or
    `None` if the row does not have the expected number of columns or does
    not carry a valid ISO date - rather than silently mis-mapping cells,
    such rows are skipped.
    """
    if len(others) != _OTHERS_COUNT:
        return None

    (
        place,
        federation,
        date,
        location,
        meet_name,
        _division,
        _age,
        _equip,
        weight_class,
        bodyweight,
        total,
        _dots,
    ) = others

    date = (date or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return None

    return {
        "competition_date_iso": date,
        "meet_name": meet_name or None,
        "federation": federation or None,
        "location": location or None,
        "weight_class": weight_class or None,
        "placing": _ordinal(place) or None,
        "bodyweight_kg": _parse_float(bodyweight),
        "squat_kg": _best_attempt(attempts.get("squat", [])),
        "bench_kg": _best_attempt(attempts.get("bench", [])),
        "deadlift_kg": _best_attempt(attempts.get("deadlift", [])),
        "total_kg": _parse_float(total),
        "notes": "Imported from OpenPowerlifting.",
    }


def _fetch_profile_html(username: str) -> tuple[str, str]:
    """Fetches the raw profile-page HTML for `username`.

    Raises `FetchError` with a user-facing message for a blank username, a
    network failure, a missing lifter (404), or any other non-200
    response. Returns `(html, profile_url)`. Shared by
    `fetch_personal_bests` and `fetch_competition_history` - disambiguation
    detection is left to each caller since both already run their own
    `_BestLiftsTableParser` pass over the returned HTML.
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

    return response.text, url


def _raise_if_disambiguation(username: str, html: str) -> None:
    parser = _BestLiftsTableParser()
    parser.feed(html)
    if parser.saw_disambiguation:
        suggestions = sorted(set(re.findall(rf'/u/({re.escape(username)}\d+)"', html)))
        if suggestions:
            hint = "Did you mean: " + ", ".join(suggestions) + "?"
        else:
            hint = "Try the fuller username shown on openpowerlifting.org, e.g. with a trailing number."
        raise FetchError(
            f"'{username}' matches more than one lifter on openpowerlifting.org. {hint}"
        )


def fetch_personal_bests(username: str) -> dict:
    """Fetches and parses the best-lifts table for `username`.

    Returns a dict with keys `equip`, `squat`, `bench`, `deadlift`, `total`
    (kg, or `None` where the lifter has no result for that lift) and
    `profile_url`. Raises `FetchError` with a user-facing message on any
    failure, including an ambiguous username.
    """
    username = (username or "").strip()
    html, url = _fetch_profile_html(username)
    _raise_if_disambiguation(username, html)

    parser = _BestLiftsTableParser()
    parser.feed(html)

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


def fetch_competition_history(username: str) -> list[dict]:
    """Fetches and parses the full meet-by-meet competition history for
    `username` from the "Competition Results" table on their profile page.

    Returns a list of dicts shaped for `db.insert_competition` (each also
    carries a `competition_date_iso` key), in whatever order
    openpowerlifting.org lists them (most recent first on the live site).
    Raises `FetchError` with a user-facing message on any failure,
    including an ambiguous username - mirrors `fetch_personal_bests`. Rows
    that cannot be mapped safely (unexpected cell count, unparseable date)
    are skipped rather than raising, since one malformed row should not
    block importing the rest of a lifter's history.
    """
    username = (username or "").strip()
    html, _url = _fetch_profile_html(username)

    _raise_if_disambiguation(username, html)

    parser = _MeetResultsTableParser()
    parser.feed(html)

    meets = []
    for row in parser.rows:
        meet = _row_to_meet(row["others"], row["attempts"])
        if meet is not None:
            meets.append(meet)
    return meets
