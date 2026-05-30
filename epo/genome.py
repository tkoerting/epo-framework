"""
EPO Template Genome -- Structural output optimization through evolutionary tracking.

Tracks which sections of LLM outputs survive user editing, which get deleted,
and which the user adds. Over N generations, the genome converges to the optimal
structure for each output type.
"""

import logging

from sqlalchemy import Integer, cast, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from epo.exceptions import GenomeNotFoundError
from epo.models import TemplateGenome, GenomeSection
from epo.schemas import GenomeSectionOut, GenomeStatsOut, TemplateGenomeOut

logger = logging.getLogger("epo.genome")

# Pruning thresholds
SURVIVAL_THRESHOLD = 0.2
MIN_OBSERVATIONS_FOR_PRUNING = 5


def _normalize_key(name: str) -> str:
    return name.lower().strip()


async def get_or_create_genome(db: AsyncSession, user_id: int, source_type: str) -> TemplateGenome:
    """Get existing genome or create a new one."""
    result = await db.execute(
        select(TemplateGenome).where(
            TemplateGenome.user_id == user_id,
            TemplateGenome.source_type == source_type,
        )
    )
    genome = result.scalar_one_or_none()
    if genome:
        return genome

    genome = TemplateGenome(user_id=user_id, source_type=source_type)
    db.add(genome)
    await db.flush()
    await db.refresh(genome)
    return genome


async def update_genome(
    db: AsyncSession,
    user_id: int,
    source_type: str,
    original_sections: list[str],
    final_sections: list[str],
    section_edit_distances: dict[str, float] | None = None,
) -> TemplateGenome:
    """
    Update the template genome after a user edits an LLM output.

    Uses Welford's online algorithm for running averages -- no history storage needed.

    Args:
        original_sections: Section headings from the LLM-generated output
        final_sections: Section headings from the user-edited version
        section_edit_distances: Optional per-section edit distances {section_name: score}
    """
    if section_edit_distances is None:
        section_edit_distances = {}

    genome = await get_or_create_genome(db, user_id, source_type)

    # Build lookup of final sections for survival check
    final_keys = set(_normalize_key(s) for s in final_sections)

    # Build position map from final sections
    final_positions = {}
    for i, s in enumerate(final_sections):
        key = _normalize_key(s)
        if key not in final_positions:
            final_positions[key] = float(i)

    # Load existing genome sections
    result = await db.execute(
        select(GenomeSection).where(GenomeSection.genome_id == genome.id)
    )
    existing_sections = {s.section_key: s for s in result.scalars().all()}

    # Update or create sections from original (LLM-generated)
    for i, section_name in enumerate(original_sections):
        key = _normalize_key(section_name)
        survived = 1.0 if key in final_keys else 0.0
        edit_dist = section_edit_distances.get(section_name, 0.0 if survived else 1.0)
        position = final_positions.get(key, float(i))

        if key in existing_sections:
            section = existing_sections[key]
            n = section.observation_count
            # Welford's online mean update
            section.survival_rate += (survived - section.survival_rate) / (n + 1)
            section.avg_edit_distance += (edit_dist - section.avg_edit_distance) / (n + 1)
            section.avg_position += (position - section.avg_position) / (n + 1)
            section.observation_count = n + 1
        else:
            section = GenomeSection(
                genome_id=genome.id,
                section_key=key,
                section_label=section_name,
                survival_rate=survived,
                avg_edit_distance=edit_dist,
                avg_position=position,
                observation_count=1,
                origin="generated",
            )
            db.add(section)
            existing_sections[key] = section

    # Detect user-added sections (in final but not in original)
    original_keys = set(_normalize_key(s) for s in original_sections)
    for i, section_name in enumerate(final_sections):
        key = _normalize_key(section_name)
        if key in original_keys:
            continue

        if key in existing_sections:
            section = existing_sections[key]
            n = section.observation_count
            section.survival_rate += (1.0 - section.survival_rate) / (n + 1)
            section.avg_position += (float(i) - section.avg_position) / (n + 1)
            section.observation_count = n + 1
        else:
            section = GenomeSection(
                genome_id=genome.id,
                section_key=key,
                section_label=section_name,
                survival_rate=1.0,
                avg_edit_distance=0.0,
                avg_position=float(i),
                observation_count=1,
                origin="user_added",
            )
            db.add(section)
            existing_sections[key] = section

    # Pruning: deactivate sections with low survival after enough observations
    for section in existing_sections.values():
        if (
            section.observation_count >= MIN_OBSERVATIONS_FOR_PRUNING
            and section.survival_rate < SURVIVAL_THRESHOLD
        ):
            section.active = False

    genome.generation += 1
    await db.flush()
    await db.refresh(genome)
    return genome


