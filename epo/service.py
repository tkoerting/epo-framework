"""
EPO Service Layer -- Feedback CRUD, Convention management, Prompt injection.
"""

import logging

from sqlalchemy import select, func, desc, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from epo.exceptions import ConventionNotFoundError
from epo.models import OutputFeedback, Convention
from epo.schemas import (
    FeedbackCreate, FeedbackOut, FeedbackStats, SourceTypeStats,
    ConventionCreate, ConventionUpdate,
)

logger = logging.getLogger("epo")


# =============================================================================
# Feedback
# =============================================================================


async def create_feedback(db: AsyncSession, user_id: int, data: FeedbackCreate) -> OutputFeedback:
    """UPSERT: If (user_id, source_type, source_id) exists, update. Otherwise insert."""
    result = await db.execute(
        select(OutputFeedback).where(
            OutputFeedback.user_id == user_id,
            OutputFeedback.source_type == data.source_type,
            OutputFeedback.source_id == data.source_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.rating = data.rating
        existing.comment = data.comment
        await db.flush()
        await db.refresh(existing)
        return existing

    feedback = OutputFeedback(
        user_id=user_id,
        source_type=data.source_type,
        source_id=data.source_id,
        rating=data.rating,
        comment=data.comment,
    )

    async with db.begin_nested():
        db.add(feedback)
        try:
            await db.flush()
        except IntegrityError:
            # Race condition: another request inserted between SELECT and INSERT
            result2 = await db.execute(
                select(OutputFeedback).where(
                    OutputFeedback.user_id == user_id,
                    OutputFeedback.source_type == data.source_type,
                    OutputFeedback.source_id == data.source_id,
                )
            )
            existing = result2.scalar_one_or_none()
            if existing:
                existing.rating = data.rating
                existing.comment = data.comment
                await db.flush()
                await db.refresh(existing)
                return existing
            raise

    await db.refresh(feedback)
    return feedback


async def get_feedback_stats(db: AsyncSession, user_id: int, source_type: str | None = None) -> FeedbackStats:
    """Aggregated stats: total, avg_rating, by_source_type, recent 10."""
    base_filter = [OutputFeedback.user_id == user_id]
    if source_type:
        base_filter.append(OutputFeedback.source_type == source_type)

    result = await db.execute(
        select(
            func.count(OutputFeedback.id).label("total"),
            func.avg(OutputFeedback.rating).label("avg_rating"),
        ).where(*base_filter)
    )
    row = result.one()
    total = row.total or 0
    avg_rating = round(float(row.avg_rating), 2) if row.avg_rating else None

    # By source_type -- always shows full breakdown (overview)
    type_result = await db.execute(
        select(
            OutputFeedback.source_type,
            func.count(OutputFeedback.id).label("count"),
            func.avg(OutputFeedback.rating).label("avg"),
        )
        .where(OutputFeedback.user_id == user_id)
        .group_by(OutputFeedback.source_type)
    )
    by_source_type = {}
    for r in type_result.all():
        by_source_type[r.source_type] = SourceTypeStats(
            count=r.count,
            avg_rating=round(float(r.avg), 2) if r.avg else None,
        )

    recent_result = await db.execute(
        select(OutputFeedback).where(*base_filter).order_by(desc(OutputFeedback.created_at)).limit(10)
    )
    recent = [FeedbackOut.model_validate(f) for f in recent_result.scalars().all()]

    return FeedbackStats(total=total, avg_rating=avg_rating, by_source_type=by_source_type, recent=recent)


async def get_feedback_for_source(db: AsyncSession, source_type: str, source_id: str, user_id: int) -> list[OutputFeedback]:
    """All feedbacks for a specific source, filtered by user."""
    result = await db.execute(
        select(OutputFeedback)
        .where(OutputFeedback.user_id == user_id, OutputFeedback.source_type == source_type, OutputFeedback.source_id == source_id)
        .order_by(desc(OutputFeedback.created_at))
    )
    return list(result.scalars().all())


# =============================================================================
# Conventions
# =============================================================================


async def list_conventions(db: AsyncSession, user_id: int, category: str | None = None, active_only: bool = False) -> list[Convention]:
    """All conventions for a user, optionally filtered."""
    filters = [Convention.user_id == user_id]
    if category:
        filters.append(Convention.category == category)
    if active_only:
        filters.append(Convention.active == True)  # noqa: E712
    result = await db.execute(select(Convention).where(*filters).order_by(desc(Convention.score), Convention.name))
    return list(result.scalars().all())


async def get_conventions_for_prompt(db: AsyncSession, user_id: int, source_type: str | None = None) -> list[Convention]:
    """
    Active conventions for prompt injection.
    Returns max 20, sorted by score DESC.
    Includes global rules (source_type IS NULL) + type-specific rules.
    """
    source_filter = Convention.source_type.is_(None)
    if source_type:
        source_filter = or_(Convention.source_type.is_(None), Convention.source_type == source_type)

    result = await db.execute(
        select(Convention)
        .where(Convention.user_id == user_id, Convention.active == True, source_filter)  # noqa: E712
        .order_by(desc(Convention.score))
        .limit(20)
    )
    return list(result.scalars().all())


def format_conventions_for_prompt(conventions: list[Convention]) -> str:
    """Format conventions as a prompt-ready string block."""
    if not conventions:
        return ""
    rules = "\n".join(f"- {c.rule}" for c in conventions)
    return f"\n\nKonventionen (befolge diese Regeln):\n{rules}"


async def create_convention(db: AsyncSession, user_id: int, data: ConventionCreate) -> Convention:
    """Create a new convention."""
    convention = Convention(
        user_id=user_id, name=data.name, rule=data.rule, category=data.category,
        source_type=data.source_type, example_bad=data.example_bad, example_good=data.example_good,
    )
    db.add(convention)
    await db.flush()
    await db.refresh(convention)
    return convention


async def update_convention(db: AsyncSession, convention_id: int, user_id: int, data: ConventionUpdate) -> Convention:
    """Update a convention. Allowlist pattern."""
    result = await db.execute(select(Convention).where(Convention.id == convention_id, Convention.user_id == user_id))
    convention = result.scalar_one_or_none()
    if not convention:
        raise ConventionNotFoundError(convention_id)

    allowed_fields = {"name", "rule", "active", "score", "example_bad", "example_good"}
    for field, value in data.model_dump(exclude_unset=True).items():
        if field in allowed_fields:
            setattr(convention, field, value)

    await db.flush()
    await db.refresh(convention)
    return convention


async def delete_convention(db: AsyncSession, convention_id: int, user_id: int) -> bool:
    """Delete a convention."""
    result = await db.execute(select(Convention).where(Convention.id == convention_id, Convention.user_id == user_id))
    convention = result.scalar_one_or_none()
    if not convention:
        raise ConventionNotFoundError(convention_id)
    await db.delete(convention)
    await db.flush()
    return True


# --- Seed ---

SEED_CONVENTIONS = [
    {"name": "Deutsche UI-Texte", "rule": "Alle UI-Texte und Outputs auf Deutsch. Variablennamen und Code-Kommentare auf Englisch.", "category": "general"},
    {"name": "Keine Emojis", "rule": "Keine Emojis in UI-Texten, Reports oder Content verwenden.", "category": "content"},
    {"name": "Korrekte Umlaute", "rule": "Immer echte Umlaute verwenden (ä, ö, ü, ß statt ae, oe, ue, ss).", "category": "content"},
    {"name": "Kompakte Briefings", "rule": "Briefings maximal 400 Wörter. Keine Floskeln oder Füllsätze.", "category": "briefing"},
    {"name": "Nächste Schritte", "rule": "Jedes Briefing und jeden Report mit einer konkreten 'Nächste Schritte' Section beenden.", "category": "briefing"},
    {"name": "Kurze Listen", "rule": "Bullet-Listen mit maximal 5-7 Punkten. Längere Listen gruppieren oder priorisieren.", "category": "general"},
    {"name": "Direkter Ton", "rule": "Keine Einleitungssätze wie 'Gerne erstelle ich...' oder 'Hier ist eine Zusammenfassung...'. Direkt mit dem Inhalt beginnen.", "category": "content"},
    {"name": "Business-Impact", "rule": "Reports und Analysen immer mit Umsatz- oder Business-Bezug versehen. Zahlen und Metriken bevorzugen.", "category": "report"},
    {"name": "Handlungsempfehlungen", "rule": "Berichte und Analysen enden mit konkreten, umsetzbaren Empfehlungen.", "category": "report"},
    {"name": "KPI-fokussiert", "rule": "Status-Reports beginnen mit den wichtigsten KPIs und Zahlen, dann Details.", "category": "report"},
    {"name": "Risiken benennen", "rule": "Meeting-Briefings enthalten einen Abschnitt zu Risiken und offenen Punkten.", "category": "briefing"},
    {"name": "Kontext vor Detail", "rule": "Erst den Kontext und Hintergrund liefern, dann ins Detail gehen. Nie mit Details starten.", "category": "general"},
    {"name": "Entscheidungsvorlagen", "rule": "Bei Meetings: Optionen mit Vor-/Nachteilen und eine Empfehlung formulieren, nicht nur Fakten auflisten.", "category": "briefing"},
    {"name": "Markdown-Struktur", "rule": "Überschriften, Listen und Tabellen nutzen für bessere Lesbarkeit. Keine Textwüsten.", "category": "general"},
    {"name": "Quellen referenzieren", "rule": "Wenn Daten aus dem System verwendet werden, die Quellen benennen.", "category": "general"},
]


async def seed_conventions(db: AsyncSession, user_id: int) -> dict:
    """Create seed conventions. Idempotent: only if user has none."""
    result = await db.execute(select(func.count(Convention.id)).where(Convention.user_id == user_id))
    if (result.scalar() or 0) > 0:
        return {"seeded": 0, "detail": "User hat bereits Conventions"}

    for seed in SEED_CONVENTIONS:
        db.add(Convention(user_id=user_id, name=seed["name"], rule=seed["rule"], category=seed["category"]))
    await db.flush()
    return {"seeded": len(SEED_CONVENTIONS)}
