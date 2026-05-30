"""
EPO -- Evolutionary Prompt Optimization

A feedback-driven middleware layer that makes LLM outputs better over time.
Captures implicit user feedback (edits, ratings) and evolves prompts automatically.

Public API:
- Models: OutputFeedback, Convention, EPOBase, TemplateGenome, GenomeSection
- Service: get_conventions_for_prompt, format_conventions_for_prompt
- Genome: update_genome, get_genome_sections, format_genome_for_prompt
- Router: create_router(get_db, get_user) -> APIRouter
- Edit Distance: calculate_edit_score, calculate_section_survival
- Metrics: get_epo_metrics (convergence, effectiveness, paper-ready data)
- Exceptions: EPOError, ConventionNotFoundError, GenomeNotFoundError
"""

from epo.models import OutputFeedback, Convention, EPOBase, TemplateGenome, GenomeSection
from epo.edit_distance import calculate_edit_score, calculate_section_survival
from epo.router import create_router
from epo.service import get_conventions_for_prompt, format_conventions_for_prompt
from epo.genome import update_genome, get_genome_sections, format_genome_for_prompt
from epo.exceptions import EPOError, ConventionNotFoundError, GenomeNotFoundError
from epo.schemas import SourceType

__all__ = [
    "OutputFeedback",
    "Convention",
    "EPOBase",
    "TemplateGenome",
    "GenomeSection",
    "calculate_edit_score",
    "calculate_section_survival",
    "create_router",
    "get_conventions_for_prompt",
    "format_conventions_for_prompt",
    "update_genome",
    "get_genome_sections",
    "format_genome_for_prompt",
    "EPOError",
    "ConventionNotFoundError",
    "GenomeNotFoundError",
    "SourceType",
]

__version__ = "0.4.0"
