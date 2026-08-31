import asyncio
from datetime import datetime, timedelta, timezone

from apps.api.app.analytics.channel_performance import build_channel_profiles
from apps.api.app.analytics.comparisons import MAX_COMPARISON_TRANSCRIPT_CHARS, select_matched_pairs
from apps.api.app.analytics.recommendation import recommend
from apps.api.app.analytics.saturation import SaturationResult, assess_saturation
from apps.api.app.analytics.shorts import ShortStatus, classify_short
from apps.api.app.domain.enums import RequestedFormat
from apps.api.app.research.orchestrator import _annotate_production_ideas, _assessment_video_groups, _build_rate_cohorts, _cluster_channel_profiles, _cluster_matched_pairs, _current_major_outliers, _current_outlier_videos, _english_evidence_allows, _mechanism_evidence_channel_count, _outlier_cohort_key, _select_representative_media_ids
from apps.api.app.sources.assets import FixtureAssetConnector, calculate_clip_ceiling
from apps.api.app.sources.base import BrowserMediaRecord, SearchResult, VideoRecord
from apps.api.app.sources.trends import DisabledTrendConnector


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def video(video_id: str, views: int, days: int, *, channel: str = "channel-a", duration: int = 45, is_short: bool = True) -> VideoRecord:
    return VideoRecord(video_id, channel, f"https://www.youtube.com/watch?v={video_id}", f"Visual test {video_id}", "", duration, NOW - timedelta(days=days), "27", ["test"], {}, views, is_short=is_short, format_label="proof format", topic="visual test")


def media(short: bool = True) -> BrowserMediaRecord:
    return BrowserMediaRecord("fixture", short, "Watch this fail. Now it works.", None, ["fixture://frame"], "The result appears first.", "large captions", ["hook", "failure", "proof"], NOW, .95, pacing_score=.8)


def test_shorts_classifier_distinguishes_confirmation_probability_and_long_form():
    item = video("confirmed", 10, 2)
    observation = SearchResult("confirmed", "https://youtube.com/shorts/confirmed", "t", "c", "c", "", "", True, 1)
    assert classify_short(item, observation, media()).status == ShortStatus.CONFIRMED
    assert classify_short(video("probable", 10, 2), None, None).status == ShortStatus.PROBABLE
    assert classify_short(video("long", 10, 2, duration=181, is_short=False), None, None).status == ShortStatus.NOT_SHORT


def test_keyless_landscape_and_unknown_aspect_cannot_be_promoted_by_duration():
    landscape = VideoRecord(**{
        **video("landscape", 10, 2, duration=90, is_short=False).__dict__,
        "shorts_evidence": "landscape",
    })
    unknown = VideoRecord(**{
        **video("unknown", 10, 2, duration=90, is_short=False).__dict__,
        "shorts_evidence": "aspect_ratio_unknown",
    })
    assert classify_short(landscape).status == ShortStatus.NOT_SHORT
    assert classify_short(unknown).status == ShortStatus.UNKNOWN


def test_channel_profiles_require_repeated_upload_context():
    items = [video("winner", 250_000, 10), video("normal", 70_000, 12), video("loser", 30_000, 14)]
    classifications = {item.youtube_video_id: classify_short(item, None, media()) for item in items}
    profile = build_channel_profiles(items, classifications, NOW)["channel-a"]
    assert profile["shorts_analyzed"] == 3
    assert profile["outliers_2x"] >= 1
    assert profile["successful"] is True
    assert profile["data_scope"].startswith("public")


def test_long_form_channel_profiles_include_only_requested_long_form_uploads():
    long_items = [video("long-winner", 250_000, 10, duration=600, is_short=False), video("long-normal", 70_000, 12, duration=540, is_short=False), video("long-loser", 30_000, 14, duration=720, is_short=False)]
    short_item = video("short-control", 500_000, 8)
    items = [*long_items, short_item]
    classifications = {item.youtube_video_id: classify_short(item) for item in items}
    profile = build_channel_profiles(items, classifications, NOW, requested_format=RequestedFormat.LONG_FORM)["channel-a"]
    assert profile["uploads_analyzed"] == 3
    assert profile["longform_analyzed"] == 3
    assert profile["shorts_analyzed"] == 0
    assert profile["successful"] is True


