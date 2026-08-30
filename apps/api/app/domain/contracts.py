"""Pydantic contracts shared by HTTP, orchestration, source and report layers."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from .enums import RequestedFormat, RunStatus, SourceType, Verdict
from .youtube_urls import classify_direct_youtube_url


MAX_SEED_COUNT = 20
MAX_SEED_LENGTH = 2048
SeedInput = Annotated[str, StringConstraints(max_length=MAX_SEED_LENGTH)]


class ResearchLimits(BaseModel):
    max_queries: int = Field(default=5, ge=1, le=20)
    max_results_per_query: int = Field(default=20, ge=1, le=30)
    max_channels: int = Field(default=10, ge=1, le=100)
    max_videos: int = Field(default=30, ge=1, le=100)
    max_expansion_depth: int = Field(default=1, ge=0, le=3)
    deep_research: bool = False


class ResearchRunCreate(BaseModel):
    requested_format: RequestedFormat = RequestedFormat.BOTH
    language: str = "English"
    regions: list[str] = Field(default_factory=lambda: ["US"])
    seeds: list[SeedInput] = Field(default_factory=list, max_length=MAX_SEED_COUNT)
    broad_discovery: bool = False
    recency_days: int = Field(default=90, ge=1, le=730)
    production_constraints: list[str] = Field(default_factory=lambda: ["faceless"], max_length=10)
    minimum_idea_ceiling: int = Field(default=10, ge=10, le=30)
    minimum_clip_coverage: float = Field(default=0.7, ge=0.7, le=1)
    minimum_successful_channels: int = Field(default=3, ge=3, le=20)
    minimum_recent_outliers: int = Field(default=3, ge=3, le=50)
    minimum_outlier_channels: int = Field(default=2, ge=2, le=20)
    minimum_winner_loser_pairs: int = Field(default=3, ge=3, le=20)
    maximum_saturation: float = Field(default=0.75, ge=0, le=0.75)
    limits: ResearchLimits = Field(default_factory=ResearchLimits)

    @field_validator("seeds", mode="before")
    @classmethod
    def reject_oversized_seed_collection(cls, value: Any) -> Any:
        """Reject raw work before normalization or query expansion can iterate it."""
        if isinstance(value, (list, tuple)) and len(value) > MAX_SEED_COUNT:
            raise ValueError(f"at most {MAX_SEED_COUNT} seeds may be submitted")
        return value

    @field_validator("seeds")
    @classmethod
    def normalize_seeds(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(seed.strip() for seed in value if seed.strip()))

    @field_validator("language")
    @classmethod
    def english_only_for_mvp(cls, value: str) -> str:
        if value.strip().lower() not in {"english", "en", "en-us", "en-gb"}:
            raise ValueError("the MVP researches English-language niches only")
        return "English"

    @field_validator("production_constraints")
    @classmethod
    def normalize_production_constraints(cls, value: list[str]) -> list[str]:
        constraints = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if any(len(item) > 120 for item in constraints):
            raise ValueError("production constraints must be at most 120 characters each")
        return constraints

    @model_validator(mode="after")
    def apply_empty_seed_portfolio_defaults(self) -> "ResearchRunCreate":
        """Keep API and UI broad-discovery defaults at canonical 12/20 markets."""
        if not self.seeds and "max_queries" not in self.limits.model_fields_set:
            self.limits.max_queries = 20 if self.limits.deep_research else 12
        return self


class ResearchRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: RunStatus
    requested_format: RequestedFormat
    language: str
    seeds: list[str]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    fixture_mode: bool = False
    metadata_source: SourceType


class SourceHealth(BaseModel):
    source: SourceType
    healthy: bool | None
    mode: str
    detail: str
    last_checked_at: datetime


class QuotaStatus(BaseModel):
    daily_budget: int
    reserved_search_calls: int
    used_search_calls: int
    remaining_search_calls: int
    can_search: bool
    daily_unit_budget: int = 10000
    reserved_units: int = 500
    used_units: int = 0
    remaining_units: int = 10000


class Evidence(BaseModel):
    id: UUID
    evidence_type: str
    source_type: SourceType
    observed_at: datetime
    payload: dict[str, Any]
    confidence: float | None = None
    human_readable_summary: str


class Assessment(BaseModel):
    fit: str
    score: float | None
    reason: str
    evidence_ids: list[UUID] = Field(default_factory=list)


class NicheCandidateResponse(BaseModel):
    id: UUID
    rank: int
    broad_market: str
    niche: str
    sub_niche: str
    repeatable_format: str
    primary_viral_mechanism: str
    shorts_assessment: Assessment
    longform_assessment: Assessment
    bridge_assessment: dict[str, Any] = Field(default_factory=dict)
    idea_ceiling: dict[str, Any]
    clip_ceiling: dict[str, Any]
    saturation_assessment: dict[str, Any]
    demand_assessment: dict[str, Any]
    momentum_assessment: dict[str, Any]
    research_synthesis: dict[str, Any] = Field(default_factory=dict)
    critic_assessment: dict[str, Any] = Field(default_factory=dict)
    confidence: float
    verdict: Verdict
    evidence_ids: list[UUID] = Field(default_factory=list)


class ReportResponse(BaseModel):
    research_run_id: UUID
    generated_at: datetime
    why_now: str
    evidence_summary: dict[str, Any]
    candidates: list[NicheCandidateResponse]
    viral_mechanisms: list[dict[str, Any]] = Field(default_factory=list)
    winner_loser_comparisons: list[dict[str, Any]] = Field(default_factory=list)
    research_synthesis: dict[str, Any] = Field(default_factory=dict)
    action_plan: dict[str, Any]
    fixture_mode: bool = False
    metadata_source: SourceType


class VideoAnalysisRequest(BaseModel):
    url: str = Field(min_length=1, max_length=MAX_SEED_LENGTH)

    @field_validator("url")
    @classmethod
    def require_video_url(cls, value: str) -> str:
        candidate = value.strip()
        if classify_direct_youtube_url(candidate) != "video":
            raise ValueError("a valid YouTube watch, Shorts, or youtu.be video URL is required")
        return candidate


class ChannelAnalysisRequest(BaseModel):
    url: str = Field(min_length=1, max_length=MAX_SEED_LENGTH)

    @field_validator("url")
    @classmethod
    def require_channel_url(cls, value: str) -> str:
        candidate = value.strip()
        if classify_direct_youtube_url(candidate) != "channel":
            raise ValueError("a valid YouTube channel URL is required")
        return candidate


class NicheAnalysisRequest(BaseModel):
    niche: str = Field(min_length=1, max_length=MAX_SEED_LENGTH)
    requested_format: RequestedFormat = RequestedFormat.BOTH

    @field_validator("niche")
    @classmethod
    def normalize_niche(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("niche must not be blank")
        return candidate
