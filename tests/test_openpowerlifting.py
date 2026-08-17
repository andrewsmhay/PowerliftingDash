"""Unit tests for the OpenPowerlifting personal-best fetcher, run entirely
against saved fixture HTML - no real network access, per the "explicit,
on-demand, never in a test loop" spirit of the integration itself.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.openpowerlifting import FetchError, _BestLiftsTableParser, _parse_float, fetch_personal_bests

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
