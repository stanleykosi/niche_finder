"""Source protocols and normalized records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from ..domain.enums import SourceType


@dataclass(frozen=True)
class DiscoveryRequest:
    query: str
    requested_format: str = "both"
    recency_days: int = 90
    max_results: int = 20
    profile_id: str = "fixture-profile"
    language: str = "en"
    region: str = "US"
    order: str = "relevance"


@dataclass(frozen=True)
class SearchResult:
    youtube_video_id: str
    canonical_url: str
    title: str
    channel_id: str
    channel_title: str
    visible_views_text: str
    visible_age_text: str
    presented_as_short: bool
    result_position: int
    screenshot_ref: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiscoveryResult:
    source: SourceType
    query: str
    results: list[SearchResult]
    screenshot_refs: list[str] = field(default_factory=list)
    partial: bool = False
    missing_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChannelRecord:
    youtube_channel_id: str
    canonical_url: str
    title: str
    description: str = ""
    subscriber_count: int | None = None
    total_view_count: int | None = None
    video_count: int | None = None


@dataclass(frozen=True)
class VideoRecord:
    youtube_video_id: str
    channel_id: str
    canonical_url: str
    title: str
    description: str
    duration_seconds: int | None
    published_at: datetime
    category_id: str | None
    tags: list[str]
    thumbnails: dict[str, Any]
    view_count: int
    like_count: int | None = None
    comment_count: int | None = None
    is_short: bool = False
    format_label: str = ""
    topic: str = ""
    # Source-specific evidence that must survive normalization. In particular,
    # keyless metadata may affirm portrait, landscape, or an unknown aspect
    # ratio; duration must not overwrite that observation.
    shorts_evidence: str = "unspecified"


@dataclass(frozen=True)
class CommentRecord:
    source_comment_id: str
    text: str
    like_count: int
    published_at: datetime | None
    is_pinned_if_known: bool | None = None


@dataclass(frozen=True)
class SourceDiagnostic:
    """A bounded, provenance-bearing observation about unusable source data."""

    diagnostic_type: str
    source_entity_id: str
    channel_id: str | None
    source_url: str | None
    reason: str
    error_code: str
    observed_at: datetime
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserMediaRecord:
    source_profile: str
    is_short_presentation: bool
    visible_transcript: str | None
    thumbnail_ref: str | None
    frame_refs: list[str]
    opening_visual_summary: str | None
    caption_style: str | None
    observable_structure: list[str]
    observed_at: datetime
    confidence: float
    first_spoken_line: str | None = None
    duration_seconds: float | None = None
    scene_change_count: int | None = None
    average_shot_duration_seconds: float | None = None
    reveal_timestamp_seconds: float | None = None
    caption_density: float | None = None
    motion_score: float | None = None
    pacing_score: float | None = None
    music_cue_count: int | None = None
    editing_pattern: str | None = None
    visual_features: dict[str, Any] = field(default_factory=dict)


class DiscoverySource(Protocol):
    async def discover(self, request: DiscoveryRequest) -> DiscoveryResult: ...


class EnrichmentSource(Protocol):
    async def enrich_videos(self, video_ids: list[str], context_by_video_id: dict[str, dict[str, Any]] | None = None) -> list[VideoRecord]: ...
    async def enrich_channels(self, channel_ids: list[str]) -> list[ChannelRecord]: ...
    async def expand_channel_uploads(self, channel_id: str, limit: int = 20) -> list[VideoRecord]: ...
    async def sample_comments(self, video_id: str, limit: int = 5) -> list[CommentRecord]: ...
