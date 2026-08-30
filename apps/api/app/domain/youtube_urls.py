"""Strict classification helpers for direct YouTube resource URLs."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import parse_qs, urlparse, urlunparse


YouTubeResourceKind = Literal["video", "channel"]

_YOUTUBE_HOSTS = {"www.youtube.com", "youtube.com", "m.youtube.com"}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def classify_direct_youtube_url(value: str) -> YouTubeResourceKind | None:
    """Return the declared YouTube resource kind for a safe direct URL."""
    candidate = value.strip()
    if not candidate:
        return None
    parsed = urlparse(candidate)
    try:
        port = parsed.port
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        return None

    segments = [segment for segment in parsed.path.split("/") if segment]
    if host == "youtu.be":
        return "video" if len(segments) == 1 and _valid_video_id(segments[0]) else None
    if host not in _YOUTUBE_HOSTS:
        return None

    if parsed.path.rstrip("/") == "/watch":
        video_ids = parse_qs(parsed.query, keep_blank_values=True).get("v", [])
        return "video" if len(video_ids) == 1 and _valid_video_id(video_ids[0]) else None
    if len(segments) == 2 and segments[0] == "shorts" and _valid_video_id(segments[1]):
        return "video"
    if _valid_channel_segments(segments):
        return "channel"
    return None


def channel_videos_url(value: str) -> str:
    """Return a validated channel URL targeting its public videos grid."""
    candidate = value.strip()
    if classify_direct_youtube_url(candidate) != "channel":
        raise ValueError("a valid YouTube channel URL is required")
    parsed = urlparse(candidate)
    path = parsed.path.rstrip("/")
    if path.endswith("/videos"):
        return candidate
    return urlunparse(parsed._replace(path=f"{path}/videos"))


def _valid_video_id(value: str) -> bool:
    return bool(value and _VIDEO_ID.fullmatch(value))


def _valid_channel_segments(segments: list[str]) -> bool:
    suffix_count = 1 if segments and segments[-1] == "videos" else 0
    resource = segments[:-suffix_count] if suffix_count else segments
    if len(resource) == 1 and resource[0].startswith("@"):
        return _valid_channel_component(resource[0][1:])
    return (
        len(resource) == 2
        and resource[0] in {"channel", "c", "user"}
        and _valid_channel_component(resource[1])
    )


def _valid_channel_component(value: str) -> bool:
    return bool(value and value not in {".", ".."} and not any(character.isspace() for character in value))
