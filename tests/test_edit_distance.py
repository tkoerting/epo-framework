"""Tests for EPO edit-distance calculation."""

from epo.edit_distance import calculate_edit_score, calculate_section_survival


class TestCalculateEditScore:
    def test_identical_texts(self):
        assert calculate_edit_score("hello world", "hello world") == 0.0

    def test_completely_different(self):
        score = calculate_edit_score("aaa", "zzz")
        assert score > 0.9

    def test_empty_original(self):
        assert calculate_edit_score("", "something") == 1.0

    def test_empty_edited(self):
        assert calculate_edit_score("something", "") == 1.0

    def test_both_empty(self):
        assert calculate_edit_score("", "") == 0.0

    def test_minor_edit(self):
        original = "Das ist ein langer Text mit vielen Woertern darin."
        edited = "Das ist ein langer Text mit einigen Woertern darin."
        score = calculate_edit_score(original, edited)
        assert 0.0 < score < 0.3

    def test_major_edit(self):
        original = "Komplett anderer Inhalt hier."
        edited = "Voellig neuer Text mit anderen Woertern und Saetzen und mehr Inhalt."
        score = calculate_edit_score(original, edited)
        assert score > 0.4

    def test_score_range(self):
        score = calculate_edit_score("abc def", "abc xyz")
        assert 0.0 <= score <= 1.0


class TestCalculateSectionSurvival:
    def test_all_survive(self):
        original = ["Kontext", "Risiken", "Naechste Schritte"]
        final = ["Kontext", "Risiken", "Naechste Schritte"]
        result = calculate_section_survival(original, final)
        assert all(v == 1.0 for v in result.values())

    def test_none_survive(self):
        original = ["Einleitung", "Zusammenfassung"]
        final = ["Analyse", "Empfehlungen"]
        result = calculate_section_survival(original, final)
        assert all(v == 0.0 for v in result.values())

    def test_partial_survival(self):
        original = ["Kontext", "Einleitung", "Naechste Schritte"]
        final = ["Kontext", "Naechste Schritte"]
        result = calculate_section_survival(original, final)
        assert result["Kontext"] == 1.0
        assert result["Einleitung"] == 0.0
        assert result["Naechste Schritte"] == 1.0

    def test_case_insensitive(self):
        original = ["KONTEXT"]
        final = ["kontext"]
        result = calculate_section_survival(original, final)
        assert result["KONTEXT"] == 1.0
