"""Tests for EPO exceptions."""

from epo.exceptions import EPOError, ConventionNotFoundError


class TestConventionNotFoundError:
    def test_is_epo_error(self):
        err = ConventionNotFoundError(42)
        assert isinstance(err, EPOError)
        assert isinstance(err, Exception)

    def test_stores_convention_id(self):
        err = ConventionNotFoundError(99)
        assert err.convention_id == 99

    def test_message(self):
        err = ConventionNotFoundError(7)
        assert "7" in str(err)
