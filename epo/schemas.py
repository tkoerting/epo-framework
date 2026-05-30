"""
Pydantic schemas for EPO API endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    """Allowed source types for feedback and conventions."""
    briefing = "briefing"
    assistant = "assistant"
    content_draft = "content_draft"
    tool_result = "tool_result"


# --- Feedback ---

class FeedbackCreate(BaseModel):
    source_type: SourceType
    source_id: str = Field(..., min_length=1, max_length=200)
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_type: str
    source_id: str
    rating: int
    comment: Optional[str] = None
    created_at: datetime


class SourceTypeStats(BaseModel):
    count: int
    avg_rating: Optional[float] = None


class FeedbackStats(BaseModel):
    total: int = 0
    avg_rating: Optional[float] = None
    by_source_type: dict[str, SourceTypeStats] = {}
    recent: list[FeedbackOut] = []


# --- Convention ---

class ConventionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    rule: str = Field(..., min_length=1, max_length=2000)
    category: str = Field(..., pattern=r"^(code|content|briefing|report|general)$")
    source_type: Optional[SourceType] = None
    example_bad: Optional[str] = Field(None, max_length=1000)
    example_good: Optional[str] = Field(None, max_length=1000)


class ConventionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    rule: Optional[str] = Field(None, min_length=1, max_length=2000)
    active: Optional[bool] = None
    score: Optional[float] = Field(None, ge=0.0, le=10.0)
    example_bad: Optional[str] = Field(None, max_length=1000)
    example_good: Optional[str] = Field(None, max_length=1000)


class ConventionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    rule: str
    category: str
    source_type: Optional[str] = None
    example_bad: Optional[str] = None
    example_good: Optional[str] = None
    score: float
    active: bool
    created_at: datetime
    updated_at: datetime


# --- Metrics (for paper) ---

class RatingTrendEntry(BaseModel):
    date: str
    avg_rating: float
    count: int


class EditScoreTrendEntry(BaseModel):
    date: str
    avg_score: float
    count: int


class TopConventionEntry(BaseModel):
    name: str
    score: float
    category: str


class EPOMetrics(BaseModel):
    """Aggregated metrics for the EPO paper."""
    period_days: int
    total_feedback: int
    avg_rating: Optional[float] = None
    rating_trend: list[RatingTrendEntry] = []
    edit_score_trend: list[EditScoreTrendEntry] = []
    convention_count: int = 0
    active_convention_count: int = 0
    top_conventions: list[TopConventionEntry] = []
    feedback_by_type: dict[str, SourceTypeStats] = {}
    convergence_indicator: Optional[float] = None  # Slope of edit_score trend (negative = improving)


# --- Template Genome ---

class GenomeSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    section_key: str
    section_label: str
    survival_rate: float
    avg_edit_distance: float
    avg_position: float
    observation_count: int
    active: bool
    origin: str


class TemplateGenomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_type: str
    generation: int
    sections: list[GenomeSectionOut] = []
    created_at: datetime
    updated_at: datetime


class GenomeUpdateRequest(BaseModel):
    source_type: SourceType
    original_sections: list[str] = Field(..., min_length=1)
    final_sections: list[str]
    section_edit_distances: dict[str, float] = Field(default_factory=dict)


class GenomeStatsOut(BaseModel):
    source_type: str
    generation: int
    total_sections: int
    active_sections: int
    pruned_sections: int
    user_added_sections: int
    avg_survival_rate: Optional[float] = None
