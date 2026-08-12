import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.metrics import build_lift_cards, build_body_cards, build_total_card


def test_lift_progress_is_plain_current_over_target():
    """Progress bars must reflect current/target directly. Regression test
    for a bug where the bar used the competition value as its baseline: a
    lifter sitting exactly at their competition number (no change since the
    meet) saw a 0% bar even when very close to their target, which
    contradicted the "remaining" figure shown next to it."""
    entry = {
        "squat_1rm_current": 161.0,
        "squat_1rm_target": 170.0,
        "squat_1rm_competition": 161.0,  # same as current: no change since comp
        "squat_1rm_remaining": 9.0,
        "squat_1rm_competition_delta": 0.0,
    }
    cards = build_lift_cards(entry)
    squat = next(c for c in cards if c["label"] == "Squat")
    assert squat["progress_pct"] == 94.7


def test_lift_progress_ignores_competition_value_entirely():
    """Two lifters with the same current/target but different competition
    numbers must get the same progress percentage."""
    base = {
        "squat_1rm_current": 150.0,
        "squat_1rm_target": 150.0,
        "squat_1rm_remaining": 0.0,
        "squat_1rm_competition_delta": 0.0,
    }
    low_comp = {**base, "squat_1rm_competition": 100.0}
    high_comp = {**base, "squat_1rm_competition": 149.0}
    pct_low = next(c for c in build_lift_cards(low_comp) if c["label"] == "Squat")["progress_pct"]
    pct_high = next(c for c in build_lift_cards(high_comp) if c["label"] == "Squat")["progress_pct"]
    assert pct_low == pct_high == 100.0


def test_total_card_progress_is_plain_ratio():
    entry = {
        "total_weight_lifted_current": 441.0,
        "total_weight_lifted_target": 480.0,
        "total_weight_lifted_in_competition": 441.0,
        "total_weight_lifted_remaining": 39.0,
    }
    total = build_total_card(entry)
    assert total["progress_pct"] == 91.9


def test_body_card_progress_unaffected():
    entry = {"body_weight_mass": 82.0, "body_weight_mass_target": 80.0}
    cards = build_body_cards(entry)
    weight = next(c for c in cards if c["label"] == "Body Weight")
    assert weight["progress_pct"] == 100.0


def test_progress_pct_none_when_missing_current_or_target():
    entry = {"squat_1rm_target": 170.0}
    cards = build_lift_cards(entry)
    squat = next(c for c in cards if c["label"] == "Squat")
    assert squat["progress_pct"] is None
