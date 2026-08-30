"""Matched winner/loser pair selection before AI interpretation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..sources.base import BrowserMediaRecord, VideoRecord


MAX_COMPARISON_TRANSCRIPT_CHARS = 2_400


def select_matched_pairs(
    videos: list[VideoRecord], multiples: dict[str, float], media: dict[str, BrowserMediaRecord], limit: int = 6
) -> list[dict[str, Any]]:
    grouped: dict[str, list[VideoRecord]] = defaultdict(list)
    for video in videos:
        grouped[video.channel_id].append(video)
    pairs: list[dict[str, Any]] = []
    used_video_ids: set[str] = set()
    for channel_id, items in sorted(grouped.items()):
        winners = sorted(items, key=lambda item: multiples.get(item.youtube_video_id, 0), reverse=True)
        losers = sorted(items, key=lambda item: multiples.get(item.youtube_video_id, 0))
        for winner in winners:
            if winner.youtube_video_id in used_video_ids:
                continue
            loser = next((
                item for item in losers
                if item.youtube_video_id not in used_video_ids
                and _match(winner, item)
                and multiples.get(winner.youtube_video_id, 0) >= 2 * max(multiples.get(item.youtube_video_id, 0), 0.01)
            ), None)
            if loser is None:
                continue
            used_video_ids.update({winner.youtube_video_id, loser.youtube_video_id})
            winner_multiple = multiples.get(winner.youtube_video_id, 0)
            loser_multiple = multiples.get(loser.youtube_video_id, 0)
            pairs.append({
                "channel_id": channel_id,
                "winner": _dossier(winner, multiples, media),
                "loser": _dossier(loser, multiples, media),
                "match_basis": ["same channel", "same topic/format family", "similar duration", "similar publication window"],
                "performance_ratio": round(winner_multiple / max(loser_multiple, 0.01), 3),
                "performance_metric": "outlier_multiple",
                "winner_performance_value": round(winner_multiple, 3),
                "loser_performance_value": round(loser_multiple, 3),
                "match_quality": _match_quality(winner, loser),
                "purpose": "Hold creator, subject family, format, duration and time window as constant as public data permits, so packaging/mechanism differences become testable explanations for performance—not causal claims.",
            })
            if len(pairs) >= limit:
                return pairs
        if len(pairs) >= limit:
            break
    return pairs


def _match(winner: VideoRecord, loser: VideoRecord) -> bool:
    if winner.youtube_video_id == loser.youtube_video_id:
        return False
    duration_close = winner.duration_seconds is None or loser.duration_seconds is None or abs(winner.duration_seconds - loser.duration_seconds) <= 30
    date_close = abs((winner.published_at - loser.published_at).days) <= 90
    family_match = winner.format_label == loser.format_label or winner.topic == loser.topic
    return duration_close and date_close and family_match


def _dossier(video: VideoRecord, multiples: dict[str, float], media: dict[str, BrowserMediaRecord]) -> dict[str, Any]:
    observed = media.get(video.youtube_video_id)
    return {
        "id": video.youtube_video_id,
        "title": video.title,
        "topic": video.topic,
        "format": video.format_label,
        "duration_seconds": video.duration_seconds,
        "published_at": video.published_at.isoformat(),
        "views": video.view_count,
        "outlier_multiple": round(multiples.get(video.youtube_video_id, 0), 3),
        "transcript": _bounded_transcript(observed.visible_transcript) if observed else None,
        "transcript_truncated": bool(
            observed and observed.visible_transcript and len(observed.visible_transcript) > MAX_COMPARISON_TRANSCRIPT_CHARS
        ),
        "opening_visual": observed.opening_visual_summary if observed else None,
        "structure": observed.observable_structure if observed else [],
        "pacing_score": observed.pacing_score if observed else None,
        "frame_refs": observed.frame_refs if observed else [],
        "first_spoken_line": observed.first_spoken_line if observed else None,
        "caption_style": observed.caption_style if observed else None,
        "estimated_visual_state_count": len(observed.observable_structure) if observed else 0,
        "reveal_timestamp_seconds": observed.reveal_timestamp_seconds if observed else None,
    }


def _bounded_transcript(text: str | None) -> str | None:
    """Bound comparison prompts without manufacturing transcript timing."""
    if not text or not text.strip():
        return None
    normalized = " ".join(text.split())
    if len(normalized) <= MAX_COMPARISON_TRANSCRIPT_CHARS:
        return normalized
    boundary = normalized.rfind(" ", 0, MAX_COMPARISON_TRANSCRIPT_CHARS)
    end = boundary if boundary > MAX_COMPARISON_TRANSCRIPT_CHARS // 2 else MAX_COMPARISON_TRANSCRIPT_CHARS
    return normalized[:end].rstrip()


def _match_quality(winner: VideoRecord, loser: VideoRecord) -> dict[str, Any]:
    duration_gap = abs((winner.duration_seconds or 0) - (loser.duration_seconds or 0))
    date_gap = abs((winner.published_at - loser.published_at).days)
    return {
        "same_topic": winner.topic == loser.topic,
        "same_format": winner.format_label == loser.format_label,
        "duration_gap_seconds": duration_gap,
        "publication_gap_days": date_gap,
        "score": round((.3 if winner.topic == loser.topic else 0) + (.3 if winner.format_label == loser.format_label else 0) + max(0, .2 - duration_gap / 150) + max(0, .2 - date_gap / 450), 3),
    }
