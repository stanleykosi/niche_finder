"""Local browser fixture adapter. It models the semantic result contract without live YouTube."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..domain.enums import SourceType
from .base import BrowserMediaRecord, DiscoveryRequest, DiscoveryResult, SearchResult


class FixtureBrowserSource:
    def __init__(self, scenario: str = "strong", fixture_root: Path | None = None) -> None:
        root = fixture_root or Path(__file__).resolve().parents[4] / "fixtures" / "browser"
        path = root / f"{scenario}.json"
        if not path.exists():
            path = root / "strong.json"
        self.payload: dict[str, Any] = json.loads(path.read_text())
        self.scenario = scenario

    async def discover(self, request: DiscoveryRequest) -> DiscoveryResult:
        items = self.payload.get("search", [])[:request.max_results]
        results = [SearchResult(
            youtube_video_id=item["video_id"], canonical_url=item["url"], title=item["title"],
            channel_id=item.get("channel_id", ""), channel_title=item.get("channel_title", ""),
            visible_views_text=item.get("visible_views_text", ""), visible_age_text=item.get("visible_age_text", ""),
            presented_as_short=item.get("presented_as_short", False), result_position=index,
            screenshot_ref=item.get("screenshot_ref"), raw_payload=item,
        ) for index, item in enumerate(items, start=1)]
        return DiscoveryResult(SourceType.FIXTURE_BROWSER, request.query, results, ["fixture://screenshots/search-strong.png"])

    async def inspect_video(self, video_id: str, canonical_url: str | None = None, profile_id: str = "fixture-profile", capture_frames: bool = True) -> BrowserMediaRecord:
        item = self.payload.get("videos", {}).get(video_id)
        if not isinstance(item, dict):
            missing_fields = [
                "shorts_presentation", "visible_transcript", "thumbnail", "frames",
                "opening_visual", "captions", "observable_structure", "duration",
                "scene_changes", "reveal", "motion", "pacing", "editing_pattern",
            ]
            return BrowserMediaRecord(
                source_profile=profile_id,
                is_short_presentation=False,
                visible_transcript=None,
                thumbnail_ref=None,
                frame_refs=[],
                opening_visual_summary=None,
                caption_style=None,
                observable_structure=[],
                observed_at=datetime.now(timezone.utc),
                confidence=0.0,
                visual_features={
                    "inspection_status": "unavailable",
                    "error_code": "not_found",
                    "source": "fixture",
                    "video_id": video_id,
                    "missing_fields": missing_fields,
                },
            )
        return BrowserMediaRecord(
            source_profile=profile_id, is_short_presentation=item.get("is_short_presentation", False),
            visible_transcript=item.get("visible_transcript"), thumbnail_ref=item.get("thumbnail_ref"),
            frame_refs=item.get("frame_refs", []) if capture_frames else [], opening_visual_summary=item.get("opening_visual_summary") if capture_frames else None,
            caption_style=item.get("caption_style"), observable_structure=item.get("observable_structure", []),
            observed_at=datetime.now(timezone.utc), confidence=item.get("confidence", 0.0),
            first_spoken_line=item.get("first_spoken_line") or ((item.get("visible_transcript") or "").split(".")[0] or None),
            duration_seconds=item.get("duration_seconds"), scene_change_count=item.get("scene_change_count"),
            average_shot_duration_seconds=item.get("average_shot_duration_seconds"), reveal_timestamp_seconds=item.get("reveal_timestamp_seconds"),
            caption_density=item.get("caption_density"), motion_score=item.get("motion_score"),
            pacing_score=item.get("pacing_score"), visual_features=item.get("visual_features", {"inspection_status": "available", "source": "fixture"}),
            music_cue_count=item.get("music_cue_count"), editing_pattern=item.get("editing_pattern"),
        )

    async def inspect_channel(self, channel_id: str) -> dict[str, Any]:
        return self.payload.get("channels", {}).get(channel_id, {"channel_id": channel_id, "videos": []})
