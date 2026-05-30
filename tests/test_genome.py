"""Tests for EPO Template Genome -- the core evolutionary mechanism."""

from epo.genome import (
    _normalize_key,
    format_genome_for_prompt,
    SURVIVAL_THRESHOLD,
    MIN_OBSERVATIONS_FOR_PRUNING,
)
from epo.edit_distance import (
    calculate_section_edit_distances,
    detect_added_sections,
)


class TestNormalizeKey:
    def test_lowercase(self):
        assert _normalize_key("Kontext") == "kontext"

    def test_strip(self):
        assert _normalize_key("  Risiken  ") == "risiken"

    def test_combined(self):
        assert _normalize_key("  Naechste Schritte  ") == "naechste schritte"


class TestCalculateSectionEditDistances:
    def test_identical_sections(self):
        original = {"Kontext": "Gleicher Inhalt"}
        final = {"Kontext": "Gleicher Inhalt"}
        result = calculate_section_edit_distances(original, final)
        assert result["Kontext"] == 0.0

    def test_deleted_section(self):
        original = {"Kontext": "Etwas", "Einleitung": "Wird geloescht"}
        final = {"Kontext": "Etwas"}
        result = calculate_section_edit_distances(original, final)
        assert result["Einleitung"] == 1.0

    def test_edited_section(self):
        original = {"Kontext": "Der originale Text mit vielen Details hier drin."}
        final = {"Kontext": "Der originale Text mit wenigen Details hier drin."}
        result = calculate_section_edit_distances(original, final)
        assert 0.0 < result["Kontext"] < 0.3

    def test_case_insensitive_matching(self):
        original = {"KONTEXT": "Inhalt A"}
        final = {"kontext": "Inhalt A"}
        result = calculate_section_edit_distances(original, final)
        assert result["KONTEXT"] == 0.0

    def test_empty_inputs(self):
        result = calculate_section_edit_distances({}, {})
        assert result == {}


class TestDetectAddedSections:
    def test_no_additions(self):
        original = ["Kontext", "Risiken"]
        final = ["Kontext", "Risiken"]
        assert detect_added_sections(original, final) == []

    def test_user_added_section(self):
        original = ["Kontext"]
        final = ["Kontext", "Naechste Schritte"]
        result = detect_added_sections(original, final)
        assert result == ["Naechste Schritte"]

    def test_case_insensitive(self):
        original = ["KONTEXT"]
        final = ["kontext", "Risiken"]
        result = detect_added_sections(original, final)
        assert result == ["Risiken"]

    def test_all_new(self):
        original = ["Alt"]
        final = ["Neu1", "Neu2"]
        result = detect_added_sections(original, final)
        assert len(result) == 2


class TestFormatGenomeForPrompt:
    def test_empty_sections(self):
        assert format_genome_for_prompt([]) == ""

    def test_format_output(self):
        class FakeSection:
            section_label = "Kontext"
            survival_rate = 0.95

        class FakeSection2:
            section_label = "Naechste Schritte"
            survival_rate = 0.88

        result = format_genome_for_prompt([FakeSection(), FakeSection2()])
        assert "Strukturvorlage" in result
        assert "1. Kontext [Relevanz: 95%]" in result
        assert "2. Naechste Schritte [Relevanz: 88%]" in result


class TestWelfordAlgorithm:
    """Test the running average logic that update_genome uses."""

    def test_running_average_converges(self):
        """Simulate Welford's online mean for survival_rate."""
        # Section survives 7 out of 10 times -> should converge to 0.7
        survival_rate = 0.0
        observations = [1, 1, 1, 0, 1, 1, 0, 1, 0, 1]
        for i, survived in enumerate(observations):
            survival_rate += (survived - survival_rate) / (i + 1)
        assert round(survival_rate, 2) == 0.70

    def test_running_average_single(self):
        survival_rate = 0.0
        survival_rate += (1.0 - survival_rate) / 1
        assert survival_rate == 1.0

    def test_running_average_two(self):
        survival_rate = 1.0
        survival_rate += (0.0 - survival_rate) / 2
        assert survival_rate == 0.5


class TestPruningThresholds:
    def test_thresholds_are_reasonable(self):
        assert 0.0 < SURVIVAL_THRESHOLD < 0.5
        assert MIN_OBSERVATIONS_FOR_PRUNING >= 3
