from datetime import datetime, timedelta, timezone

from apps.api.app.analytics.metrics import age_days, median_baseline, outlier_label, outlier_metric, snapshot_momentum, views_per_day


def test_views_per_day_and_age():
    now = datetime.now(timezone.utc)
    published = now - timedelta(days=4)
    assert age_days(published, now) == 4
    assert views_per_day(400, published, now) == 100


def test_median_baseline_excludes_candidate():
    assert median_baseline([10, 20, 100], exclude=100) == 15
    metric = outlier_metric("v", 100, [10, 20, 100])
    assert metric.outlier_multiple == 6.666666666666667
    assert metric.label == "major outlier"


def test_edge_cases_and_labels():
    now = datetime.now(timezone.utc)
    assert views_per_day(10, now, now) == 10
    assert median_baseline([]) == 0
    assert outlier_label(.5) == "below normal"
    assert outlier_label(2.2) == "strong"
    assert outlier_label(3.2) == "outlier"


def test_outlier_labels_follow_configured_threshold_and_history_is_display_only():
    assert outlier_label(3.5, outlier_threshold=4.0) == "strong"
    assert outlier_label(4.0, outlier_threshold=4.0) == "outlier"
    historical = outlier_metric(
        "historical", 1_000, [100, 100, 1_000],
        video_age_days=91, baseline_recency_days=90,
        outlier_threshold=4.0,
    )
    assert historical.recency_bucket == "historical"
    assert historical.outlier_multiple == 0
    assert historical.label == "historical"
    assert historical.confidence == 0


def test_snapshot_growth_and_acceleration():
    now = datetime.now(timezone.utc)
    metric = snapshot_momentum("v", [(now - timedelta(days=2), 100), (now - timedelta(days=1), 250), (now, 500)])
    assert metric.absolute_growth == 400
    assert metric.views_gained_per_day == 200
    assert metric.acceleration is not None