async def get_genome_sections(
    db: AsyncSession,
    user_id: int,
    source_type: str,
    active_only: bool = True,
) -> list[GenomeSection]:
    """Get genome sections sorted by avg_position."""
    result = await db.execute(
        select(TemplateGenome).where(
            TemplateGenome.user_id == user_id,
            TemplateGenome.source_type == source_type,
        )
    )
    genome = result.scalar_one_or_none()
    if not genome:
        return []

    filters = [GenomeSection.genome_id == genome.id]
    if active_only:
        filters.append(GenomeSection.active == True)  # noqa: E712

    result = await db.execute(
        select(GenomeSection).where(*filters).order_by(GenomeSection.avg_position)
    )
    return list(result.scalars().all())


def format_genome_for_prompt(sections: list[GenomeSection]) -> str:
    """Format active genome sections as a structural template for prompt injection."""
    if not sections:
        return ""
    lines = []
    for i, s in enumerate(sections, 1):
        pct = f"{s.survival_rate:.0%}"
        lines.append(f"{i}. {s.section_label} [Relevanz: {pct}]")
    return "\n\nStrukturvorlage (folge dieser Gliederung):\n" + "\n".join(lines)


async def get_genome_with_sections(
    db: AsyncSession,
    user_id: int,
    source_type: str,
) -> TemplateGenomeOut:
    """Get a genome with all its sections for API response."""
    result = await db.execute(
        select(TemplateGenome).where(
            TemplateGenome.user_id == user_id,
            TemplateGenome.source_type == source_type,
        )
    )
    genome = result.scalar_one_or_none()
    if not genome:
        raise GenomeNotFoundError(source_type)

    sections_result = await db.execute(
        select(GenomeSection)
        .where(GenomeSection.genome_id == genome.id)
        .order_by(GenomeSection.avg_position)
    )
    sections = [
        GenomeSectionOut.model_validate(s) for s in sections_result.scalars().all()
    ]

    genome_out = TemplateGenomeOut.model_validate(genome)
    genome_out.sections = sections
    return genome_out


async def get_genome_stats(
    db: AsyncSession,
    user_id: int,
    source_type: str,
) -> GenomeStatsOut:
    """Aggregated stats for a genome."""
    result = await db.execute(
        select(TemplateGenome).where(
            TemplateGenome.user_id == user_id,
            TemplateGenome.source_type == source_type,
        )
    )
    genome = result.scalar_one_or_none()
    if not genome:
        raise GenomeNotFoundError(source_type)

    stats_result = await db.execute(
        select(
            func.count(GenomeSection.id).label("total"),
            func.sum(cast(GenomeSection.active, Integer)).label("active_count"),
            func.avg(GenomeSection.survival_rate).label("avg_survival"),
        ).where(GenomeSection.genome_id == genome.id)
    )
    row = stats_result.one()
    total = row.total or 0
    active_count = row.active_count or 0

    # Count user-added
    added_result = await db.execute(
        select(func.count(GenomeSection.id)).where(
            GenomeSection.genome_id == genome.id,
            GenomeSection.origin == "user_added",
        )
    )
    user_added = added_result.scalar() or 0

    return GenomeStatsOut(
        source_type=source_type,
        generation=genome.generation,
        total_sections=total,
        active_sections=active_count,
        pruned_sections=total - active_count,
        user_added_sections=user_added,
        avg_survival_rate=round(float(row.avg_survival), 3) if row.avg_survival else None,
    )
