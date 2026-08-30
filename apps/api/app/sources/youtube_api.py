"""Official YouTube Data API adapter. Never construct it in closed mode."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..core.config import AppMode
from ..core.errors import ClosedModeViolation, NicheIntelError, ErrorCode
from ..domain.enums import SourceType
from .base import ChannelRecord, CommentRecord, DiscoveryRequest, DiscoveryResult, EnrichmentSource, SearchResult, SourceDiagnostic, VideoRecord
from .quota import QuotaManager
from ..research.preprocessing import preprocess_video


class YouTubeDataApiSource(EnrichmentSource):
    base_url = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str | None, mode: AppMode, quota: QuotaManager, timeout: float = 20.0) -> None:
        if mode == AppMode.CLOSED_TEST:
            raise ClosedModeViolation("YouTube Data API is unavailable in closed_test mode")
        if not api_key:
            raise NicheIntelError("YOUTUBE_API_KEY is required for the YouTube API", ErrorCode.CONFIGURATION)
        self.api_key = api_key
        self.quota = quota
        self.timeout = timeout
        self._diagnostics: list[SourceDiagnostic] = []

    async def _get(self, resource: str, params: dict[str, Any], attempts: int = 3) -> dict[str, Any]:
        params = {**params, "key": self.api_key}
        for attempt in range(attempts):
            operation = f"{resource}.list"
            # Reserve quota immediately before every network attempt. A 5xx or
            # timeout still consumed a Data API request and must be visible in
            # the shared ledger before a retry is issued.
            self.quota.consume(operation, _OPERATION_UNITS.get(operation, 1))
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(f"{self.base_url}/{resource}", params=params)
                if response.status_code == 429 or _is_quota_response(response):
                    raise NicheIntelError("YouTube API quota exceeded", ErrorCode.QUOTA_EXHAUSTED)
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == attempts - 1:
                    raise NicheIntelError(f"transient YouTube API failure: {exc}", ErrorCode.SOURCE_UNAVAILABLE) from exc
                await asyncio.sleep(0.1 * (2**attempt))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {500, 502, 503, 504}:
                    raise NicheIntelError(f"YouTube API request failed with HTTP {exc.response.status_code}", ErrorCode.SOURCE_UNAVAILABLE) from exc
                if attempt == attempts - 1:
                    raise NicheIntelError(f"transient YouTube API failure: HTTP {exc.response.status_code}", ErrorCode.SOURCE_UNAVAILABLE) from exc
                await asyncio.sleep(0.1 * (2**attempt))
        raise AssertionError("unreachable")

    async def discover(self, request: DiscoveryRequest) -> DiscoveryResult:
        params: dict[str, Any] = {
            "part": "snippet", "q": request.query, "type": "video", "maxResults": request.max_results,
            "publishedAfter": (datetime.now(timezone.utc) - timedelta(days=request.recency_days)).isoformat().replace("+00:00", "Z"),
            "order": request.order, "regionCode": request.region,
        }
        if request.language:
            params["relevanceLanguage"] = request.language
        data = await self._get("search", params)
        results: list[SearchResult] = []
        for position, item in enumerate(data.get("items", []), start=1):
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId", "")
            results.append(SearchResult(
                youtube_video_id=video_id,
                canonical_url=f"https://www.youtube.com/watch?v={video_id}",
                title=snippet.get("title", ""),
                channel_id=snippet.get("channelId", ""),
                channel_title=snippet.get("channelTitle", ""),
                visible_views_text="unknown",
                visible_age_text=snippet.get("publishedAt", ""),
                presented_as_short=False,
                result_position=position,
                raw_payload=item,
            ))
        return DiscoveryResult(SourceType.YOUTUBE_API, request.query, results)

    async def enrich_videos(self, video_ids: list[str], context_by_video_id: dict[str, dict[str, Any]] | None = None) -> list[VideoRecord]:
        records: list[VideoRecord] = []
        for batch in _batches(list(dict.fromkeys(video_ids))):
            data = await self._get("videos", {"part": "snippet,contentDetails,statistics", "id": ",".join(batch)})
            items = data.get("items") if isinstance(data.get("items"), list) else []
            returned_ids = {str(item.get("id")) for item in items if isinstance(item, dict) and item.get("id")}
            for item in items:
                record = _video_from_api(item)
                if record is None:
                    video_id = str(item.get("id") or "unknown-video")
                    snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
                    self._diagnostics.append(SourceDiagnostic(
                        diagnostic_type="youtube_api_video_skipped",
                        source_entity_id=video_id,
                        channel_id=str(snippet.get("channelId")) if snippet.get("channelId") else None,
                        source_url=f"https://www.youtube.com/watch?v={video_id}",
                        reason="YouTube Data API video omitted a valid publication timestamp",
                        error_code=ErrorCode.VALIDATION.value,
                        observed_at=datetime.now(timezone.utc),
                        raw_payload={"id": video_id, "publishedAt": snippet.get("publishedAt")},
                    ))
                    continue
                records.append(preprocess_video(record))
            for video_id in batch:
                if video_id in returned_ids:
                    continue
                context = (context_by_video_id or {}).get(video_id, {})
                self._diagnostics.append(SourceDiagnostic(
                    diagnostic_type="youtube_api_video_omitted",
                    source_entity_id=video_id,
                    channel_id=str(context.get("channel_id")) if context.get("channel_id") else None,
                    source_url=str(context.get("url") or f"https://www.youtube.com/watch?v={video_id}"),
                    reason="YouTube Data API omitted the requested video; it may be private, removed, or unavailable",
                    error_code=ErrorCode.NOT_FOUND.value,
                    observed_at=datetime.now(timezone.utc),
                    raw_payload={"requested_video_id": video_id, "discovery_context": context},
                ))
        return records

    def drain_diagnostics(self) -> list[SourceDiagnostic]:
        diagnostics = self._diagnostics[:]
        self._diagnostics.clear()
        return diagnostics

    async def enrich_channels(self, channel_ids: list[str]) -> list[ChannelRecord]:
        records: list[ChannelRecord] = []
        for batch in _batches(channel_ids):
            data = await self._get("channels", {"part": "snippet,statistics,contentDetails", "id": ",".join(batch)})
            for item in data.get("items", []):
                snippet, stats = item.get("snippet", {}), item.get("statistics", {})
                records.append(ChannelRecord(
                    youtube_channel_id=item.get("id", ""),
                    canonical_url=f"https://www.youtube.com/channel/{item.get('id', '')}",
                    title=snippet.get("title", ""), description=snippet.get("description", ""),
                    subscriber_count=_int_or_none(stats.get("subscriberCount")),
                    total_view_count=_int_or_none(stats.get("viewCount")),
                    video_count=_int_or_none(stats.get("videoCount")),
                ))
        return records

    async def expand_channel_uploads(self, channel_id: str, limit: int = 20) -> list[VideoRecord]:
        channel_data = await self._get("channels", {"part": "contentDetails", "id": channel_id})
        channel_items = channel_data.get("items") or []
        if not channel_items:
            return []
        uploads = channel_items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        if not uploads:
            return []
        ids: list[str] = []
        page_token: str | None = None
        while len(ids) < limit:
            params = {"part": "contentDetails", "playlistId": uploads, "maxResults": min(limit - len(ids), 50)}
            if page_token:
                params["pageToken"] = page_token
            playlist = await self._get("playlistItems", params)
            ids.extend(item.get("contentDetails", {}).get("videoId", "") for item in playlist.get("items", []))
            page_token = playlist.get("nextPageToken")
            if not page_token:
                break
        return await self.enrich_videos([video_id for video_id in ids if video_id])

    async def sample_comments(self, video_id: str, limit: int = 5) -> list[CommentRecord]:
        try:
            data = await self._get("commentThreads", {"part": "snippet", "videoId": video_id, "maxResults": min(limit, 100), "textFormat": "plainText"})
        except NicheIntelError:
            return []
        records: list[CommentRecord] = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            records.append(CommentRecord(
                source_comment_id=item.get("id", ""), text=snippet.get("textDisplay", ""),
                like_count=int(snippet.get("likeCount", 0)),
                published_at=_parse_dt(snippet.get("publishedAt")),
                is_pinned_if_known=None,
            ))
        return records


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


_OPERATION_UNITS = {
    "search.list": 100,
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.list": 1,
    "commentThreads.list": 1,
}


_QUOTA_REASONS = {
    "quotaexceeded",
    "dailylimitexceeded",
    "dailylimitexceededunreg",
    "userratelimitexceeded",
    "ratelimitexceeded",
}


def _is_quota_response(response: httpx.Response) -> bool:
    """Classify YouTube's normal HTTP 403 quota envelopes precisely."""
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return False
    reasons = {
        str(item.get("reason") or "").replace("_", "").lower()
        for item in error.get("errors", [])
        if isinstance(item, dict)
    }
    status = str(error.get("status") or "").replace("_", "").lower()
    message = str(error.get("message") or "").replace(" ", "").lower()
    return bool(reasons & _QUOTA_REASONS) or status == "resourceexhausted" or any(
        reason in message for reason in ("quotaexceeded", "dailylimitexceeded")
    )