def test_channel_success_uses_bounded_media_and_repeatable_format_cohorts():
    format_a = [video("a-winner", 300_000, 10), video("a-control", 10_000, 10)]
    format_b = [
        VideoRecord(**{**video("b-one", 10_000, 10).__dict__, "format_label": "ranking format"}),
        VideoRecord(**{**video("b-two", 10_000, 12).__dict__, "format_label": "ranking format"}),
    ]
    stale = video("a-stale", 1_000, 200)
    items = [*format_a, *format_b, stale]
    classifications = {item.youtube_video_id: classify_short(item) for item in items}
    profile = build_channel_profiles(items, classifications, NOW)["channel-a"]
    assert profile["uploads_analyzed"] == 4
    assert len(profile["cohorts"]) == 2
    assert profile["successful"] is False


def test_candidate_channel_success_cannot_come_from_an_unrelated_format():
    profiles = {"channel-a": {"cohorts": [
        {"repeatable_format": "proof format", "uploads_analyzed": 2, "outliers_2x": 1, "outlier_multiples": [4, .5], "successful": False},
        {"repeatable_format": "ranking format", "uploads_analyzed": 4, "outliers_2x": 2, "outlier_multiples": [5, 3, 1, .5], "successful": True},
    ], "successful": True}}
    selected = _cluster_channel_profiles(profiles, [video("proof-candidate", 100_000, 5)])
    assert selected["channel-a"]["successful"] is False
    assert selected["channel-a"]["uploads_analyzed"] == 2


def test_both_requests_create_non_overlapping_media_assessment_inputs():
    short = video("short-assessment", 100_000, 5)
    longform = video("long-assessment", 100_000, 5, duration=600, is_short=False)
    items = [short, longform]
    classifications = {item.youtube_video_id: classify_short(item) for item in items}
    groups = _assessment_video_groups(items, classifications, RequestedFormat.BOTH)
    assert [(kind.value, [item.youtube_video_id for item in group]) for kind, group in groups] == [
        ("shorts", ["short-assessment"]),
        ("long_form", ["long-assessment"]),
    ]


def test_explicit_non_english_evidence_is_not_replaced_by_unknown_fallback():
    assert _english_evidence_allows(None) is True
    assert _english_evidence_allows("これは英語ではない動画です") is False


def test_current_outlier_gate_uses_configured_three_x_default():
    from types import SimpleNamespace
    weak = video("strong-not-outlier", 10, 5)
    outlier = video("actual-outlier", 10, 5)
    metrics = {
        weak.youtube_video_id: SimpleNamespace(recency_bucket="current", outlier_multiple=2.99),
        outlier.youtube_video_id: SimpleNamespace(recency_bucket="current", outlier_multiple=3.0),
    }
    assert [item.youtube_video_id for item in _current_outlier_videos([weak, outlier], metrics, 3.0)] == ["actual-outlier"]


def test_major_outlier_summary_excludes_supporting_window_observations():
    outliers = [
        {"video_id": "current", "outlier_label": "major outlier", "recency_bucket": "current"},
        {"video_id": "supporting", "outlier_label": "major outlier", "recency_bucket": "supporting"},
        {"video_id": "strong", "outlier_label": "outlier", "recency_bucket": "current"},
    ]
    assert [item["video_id"] for item in _current_major_outliers(outliers)] == ["current"]


def test_outlier_cohorts_are_partitioned_by_known_format_label():
    first = video("format-a", 10_000, 10)
    second = VideoRecord(**{**first.__dict__, "youtube_video_id": "format-b", "format_label": "ranking format"})
    first_classification = classify_short(first)
    assert _outlier_cohort_key(first, first_classification) != _outlier_cohort_key(second, classify_short(second))


def test_outlier_cohorts_partition_shorts_and_longform_with_same_format_label():
    short = video("short", 10_000, 10)
    longform = VideoRecord(**{
        **short.__dict__,
        "youtube_video_id": "longform",
        "duration_seconds": 600,
        "is_short": False,
        "format_label": short.format_label,
    })
    short_key = _outlier_cohort_key(short, classify_short(short))
    long_key = _outlier_cohort_key(longform, classify_short(longform))
    assert short_key[0] == long_key[0]
    assert short_key[1].startswith("shorts:")
    assert long_key[1].startswith("long_form:")
    assert short_key != long_key


def test_outlier_baseline_excludes_uploads_older_than_supporting_window():
    candidate = video("candidate", 100_000, 10)
    recent_control = video("recent-control", 10_000, 10)
    historical_low_rate = video("historical", 10_000, 200)
    items = [candidate, recent_control, historical_low_rate]
    classifications = {item.youtube_video_id: classify_short(item) for item in items}
    rates, cohorts = _build_rate_cohorts(items, classifications, NOW, 90)
    key = _outlier_cohort_key(candidate, classifications[candidate.youtube_video_id])
    assert rates[historical_low_rate.youtube_video_id] > 0
    assert len(cohorts[key]) == 2
    assert rates[historical_low_rate.youtube_video_id] not in cohorts[key]


