"""
EPO CLAUDE.md Integration -- Inject learned conventions into CLAUDE.md.

Uses markers to manage the EPO section without touching the rest of the file.
"""

from pathlib import Path

EPO_START_MARKER = "<!-- EPO:START -->"
EPO_END_MARKER = "<!-- EPO:END -->"


def inject_into_claude_md(
    conventions: list[str],
    project_root: Path,
    genome_template: str | None = None,
) -> bool:
    """
    Write learned EPO conventions into the project's CLAUDE.md.

    Inserts or updates a marked section. Does not touch other content.

    Args:
        conventions: List of convention rule strings
        project_root: Path to the git project root
        genome_template: Optional formatted genome template string

    Returns:
        True if CLAUDE.md was modified, False if no changes needed.
    """
    claude_md_path = project_root / "CLAUDE.md"

    # Build the EPO block
    lines = [EPO_START_MARKER]
    lines.append("")
    lines.append("## Gelernte Regeln (EPO -- nicht manuell editieren)")
    lines.append("")

    if conventions:
        for rule in conventions:
            lines.append(f"- {rule}")
        lines.append("")

    if genome_template:
        lines.append(genome_template)
        lines.append("")

    if not conventions and not genome_template:
        lines.append("_Noch keine Regeln gelernt. Nutze `epo analyze` nach einigen Sessions._")
        lines.append("")

    lines.append(EPO_END_MARKER)
    epo_block = "\n".join(lines)

    # Read existing file or start fresh
    if claude_md_path.exists():
        content = claude_md_path.read_text(encoding="utf-8")
    else:
        content = ""

    # Replace existing EPO block or append
    if EPO_START_MARKER in content and EPO_END_MARKER in content:
        start_idx = content.index(EPO_START_MARKER)
        end_idx = content.index(EPO_END_MARKER) + len(EPO_END_MARKER)
        new_content = content[:start_idx] + epo_block + content[end_idx:]
    else:
        # Append with spacing
        separator = "\n\n" if content and not content.endswith("\n\n") else "\n" if content and not content.endswith("\n") else ""
        new_content = content + separator + epo_block + "\n"

    # Check if anything changed
    if claude_md_path.exists() and claude_md_path.read_text(encoding="utf-8") == new_content:
        return False

    claude_md_path.write_text(new_content, encoding="utf-8")
    return True


def read_conventions_from_claude_md(project_root: Path) -> list[str]:
    """
    Read EPO conventions back from CLAUDE.md.

    Used for bootstrapping on a new machine after git pull.

    Returns:
        List of convention rule strings, or empty list if no EPO block found.
    """
    claude_md_path = project_root / "CLAUDE.md"
    if not claude_md_path.exists():
        return []

    content = claude_md_path.read_text(encoding="utf-8")
    if EPO_START_MARKER not in content or EPO_END_MARKER not in content:
        return []

    start_idx = content.index(EPO_START_MARKER) + len(EPO_START_MARKER)
    end_idx = content.index(EPO_END_MARKER)
    block = content[start_idx:end_idx]

    rules = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and not stripped.startswith("_"):
            rules.append(stripped[2:])  # Remove "- " prefix

    return rules


def remove_from_claude_md(project_root: Path) -> bool:
    """Remove the EPO section from CLAUDE.md."""
    claude_md_path = project_root / "CLAUDE.md"
    if not claude_md_path.exists():
        return False

    content = claude_md_path.read_text(encoding="utf-8")
    if EPO_START_MARKER not in content:
        return False

    start_idx = content.index(EPO_START_MARKER)
    end_idx = content.index(EPO_END_MARKER) + len(EPO_END_MARKER)

    # Remove the block and any trailing whitespace
    new_content = content[:start_idx].rstrip() + content[end_idx:].lstrip("\n")
    claude_md_path.write_text(new_content, encoding="utf-8")
    return True
