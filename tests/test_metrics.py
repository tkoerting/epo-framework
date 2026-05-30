"""Tests for EPO metrics calculation."""

from epo.metrics import _calculate_convergence


class TestCalculateConvergence:
    def test_insufficient_data(self):
        assert _calculate_convergence([]) is None
        assert _calculate_convergence([{"score": 0.5}]) is None
        assert _calculate_convergence([{"score": 0.5}, {"score": 0.4}]) is None

    def test_improving_trend(self):
        """Decreasing edit scores = negative slope = improving."""
        data = [{"score": 0.8}, {"score": 0.6}, {"score": 0.4}, {"score": 0.2}]
        slope = _calculate_convergence(data)
        assert slope is not None
        assert slope < 0

    def test_degrading_trend(self):
        """Increasing edit scores = positive slope = degrading."""
        data = [{"score": 0.2}, {"score": 0.4}, {"score": 0.6}, {"score": 0.8}]
        slope = _calculate_convergence(data)
        assert slope is not None
        assert slope > 0

    def test_flat_trend(self):
        """Constant scores = zero slope."""
        data = [{"score": 0.5}, {"score": 0.5}, {"score": 0.5}]
        slope = _calculate_convergence(data)
        assert slope == 0.0

    def test_uses_avg_score_key(self):
        """Should also work with avg_score key."""
        data = [{"avg_score": 0.8}, {"avg_score": 0.6}, {"avg_score": 0.4}]
        slope = _calculate_convergence(data)
        assert slope is not None
        assert slope < 0