def test_heavy_media_targets_honor_the_configured_bound_and_channel_diversity():
    items = [video(f"v{index}", 100_000 - index * 1000, 5 + index, channel=f"channel-{index % 8}") for index in range(20)]
    selected = _select_representative_media_ids(items, 6)
    assert len(selected) == 6
    assert len({item.channel_id for item in items if item.youtube_video_id in selected}) == 6
    assert len(_select_representative_media_ids(items, 12)) == 12


def test_mechanism_replication_counts_only_channels_in_supporting_evidence():
    from types import SimpleNamespace
    evidence = [
        SimpleNamespace(id="ev-1", evidence_type="browser_media_observation", confidence=.9, payload={"channel_id": "channel-a", "observable_structure": ["attempt then proof"]}),
        SimpleNamespace(id="ev-2", evidence_type="browser_media_observation", confidence=.9, payload={"channel_id": "channel-b", "visible_transcript": "Will it hold? It works."}),
        SimpleNamespace(id="ev-3", evidence_type="browser_media_observation", confidence=.9, payload={"channel_id": "channel-c", "opening_visual_summary": "paper bridge under load"}),
    ]
    assert _mechanism_evidence_channel_count(evidence, ["ev-1"]) == 1
    assert _mechanism_evidence_channel_count(evidence, ["ev-1", "ev-2", "unknown"]) == 2


def test_matched_pairs_use_same_channel_family_and_performance_gap():
    items = [video("winner", 300_000, 10), video("normal", 50_000, 12), video("loser", 10_000, 14)]
    pairs = select_matched_pairs(items, {"winner": 5, "normal": 1, "loser": .2}, {item.youtube_video_id: media() for item in items})
    assert len(pairs) == 1
    assert pairs[0]["winner"]["id"] == "winner"
    assert pairs[0]["loser"]["id"] == "loser"
    assert "same channel" in pairs[0]["match_basis"]
    assert pairs[0]["match_quality"]["same_topic"] is True
    assert pairs[0]["purpose"].startswith("Hold creator")
    assert pairs[0]["performance_metric"] == "outlier_multiple"
    assert pairs[0]["performance_ratio"] == 25.0


def test_matched_pairs_allow_three_independent_pairs_across_two_channels_and_bound_transcripts():
    items = [
        video("a-win-1", 9000, 10, channel="a"), video("a-loss-1", 1000, 10, channel="a"),
        video("a-win-2", 8000, 11, channel="a"), video("a-loss-2", 1000, 11, channel="a"),
        video("b-win", 7000, 12, channel="b"), video("b-loss", 1000, 12, channel="b"),
    ]
    multiples = {
        "a-win-1": 8, "a-loss-1": .5, "a-win-2": 6, "a-loss-2": 1,
        "b-win": 5, "b-loss": .5,
    }
    long_media = BrowserMediaRecord(**{
        **media().__dict__,
        "visible_transcript": "bounded words " * 10_000,
    })
    pairs = select_matched_pairs(
        items, multiples, {item.youtube_video_id: long_media for item in items}, limit=6
    )
    assert len(pairs) == 3
    assert {pair["channel_id"] for pair in pairs} == {"a", "b"}
    used = [identifier for pair in pairs for identifier in (pair["winner"]["id"], pair["loser"]["id"])]
    assert len(used) == len(set(used))
    assert all(len(pair["winner"]["transcript"]) <= MAX_COMPARISON_TRANSCRIPT_CHARS for pair in pairs)
    assert all(pair["winner"]["transcript_truncated"] for pair in pairs)


