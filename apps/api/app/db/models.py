"""SQLAlchemy persistence schema. All identifiers are UUID strings for SQLite/Postgres parity."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class ResearchRun(Base):
    __tablename__ = "research_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    requested_format: Mapped[str] = mapped_column(String(20), default="both")
    language: Mapped[str] = mapped_column(String(80), default="English")
    regions: Mapped[list[str]] = mapped_column(JSON, default=list)
    seeds: Mapped[list[str]] = mapped_column(JSON, default=list)
    recency_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    research_limits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SearchObservation(Base):
    __tablename__ = "search_observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    research_run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    source: Mapped[str] = mapped_column(String(32))
    profile_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    query: Mapped[str] = mapped_column(Text)
    result_position: Mapped[int] = mapped_column(Integer)
    observed_url: Mapped[str] = mapped_column(Text)
    observed_title: Mapped[str] = mapped_column(Text)
    observed_channel: Mapped[str | None] = mapped_column(Text, nullable=True)
    visible_views_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    visible_age_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    presented_as_short: Mapped[bool] = mapped_column(default=False)
    screenshot_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    youtube_channel_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    canonical_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ChannelSnapshot(Base):
    __tablename__ = "channel_snapshots"
    __table_args__ = (
        UniqueConstraint("research_run_id", "channel_id", "source", name="uq_channel_snapshot_run_source"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    research_run_id: Mapped[str | None] = mapped_column(ForeignKey("research_runs.id"), nullable=True, index=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    subscriber_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_view_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    video_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(32))


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    youtube_video_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    channel_id: Mapped[str | None] = mapped_column(ForeignKey("channels.id"), nullable=True, index=True)
    canonical_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    category_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    thumbnails: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class VideoSnapshot(Base):
    __tablename__ = "video_snapshots"
    __table_args__ = (
        UniqueConstraint("research_run_id", "video_id", "source", name="uq_video_snapshot_run_source"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    research_run_id: Mapped[str | None] = mapped_column(ForeignKey("research_runs.id"), nullable=True, index=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    view_count: Mapped[int] = mapped_column(BigInteger, default=0)
    like_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(32))


class CommentSample(Base):
    __tablename__ = "comment_samples"
    __table_args__ = (
        UniqueConstraint("video_id", "source_comment_id", "source", name="uq_comment_sample_source_identity"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    source_comment_id: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    like_count: Mapped[int] = mapped_column(BigInteger, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    is_pinned_if_known: Mapped[bool | None] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(String(32))


class BrowserMediaObservation(Base):
    __tablename__ = "browser_media_observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    research_run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    source_profile: Mapped[str] = mapped_column(String(120))
    is_short_presentation: Mapped[bool] = mapped_column(default=False)
    visible_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    frame_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    opening_visual_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption_style: Mapped[str | None] = mapped_column(Text, nullable=True)
    observable_structure: Mapped[list[str]] = mapped_column(JSON, default=list)
    feature_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class RuntimeArtifact(Base):
    __tablename__ = "runtime_artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    research_run_id: Mapped[str | None] = mapped_column(ForeignKey("research_runs.id"), nullable=True, index=True)
    artifact_type: Mapped[str] = mapped_column(String(48), index=True)
    path: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    state: Mapped[str] = mapped_column(String(24), default="available", index=True)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FormatCluster(Base):
    __tablename__ = "format_clusters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    research_run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    label: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    centroid: Mapped[list[float]] = mapped_column(JSON, default=list)
    representative_video_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class OutlierResult(Base):
    __tablename__ = "outlier_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    research_run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    comparison_cohort: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    baseline_metric: Mapped[float] = mapped_column(Float, default=0.0)
    metric_value: Mapped[float] = mapped_column(Float, default=0.0)
    outlier_multiple: Mapped[float] = mapped_column(Float, default=0.0)
    label: Mapped[str] = mapped_column(String(32))
    calculation_version: Mapped[str] = mapped_column(String(32), default="analytics-v1")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ViralMechanismAnalysis(Base):
    __tablename__ = "viral_mechanism_analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    format_cluster_id: Mapped[str] = mapped_column(ForeignKey("format_clusters.id"), index=True)
    primary_mechanism: Mapped[str] = mapped_column(Text)
    secondary_mechanisms: Mapped[list[str]] = mapped_column(JSON, default=list)
    viewer_question: Mapped[str] = mapped_column(Text)
    hook_pattern: Mapped[str] = mapped_column(Text)
    payoff_pattern: Mapped[str] = mapped_column(Text)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    alternative_explanation: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    provider: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(32))


class WinnerLoserComparison(Base):
    __tablename__ = "winner_loser_comparisons"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    research_run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    winner_video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"))
    loser_video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    provider: Mapped[str] = mapped_column(String(80))


class NicheCandidate(Base):
    __tablename__ = "niche_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    research_run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=1)
    broad_market: Mapped[str] = mapped_column(Text)
    niche: Mapped[str] = mapped_column(Text)
    sub_niche: Mapped[str] = mapped_column(Text)
    repeatable_format: Mapped[str] = mapped_column(Text)
    primary_viral_mechanism: Mapped[str] = mapped_column(Text)
    shorts_assessment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    longform_assessment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    bridge_assessment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    idea_ceiling: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    clip_ceiling: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    saturation_assessment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    demand_assessment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    momentum_assessment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    research_synthesis: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    critic_assessment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verdict: Mapped[str] = mapped_column(String(80))
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    research_run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(80))
    source_type: Mapped[str] = mapped_column(String(32))
    source_entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    human_readable_summary: Mapped[str] = mapped_column(Text)


class SourceRoutingAudit(Base):
    __tablename__ = "source_routing_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    research_run_id: Mapped[str | None] = mapped_column(ForeignKey("research_runs.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(80))
    selected_source: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    quota_delta: Mapped[int] = mapped_column(Integer, default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TaskJob(Base):
    __tablename__ = "task_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    research_run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class QuotaLedger(Base):
    """One database-backed daily YouTube quota counter shared by all processes."""

    __tablename__ = "quota_ledgers"
    ledger_date: Mapped[date] = mapped_column(Date, primary_key=True)
    used_search_calls: Mapped[int] = mapped_column(Integer, default=0)
    used_units: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


__all__ = [name for name in globals() if name[0].isupper()]
