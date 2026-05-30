"""Tests for EPO Pydantic schemas."""

import pytest
from pydantic import ValidationError

from epo.schemas import (
    FeedbackCreate, ConventionCreate, ConventionUpdate, SourceType,
    SourceTypeStats, RatingTrendEntry, EditScoreTrendEntry, TopConventionEntry,
)


class TestSourceType:
    def test_all_values(self):
        assert set(SourceType) == {
            SourceType.briefing, SourceType.assistant,
            SourceType.content_draft, SourceType.tool_result,
        }

    def test_string_coercion(self):
        assert SourceType("briefing") == SourceType.briefing
        assert str(SourceType.briefing) == "SourceType.briefing"
        assert SourceType.briefing.value == "briefing"


class TestFeedbackCreate:
    def test_valid_feedback(self):
        fb = FeedbackCreate(source_type="briefing", source_id="ws-123", rating=5)
        assert fb.rating == 5
        assert fb.source_type == SourceType.briefing

    def test_all_valid_source_types(self):
        for st in ["briefing", "assistant", "content_draft", "tool_result"]:
            fb = FeedbackCreate(source_type=st, source_id="id-1", rating=3)
            assert fb.source_type.value == st

    def test_invalid_source_type(self):
        with pytest.raises(ValidationError):
            FeedbackCreate(source_type="invalid", source_id="ws-123", rating=5)

    def test_rating_out_of_range(self):
        with pytest.raises(ValidationError):
            FeedbackCreate(source_type="briefing", source_id="ws-123", rating=0)
        with pytest.raises(ValidationError):
            FeedbackCreate(source_type="briefing", source_id="ws-123", rating=6)

    def test_empty_source_id(self):
        with pytest.raises(ValidationError):
            FeedbackCreate(source_type="briefing", source_id="", rating=5)

    def test_optional_comment(self):
        fb = FeedbackCreate(source_type="assistant", source_id="msg-1", rating=3, comment="Gut")
        assert fb.comment == "Gut"

    def test_comment_none_by_default(self):
        fb = FeedbackCreate(source_type="briefing", source_id="ws-1", rating=4)
        assert fb.comment is None


class TestConventionCreate:
    def test_valid_convention(self):
        c = ConventionCreate(name="Test", rule="Do X", category="general")
        assert c.source_type is None

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            ConventionCreate(name="Test", rule="Do X", category="invalid")

    def test_valid_categories(self):
        for cat in ["code", "content", "briefing", "report", "general"]:
            c = ConventionCreate(name="Test", rule="Do X", category=cat)
            assert c.category == cat

    def test_with_source_type(self):
        c = ConventionCreate(name="Test", rule="Do X", category="general", source_type="briefing")
        assert c.source_type == SourceType.briefing

    def test_invalid_source_type(self):
        with pytest.raises(ValidationError):
            ConventionCreate(name="Test", rule="Do X", category="general", source_type="invalid")


class TestConventionUpdate:
    def test_partial_update(self):
        u = ConventionUpdate(active=False)
        assert u.active is False
        assert u.name is None

    def test_score_range(self):
        with pytest.raises(ValidationError):
            ConventionUpdate(score=-1.0)
        with pytest.raises(ValidationError):
            ConventionUpdate(score=11.0)

    def test_valid_score_boundaries(self):
        assert ConventionUpdate(score=0.0).score == 0.0
        assert ConventionUpdate(score=10.0).score == 10.0

    def test_all_fields_unset(self):
        u = ConventionUpdate()
        dumped = u.model_dump(exclude_unset=True)
        assert dumped == {}


class TestTypedSchemas:
    def test_source_type_stats(self):
        s = SourceTypeStats(count=10, avg_rating=4.5)
        assert s.count == 10
        assert s.avg_rating == 4.5

    def test_source_type_stats_no_rating(self):
        s = SourceTypeStats(count=0)
        assert s.avg_rating is None

    def test_rating_trend_entry(self):
        e = RatingTrendEntry(date="2026-03-17", avg_rating=4.2, count=5)
        assert e.date == "2026-03-17"

    def test_edit_score_trend_entry(self):
        e = EditScoreTrendEntry(date="2026-03-17", avg_score=0.3, count=8)
        assert e.avg_score == 0.3

    def test_top_convention_entry(self):
        e = TopConventionEntry(name="Test", score=8.5, category="general")
        assert e.name == "Test"
