"""Pure deterministic metrics. Inputs and versions are kept explicit for auditability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median


ANALYTICS_VERSION = "analytics-v3"


@dataclass(frozen=True)
class OutlierMetric:
    video_id: str
    metric_value: float
    baseline_metric: float
    outlier_multiple: float
    label: str
    calculation_version: str = ANALYTICS_VERSION
    cohort_size: int = 0
    confidence: float = 0.0
    age_days: float = 0.0
    recency_bucket: str = "unknown"


@dataclass(frozen=True)
class MomentumMetric:
    video_id: str
    absolute_growth: int
    views_gained_per_day: float
    acceleration: float | None
    calculation_version: str = ANALYTICS_VERSION


def age_days(published_at: datetime, observed_at: datetime | None = None) -> float:
    observed = observed_at or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return max((observed - published_at).total_seconds() / 86400, 0.0)


def views_per_day(view_count: int, published_at: datetime, observed_at: datetime | None = None) -> float:
    return view_count / max(age_days(published_at, observed_at), 1.0)


def median_baseline(metrics: list[float], exclude: float | None = None) -> float:
    values = list(metrics)
    if exclude is not None:
        removed = False
        filtered: list[float] = []
        for value in values:
            if not removed and value == exclude:
                removed = True
                continue
            filtered.append(value)
        values = filtered
    return float(median(values)) if values else 0.0


def outlier_label(
    multiple: float,
    outlier_threshold: float = 3.0,
    major_outlier_threshold: float | None = None,
) -> str:
    major_threshold = major_outlier_threshold or max(5.0, outlier_threshold + 2.0)
    if multiple < 1:
        return "below normal"
    if multiple < 2:
        return "normal"
    if multiple < outlier_threshold:
        return "strong"
    if multiple < major_threshold:
        return "outlier"
    return "major outlier"


def outlier_metric(
    video_id: str,
    candidate_metric: float,
    cohort_metrics: list[float],
    video_age_days: float = 0.0,
    primary_recency_days: int = 45,
    baseline_recency_days: int = 90,
    outlier_threshold: float = 3.0,
) -> OutlierMetric:
    baseline = median_baseline(cohort_metrics, exclude=candidate_metric)
    multiple = candidate_metric / baseline if baseline > 0 else 0.0
    cohort_size = max(0, len(cohort_metrics) - 1)
    confidence = min(0.98, 0.35 + cohort_size * 0.14) if baseline else 0.15
    bucket = "current" if video_age_days <= primary_recency_days else "supporting" if video_age_days <= baseline_recency_days else "historical"
    if bucket == "historical":
        # Historical uploads remain available for display, but cannot influence
        # ranking, pair selection, saturation, or any recommendation gate.
        multiple = 0.0
        confidence = 0.0
        label = "historical"
    else:
        label = outlier_label(multiple, outlier_threshold)
    return OutlierMetric(video_id, candidate_metric, baseline, multiple, label, ANALYTICS_VERSION, cohort_size, round(confidence, 3), round(video_age_days, 2), bucket)


def snapshot_momentum(video_id: str, snapshots: list[tuple[datetime, int]]) -> MomentumMetric:
    if len(snapshots) < 2:
        return MomentumMetric(video_id, 0, 0.0, None)
    ordered = sorted(snapshots, key=lambda item: item[0])
    first_time, first_views = ordered[0]
    last_time, last_views = ordered[-1]
    days = max((last_time - first_time).total_seconds() / 86400, 1 / 24)
    growth = last_views - first_views
    acceleration: float | None = None
    if len(ordered) >= 3:
        prev_time, prev_views = ordered[-2]
        previous_days = max((prev_time - first_time).total_seconds() / 86400, 1 / 24)
        previous_rate = (prev_views - first_views) / previous_days
        acceleration = (growth / days) - previous_rate
    return MomentumMetric(video_id, growth, growth / days, acceleration)


def repeated_outlier_count(metrics: list[OutlierMetric], minimum_multiple: float = 2.0) -> int:
    return sum(1 for metric in metrics if metric.outlier_multiple >= minimum_multiple)