def test_matched_pair_limit_is_applied_independently_per_semantic_cluster():
    from types import SimpleNamespace

    first_cluster = [
        video(f"a-{channel}-{kind}", 300_000 if kind == "winner" else 10_000, 10, channel=f"channel-a-{channel}")
        for channel in range(6)
        for kind in ("winner", "loser")
    ]
    second_cluster = [
        video(f"b-{channel}-{kind}", 300_000 if kind == "winner" else 10_000, 10, channel=f"channel-b-{channel}")
        for channel in range(3)
        for kind in ("winner", "loser")
    ]
    all_videos = [*first_cluster, *second_cluster]
    multiples = {
        item.youtube_video_id: 5.0 if item.youtube_video_id.endswith("winner") else .2
        for item in all_videos
    }
    assessed = [
        (RequestedFormat.SHORTS, SimpleNamespace(video_ids=[item.youtube_video_id for item in first_cluster]), all_videos),
        (RequestedFormat.SHORTS, SimpleNamespace(video_ids=[item.youtube_video_id for item in second_cluster]), all_videos),
    ]
    selected = _cluster_matched_pairs(
        assessed,
        multiples,
        {item.youtube_video_id: media() for item in all_videos},
    )
    winner_ids = [pair["winner"]["id"] for _, pair in selected]
    assert sum(item.startswith("a-") for item in winner_ids) == 6
    assert sum(item.startswith("b-") for item in winner_ids) == 3


def test_saturation_density_reports_the_retained_supporting_window():
    items = [video(f"recent-{index}", 10_000, 10 + index, channel=f"channel-{index}") for index in range(3)]
    result = assess_saturation(items, [1.0, 1.0, 1.0], 90, NOW)
    assert result.evidence_window_days == 90
    assert result.recent_upload_density == 1.0


def test_clip_preflight_counts_only_rights_known_three_clip_ideas():
    result = asyncio.run(calculate_clip_ceiling([f"idea {index}" for index in range(15)], FixtureAssetConnector()))
    assert result["validated_count"] == 12
    assert result["asset_coverage"] == .8
    assert result["source_diversity"] >= 2
    assert "does not gate" in result["rights_note"]
    assert result["semantic_fit_share"] == .8


def test_idea_annotations_preserve_exact_user_production_constraints():
    annotated = _annotate_production_ideas(
        ["paper bridge", "coin test"],
        {"validated_ideas": ["paper bridge"]},
        ["low editing", "stock or archive footage"],
    )
    assert all(item["production_constraints"] == ["low editing", "stock or archive footage"] for item in annotated)
    assert all(item["faceless_suitability"] == "not_requested" for item in annotated)
    unconstrained = _annotate_production_ideas(["paper bridge"], {"validated_ideas": []}, [])
    assert unconstrained[0]["production_constraints"] == []
    assert unconstrained[0]["constraint_status"] == "none_specified"


def test_recommendation_exposes_all_hard_gates():
    saturation = SaturationResult(3, 3, 3, .4, .1, .2, .4, .35, "low")
    result = recommend(RequestedFormat.SHORTS, 3, 3, {"unique_count": 15}, {"validated_count": 12, "asset_coverage": .8, "source_diversity": 2, "rights_metadata_share": 1, "reveal_coverage": .8, "semantic_fit_share": .8}, saturation, .85, .9, successful_channel_count=3, outlier_channel_count=3, comparison_count=3, mechanism_channel_count=3)
    assert result.hard_gates["all_passed"] is True
    assert result.hard_gates["total"] == 8
    assert result.verdict.value == "Shorts only"


def test_recommendation_function_clamps_weaker_internal_gate_overrides():
    saturation = SaturationResult(2, 2, 1, .4, .1, .2, .4, .5, "moderate")
    result = recommend(
        RequestedFormat.SHORTS, 2, 1,
        {"unique_count": 2},
        {"validated_count": 2, "asset_coverage": .2, "source_diversity": 1, "reveal_coverage": 0, "semantic_fit_share": .2},
        saturation, .9, .9,
        successful_channel_count=2, outlier_channel_count=1, comparison_count=1,
        mechanism_channel_count=2, minimum_ideas=1, minimum_clip_coverage=0,
        minimum_channels=1, minimum_outliers=1, minimum_outlier_channels=1,
        minimum_comparisons=1, maximum_saturation=1,
    )
    assert result.hard_gates["idea_ceiling"]["required"] == 10
    assert result.hard_gates["successful_channels"]["required"] == 3
    assert result.hard_gates["recent_outliers"]["required"] == 3
    assert result.hard_gates["outlier_channels"]["required"] == 2
    assert result.hard_gates["winner_loser_pairs"]["required"] == 3
    assert result.hard_gates["saturation"]["required"] == .75
    assert result.hard_gates["all_passed"] is False


def test_external_trends_are_optional_and_network_free_by_default():
    result = asyncio.run(DisabledTrendConnector().assess(["visual tests"], ["US"], 90))
    assert result == {"enabled": False, "status": "not_configured", "score": None, "observations": [], "weight": 0}
