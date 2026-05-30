"""
Edit-distance calculation for tracking how much LLM outputs get modified.
Core metric of Evolutionary Prompt Optimization.
"""

from difflib import SequenceMatcher


def calculate_edit_score(original: str, edited: str) -> float:
    """
    Normalized edit score between original LLM output and user-edited version.

    Returns:
        0.0 = identical (no edits)
        1.0 = completely different (full rewrite)

    Uses stdlib SequenceMatcher (Ratcliff/Obershelp pattern matching).
    No external dependencies.
    """
    if original == edited:
        return 0.0
    if not original or not edited:
        return 1.0
    similarity = SequenceMatcher(None, original, edited).ratio()
    return round(1.0 - similarity, 3)


def calculate_section_survival(original_sections: list[str], final_sections: list[str]) -> dict[str, float]:
    """
    Calculate survival rate for each section of a generated output.

    Args:
        original_sections: Section headings/titles from the generated output
        final_sections: Section headings/titles from the user-edited version

    Returns:
        Dict mapping section name to survival score (1.0 = kept, 0.0 = deleted)
    """
    final_set = set(s.lower().strip() for s in final_sections)
    survival = {}
    for section in original_sections:
        key = section.lower().strip()
        survival[section] = 1.0 if key in final_set else 0.0
    return survival


def calculate_section_edit_distances(
    original_sections: dict[str, str],
    final_sections: dict[str, str],
) -> dict[str, float]:
    """
    Calculate per-section edit distances.

    Args:
        original_sections: {section_name: section_content} from LLM output
        final_sections: {section_name: section_content} from user-edited version

    Returns:
        Dict mapping section name to edit score (0.0-1.0).
        Sections only in original get 1.0 (deleted). Sections only in final are omitted.
    """
    final_lookup = {k.lower().strip(): v for k, v in final_sections.items()}
    distances = {}
    for name, content in original_sections.items():
        key = name.lower().strip()
        if key in final_lookup:
            distances[name] = calculate_edit_score(content, final_lookup[key])
        else:
            distances[name] = 1.0  # deleted
    return distances


def detect_added_sections(original_sections: list[str], final_sections: list[str]) -> list[str]:
    """
    Detect sections that the user added (present in final but not in original).

    Returns:
        List of section names that were added by the user.
    """
    original_set = set(s.lower().strip() for s in original_sections)
    return [s for s in final_sections if s.lower().strip() not in original_set]
