"""Unit tests for the OpenPowerlifting personal-best fetcher, run entirely
against saved fixture HTML - no real network access, per the "explicit,
on-demand, never in a test loop" spirit of the integration itself.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.openpowerlifting import (
    FetchError,
    _BestLiftsTableParser,
    _MeetResultsTableParser,
    _best_attempt,
    _ordinal,
    _parse_float,
    _row_to_meet,
    fetch_competition_history,
    fetch_personal_bests,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class _FakeResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parse_float_handles_blank_and_dash():
    assert _parse_float("") is None
    assert _parse_float("-") is None
    assert _parse_float(None) is None
    assert _parse_float("193") == 193.0
    assert _parse_float("555.75") == 555.75


def test_best_lifts_table_parser_reads_first_table_only():
    parser = _BestLiftsTableParser()
    parser.feed(_fixture("opl_profile.html"))

    assert parser.saw_disambiguation is False
    assert parser.rows[0] == ["Raw", "193", "115", "246", "549", "555.75", ""]
    # A second "Single" row exists on this profile - confirms multiple rows
    # in the one table are all captured, not just the first.
    assert parser.rows[1][0] == "Single"


def test_best_lifts_table_parser_detects_disambiguation_page():
    parser = _BestLiftsTableParser()
    parser.feed(_fixture("opl_disambiguation.html"))

    assert parser.saw_disambiguation is True


def test_fetch_personal_bests_parses_raw_row():
    with patch("httpx.get", return_value=_FakeResponse(200, _fixture("opl_profile.html"))):
        result = fetch_personal_bests("kimberlywalford")

    assert result["equip"] == "Raw"
    assert result["squat"] == 193.0
    assert result["bench"] == 115.0
    assert result["deadlift"] == 246.0
    assert result["total"] == 549.0
    assert result["profile_url"] == "https://www.openpowerlifting.org/u/kimberlywalford"


def test_fetch_personal_bests_raises_on_404():
    with patch("httpx.get", return_value=_FakeResponse(404, "404")):
        try:
            fetch_personal_bests("thisdoesnotexist999999")
            assert False, "expected FetchError"
        except FetchError as exc:
            assert "thisdoesnotexist999999" in str(exc)


def test_fetch_personal_bests_raises_on_disambiguation_with_suggestions():
    with patch("httpx.get", return_value=_FakeResponse(200, _fixture("opl_disambiguation.html"))):
        try:
            fetch_personal_bests("joshuabaker")
            assert False, "expected FetchError"
        except FetchError as exc:
            message = str(exc)
            assert "joshuabaker1" in message
            assert "joshuabaker2" in message


def test_fetch_personal_bests_rejects_empty_username():
    try:
        fetch_personal_bests("")
        assert False, "expected FetchError"
    except FetchError:
        pass


def test_fetch_personal_bests_raises_when_no_table_found():
    with patch("httpx.get", return_value=_FakeResponse(200, "<html><body>no table here</body></html>")):
        try:
            fetch_personal_bests("someone")
            assert False, "expected FetchError"
        except FetchError:
            pass


# --- Competition history sync -------------------------------------------------


def test_ordinal_formats_plain_integers_and_leaves_other_text_alone():
    assert _ordinal("1") == "1st"
    assert _ordinal("2") == "2nd"
    assert _ordinal("3") == "3rd"
    assert _ordinal("4") == "4th"
    assert _ordinal("11") == "11th"
    assert _ordinal("12") == "12th"
    assert _ordinal("13") == "13th"
    assert _ordinal("21") == "21st"
    assert _ordinal("DQ") == "DQ"
    assert _ordinal("") == ""
    assert _ordinal(None) == ""


def test_best_attempt_ignores_blanks_and_failed_lifts():
    assert _best_attempt(["155", "162.5", "170", ""]) == 170.0
    assert _best_attempt(["95", "102.5", "-105", ""]) == 102.5
    assert _best_attempt(["", "", "", ""]) is None
    assert _best_attempt(["-100", "-105", "-110", ""]) is None


def test_row_to_meet_skips_rows_with_the_wrong_cell_count():
    # 11 cells instead of the required 12 - a real mismatch would otherwise
    # silently shift every later field (e.g. bodyweight landing in placing).
    others = ["1", "CPU", "2026-03-14", "Canada", "Provincials", "Open", "30", "Raw", "93", "91.4", "620"]
    attempts = {"squat": ["220"], "bench": ["150"], "deadlift": ["250"]}
    assert _row_to_meet(others, attempts) is None


def test_row_to_meet_skips_rows_with_an_unparseable_date():
    others = ["1", "CPU", "not-a-date", "Canada", "Provincials", "Open", "30", "Raw", "93", "91.4", "620", "450.1"]
    attempts = {"squat": ["220"], "bench": ["150"], "deadlift": ["250"]}
    assert _row_to_meet(others, attempts) is None


def test_row_to_meet_maps_a_well_formed_row():
    others = ["1", "CPU", "2026-03-14", "Canada", "Provincials", "Open", "30", "Raw", "93", "91.4", "620", "450.1"]
    attempts = {
        "squat": ["200", "210", "220", ""],
        "bench": ["140", "-145", "", ""],
        "deadlift": ["230", "240", "250", ""],
    }
    meet = _row_to_meet(others, attempts)
    assert meet == {
        "competition_date_iso": "2026-03-14",
        "meet_name": "Provincials",
        "federation": "CPU",
        "location": "Canada",
        "weight_class": "93",
        "placing": "1st",
        "bodyweight_kg": 91.4,
        "squat_kg": 220.0,
        "bench_kg": 140.0,
        "deadlift_kg": 250.0,
        "total_kg": 620.0,
        "notes": "Imported from OpenPowerlifting.",
    }


def test_meet_results_table_parser_reads_second_table_only():
    parser = _MeetResultsTableParser()
    parser.feed(_fixture("opl_profile.html"))

    # 71 real meet rows on this fixture profile - confirmed by manual count
    # against the fixture's <tr> total (75 minus the 3 best-lifts-table rows
    # minus the results-table header row).
    assert len(parser.rows) == 71


def test_fetch_competition_history_parses_real_fixture_end_to_end():
    with patch("httpx.get", return_value=_FakeResponse(200, _fixture("opl_profile.html"))):
        meets = fetch_competition_history("kimberlywalford")

    assert len(meets) == 71

    dq_meets = [m for m in meets if m["placing"] == "DQ"]
    assert len(dq_meets) == 2
    for meet in dq_meets:
        assert meet["squat_kg"] is None
        assert meet["bench_kg"] is None
        assert meet["deadlift_kg"] is None
        assert meet["total_kg"] is None

    # Two rows share this date because the lifter was entered in two
    # divisions (Masters 1 and Open) at the same meet with the same total -
    # the parser itself does not dedupe (that is the sync route's job), so
    # both rows should come through with identical totals.
    same_day = [m for m in meets if m["competition_date_iso"] == "2024-03-02"]
    assert len(same_day) == 2
    assert {m["total_kg"] for m in same_day} == {527.5}


def test_fetch_competition_history_raises_on_404():
    with patch("httpx.get", return_value=_FakeResponse(404, "404")):
        try:
            fetch_competition_history("thisdoesnotexist999999")
            assert False, "expected FetchError"
        except FetchError as exc:
            assert "thisdoesnotexist999999" in str(exc)


def test_fetch_competition_history_raises_on_disambiguation():
    with patch("httpx.get", return_value=_FakeResponse(200, _fixture("opl_disambiguation.html"))):
        try:
            fetch_competition_history("joshuabaker")
            assert False, "expected FetchError"
        except FetchError as exc:
            assert "joshuabaker1" in str(exc)


def test_fetch_competition_history_rejects_empty_username():
    try:
        fetch_competition_history("")
        assert False, "expected FetchError"
    except FetchError:
        pass


def test_fetch_competition_history_returns_empty_list_when_no_results_table():
    with patch("httpx.get", return_value=_FakeResponse(200, "<html><body>no tables here</body></html>")):
        assert fetch_competition_history("someone") == []
