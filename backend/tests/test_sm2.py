"""Unit tests for the SM-2 spaced-repetition algorithm."""

import pytest
from database import apply_sm2


class TestApplySM2FailingQuality:
    """Quality < 3 should reset to day-1 schedule regardless of history."""

    @pytest.mark.parametrize("quality", [0, 1, 2])
    def test_resets_interval_to_1(self, quality):
        interval, ease, reps = apply_sm2(interval=10, ease=2.5, reps=5, quality=quality)
        assert interval == 1

    @pytest.mark.parametrize("quality", [0, 1, 2])
    def test_resets_reps_to_0(self, quality):
        _, _, reps = apply_sm2(interval=10, ease=2.5, reps=5, quality=quality)
        assert reps == 0

    @pytest.mark.parametrize("quality", [0, 1, 2])
    def test_preserves_ease_factor(self, quality):
        _, ease, _ = apply_sm2(interval=10, ease=2.5, reps=5, quality=quality)
        assert ease == 2.5


class TestApplySM2PassingQuality:
    """Quality >= 3 should advance the schedule."""

    def test_first_review_interval_is_1(self):
        interval, _, reps = apply_sm2(interval=1, ease=2.5, reps=0, quality=4)
        assert interval == 1
        assert reps == 1

    def test_second_review_interval_is_6(self):
        interval, _, reps = apply_sm2(interval=1, ease=2.5, reps=1, quality=4)
        assert interval == 6
        assert reps == 2

    def test_subsequent_review_multiplies_by_ease(self):
        # reps=2, interval=6, ease=2.5 → next = round(6 * 2.5) = 15
        interval, _, reps = apply_sm2(interval=6, ease=2.5, reps=2, quality=4)
        assert interval == 15
        assert reps == 3

    def test_quality_5_increases_ease(self):
        # Δease = 0.1 - (5-5)*(0.08 + (5-5)*0.02) = 0.1
        _, ease, _ = apply_sm2(interval=1, ease=2.5, reps=0, quality=5)
        assert ease == pytest.approx(2.6)

    def test_quality_3_decreases_ease(self):
        # Δease = 0.1 - (5-3)*(0.08 + (5-3)*0.02) = 0.1 - 2*(0.12) = -0.14
        _, ease, _ = apply_sm2(interval=1, ease=2.5, reps=0, quality=3)
        assert ease == pytest.approx(2.36)

    def test_ease_factor_floor_at_1_3(self):
        # Starting ease near floor with bad-but-passing quality should not go below 1.3
        _, ease, _ = apply_sm2(interval=1, ease=1.3, reps=0, quality=3)
        assert ease >= 1.3