def _batches(ids: list[str], size: int = 50) -> list[list[str]]:
    """YouTube videos.list and channels.list accept at most 50 IDs."""
    return [ids[index:index + size] for index in range(0, len(ids), size)]


def _parse_dt(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _video_from_api(item: dict[str, Any]) -> VideoRecord | None:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    content = item.get("contentDetails", {})
    published_at = _parse_dt(snippet.get("publishedAt"))
    if published_at is None:
        return None
    return VideoRecord(
        youtube_video_id=item.get("id", ""), channel_id=snippet.get("channelId", ""),
        canonical_url=f"https://www.youtube.com/watch?v={item.get('id', '')}", title=snippet.get("title", ""),
        description=snippet.get("description", ""), duration_seconds=_parse_iso8601_duration(content.get("duration")),
        published_at=published_at, category_id=snippet.get("categoryId"),
        tags=snippet.get("tags", []), thumbnails=snippet.get("thumbnails", {}),
        view_count=int(stats.get("viewCount", 0)), like_count=_int_or_none(stats.get("likeCount")),
        comment_count=_int_or_none(stats.get("commentCount")),
    )


def _parse_iso8601_duration(value: str | None) -> int | None:
    if not value:
        return None
    match = re.fullmatch(r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?", value)
    if not match:
        return None
    parts = {name: int(number or 0) for name, number in match.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]
