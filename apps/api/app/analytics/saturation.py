from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..sources.base import VideoRecord


@dataclass(frozen=True)
class SaturationResult:
    direct_competitor_count: int
    active_competitor_count: int
    recent_upload_density: float
    high_performing_share: float
    weak_copycat_share: float
    format_similarity: float
    evidence_concentration: float
    risk_score: float
    risk: str
    evidence_window_days: int = 90

    def as_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "calculation_version": "saturation-v2"}


def assess_saturation(videos: list[VideoRecord], outlier_multiples: list[float], evidence_window_days: int = 90, now: datetime | None = None) -> SaturationResult:
    observed = now or datetime.now(timezone.utc)
    channels = {video.channel_id for video in videos}
    recent = [video for video in videos if max(0, (observed - video.published_at).days) <= evidence_window_days]
    active = {video.channel_id for video in recent}
    high_share = sum(value >= 2 for value in outlier_multiples) / max(len(videos), 1)
    weak_share = sum(value < 1 for value in outlier_multiples) / max(len(videos), 1)
    token_sets = [_tokens(video.title + " " + video.format_label) for video in videos]
    pairwise = [_jaccard(left, right) for index, left in enumerate(token_sets) for right in token_sets[index + 1:]]
    similarity = sum(pairwise) / max(len(pairwise), 1)
    view_by_channel = Counter()
    for video in videos:
        view_by_channel[video.channel_id] += video.view_count
    concentration = max(view_by_channel.values(), default=0) / max(sum(view_by_channel.values()), 1)
    density = len(recent) / max(evidence_window_days / 30, 1)
    risk_score = min(1.0, min(1, len(active) / 6) * .35 + min(1, density / 2) * .2 + similarity * .3 + weak_share * .1 + concentration * .05)
    risk = "high" if risk_score >= .7 else "moderate" if risk_score >= .42 else "low"
    return SaturationResult(len(channels), len(active), round(density, 2), round(high_share, 3), round(weak_share, 3), round(similarity, 3), round(concentration, 3), round(risk_score, 3), risk, evidence_window_days)


def _tokens(value: str) -> set[str]:
    return {token.strip("?!:,.→").lower() for token in value.split() if len(token.strip("?!:,.→")) > 2}


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(len(left | right), 1)
