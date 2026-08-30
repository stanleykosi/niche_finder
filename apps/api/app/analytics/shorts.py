"""Conservative Shorts identification; duration alone never claims certainty."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..sources.base import BrowserMediaRecord, SearchResult, VideoRecord


class ShortStatus(StrEnum):
    CONFIRMED = "confirmed_short"
    PROBABLE = "probable_short"
    NOT_SHORT = "not_short"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ShortClassification:
    status: ShortStatus
    confidence: float
    reasons: list[str]

    @property
    def eligible(self) -> bool:
        return self.status in {ShortStatus.CONFIRMED, ShortStatus.PROBABLE}

    def as_dict(self) -> dict:
        return {"status": self.status.value, "confidence": self.confidence, "reasons": self.reasons}


def classify_short(
    video: VideoRecord,
    observation: SearchResult | None = None,
    media: BrowserMediaRecord | None = None,
) -> ShortClassification:
    reasons: list[str] = []
    if media and media.is_short_presentation:
        reasons.append("YouTube browser rendered the video in a Shorts surface")
    if observation and (observation.presented_as_short or "/shorts/" in observation.canonical_url):
        reasons.append("YouTube discovery presented the result as a Short")
    if "/shorts/" in video.canonical_url:
        reasons.append("canonical observation used a /shorts/ URL")
    if reasons:
        return ShortClassification(ShortStatus.CONFIRMED, 0.98, reasons)
    if video.duration_seconds is not None and video.duration_seconds > 180:
        return ShortClassification(ShortStatus.NOT_SHORT, 0.98, ["duration exceeds the current three-minute Shorts limit"])
    if video.shorts_evidence == "landscape":
        return ShortClassification(
            ShortStatus.NOT_SHORT,
            0.9,
            ["keyless metadata observed a landscape aspect ratio; duration cannot promote it into a Shorts cohort"],
        )
    if video.shorts_evidence in {"aspect_ratio_unknown", "aspect_ratio_invalid"}:
        return ShortClassification(
            ShortStatus.UNKNOWN,
            0.3,
            ["keyless metadata supplied no confirming portrait aspect ratio; compatible duration is non-confirming"],
        )
    if video.is_short:
        reason = (
            "keyless metadata observed a portrait aspect ratio and Shorts-compatible duration"
            if video.shorts_evidence == "portrait"
            else "source labelled the item short; no Shorts surface was observed"
        )
        return ShortClassification(ShortStatus.PROBABLE, 0.84, [reason])
    if video.duration_seconds is not None and video.duration_seconds <= 180:
        return ShortClassification(ShortStatus.PROBABLE, 0.62, ["duration is Shorts-compatible but public API duration is not an isShort flag"])
    return ShortClassification(ShortStatus.UNKNOWN, 0.25, ["no reliable Shorts presentation or duration evidence"])


def summarize_short_classifications(classifications: dict[str, ShortClassification]) -> dict:
    counts = {status.value: 0 for status in ShortStatus}
    for item in classifications.values():
        counts[item.status.value] += 1
    total = max(len(classifications), 1)
    return {
        "counts": counts,
        "eligible_share": round((counts[ShortStatus.CONFIRMED.value] + counts[ShortStatus.PROBABLE.value]) / total, 3),
        "confirmed_share": round(counts[ShortStatus.CONFIRMED.value] / total, 3),
        "method": "browser Shorts surface first; positive source evidence second; duration cannot override keyless aspect evidence",
        "calculation_version": "shorts-classification-v3-keyless-aspect-boundary",
    }
