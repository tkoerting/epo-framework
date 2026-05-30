"""
EPO Metrics -- Paper-ready data collection.

Provides aggregated metrics for the Evolutionary Prompt Optimization paper:
- Edit-score convergence over time
- Convention effectiveness
- Feedback distribution and trends
- Convergence indicator (slope of edit-score trend)
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from epo.models import OutputFeedback, Convention
from epo.schemas import (
    EPOMetrics, RatingTrendEntry, EditScoreTrendEntry,
    TopConventionEntry, SourceTypeStats,
)

logger = logging.getLogger("epo.metrics")


async def get_epo_metrics(
    db: AsyncSession,
    user_id: int,
    period_days: int = 30,
    edit_scores: list[dict] | None = None,
) -> EPOMetrics:
    """
    Collect aggregated EPO metrics for the paper.

    Args:
        db: Database session
        user_id: User to collect metrics for
        period_days: How many days to look back
        edit_scores: Optional list of {"date": str, "score": float} from the host app
                     (EPO doesn't own the edit_score data -- the host app tracks it on
                      its own models, e.g. Workspace.edit_score)
    """
    since = datetime.now(timezone.utc) - timedelta(days=period_days)

    # --- Feedback metrics ---
    feedback_result = await db.execute(
        select(
            func.count(OutputFeedback.id).label("total"),
            func.avg(OutputFeedback.rating).label("avg"),
        ).where(OutputFeedback.user_id == user_id, OutputFeedback.created_at >= since)
    )
    fb_row = feedback_result.one()
    total_feedback = fb_row.total or 0
    avg_rating = round(float(fb_row.avg), 2) if fb_row.avg else None

    # Rating trend (per day)
    rating_trend_result = await db.execute(
        select(
            cast(OutputFeedback.created_at, Date).label("date"),
            func.avg(OutputFeedback.rating).label("avg_rating"),
            func.count(OutputFeedback.id).label("count"),
        )
        .where(OutputFeedback.user_id == user_id, OutputFeedback.created_at >= since)
        .group_by(cast(OutputFeedback.created_at, Date))
        .order_by(cast(OutputFeedback.created_at, Date))
    )
    rating_trend = [
        RatingTrendEntry(date=str(r.date), avg_rating=round(float(r.avg_rating), 2), count=r.count)
        for r in rating_trend_result.all()
    ]

    # Feedback by type
    type_result = await db.execute(
        select(
            OutputFeedback.source_type,
            func.count(OutputFeedback.id).label("count"),
            func.avg(OutputFeedback.rating).label("avg"),
        )
        .where(OutputFeedback.user_id == user_id, OutputFeedback.created_at >= since)
        .group_by(OutputFeedback.source_type)
    )
    feedback_by_type = {}
    for r in type_result.all():
        feedback_by_type[r.source_type] = SourceTypeStats(
            count=r.count,
            avg_rating=round(float(r.avg), 2) if r.avg else None,
        )

    # --- Convention metrics ---
    conv_result = await db.execute(
        select(
            func.count(Convention.id).label("total"),
            func.sum(cast(Convention.active, Integer)).label("active_count"),
        ).where(Convention.user_id == user_id)
    )
    conv_row = conv_result.one()
    convention_count = conv_row.total or 0
    active_convention_count = conv_row.active_count or 0

    # Top conventions by score
    top_result = await db.execute(
        select(Convention.name, Convention.score, Convention.category)
        .where(Convention.user_id == user_id, Convention.active == True)  # noqa: E712
        .order_by(Convention.score.desc())
        .limit(10)
    )
    top_conventions = [
        TopConventionEntry(name=r.name, score=r.score, category=r.category)
        for r in top_result.all()
    ]

    # --- Edit-score trend (from host app data) ---
    # Host apps may use "score" or "avg_score" as key -- normalize to "avg_score"
    normalized_scores = []
    for s in (edit_scores or []):
        entry = dict(s)
        if "score" in entry and "avg_score" not in entry:
            entry["avg_score"] = entry.pop("score")
        normalized_scores.append(entry)
    edit_score_trend = [
        EditScoreTrendEntry(**s) for s in normalized_scores
    ]
    convergence_indicator = _calculate_convergence(edit_scores or [])

    return EPOMetrics(
        period_days=period_days,
        total_feedback=total_feedback,
        avg_rating=avg_rating,
        rating_trend=rating_trend,
        edit_score_trend=edit_score_trend,
        convention_count=convention_count,
        active_convention_count=active_convention_count,
        top_conventions=top_conventions,
        feedback_by_type=feedback_by_type,
        convergence_indicator=convergence_indicator,
    )


def _calculate_convergence(edit_scores: list[dict]) -> float | None:
    """
    Calculate the slope of the edit-score trend line.

    Returns:
        Negative = improving (edit scores decreasing over time)
        Positive = degrading
        None = insufficient data (need at least 3 points)
    """
    if len(edit_scores) < 3:
        return None

    # Simple linear regression on the scores
    n = len(edit_scores)
    scores = [s.get("score", s.get("avg_score", 0)) for s in edit_scores]
    x = list(range(n))

    mean_x = sum(x) / n
    mean_y = sum(scores) / n

    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, scores))
    denominator = sum((xi - mean_x) ** 2 for xi in x)

    if denominator == 0:
        return 0.0

    slope = numerator / denominator
    return round(slope, 4)
