"""
EPO Database Models -- OutputFeedback + Convention.

These models use SQLAlchemy declarative mapping. The host application must:
1. Use the same Base class (or register these tables)
2. Provide user_id values from its own user management
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase


class EPOBase(DeclarativeBase):
    """Base class for EPO models. Override with your app's Base if needed."""
    pass


class OutputFeedback(EPOBase):
    """Tracks user feedback (thumbs up/down, rating) on LLM-generated outputs."""

    __tablename__ = "output_feedback"

    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "source_id", name="uq_feedback_user_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1=thumbs down, 5=thumbs up
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<OutputFeedback {self.id}: user={self.user_id} {self.source_type}:{self.source_id} rating={self.rating}>"


class Convention(EPOBase):
    """Learned rules/patterns for prompt evolution."""

    __tablename__ = "conventions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rule: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    example_bad: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_good: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1.0")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Convention {self.id}: {self.name} ({self.category}) score={self.score}>"


class TemplateGenome(EPOBase):
    """Per-user, per-output-type structural template that evolves over generations."""

    __tablename__ = "template_genomes"

    __table_args__ = (
        UniqueConstraint("user_id", "source_type", name="uq_genome_user_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<TemplateGenome {self.id}: user={self.user_id} {self.source_type} gen={self.generation}>"


class GenomeSection(EPOBase):
    """A structural section tracked within a template genome."""

    __tablename__ = "genome_sections"

    __table_args__ = (
        UniqueConstraint("genome_id", "section_key", name="uq_section_genome_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    genome_id: Mapped[int] = mapped_column(Integer, ForeignKey("template_genomes.id"), nullable=False, index=True)
    section_key: Mapped[str] = mapped_column(String(200), nullable=False)
    section_label: Mapped[str] = mapped_column(Text, nullable=False)
    survival_rate: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    avg_edit_distance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="generated")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<GenomeSection {self.id}: '{self.section_label}' survival={self.survival_rate:.0%} obs={self.observation_count}>"
