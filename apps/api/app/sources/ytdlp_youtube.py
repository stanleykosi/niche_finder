"""Keyless public YouTube metadata adapter used by the live E2E smoke gate."""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

from ..core.errors import ErrorCode, NicheIntelError
from ..research.preprocessing import preprocess_video
from .base import ChannelRecord, CommentRecord, SourceDiagnostic, VideoRecord


class YtDlpYoutubeSource:
    def __init__(self, executable: str = "yt-dlp", timeout: float = 90) -> None:
        self.executable = executable
        self.timeout = timeout
        self._metadata: dict[str, dict[str, Any]] = {}
        self._diagnostics: list[SourceDiagnostic] = []

    async def _json(self, args: list[str], *, playlist: bool = False) -> dict[str, Any]:
        mode_args = [] if playlist else ["--no-playlist"]
        try:
            process = await asyncio.create_subprocess_exec(
                self.executable, "--no-warnings", *mode_args, "--dump-single-json", *args,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise NicheIntelError("yt-dlp is required for keyless live metadata", ErrorCode.CONFIGURATION) from exc
        communication = asyncio.create_task(process.communicate())
        try:
            # Shield the pipe-draining task so timeout/cancellation cleanup can
            # kill and then reap the exact child before returning control.
            stdout, stderr = await asyncio.wait_for(asyncio.shield(communication), self.timeout)
        except BaseException as exc:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            try:
                await communication
            except BaseException:
                pass
            if isinstance(exc, TimeoutError):
                raise NicheIntelError("yt-dlp metadata request timed out", ErrorCode.SOURCE_UNAVAILABLE) from exc
            raise
        if process.returncode:
            raise NicheIntelError(f"yt-dlp metadata failed: {stderr.decode(errors='replace')[-400:]}", ErrorCode.SOURCE_UNAVAILABLE)
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise NicheIntelError("yt-dlp returned invalid JSON metadata", ErrorCode.SOURCE_UNAVAILABLE) from exc

    async def enrich_videos(self, video_ids: list[str], context_by_video_id: dict[str, dict[str, Any]] | None = None) -> list[VideoRecord]:
        records: list[VideoRecord] = []
        for video_id in dict.fromkeys(video_ids):
            video_id = str(video_id)
            source_entry = (context_by_video_id or {}).get(video_id)
            record = await self._enrich_video(
                video_id,
                channel_id=_known_channel_id(source_entry or {}),
                source_entry=source_entry,
            )
            if record is not None:
                records.append(record)
        return records

    async def _enrich_video(
        self,
        video_id: str,
        *,
        channel_id: str | None = None,
        source_entry: dict[str, Any] | None = None,
    ) -> VideoRecord | None:
        source_context = dict(source_entry or {})
        if channel_id and not _known_channel_id(source_context):
            source_context["channel_id"] = channel_id
        canonical_source_url = _canonical_video_url(video_id, source_context)
        item: dict[str, Any] = {"id": video_id, **source_context}
        try:
            extracted = await self._json([f"https://www.youtube.com/watch?v={video_id}"])
            item = _merge_metadata(source_context, extracted, video_id)
            record = preprocess_video(_video(item, video_id))
        except NicheIntelError as exc:
            if exc.code == ErrorCode.CONFIGURATION:
                raise
            diagnostic_channel = channel_id or _known_channel_id(item)
            diagnostic_payload = {**source_context, **item, "id": video_id}
            self._diagnostics.append(
                _skip_diagnostic(
                    diagnostic_channel,
                    video_id,
                    diagnostic_payload,
                    exc,
                    diagnostic_type="keyless_video_skipped",
                    source_url=canonical_source_url,
                )
            )
            return None
        self._metadata[video_id] = item
        return record

    async def enrich_channels(self, channel_ids: list[str]) -> list[ChannelRecord]:
        records: list[ChannelRecord] = []
        for channel_id in dict.fromkeys(channel_ids):
            item = next((value for value in self._metadata.values() if _channel_id(value) == channel_id), {})
            title = str(item.get("channel") or item.get("uploader") or item.get("channel_title") or channel_id)
            # Cached entries are video-level responses. Their ``description``
            # describes the video, not its channel, so channel description is
            # deliberately preserved as unknown until a channel-level source
            # supplies it.
            records.append(ChannelRecord(channel_id, str(item.get("channel_url") or f"https://www.youtube.com/channel/{channel_id}"), title, "", item.get("channel_follower_count"), None, None))
        return records

    async def expand_channel_uploads(self, channel_id: str, limit: int = 20) -> list[VideoRecord]:
        bounded_limit = max(1, min(limit, 30))
        seed = next((value for value in self._metadata.values() if _channel_id(value) == channel_id), None)
        channel_url = str((seed or {}).get("channel_url") or f"https://www.youtube.com/channel/{channel_id}")
        uploads_url = _uploads_url(channel_url)
        try:
            playlist = await self._json(
                ["--flat-playlist", "--playlist-end", str(bounded_limit), uploads_url],
                playlist=True,
            )
        except NicheIntelError as exc:
            if exc.code == ErrorCode.CONFIGURATION:
                raise
            self._diagnostics.append(SourceDiagnostic(
                diagnostic_type="keyless_channel_feed_skipped",
                source_entity_id=channel_id,
                channel_id=channel_id,
                source_url=uploads_url,
                reason=exc.message[:500],
                error_code=exc.code.value,
                observed_at=datetime.now(timezone.utc),
                raw_payload={"channel_url": channel_url, "uploads_url": uploads_url, "requested_limit": bounded_limit},
            ))
            return []
        entries = [item for item in playlist.get("entries", [])[:bounded_limit] if item and item.get("id")]
        records: list[VideoRecord] = []
        seen: set[str] = set()
        for entry in entries:
            video_id = str(entry["id"])
            if video_id in seen:
                continue
            seen.add(video_id)
            record = await self._enrich_video(video_id, channel_id=channel_id, source_entry=entry)
            if record is not None:
                records.append(record)
        return records

    def drain_diagnostics(self) -> list[SourceDiagnostic]:
        diagnostics = self._diagnostics[:]
        self._diagnostics.clear()
        return diagnostics

    async def sample_comments(self, video_id: str, limit: int = 5) -> list[CommentRecord]:
        return []


def _channel_id(item: dict[str, Any]) -> str:
    return str(item.get("channel_id") or item.get("uploader_id") or "unknown-channel")


def _known_channel_id(item: dict[str, Any]) -> str | None:
    value = item.get("channel_id") or item.get("uploader_id")
    return str(value) if value else None


def _uploads_url(channel_url: str) -> str:
    parsed = urlparse(channel_url)
    path = parsed.path.rstrip("/").removesuffix("/videos")
    return urlunparse(parsed._replace(path=f"{path}/videos" if path else "/videos"))


def _canonical_video_url(video_id: str, source_entry: dict[str, Any]) -> str:
    """Retain a canonical discovery URL, never an extracted media-stream URL."""
    fallback = f"https://www.youtube.com/watch?v={video_id}"
    candidate = str(source_entry.get("url") or "").strip()
    if not candidate:
        return fallback
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return fallback
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    path_parts = [part for part in parsed.path.split("/") if part]
    if host == "youtu.be" and path_parts and path_parts[0] == video_id:
        return candidate
    if host not in {"youtube.com", "youtube-nocookie.com"}:
        return fallback
    if parsed.path == "/watch" and parse_qs(parsed.query).get("v", [None])[0] == video_id:
        return candidate
    if len(path_parts) >= 2 and path_parts[0] in {"shorts", "live", "embed"} and path_parts[1] == video_id:
        return candidate
    return fallback


def _video(item: dict[str, Any], fallback_id: str) -> VideoRecord:
    video_id = str(item.get("id") or fallback_id)
    published = _publication_datetime(item)
    if published is None:
        raise NicheIntelError(
            f"yt-dlp publication date is unavailable for video {video_id}; entry excluded",
            ErrorCode.VALIDATION,
        )
    duration = _optional_int(item.get("duration"))
    aspect_ratio = _finite_float(item.get("aspect_ratio"))
    if aspect_ratio is None:
        shorts_evidence = "aspect_ratio_unknown"
    elif aspect_ratio <= 0:
        shorts_evidence = "aspect_ratio_invalid"
    elif aspect_ratio < 1:
        shorts_evidence = "portrait"
    else:
        shorts_evidence = "landscape"
    return VideoRecord(
        video_id, _channel_id(item), f"https://www.youtube.com/watch?v={video_id}", str(item.get("title") or video_id),
        str(item.get("description") or ""), duration, published,
        str(item.get("categories", [""])[0]) if item.get("categories") else None, list(item.get("tags") or []),
        {"thumbnail": item.get("thumbnail")}, int(item.get("view_count") or 0), item.get("like_count"),
        item.get("comment_count"), bool(duration is not None and duration <= 180 and shorts_evidence == "portrait"),
        shorts_evidence=shorts_evidence,
    )


def _merge_metadata(
    source_entry: dict[str, Any] | None,
    extracted: dict[str, Any],
    video_id: str,
) -> dict[str, Any]:
    """Overlay real extraction while retaining known nonempty discovery data."""
    merged = {"id": video_id, **(source_entry or {})}
    for key, value in extracted.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        merged[key] = value
    merged["id"] = str(merged.get("id") or video_id)
    return merged


def _publication_datetime(item: dict[str, Any]) -> datetime | None:
    for key in ("timestamp", "release_timestamp"):
        value = item.get(key)
        if value is None:
            continue
        try:
            return datetime.fromtimestamp(float(value), timezone.utc)
        except (OSError, OverflowError, TypeError, ValueError):
            continue
    for key in ("upload_date", "release_date"):
        value = str(item.get(key) or "").strip()
        for date_format in ("%Y%m%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, date_format).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _optional_int(value: Any) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) else None


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _skip_diagnostic(
    channel_id: str | None,
    video_id: str,
    entry: dict[str, Any],
    exc: Exception,
    *,
    diagnostic_type: str = "keyless_upload_skipped",
    source_url: str | None = None,
) -> SourceDiagnostic:
    if isinstance(exc, NicheIntelError):
        reason = exc.message
        error_code = exc.code.value
    else:
        reason = f"{type(exc).__name__}: {exc}"
        error_code = ErrorCode.SOURCE_UNAVAILABLE.value
    return SourceDiagnostic(
        diagnostic_type=diagnostic_type,
        source_entity_id=video_id,
        channel_id=channel_id,
        source_url=source_url or _canonical_video_url(video_id, entry),
        reason=reason[:500],
        error_code=error_code,
        observed_at=datetime.now(timezone.utc),
        raw_payload={
            key: entry.get(key)
            for key in (
                "id", "title", "availability", "url", "channel_id",
                "channel_title", "visible_views_text", "visible_age_text",
                "presented_as_short", "result_position", "screenshot_ref",
                "discovery_raw_payload",
            )
            if entry.get(key) is not None
        },
    )
