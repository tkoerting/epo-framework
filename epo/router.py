"""
EPO FastAPI Router -- plug into any FastAPI app.

Usage:
    from epo.router import create_router
    epo_router = create_router(get_db=get_db, get_user=get_current_user_required)
    app.include_router(epo_router)

The host app must provide:
    - get_db: AsyncSession dependency (FastAPI Depends-compatible)
    - get_user: Returns object with .id attribute (FastAPI Depends-compatible)
"""

from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from epo import service
from epo import genome as genome_service
from epo.exceptions import ConventionNotFoundError, GenomeNotFoundError
from epo.schemas import (
    FeedbackCreate, FeedbackOut, FeedbackStats,
    ConventionCreate, ConventionUpdate, ConventionOut,
    EPOMetrics, SourceType,
    GenomeUpdateRequest, TemplateGenomeOut, GenomeStatsOut,
)
from epo.metrics import get_epo_metrics


def create_router(get_db: Callable[..., Any], get_user: Callable[..., Any]) -> APIRouter:
    """
    Create a configured EPO router with the host app's dependencies.

    Args:
        get_db: FastAPI dependency that yields AsyncSession
        get_user: FastAPI dependency that returns user object with .id
    """
    router = APIRouter(tags=["EPO"])

    # =============================================================================
    # Feedback
    # =============================================================================

    @router.post("/api/feedback", response_model=FeedbackOut, status_code=201)
    async def create_feedback(
        data: FeedbackCreate,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ):
        return FeedbackOut.model_validate(await service.create_feedback(db, user.id, data))

    @router.get("/api/feedback/stats", response_model=FeedbackStats)
    async def get_feedback_stats(
        source_type: Optional[SourceType] = Query(None),
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ):
        value = source_type.value if source_type else None
        return await service.get_feedback_stats(db, user.id, source_type=value)

    @router.get("/api/feedback", response_model=list[FeedbackOut])
    async def get_feedback_for_source(
        source_type: SourceType = Query(...),
        source_id: str = Query(..., min_length=1),
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ):
        feedbacks = await service.get_feedback_for_source(db, source_type.value, source_id, user.id)
        return [FeedbackOut.model_validate(f) for f in feedbacks]

    # =============================================================================
    # Conventions (static routes before parametrised)
    # =============================================================================

    @router.get("/api/conventions/for-prompt")
    async def conventions_for_prompt(
        source_type: Optional[SourceType] = Query(None),
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ) -> list[str]:
        value = source_type.value if source_type else None
        conventions = await service.get_conventions_for_prompt(db, user.id, source_type=value)
        return [f"- {c.name}: {c.rule}" for c in conventions]

    @router.post("/api/conventions/seed")
    async def seed_conventions(
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ):
        return await service.seed_conventions(db, user.id)

    @router.get("/api/conventions", response_model=list[ConventionOut])
    async def list_conventions(
        category: Optional[str] = Query(None),
        active_only: bool = Query(False),
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ):
        conventions = await service.list_conventions(db, user.id, category=category, active_only=active_only)
        return [ConventionOut.model_validate(c) for c in conventions]

    @router.post("/api/conventions", response_model=ConventionOut, status_code=201)
    async def create_convention(
        data: ConventionCreate,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ):
        return ConventionOut.model_validate(await service.create_convention(db, user.id, data))

    @router.patch("/api/conventions/{convention_id}", response_model=ConventionOut)
    async def update_convention(
        convention_id: int = Path(..., ge=1),
        data: ConventionUpdate = ...,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ):
        try:
            return ConventionOut.model_validate(await service.update_convention(db, convention_id, user.id, data))
        except ConventionNotFoundError:
            raise HTTPException(status_code=404, detail="Convention nicht gefunden")

    @router.delete("/api/conventions/{convention_id}")
    async def delete_convention(
        convention_id: int = Path(..., ge=1),
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ):
        try:
            await service.delete_convention(db, convention_id, user.id)
        except ConventionNotFoundError:
            raise HTTPException(status_code=404, detail="Convention nicht gefunden")
        return {"deleted": convention_id}

    # =============================================================================
    # Template Genome
    # =============================================================================

    @router.post("/api/genome/update", response_model=TemplateGenomeOut)
    async def update_genome(
        data: GenomeUpdateRequest,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ):
        """Update the template genome after a user edits an LLM output."""
        genome = await genome_service.update_genome(
            db, user.id, data.source_type.value,
            data.original_sections, data.final_sections,
            data.section_edit_distances or None,
        )
        return await genome_service.get_genome_with_sections(db, user.id, data.source_type.value)

    @router.get("/api/genome/{source_type}", response_model=TemplateGenomeOut)
    async def get_genome(
        source_type: SourceType,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ):
        try:
            return await genome_service.get_genome_with_sections(db, user.id, source_type.value)
        except GenomeNotFoundError:
            raise HTTPException(status_code=404, detail=f"Kein Genom fuer '{source_type.value}'")

    @router.get("/api/genome/{source_type}/for-prompt")
    async def genome_for_prompt(
        source_type: SourceType,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ) -> str:
        sections = await genome_service.get_genome_sections(db, user.id, source_type.value)
        return genome_service.format_genome_for_prompt(sections)

    @router.get("/api/genome/{source_type}/stats", response_model=GenomeStatsOut)
    async def genome_stats(
        source_type: SourceType,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ):
        try:
            return await genome_service.get_genome_stats(db, user.id, source_type.value)
        except GenomeNotFoundError:
            raise HTTPException(status_code=404, detail=f"Kein Genom fuer '{source_type.value}'")

    # =============================================================================
    # Metrics (for paper)
    # =============================================================================

    @router.get("/api/epo/metrics", response_model=EPOMetrics)
    async def get_metrics(
        period_days: int = Query(30, ge=1, le=365),
        db: AsyncSession = Depends(get_db),
        user=Depends(get_user),
    ):
        """EPO metrics for convergence analysis and paper data."""
        return await get_epo_metrics(db, user.id, period_days=period_days)

    return router
