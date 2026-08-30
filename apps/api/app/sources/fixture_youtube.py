"""Fixture YouTube source with the same methods as the live API adapter."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..domain.enums import SourceType
from .base import ChannelRecord, CommentRecord, DiscoveryRequest, DiscoveryResult, SearchResult, VideoRecord


class FixtureYoutubeSource:
    def __init__(self, scenario: str = "strong", fixture_root: Path | None = None) -> None:
        root = fixture_root or Path(__file__).resolve().parents[4] / "fixtures" / "youtube_api"
        file = root / f"{scenario}.json"
        if not file.exists():
            file = root / "strong.json"
        self.scenario = scenario
        self.payload: dict[str, Any] = json.loads(file.read_text())
        self.videos = {item["id"]: item for item in self.payload.get("videos", [])}
        self.channels = {item["id"]: item for item in self.payload.get("channels", [])}
        self.comments = self.payload.get("comments", {})
        anchor = date.fromisoformat(self.payload.get("fixture_anchor_date", date.today().isoformat()))
        self.date_shift = timedelta(days=(date.today() - anchor).days)

    async def discover(self, request: DiscoveryRequest) -> DiscoveryResult:
        results: list[SearchResult] = []
        query = request.query.lower()
        candidates = [item for item in self.payload.get("search", []) if not query or any(term in item.get("title", "").lower() for term in query.split())]
        if not candidates:
            candidates = self.payload.get("search", [])
        for position, item in enumerate(candidates[:request.max_results], start=1):
            results.append(SearchResult(
                youtube_video_id=item["video_id"], canonical_url=item["url"], title=item["title"],
                channel_id=item["channel_id"], channel_title=item["channel_title"],
                visible_views_text=item.get("visible_views_text", ""), visible_age_text=item.get("visible_age_text", ""),
                presented_as_short=item.get("presented_as_short", False), result_position=position,
                raw_payload=item,
            ))
        return DiscoveryResult(SourceType.FIXTURE_API, request.query, results)

    async def enrich_videos(self, video_ids: list[str], context_by_video_id: dict[str, dict[str, Any]] | None = None) -> list[VideoRecord]:
        return [_video(item, self.date_shift) for video_id in video_ids if (item := self.videos.get(video_id))]

    async def enrich_channels(self, channel_ids: list[str]) -> list[ChannelRecord]:
        return [_channel(item) for channel_id in channel_ids if (item := self.channels.get(channel_id))]

    async def expand_channel_uploads(self, channel_id: str, limit: int = 20) -> list[VideoRecord]:
        ids = self.channels.get(channel_id, {}).get("uploads", [])[:limit]
        return await self.enrich_videos(ids)

    async def sample_comments(self, video_id: str, limit: int = 5) -> list[CommentRecord]:
        return [_comment(item, self.date_shift) for item in self.comments.get(video_id, [])[:limit]]


def _channel(item: dict[str, Any]) -> ChannelRecord:
    return ChannelRecord(
        youtube_channel_id=item["id"], canonical_url=item["url"], title=item["title"],
        description=item.get("description", ""), subscriber_count=item.get("subscriber_count"),
        total_view_count=item.get("total_view_count"), video_count=item.get("video_count"),
    )


def _video(item: dict[str, Any], date_shift: timedelta = timedelta()) -> VideoRecord:
    return VideoRecord(
        youtube_video_id=item["id"], channel_id=item["channel_id"], canonical_url=item["url"],
        title=item["title"], description=item.get("description", ""), duration_seconds=item.get("duration_seconds"),
        published_at=datetime.fromisoformat(item["published_at"]) + date_shift, category_id=item.get("category_id"),
        tags=item.get("tags", []), thumbnails=item.get("thumbnails", {}), view_count=item["view_count"],
        like_count=item.get("like_count"), comment_count=item.get("comment_count"), is_short=item.get("is_short", False),
        format_label=item.get("format_label", ""), topic=item.get("topic", ""),
    )


def _comment(item: dict[str, Any], date_shift: timedelta = timedelta()) -> CommentRecord:
    return CommentRecord(
        source_comment_id=item["id"], text=item["text"], like_count=item.get("like_count", 0),
        published_at=datetime.fromisoformat(item["published_at"]) + date_shift if item.get("published_at") else None,
        is_pinned_if_known=item.get("is_pinned"),
    )
