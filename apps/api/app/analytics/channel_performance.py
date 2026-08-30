"""Public-data channel performance proxies for channels the user does not administer."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import median
from typing import Any

from .metrics import outlier_metric, views_per_day
from .shorts import ShortClassification
from ..domain.enums import RequestedFormat
from ..sources.base import VideoRecord


def build_channel_profiles(
    videos: list[VideoRecord],
    classifications: dict[str, ShortClassification],
    now: datetime,
    recent_days: int = 45,
    supporting_days: int = 90,
    outlier_threshold: float = 3.0,
    requested_format: RequestedFormat = RequestedFormat.SHORTS,
) -> dict[str, dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[VideoRecord]] = defaultdict(list)
    for video in videos:
        classification = classifications[video.youtube_video_id]
        if _matches_requested_format(classification, requested_format) and _age_days(video, now) <= supporting_days:
            grouped[(video.channel_id, _media_class(classification), video.format_label.strip() or "unclassified")].append(video)

    cohorts_by_channel: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (channel_id, media_class, repeatable_format), items in grouped.items():
        rates = [views_per_day(item.view_count, item.published_at, now) for item in items]
        multiples = [
            outlier_metric(item.youtube_video_id, rate, rates, outlier_threshold=outlier_threshold).outlier_multiple
            for item, rate in zip(items, rates, strict=True)
        ]
        largest_share = max((item.view_count for item in items), default=0) / max(sum(item.view_count for item in items), 1)
        cohorts_by_channel[channel_id].append({
            "channel_id": channel_id,
            "media_class": media_class,
            "repeatable_format": repeatable_format,
            "supporting_window_days": supporting_days,
            "uploads_analyzed": len(items),
            "median_views_per_day": round(median(rates), 2) if rates else 0.0,
            "outlier_multiples": [round(value, 3) for value in multiples],
            "outliers_2x": sum(value >= 2 for value in multiples),
            "outliers_at_threshold": sum(value >= outlier_threshold for value in multiples),
            "largest_video_view_share": round(largest_share, 3),
            "successful": len(items) >= 3 and max(multiples, default=0) >= outlier_threshold and largest_share <= 0.8,
        })

    profiles: dict[str, dict[str, Any]] = {}
    for channel_id, cohorts in cohorts_by_channel.items():
        items = [item for cohort_key, cohort_items in grouped.items() if cohort_key[0] == channel_id for item in cohort_items]
        multiples = [value for cohort in cohorts for value in cohort["outlier_multiples"]]
        rates = [views_per_day(item.view_count, item.published_at, now) for item in items]
        recent = [item for item in items if max(0, (now - item.published_at).days) <= recent_days]
        largest_share = max((item.view_count for item in items), default=0) / max(sum(item.view_count for item in items), 1)
        recent_rates = [views_per_day(item.view_count, item.published_at, now) for item in recent]
        estimated_30d = int(median(recent_rates or rates or [0]) * 30)
        profiles[channel_id] = {
            "channel_id": channel_id,
            "requested_format": requested_format.value,
            "uploads_analyzed": len(items),
            "shorts_analyzed": sum(classifications[item.youtube_video_id].eligible for item in items),
            "longform_analyzed": sum(classifications[item.youtube_video_id].status.value == "not_short" for item in items),
            "uploads_7d": _count_since(recent, now, 7),
            "uploads_30d": _count_since(recent, now, 30),
            "uploads_45d": _count_since(recent, now, 45),
            "uploads_90d": _count_since(items, now, 90),
            "median_views_per_day": round(median(rates), 2) if rates else 0.0,
            "estimated_30d_views": estimated_30d,
            "outliers_2x": sum(value >= 2 for value in multiples),
            "outliers_3x": sum(value >= 3 for value in multiples),
            "outlier_frequency": round(sum(value >= 2 for value in multiples) / max(len(items), 1), 3),
            "largest_video_view_share": round(largest_share, 3),
            "consistency_score": round(max(0.0, 1 - largest_share), 3),
            "successful": any(cohort["successful"] for cohort in cohorts),
            "successful_cohort_count": sum(cohort["successful"] for cohort in cohorts),
            "outlier_threshold": outlier_threshold,
            "supporting_window_days": supporting_days,
            "cohorts": cohorts,
            "confidence": round(min(0.95, 0.45 + len(items) * 0.1), 3),
            "data_scope": "public uploads inside the supporting window, partitioned by media class and repeatable format; estimated_30d_views is not private YouTube Analytics",
        }
    return profiles


def _matches_requested_format(classification: ShortClassification, requested_format: RequestedFormat) -> bool:
    if requested_format == RequestedFormat.SHORTS:
        return classification.eligible
    if requested_format == RequestedFormat.LONG_FORM:
        return classification.status.value == "not_short"
    return True


def _count_since(items: list[VideoRecord], now: datetime, days: int) -> int:
    return sum(max(0, (now - item.published_at).days) <= days for item in items)


def _media_class(classification: ShortClassification) -> str:
    if classification.eligible:
        return "shorts"
    if classification.status.value == "not_short":
        return "long_form"
    return "unknown"


def _age_days(video: VideoRecord, now: datetime) -> float:
    published = video.published_at
    if published.tzinfo is None and now.tzinfo is not None:
        published = published.replace(tzinfo=now.tzinfo)
    return max(0.0, (now - published).total_seconds() / 86400)
