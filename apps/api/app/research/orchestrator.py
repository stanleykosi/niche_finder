"""Bounded evidence pipeline for finding, validating, and rejecting niches."""

from __future__ import annotations

import logging
import json
import hashlib
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from ..ai.base import AIProvider
from ..ai.embeddings import EmbeddingsProvider, FakeEmbeddingsProvider
from ..ai.schemas import (
    CandidateSynthesis,
    CriticAssessment,
    NicheClassification,
    ReportSynthesis,
    VideoEvidenceAnalysis,
    ViralMechanism,
    VisualStructureAnalysis,
    WinnerLoserComparison,
)
from ..analytics.channel_performance import build_channel_profiles
from ..analytics.clustering import cluster_videos
from ..analytics.comparisons import select_matched_pairs
from ..analytics.idea_ceiling import calculate_idea_ceiling
from ..analytics.metrics import age_days, outlier_metric, snapshot_momentum, views_per_day
from ..analytics.recommendation import recommend
from ..analytics.saturation import assess_saturation
from ..analytics.shorts import ShortStatus, classify_short, summarize_short_classifications
from ..core.config import Settings
from ..core.errors import ErrorCode, NicheIntelError
from ..db.models import ResearchRun
from ..domain.contracts import ResearchRunCreate
from ..domain.enums import RequestedFormat, SourceType, Verdict
from ..repositories.store import ResearchRepository
from ..sources.assets import AssetConnector, AssetRunSession, calculate_clip_ceiling
from ..sources.base import BrowserMediaRecord, ChannelRecord, DiscoveryRequest, SearchResult, VideoRecord
from ..sources.quota import QuotaManager
from ..sources.media_analysis import PassthroughMediaAnalyzer
from .preprocessing import english_likelihood, preprocess_video
from ..sources.router import RoutingTask, SourceRouter
from .planner import ResearchPlanner
from .evidence_packets import adjudicate_llm_output, transcript_segments, validate_citations
from ..storage.artifacts import RuntimeArtifactManager

logger = logging.getLogger(__name__)


class ResearchOrchestrator:
    def __init__(self, settings: Settings, repository: ResearchRepository, ai: AIProvider, assets: AssetConnector, browser: Any, youtube: Any, trends: Any, quota: QuotaManager | None = None, media_analyzer: Any | None = None, artifact_manager: RuntimeArtifactManager | None = None, embeddings: EmbeddingsProvider | None = None, source_health: Any | None = None) -> None:
        self.settings = settings
        self.repository = repository
        self.ai = ai
        self.assets = assets
        self.browser = browser
        self.youtube = youtube
        self.trends = trends
        self.quota = quota or QuotaManager(settings.youtube_api_daily_search_budget, settings.youtube_api_reserved_search_calls)
        self.router = SourceRouter(settings.app_mode, self.quota)
        self.planner = ResearchPlanner()
        self.media_analyzer = media_analyzer or PassthroughMediaAnalyzer()
        self.artifacts = artifact_manager or RuntimeArtifactManager(settings, repository)
        self.embeddings = embeddings or FakeEmbeddingsProvider()
        self.source_health = source_health
        self.cancelled_runs: set[str] = set()
        self._run_context: dict[str, dict[str, Any]] = {}

    async def execute(self, run: ResearchRun, request: ResearchRunCreate | None = None) -> ResearchRun:
        request = request or ResearchRunCreate.model_validate(run.configuration)
        run_id = run.id
        preflight_asset_session = AssetRunSession(
            self.assets,
            self.settings.asset_max_ideas_per_run,
            final_reserve=max(10, request.minimum_idea_ceiling),
        )
        try:
            self._transition(run, "planning")
            plan = self.planner.create(request)
            self.repository.upsert_evidence(run_id, {
                "evidence_type": "research_plan",
                "source_type": "deterministic",
                "source_entity_id": run_id,
                "payload": {
                    "discovery_strategy": plan.discovery_strategy,
                    "covered_markets": plan.covered_markets,
                    "queries": plan.queries,
                    "query_count": len(plan.queries),
                    "target_candidate_count": plan.target_candidate_count,
                    "discovery_video_limit": _discovery_video_limit(request),
                    "reserved_channel_upload_capacity": request.limits.max_videos - _discovery_video_limit(request),
                    "total_video_limit": request.limits.max_videos,
                },
                "confidence": 1.0,
                "human_readable_summary": (
                    f"Planned a {len(plan.queries)}-query cross-market sweep across {len(plan.covered_markets)} concrete markets."
                    if plan.discovery_strategy == "cross_market_portfolio"
                    else f"Planned {len(plan.queries)} bounded queries from user-provided seeds."
                ),
            })
            self._check_cancelled(run_id)
            expanded_checkpoint = self.repository.get_checkpoint(run_id, "expanded_enrichment_complete")
            if expanded_checkpoint is not None:
                search_items = {
                    item["youtube_video_id"]: _search_result_from_payload(item)
                    for item in expanded_checkpoint.get("search_items", [])
                }
                videos = [
                    preprocess_video(_video_from_payload(item))
                    for item in expanded_checkpoint.get("videos", [])
                ]
                initial_clip_preflight = dict(expanded_checkpoint.get("initial_clip_preflight", {}))
                logger.info(
                    "resumed expanded enrichment checkpoint",
                    extra={"research_run_id": run_id, "stage": "enriching", "video_count": len(videos)},
                )
            else:
                discovery_checkpoint = self.repository.get_checkpoint(run_id, "discovery_complete")
                if discovery_checkpoint is not None:
                    search_items = {
                        item["youtube_video_id"]: _search_result_from_payload(item)
                        for item in discovery_checkpoint.get("search_items", [])
                    }
                    logger.info(
                        "resumed discovery checkpoint",
                        extra={"research_run_id": run_id, "stage": "discovering", "video_count": len(search_items)},
                    )
                else:
                    search_items = await self._discover(run_id, request, plan)
                    self.repository.save_checkpoint(
                        run_id,
                        "discovery_complete",
                        {"search_items": [_search_result_to_payload(item) for item in search_items.values()]},
                        f"Discovery checkpoint retained {len(search_items)} candidate videos.",
                    )
                self._check_cancelled(run_id)
                self._transition(run, "enriching")
                initial_ids = list(search_items)[:request.limits.max_videos]
                discovery_context = {video_id: _discovery_enrichment_context(search_items[video_id]) for video_id in initial_ids}
                videos = [preprocess_video(video) for video in await self.youtube.enrich_videos(initial_ids, discovery_context)]
                self._drain_source_diagnostics(run_id)
                if not videos:
                    raise NicheIntelError("No candidate videos were discovered")
                # Fast production-feasibility rejection happens before channel
                # expansion, comments, transcripts, screenshots, or vision work.
                initial_clip_preflight = {}
                retained_initial_ids: set[str] = set()
                initial_classifications = {
                    video.youtube_video_id: classify_short(video, search_items.get(video.youtube_video_id))
                    for video in videos
                }
                initial_cluster_jobs = [
                    (assessment_format, format_records, initial_cluster)
                    for assessment_format, format_records in _assessment_video_groups(
                        videos, initial_classifications, request.requested_format
                    )
                    for initial_cluster in cluster_videos(format_records, self.embeddings)
                ]
                preflight_allocations = _fair_allocations(
                    preflight_asset_session.preflight_capacity, len(initial_cluster_jobs)
                )
                semantic_validation_available = bool(
                    getattr(self.ai, "supports_semantic_image_validation", False)
                )
                for (assessment_format, format_records, initial_cluster), preflight_allocation in zip(
                    initial_cluster_jobs, preflight_allocations, strict=True
                ):
                    preflight_key = _assessment_cluster_key(assessment_format, initial_cluster.label)
                    cached_preflight = self.repository.evidence_item(
                        run_id, "initial_clip_preflight", preflight_key
                    )
                    if cached_preflight is not None:
                        preflight = dict(cached_preflight.payload)
                    else:
                        initial_records = [
                            video for video in format_records
                            if video.youtube_video_id in initial_cluster.video_ids
                        ]
                        idea_checkpoint = self.repository.get_checkpoint(
                            run_id, f"preflight_ideas:{preflight_key}"
                        )
                        if idea_checkpoint is not None and isinstance(idea_checkpoint.get("idea"), dict):
                            preliminary_ideas = dict(idea_checkpoint["idea"])
                        else:
                            preliminary_ideas = await calculate_idea_ceiling(
                                initial_records,
                                self.ai,
                                [],
                                "Lightweight clip-supply preflight; do not treat this as the final idea ceiling.",
                                self.embeddings,
                            )
                            self.repository.save_checkpoint(
                                run_id,
                                f"preflight_ideas:{preflight_key}",
                                {"idea": preliminary_ideas},
                                f"Completed durable preliminary idea generation for {preflight_key}.",
                            )
                        preliminary_clips = await calculate_clip_ceiling(
                            preliminary_ideas["candidate_ideas"],
                            preflight_asset_session,
                            visual_validator=self.ai,
                            phase="preflight",
                            maximum_new_ideas=preflight_allocation,
                        )
                        preflight_search_bounds = preliminary_clips.get("search_bounds", {})
                        preflight_sampling_coverage = (
                            int(preflight_search_bounds.get("evaluated_ideas", 0))
                            / max(int(preflight_search_bounds.get("searched_ideas", 0)), 1)
                        )
                        preflight_conclusive = (
                            preflight_sampling_coverage >= request.minimum_clip_coverage
                        )
                        preflight = {
                            "stage": "pre_expansion_clip_preflight",
                            "cluster_label": initial_cluster.label,
                            "assessment_format": assessment_format.value,
                            "video_ids": list(initial_cluster.video_ids),
                            "generated_ideas": preliminary_ideas["unique_count"],
                            "validated_count": preliminary_clips["validated_count"],
                            "asset_coverage": preliminary_clips["asset_coverage"],
                            "evaluated_asset_coverage": preliminary_clips["evaluated_asset_coverage"],
                            "rights_metadata_share": preliminary_clips["rights_metadata_share"],
                            "source_diversity": preliminary_clips["source_diversity"],
                            "provider_diagnostics": preliminary_clips.get("provider_diagnostics", []),
                            "search_bounds": preflight_search_bounds,
                            "sampling_coverage": round(preflight_sampling_coverage, 3),
                            "conclusive": preflight_conclusive,
                            "passed": preflight_conclusive and preliminary_clips["evaluated_asset_coverage"] >= request.minimum_clip_coverage,
                            "semantic_validation_available": semantic_validation_available,
                        }
                        if not preflight_conclusive:
                            preflight["deferred_to_final_validation"] = True
                            preflight["reason"] = (
                                "The fair preflight allocation was too small for a conclusive rejection; "
                                "the authoritative final pass retains its reserved budget."
                            )
                        elif (
                            not preflight["passed"]
                            and not semantic_validation_available
                            and not self.settings.uses_fixture_sources
                        ):
                            preflight["retained_for_negative_assessment"] = True
                            preflight["reason"] = (
                                "Semantic image validation is unavailable; the candidate is retained only "
                                "to produce an insufficient-evidence assessment and cannot pass the clip gate."
                            )
                        self.repository.upsert_evidence(run_id, {
                            "evidence_type": "initial_clip_preflight",
                            "source_type": "asset_fixture" if self.settings.uses_fixture_sources else "deterministic",
                            "source_entity_id": preflight_key,
                            "payload": preflight,
                            "confidence": .98 if self.settings.uses_fixture_sources else .8,
                            "human_readable_summary": f"Early {assessment_format.value} clip preflight for {initial_cluster.label}: {preflight['validated_count']} ideas validated; coverage {preflight['asset_coverage']:.0%}.",
                        })
                    initial_clip_preflight[preflight_key] = preflight
                    if (
                        preflight.get("passed")
                        or preflight.get("deferred_to_final_validation")
                        or preflight.get("retained_for_negative_assessment")
                    ):
                        retained_initial_ids.update(preflight.get("video_ids") or initial_cluster.video_ids)
                if not retained_initial_ids:
                    raise NicheIntelError("All discovered niches failed the early real-clip availability gate")
                videos = [video for video in videos if video.youtube_video_id in retained_initial_ids]
                videos = [preprocess_video(video) for video in await self._expand_channels(run_id, videos, request)]
                persisted_videos = _persisted_video_records(self.repository, run_id)
                videos = list({
                    video.youtube_video_id: video
                    for video in [*persisted_videos, *videos]
                }.values())[:request.limits.max_videos]
                self.repository.save_checkpoint(
                    run_id,
                    "expanded_enrichment_complete",
                    {
                        "search_items": [_search_result_to_payload(item) for item in search_items.values()],
                        "videos": [_video_to_payload(video) for video in videos],
                        "initial_clip_preflight": initial_clip_preflight,
                    },
                    f"Expanded-enrichment checkpoint retained {len(videos)} normalized videos.",
                )

            if not videos:
                raise NicheIntelError("The expanded-enrichment checkpoint contains no usable videos")
            self._transition(run, "enriching")

            source_name = "fixture_api" if self.settings.uses_fixture_sources else "youtube_api" if self.settings.youtube_api_key else "keyless_ytdlp"
            channel_ids = list(dict.fromkeys(video.channel_id for video in videos))[:request.limits.max_channels]
            channel_checkpoint = self.repository.get_checkpoint(run_id, "channel_enrichment_complete")
            if channel_checkpoint is not None:
                channel_records = [
                    _channel_from_payload(item)
                    for item in channel_checkpoint.get("channels", [])
                ]
            else:
                channel_records = await self.youtube.enrich_channels(channel_ids)
                self.repository.save_checkpoint(
                    run_id,
                    "channel_enrichment_complete",
                    {"channels": [_channel_to_payload(item) for item in channel_records]},
                    f"Channel enrichment checkpoint retained {len(channel_records)} channels.",
                )
            channel_models = {
                item.youtube_channel_id: self.repository.upsert_channel(item, source_name, run_id)
                for item in channel_records
            }
            video_models: dict[str, Any] = {}
            media_by_video: dict[str, BrowserMediaRecord] = {}
            persisted_media = _persisted_media_records(self.repository, run_id)
            processed_video_ids = {
                str(item.source_entity_id)
                for item in self.repository.get_evidence(run_id)
                if item.evidence_type == "video_enrichment" and item.source_entity_id
            }
            filmstrip_targets = _select_representative_media_ids(videos, self.settings.media_max_videos_per_run)
            heavy_media_targets = filmstrip_targets if getattr(self.media_analyzer, "requires_download", False) else {video.youtube_video_id for video in videos}
            for video in videos:
                model = self.repository.upsert_video(video, channel_models.get(video.channel_id), source_name, run_id)
                video_models[video.youtube_video_id] = model
                if video.youtube_video_id in processed_video_ids and video.youtube_video_id in persisted_media:
                    media_by_video[video.youtube_video_id] = persisted_media[video.youtube_video_id]
                    logger.info(
                        "resumed completed video checkpoint",
                        extra={
                            "research_run_id": run_id,
                            "stage": "enriching",
                            "video_id": video.youtube_video_id,
                        },
                    )
                    continue
                comments = await self.youtube.sample_comments(video.youtube_video_id, 3)
                self.repository.add_comment_samples(model.id, comments, source_name)
                media = await self._inspect_video_with_partial_result(
                    run_id, video, capture_frames=video.youtube_video_id in filmstrip_targets
                )
                if video.youtube_video_id in heavy_media_targets:
                    media = await self.media_analyzer.analyze(run_id, video, media)
                else:
                    media = BrowserMediaRecord(**{
                        **media.__dict__,
                        "visual_features": {
                            **media.visual_features,
                            "heavy_media_analysis": "skipped_not_representative",
                            "heavy_media_limit": self.settings.media_max_videos_per_run,
                        },
                    })
                for frame_ref in media.frame_refs:
                    frame_path = Path(frame_ref)
                    if frame_path.is_file() and str(frame_path.resolve()).startswith(str(Path(self.settings.browser_profile_root).resolve())):
                        self.artifacts.register(frame_path, "browser_screenshot", run_id, self.settings.browser_artifact_retention_hours, {"video_id": video.youtube_video_id})
                media_by_video[video.youtube_video_id] = media
                self.repository.add_browser_media(run_id, model.id, media)
                if media.visual_features.get("deepgram_status") == "download_unavailable":
                    self.repository.upsert_evidence(run_id, {
                        "evidence_type": "media_analysis_unavailable",
                        "source_type": SourceType.KEYLESS_YTDLP.value,
                        "source_entity_id": video.youtube_video_id,
                        "observed_at": media.observed_at,
                        "payload": {
                            "video_id": video.youtube_video_id,
                            "channel_id": video.channel_id,
                            "status": "partial_browser_only",
                            "reason": media.visual_features.get("media_download_error"),
                            "error_code": media.visual_features.get("media_download_error_code"),
                            "partial": True,
                            "missing_fields": [
                                "deepgram_transcript",
                                "word_timestamps",
                                "ffmpeg_frames",
                            ],
                        },
                        "confidence": 0.0,
                        "human_readable_summary": (
                            f"Heavy media analysis for {video.title} was unavailable; "
                            "browser evidence was retained and the run continued."
                        ),
                    })
                self.repository.upsert_evidence(run_id, {
                    "evidence_type": "browser_media_observation",
                    "source_type": "fixture_browser" if self.settings.uses_fixture_sources else "browser",
                    "source_entity_id": video.youtube_video_id,
                    "observed_at": media.observed_at,
                    "payload": {
                        "video_id": video.youtube_video_id,
                        "channel_id": video.channel_id,
                        "source_profile": media.source_profile,
                        "is_short_presentation": media.is_short_presentation,
                        "visible_transcript": media.visible_transcript,
                        "thumbnail_ref": media.thumbnail_ref,
                        "frame_refs": media.frame_refs,
                        "opening_visual_summary": media.opening_visual_summary,
                        "caption_style": media.caption_style,
                        "observable_structure": media.observable_structure,
                        "first_spoken_line": media.first_spoken_line,
                        "duration_seconds": media.duration_seconds,
                        "scene_change_count": media.scene_change_count,
                        "average_shot_duration_seconds": media.average_shot_duration_seconds,
                        "reveal_timestamp_seconds": media.reveal_timestamp_seconds,
                        "caption_density": media.caption_density,
                        "motion_score": media.motion_score,
                        "pacing_score": media.pacing_score,
                        "visual_features": media.visual_features,
                        "english_likelihood": english_likelihood(media.visible_transcript),
                        "music_cue_count": media.music_cue_count,
                        "editing_pattern": media.editing_pattern,
                    },
                    "confidence": media.confidence,
                    "human_readable_summary": f"Browser inspection for {video.title}: transcript, frames, presentation, and observable structure captured with provenance.",
                })
                self.repository.upsert_evidence(run_id, {
                    "evidence_type": "video_enrichment", "source_type": source_name, "source_entity_id": video.youtube_video_id,
                    "payload": _video_to_payload(video),
                    "confidence": .99 if source_name == "fixture_api" else .96,
                    "human_readable_summary": f"Observed {video.title} with {video.view_count:,} public views.",
                })
                self.repository.save_checkpoint(
                    run_id,
                    f"video_complete:{video.youtube_video_id}",
                    {"video": _video_to_payload(video), "media": _media_to_payload(media)},
                    f"Completed and released temporary media for {video.youtube_video_id}.",
                )

            self.repository.save_checkpoint(
                run_id,
                "video_enrichment_complete",
                {"video_ids": [video.youtube_video_id for video in videos]},
                f"Per-video enrichment checkpoint completed {len(videos)} videos.",
            )

            classifications = {video.youtube_video_id: classify_short(video, search_items.get(video.youtube_video_id), media_by_video.get(video.youtube_video_id)) for video in videos}
            for video in videos:
                item = classifications[video.youtube_video_id]
                self.repository.upsert_evidence(run_id, {
                    "evidence_type": "shorts_classification", "source_type": "deterministic", "source_entity_id": video.youtube_video_id,
                    "payload": {"video_id": video.youtube_video_id, "channel_id": video.channel_id, **item.as_dict()},
                    "confidence": item.confidence, "human_readable_summary": f"{video.title}: {item.status.value} ({'; '.join(item.reasons)}).",
                })

            assessment_groups = _assessment_video_groups(videos, classifications, request.requested_format)
            analysis_videos = [video for _, group in assessment_groups for video in group]
            # English is the MVP target. Reject only positive evidence of a
            # different spoken language; missing transcripts remain unknown.
            analysis_videos = [video for video in analysis_videos if _english_evidence_allows(media_by_video[video.youtube_video_id].visible_transcript)]
            if not analysis_videos:
                raise NicheIntelError(f"No {request.requested_format.value} videos matched the requested format")
            assessment_groups = _assessment_video_groups(analysis_videos, classifications, request.requested_format)
            self._check_cancelled(run_id)
            self._transition(run, "analysing")
            now = datetime.now(timezone.utc)
            supporting_window_days = min(90, max(45, request.recency_days))
            rates, rates_by_cohort = _build_rate_cohorts(analysis_videos, classifications, now, supporting_window_days)
            outliers: dict[str, Any] = {}
            for video in analysis_videos:
                cohort_key = _outlier_cohort_key(video, classifications[video.youtube_video_id])
                metric = outlier_metric(
                    video.youtube_video_id, rates[video.youtube_video_id], rates_by_cohort[cohort_key],
                    age_days(video.published_at, now), min(45, request.recency_days),
                    supporting_window_days, self.settings.outlier_threshold,
                )
                outliers[video.youtube_video_id] = metric
                self.repository.add_outlier(run_id, video_models[video.youtube_video_id].id, {
                    "comparison_cohort": {"channel_id": cohort_key[0], "format": cohort_key[1], "cohort_size": metric.cohort_size, "age_days": metric.age_days, "recency_bucket": metric.recency_bucket, "outlier_threshold": self.settings.outlier_threshold},
                    "baseline_metric": metric.baseline_metric, "metric_value": metric.metric_value, "outlier_multiple": metric.outlier_multiple, "label": metric.label, "calculation_version": metric.calculation_version,
                })
                self.repository.upsert_evidence(run_id, {
                    "evidence_type": "deterministic_outlier", "source_type": "deterministic", "source_entity_id": video.youtube_video_id,
                    "payload": {"video_id": video.youtube_video_id, "channel_id": video.channel_id, "outlier_multiple": metric.outlier_multiple, "label": metric.label, "baseline": metric.baseline_metric, "age_days": metric.age_days, "recency_bucket": metric.recency_bucket, "cohort_size": metric.cohort_size, "outlier_threshold": self.settings.outlier_threshold},
                    "confidence": metric.confidence, "human_readable_summary": f"{video.title}: {metric.outlier_multiple:.1f}x same-channel baseline; {metric.recency_bucket} evidence.",
                })

            snapshot_histories = {video.youtube_video_id: self.repository.video_snapshot_history(video.youtube_video_id) for video in analysis_videos}
            snapshot_metrics = {video_id: snapshot_momentum(video_id, history) for video_id, history in snapshot_histories.items()}

            decision_videos = [
                video for video in analysis_videos
                if outliers[video.youtube_video_id].recency_bucket != "historical"
            ]
            decision_assessment_groups = _assessment_video_groups(
                decision_videos, classifications, request.requested_format
            )

            profiles_by_format = {
                assessment_format: build_channel_profiles(
                    decision_videos,
                    classifications,
                    now,
                    supporting_days=supporting_window_days,
                    outlier_threshold=self.settings.outlier_threshold,
                    requested_format=assessment_format,
                )
                for assessment_format, _ in decision_assessment_groups
            }
            multiple_map = {
                video_id: metric.outlier_multiple
                for video_id, metric in outliers.items()
                if metric.recency_bucket != "historical"
            }
            vision_by_video: dict[str, dict[str, Any]] = {}
            vision_target_ids = _select_vision_target_ids(
                decision_videos,
                heavy_media_targets,
                getattr(self.media_analyzer, "requires_download", False),
                self.settings.media_max_videos_per_run,
            )
            vision_targets = sorted(
                (video for video in decision_videos if video.youtube_video_id in vision_target_ids),
                key=lambda video: (rates[video.youtube_video_id], video.view_count),
                reverse=True,
            )
            for video in vision_targets:
                media = media_by_video.get(video.youtube_video_id)
                if media is None or not media.frame_refs:
                    continue
                visual = await self._checkpointed_ai(
                    run_id,
                    f"visual_analysis:{video.youtube_video_id}",
                    VisualStructureAnalysis,
                    lambda video=video, media=media: self.ai.analyze_visuals(
                        f"title={video.title}; opening={media.opening_visual_summary}; captions={media.caption_style}; structure={media.observable_structure}; pacing_score={media.pacing_score}",
                        media.frame_refs,
                        [],
                    ),
                )
                vision_by_video[video.youtube_video_id] = visual.model_dump()
                self.repository.upsert_evidence(run_id, {
                    "evidence_type": "visual_structure_analysis", "source_type": "ai", "source_entity_id": video.youtube_video_id,
                    "payload": {"video_id": video.youtube_video_id, "channel_id": video.channel_id, **visual.model_dump(), "frame_refs": media.frame_refs},
                    "confidence": visual.confidence, "human_readable_summary": f"Visual analysis for {video.title}: {visual.hook_visual}",
                })
            video_analysis_by_video: dict[str, dict[str, Any]] = {}
            interpretation_targets = sorted(
                decision_videos,
                key=lambda video: (multiple_map.get(video.youtube_video_id, 0), video.view_count),
                reverse=True,
            )[:12]
            for video in interpretation_targets:
                observed = media_by_video.get(video.youtube_video_id)
                ledger_records = [
                    item for item in self.repository.get_evidence(run_id)
                    if item.source_entity_id == video.youtube_video_id
                ]
                ledger_ids = [str(item.id) for item in ledger_records]
                packet = {
                    "packet_version": "video-evidence-packet-v1",
                    "video": {
                        "video_id": video.youtube_video_id,
                        "channel_id": video.channel_id,
                        "title": video.title,
                        "description": video.description[:1200],
                        "published_at": video.published_at.isoformat(),
                        "duration_seconds": video.duration_seconds,
                        "public_view_count": video.view_count,
                        "views_per_day": round(rates[video.youtube_video_id], 3),
                        "outlier_multiple": round(outliers[video.youtube_video_id].outlier_multiple, 3),
                        "outlier_label": outliers[video.youtube_video_id].label,
                        "format_classification": classifications[video.youtube_video_id].as_dict(),
                    },
                    "browser_observation": {
                        "opening_visual": observed.opening_visual_summary if observed else None,
                        "first_spoken_line": observed.first_spoken_line if observed else None,
                        "caption_style": observed.caption_style if observed else None,
                        "observable_structure": observed.observable_structure if observed else [],
                        "pacing_score": observed.pacing_score if observed else None,
                        "reveal_timestamp_seconds": observed.reveal_timestamp_seconds if observed else None,
                        "transcript_segments": transcript_segments(observed.visible_transcript if observed else None),
                    },
                    "visual_analysis": vision_by_video.get(video.youtube_video_id),
                    "evidence_ids": ledger_ids,
                }
                interpretation = await self._checkpointed_ai(
                    run_id,
                    f"video_analysis:{video.youtube_video_id}",
                    VideoEvidenceAnalysis,
                    lambda packet=packet, ledger_ids=ledger_ids: self.ai.analyze_video(
                        json.dumps(packet, default=str), ledger_ids
                    ),
                )
                citation_validation = validate_citations(
                    interpretation.supporting_evidence_ids + interpretation.transcript_evidence_ids,
                    ledger_ids,
                )
                interpretation_payload = {
                    **interpretation.model_dump(),
                    "citation_validation": citation_validation,
                    "packet_version": packet["packet_version"],
                }
                video_analysis_by_video[video.youtube_video_id] = interpretation_payload
                self.repository.upsert_evidence(run_id, {
                    "evidence_type": "video_ai_observation", "source_type": "ai", "source_entity_id": video.youtube_video_id,
                    "payload": {"video_id": video.youtube_video_id, "channel_id": video.channel_id, **interpretation_payload},
                    "confidence": interpretation.confidence if citation_validation["passed"] else 0.0,
                    "human_readable_summary": f"Evidence-bound video interpretation for {video.title}: {interpretation.observed_hook}",
                })
            assessed_clusters = [
                (assessment_format, cluster, format_videos)
                for assessment_format, format_videos in decision_assessment_groups
                for cluster in cluster_videos(format_videos, self.embeddings)
            ]
            comparisons: list[dict[str, Any]] = []
            all_evidence_ids = [str(item.id) for item in self.repository.get_evidence(run_id)]
            for assessment_format, pair in _cluster_matched_pairs(
                assessed_clusters,
                multiple_map,
                media_by_video,
            ):
                comparison_key = _comparison_checkpoint_key(assessment_format, pair)
                interpreted = await self._checkpointed_ai(
                    run_id,
                    f"comparison:{comparison_key}",
                    WinnerLoserComparison,
                    lambda pair=pair: self.ai.compare_winner_loser(
                        pair["winner"], pair["loser"], all_evidence_ids
                    ),
                )
                payload = _deterministic_comparison_payload(
                    pair,
                    interpreted.model_dump(),
                    assessment_format,
                )
                self.repository.add_comparison(run_id, {
                    "winner_video_id": video_models[pair["winner"]["id"]].id, "loser_video_id": video_models[pair["loser"]["id"]].id,
                    "payload": payload, "confidence": interpreted.confidence, "provider": self.ai.name,
                })
                comparisons.append(payload)
                self.repository.upsert_evidence(run_id, {
                    "evidence_type": "winner_loser_comparison",
                    "source_type": "ai",
                    "source_entity_id": comparison_key,
                    "payload": payload,
                    "confidence": interpreted.confidence,
                    "human_readable_summary": (
                        f"Compared winner {pair['winner']['id']} with loser {pair['loser']['id']} "
                        f"for {assessment_format.value}."
                    ),
                })
            self.repository.save_checkpoint(
                run_id,
                "comparative_analysis_complete",
                {"comparison_count": len(comparisons)},
                f"Comparative analysis completed {len(comparisons)} matched pairs.",
            )
            self._transition(run, "reporting")
            candidates: list[dict[str, Any]] = []
            ranked_assessed_clusters = sorted(
                assessed_clusters,
                key=lambda item: max(
                    (multiple_map.get(video_id, 0) for video_id in item[1].video_ids),
                    default=0,
                ),
                reverse=True,
            )
            # The authoritative final pass is candidate-scoped. Sharing one
            # remaining reserve across clusters makes every candidate after
            # the first unable to validate the ten ideas required for a
            # positive verdict. Candidate count and connector work remain
            # bounded by the request video limit and the configured <=30 idea
            # ceiling for each retained candidate.
            final_clip_capacity = max(10, self.settings.asset_max_ideas_per_run)
            for rank, (assessment_format, cluster, format_videos) in enumerate(
                ranked_assessed_clusters,
                start=1,
            ):
                candidate_key = _candidate_checkpoint_key(
                    assessment_format, cluster.label, cluster.video_ids
                )
                final_asset_session = AssetRunSession.for_final_candidate(
                    self.assets,
                    maximum_ideas=final_clip_capacity,
                )
                cluster_records = [video for video in format_videos if video.youtube_video_id in cluster.video_ids]
                cluster_channels = {video.channel_id for video in cluster_records}
                evidence = [item for item in self.repository.get_evidence(run_id) if item.source_entity_id in cluster.video_ids]
                evidence_ids = [str(item.id) for item in evidence]
                cluster_model = self.repository.add_cluster(run_id, {
                    "label": f"{assessment_format.value}: {cluster.label}", "description": cluster.description,
                    "centroid": cluster.centroid, "representative_video_ids": cluster.representative_video_ids, "confidence": cluster.confidence,
                })
                cluster_pairs = [
                    item for item in comparisons
                    if item["assessment_format"] == assessment_format.value
                    and item["winner_video_id"] in cluster.video_ids
                    and item["loser_video_id"] in cluster.video_ids
                ]
                dossier = self._mechanism_dossier(cluster_records, media_by_video, vision_by_video, outliers, cluster_pairs)
                mechanism = await self._checkpointed_ai(
                    run_id,
                    f"candidate_mechanism:{candidate_key}",
                    ViralMechanism,
                    lambda dossier=dossier, evidence_ids=evidence_ids: self.ai.viral_mechanism(
                        dossier, evidence_ids
                    ),
                )
                mechanism_citations = validate_citations(mechanism.supporting_evidence_ids, evidence_ids)
                mechanism_confidence, mechanism_channel_count = _validated_mechanism_support(
                    evidence,
                    mechanism.supporting_evidence_ids,
                    mechanism_citations,
                    mechanism.confidence,
                )
                self.repository.add_mechanism(cluster_model.id, {
                    "primary_mechanism": mechanism.primary_mechanism, "secondary_mechanisms": mechanism.secondary_mechanisms,
                    "viewer_question": mechanism.viewer_question, "hook_pattern": mechanism.hook_pattern, "payoff_pattern": mechanism.payoff_pattern,
                    "evidence_refs": mechanism.supporting_evidence_ids, "alternative_explanation": mechanism.alternative_explanation,
                    "confidence": mechanism_confidence, "provider": self.ai.name, "version": self.ai.version,
                })
                mechanism_evidence = self.repository.upsert_evidence(run_id, {
                    "evidence_type": "viral_mechanism_analysis", "source_type": "ai", "source_entity_id": candidate_key,
                    "payload": {**mechanism.model_dump(), "citation_validation": mechanism_citations, "mechanism_evidence_channels": mechanism_channel_count},
                    "confidence": mechanism_confidence,
                    "human_readable_summary": f"Mechanism hypothesis for {cluster.label}: {mechanism.primary_mechanism}",
                })
                asset_checkpoint = self.repository.get_checkpoint(
                    run_id, f"candidate_assets:{candidate_key}"
                )
                if asset_checkpoint is not None:
                    idea = dict(asset_checkpoint.get("idea", {}))
                    clip = dict(asset_checkpoint.get("clip", {}))
                    if not idea or not clip:
                        asset_checkpoint = None
                if asset_checkpoint is None:
                    idea_checkpoint = self.repository.get_checkpoint(
                        run_id, f"candidate_ideas:{candidate_key}"
                    )
                    if idea_checkpoint is not None and isinstance(idea_checkpoint.get("idea"), dict):
                        idea = dict(idea_checkpoint["idea"])
                    else:
                        idea = await calculate_idea_ceiling(
                            cluster_records, self.ai, evidence_ids, dossier, self.embeddings
                        )
                        self.repository.save_checkpoint(
                            run_id,
                            f"candidate_ideas:{candidate_key}",
                            {"idea": idea},
                            f"Completed durable final idea generation for {candidate_key}.",
                        )
                    clip = await calculate_clip_ceiling(
                        idea["candidate_ideas"],
                        final_asset_session,
                        visual_validator=self.ai,
                        phase="final",
                        maximum_new_ideas=final_clip_capacity,
                    )
                    self.repository.save_checkpoint(
                        run_id,
                        f"candidate_assets:{candidate_key}",
                        {"idea": idea, "clip": clip},
                        f"Completed durable idea and clip validation for {candidate_key}.",
                    )
                clip["initial_preflight"] = initial_clip_preflight.get(
                    _assessment_cluster_key(assessment_format, cluster.label),
                    {"stage": "pre_expansion_clip_preflight", "assessment_format": assessment_format.value, "passed": False, "reason": "cluster emerged only after expansion"},
                )
                idea["validated_count"] = clip["validated_count"]
                idea["validated_ideas"] = clip["validated_ideas"]
                idea["ideas_with_constraints"] = _annotate_production_ideas(
                    idea["candidate_ideas"], clip, request.production_constraints
                )
                multiples = [multiple_map.get(video.youtube_video_id, 0) for video in cluster_records]
                recent = _current_outlier_videos(cluster_records, outliers, self.settings.outlier_threshold)
                outlier_channels = {video.channel_id for video in recent}
                supporting_videos = _candidate_video_evidence(cluster_records, outliers)
                major_outliers = _current_major_outliers(supporting_videos)
                profiles = profiles_by_format[assessment_format]
                cluster_profiles = _cluster_channel_profiles(profiles, cluster_records)
                successful_channels = sum(bool(profile["successful"]) for profile in cluster_profiles.values())
                saturation = assess_saturation(cluster_records, multiples, supporting_window_days, now)
                classification = await self._checkpointed_ai(
                    run_id,
                    f"candidate_classification:{candidate_key}",
                    NicheClassification,
                    lambda dossier=dossier, evidence_ids=evidence_ids: self.ai.classify_niche(
                        dossier, evidence_ids
                    ),
                )
                evidence_confidence = _evidence_confidence(evidence)
                rec = recommend(
                    assessment_format, len(cluster_channels), len(recent), idea, clip, saturation, mechanism_confidence,
                    evidence_confidence, successful_channel_count=successful_channels,
                    outlier_channel_count=len(outlier_channels), comparison_count=len(cluster_pairs), mechanism_channel_count=mechanism_channel_count,
                    minimum_ideas=request.minimum_idea_ceiling, minimum_clip_coverage=request.minimum_clip_coverage,
                    minimum_channels=request.minimum_successful_channels, minimum_outliers=request.minimum_recent_outliers,
                    minimum_outlier_channels=request.minimum_outlier_channels, minimum_comparisons=request.minimum_winner_loser_pairs,
                    maximum_saturation=request.maximum_saturation,
                )
                trend_checkpoint = self.repository.get_checkpoint(
                    run_id, f"candidate_trend:{candidate_key}"
                )
                if trend_checkpoint is not None and isinstance(trend_checkpoint.get("trend"), dict):
                    trend = dict(trend_checkpoint["trend"])
                else:
                    trend = await self._trend_assessment(cluster_records, outliers, request)
                    self.repository.save_checkpoint(
                        run_id,
                        f"candidate_trend:{candidate_key}",
                        {"trend": trend},
                        f"Completed durable trend assessment for {candidate_key}.",
                    )
                repeated = [snapshot_metrics[video.youtube_video_id] for video in cluster_records]
                trend["repeated_observations"] = {
                    "videos_with_two_or_more_snapshots": sum(len(snapshot_histories[metric.video_id]) >= 2 for metric in repeated),
                    "observed_growth": [metric.__dict__ for metric in repeated if len(snapshot_histories[metric.video_id]) >= 2],
                    "interpretation": "Age-adjusted views/day is available immediately; acceleration becomes authoritative after repeat observations.",
                }
                deterministic_packet = {
                    "packet_version": "candidate-research-packet-v1",
                    "cluster": {"id": cluster_model.id, "label": cluster.label, "assessment_format": assessment_format.value, "description": cluster.description, "video_ids": cluster.video_ids, "channels": sorted(cluster_channels)},
                    "classification": classification.model_dump(),
                    "deterministic_decision": {"verdict": rec.verdict.value, "confidence": rec.confidence, "hard_gates": rec.hard_gates},
                    "demand": {"successful_channels": successful_channels, "recent_outliers": len(recent), "outlier_channels": len(outlier_channels), "channel_performance": cluster_profiles, "supporting_videos": supporting_videos, "major_outliers": major_outliers},
                    "momentum": trend,
                    "mechanism": {
                        **mechanism.model_dump(),
                        "validated_confidence": mechanism_confidence,
                        "replication_channel_count": mechanism_channel_count,
                        "citation_validation": mechanism_citations,
                    },
                    "winner_loser_comparisons": cluster_pairs,
                    "per_video_interpretations": {video.youtube_video_id: video_analysis_by_video.get(video.youtube_video_id) for video in cluster_records if video.youtube_video_id in video_analysis_by_video},
                    "idea_ceiling": idea,
                    "clip_ceiling": clip,
                    "saturation": saturation.as_dict(),
                    "production_constraints": request.production_constraints,
                    "production_policy": "Faceless suitability is annotated per idea and never gates discovery.",
                    "revenue_potential": _revenue_proxy(cluster_records, cluster_profiles),
                }
                packet_evidence = self.repository.upsert_evidence(run_id, {
                    "evidence_type": "candidate_research_packet", "source_type": "deterministic", "source_entity_id": candidate_key,
                    "payload": deterministic_packet, "confidence": evidence_confidence,
                    "human_readable_summary": f"Candidate packet for {classification.niche} reconciles deterministic metrics, transcripts, visual observations, comparisons, and production evidence.",
                })
                synthesis_allowed_ids = list(dict.fromkeys([*evidence_ids, str(mechanism_evidence.id), str(packet_evidence.id)]))
                synthesis = await self._checkpointed_ai(
                    run_id,
                    f"candidate_synthesis:{candidate_key}",
                    CandidateSynthesis,
                    lambda deterministic_packet=deterministic_packet, synthesis_allowed_ids=synthesis_allowed_ids: self.ai.synthesize_candidate(
                        json.dumps(deterministic_packet, default=str), synthesis_allowed_ids
                    ),
                )
                synthesis_citations = validate_citations(synthesis.supporting_evidence_ids, synthesis_allowed_ids)
                synthesis_payload = {**synthesis.model_dump(), "citation_validation": synthesis_citations, "provider": self.ai.name, "version": self.ai.version}
                synthesis_evidence = self.repository.upsert_evidence(run_id, {
                    "evidence_type": "candidate_synthesis", "source_type": "ai", "source_entity_id": candidate_key,
                    "payload": synthesis_payload, "confidence": synthesis.confidence if synthesis_citations["passed"] else 0.0,
                    "human_readable_summary": f"Research-editor synthesis for {classification.niche}: {synthesis.executive_summary}",
                })
                critic_allowed_ids = [*synthesis_allowed_ids, str(synthesis_evidence.id)]
                critic = await self._checkpointed_ai(
                    run_id,
                    f"candidate_critic:{candidate_key}",
                    CriticAssessment,
                    lambda deterministic_packet=deterministic_packet, synthesis_payload=synthesis_payload, critic_allowed_ids=critic_allowed_ids: self.ai.critique(
                        json.dumps({"candidate_packet": deterministic_packet, "editor_synthesis": synthesis_payload}, default=str),
                        critic_allowed_ids,
                    ),
                )
                critic_citations = validate_citations(critic.supporting_evidence_ids, critic_allowed_ids)
                critic_payload = {**critic.model_dump(), "citation_validation": critic_citations, "provider": self.ai.name, "version": self.ai.version}
                critic_evidence = self.repository.upsert_evidence(run_id, {
                    "evidence_type": "research_critic", "source_type": "ai", "source_entity_id": candidate_key,
                    "payload": critic_payload, "confidence": 1.0 if critic_citations["passed"] else 0.0,
                    "human_readable_summary": f"Independent critic for {classification.niche}: {'; '.join(critic.challenges)}",
                })
                adjudication = adjudicate_llm_output(
                    rec.verdict.value, rec.confidence, rec.hard_gates,
                    synthesis_citations, critic_payload, critic_citations,
                )
                payload = {
                    "rank": rank, "broad_market": classification.broad_market, "niche": classification.niche,
                    "sub_niche": classification.sub_niche, "repeatable_format": classification.repeatable_format,
                    "primary_viral_mechanism": mechanism.primary_mechanism,
                    "shorts_assessment": {**rec.shorts, "evidence_ids": evidence_ids if assessment_format == RequestedFormat.SHORTS else []},
                    "longform_assessment": {**rec.longform, "evidence_ids": evidence_ids if assessment_format == RequestedFormat.LONG_FORM else []},
                    "bridge_assessment": {"fit": "not_available", "score": None, "reason": f"Only {assessment_format.value} evidence is present for this topic cluster."},
                    "idea_ceiling": idea, "clip_ceiling": clip, "saturation_assessment": saturation.as_dict(),
                    "demand_assessment": {"assessment_format": assessment_format.value, "multiple_channels": len(cluster_channels), "successful_channels": successful_channels, "recent_outliers": len(recent), "outlier_threshold": self.settings.outlier_threshold, "outlier_channels": len(outlier_channels), "winner_loser_pairs": len(cluster_pairs), "mechanism_evidence_channels": mechanism_channel_count, "channel_performance": cluster_profiles, "supporting_videos": supporting_videos, "major_outliers": major_outliers, "competitor_30d_views_range": _competitor_range(cluster_profiles), "revenue_potential": _revenue_proxy(cluster_records, cluster_profiles), "shorts_summary": summarize_short_classifications({video.youtube_video_id: classifications[video.youtube_video_id] for video in cluster_records}), "hard_gates": rec.hard_gates, "llm_adjudication": adjudication, "score": round(min(1, successful_channels / max(request.minimum_successful_channels, 1)) * .5 + min(1, len(recent) / max(request.minimum_recent_outliers, 1)) * .5, 3)},
                    "momentum_assessment": {"recent_outlier_count": len(recent), "outlier_channel_count": len(outlier_channels), "trend_assessment": trend, "score": trend["score"], "observed_only": True},
                    "research_synthesis": synthesis_payload, "critic_assessment": critic_payload,
                    "confidence": adjudication["final_confidence"], "verdict": adjudication["final_verdict"],
                    "evidence_ids": [*critic_allowed_ids, str(critic_evidence.id)],
                    "_assessment_format": assessment_format.value,
                    "_cluster_centroid": cluster.centroid,
                    "_cluster_label": cluster.label,
                }
                candidates.append(payload)
            candidates = _rank_candidates(_assemble_media_candidates(candidates, request.requested_format))
            for candidate_rank, payload in enumerate(candidates, start=1):
                payload["rank"] = candidate_rank
                payload.pop("_assessment_format", None)
                payload.pop("_cluster_centroid", None)
                payload.pop("_cluster_label", None)
                self.repository.add_candidate(run_id, payload)
            report_ledger_ids = [str(item.id) for item in self.repository.get_evidence(run_id)]
            report_packet = {
                "packet_version": "report-research-packet-v1",
                "requested_format": request.requested_format.value,
                "candidates": [
                    {
                        "rank": item["rank"], "niche": item["niche"], "verdict": item["verdict"],
                        "confidence": item["confidence"], "hard_gates": item["demand_assessment"]["hard_gates"],
                        "research_synthesis": item["research_synthesis"], "critic_assessment": item["critic_assessment"],
                    }
                    for item in candidates
                ],
            }
            report_synthesis = await self._checkpointed_ai(
                run_id,
                "report_synthesis",
                ReportSynthesis,
                lambda: self.ai.synthesize_report(
                    json.dumps(report_packet, default=str), report_ledger_ids
                ),
            )
            report_citations = validate_citations(report_synthesis.supporting_evidence_ids, report_ledger_ids)
            self.repository.upsert_evidence(run_id, {
                "evidence_type": "report_synthesis", "source_type": "ai", "source_entity_id": run_id,
                "payload": {**report_synthesis.model_dump(), "citation_validation": report_citations, "provider": self.ai.name, "version": self.ai.version},
                "confidence": report_synthesis.confidence if report_citations["passed"] else 0.0,
                "human_readable_summary": f"Portfolio synthesis: {report_synthesis.executive_summary}",
            })
            self.repository.save_checkpoint(
                run_id,
                "pipeline_complete",
                {"candidate_count": len(candidates)},
                f"Pipeline completed with {len(candidates)} ranked candidates.",
            )
            self._transition(run, "complete")
            self._run_context[run_id] = {"videos": videos, "outliers": outliers, "classifications": classifications, "profiles_by_format": profiles_by_format, "comparisons": comparisons, "candidates": candidates}
            return run
        except Exception as exc:
            self._transition(run, "cancelled" if run_id in self.cancelled_runs else "failed", "research run cancelled" if run_id in self.cancelled_runs else str(exc))
            logger.exception("research run failed", extra={"research_run_id": run_id, "stage": run.status})
            raise
        finally:
            self.artifacts.cleanup_run_temporary(run_id)
            self.artifacts.cleanup_expired()

    async def _checkpointed_ai(
        self,
        run_id: str,
        checkpoint_key: str,
        schema: type[Any],
        operation: Any,
    ) -> Any:
        checkpoint = self.repository.get_checkpoint(run_id, checkpoint_key)
        if checkpoint is not None and isinstance(checkpoint.get("result"), dict):
            logger.info(
                "resumed AI checkpoint",
                extra={
                    "research_run_id": run_id,
                    "stage": "analysing",
                    "checkpoint_key": checkpoint_key,
                },
            )
            return schema.model_validate(checkpoint["result"])
        result = await operation()
        self.repository.save_checkpoint(
            run_id,
            checkpoint_key,
            {"result": result.model_dump(mode="json")},
            f"Completed durable AI step {checkpoint_key} with {self.ai.name}.",
        )
        return result

    async def _discover(self, run_id: str, request: ResearchRunCreate, plan: Any) -> dict[str, Any]:
        self._transition(self.repository.get_run(run_id), "discovering")
        found: dict[str, Any] = {}
        discovery_video_limit = _discovery_video_limit(request)
        query_limit, result_limit = _bounded_discovery_limits(request, self.settings)
        channel_limit = _bounded_channel_limit(request, self.settings)
        portfolio_mode = plan.discovery_strategy == "cross_market_portfolio"
        portfolio_buckets: list[list[Any]] = []
        for query_index, query in enumerate(plan.queries):
            if len(plan.visited_queries) >= query_limit:
                break
            plan.visited_queries.add(query)
            if self.source_health is not None:
                browser_healthy, api_healthy = self.source_health()
                self.router.update_health(
                    browser_healthy=browser_healthy,
                    api_healthy=api_healthy,
                )
            decision = self.router.route(RoutingTask("discovery", reproducible=True))
            self.repository.add_routing_audit(
                run_id, "discovery", decision.source.value, decision.reason, decision.quota_delta
            )
            profile_id = "fixture-profile" if self.settings.uses_fixture_sources else f"research-{run_id}-{len(plan.visited_queries) % self.settings.browser_max_tabs}"
            discovery_request = DiscoveryRequest(
                query, request.requested_format.value, request.recency_days, result_limit,
                profile_id=profile_id, language=request.language[:2].lower(),
                region=request.regions[0] if request.regions else "US",
            )
            selected_source = self.browser if decision.source in {SourceType.BROWSER, SourceType.FIXTURE_BROWSER} else self.youtube
            try:
                result = await selected_source.discover(discovery_request)
            except NicheIntelError as exc:
                can_fallback = (
                    decision.source == SourceType.BROWSER
                    and self.router.api_healthy
                    and exc.code in {ErrorCode.CONFIGURATION, ErrorCode.SOURCE_UNAVAILABLE}
                )
                if not can_fallback:
                    raise
                self.router.update_health(browser_healthy=False, api_healthy=True)
                fallback = self.router.route(RoutingTask("discovery", reproducible=True))
                self.repository.add_routing_audit(
                    run_id, "discovery", fallback.source.value,
                    f"browser attempt failed ({exc.code.value}); {fallback.reason}",
                    fallback.quota_delta,
                )
                result = await self.youtube.discover(discovery_request)
            if (
                decision.source == SourceType.BROWSER
                and not result.results
                and self.router.api_healthy
            ):
                self.router.update_health(browser_healthy=False, api_healthy=True)
                fallback = self.router.route(RoutingTask("discovery", reproducible=True))
                self.repository.add_routing_audit(
                    run_id, "discovery", fallback.source.value,
                    f"browser returned no hydrated result cards; {fallback.reason}",
                    fallback.quota_delta,
                )
                result = await self.youtube.discover(discovery_request)
            for screenshot_ref in result.screenshot_refs:
                screenshot_path = Path(screenshot_ref)
                if screenshot_path.is_file() and str(screenshot_path.resolve()).startswith(str(Path(self.settings.browser_profile_root).resolve())):
                    self.artifacts.register(screenshot_path, "browser_search_screenshot", run_id, self.settings.browser_artifact_retention_hours, {"query": query, "profile_id": profile_id})
            bounded_results = result.results[:result_limit]
            for item in bounded_results:
                self.repository.add_search_observation(run_id, {"source": result.source.value, "profile_id": profile_id, "query": query, "result_position": item.result_position, "observed_url": item.canonical_url, "observed_title": item.title, "observed_channel": item.channel_title, "visible_views_text": item.visible_views_text, "visible_age_text": item.visible_age_text, "presented_as_short": item.presented_as_short, "screenshot_ref": item.screenshot_ref, "raw_payload": item.raw_payload})
            if portfolio_mode:
                portfolio_buckets.append(bounded_results)
                continue
            before = len(found)
            for item in bounded_results:
                if len(found) >= discovery_video_limit:
                    break
                if item.channel_id not in plan.visited_channels and len(plan.visited_channels) >= channel_limit:
                    continue
                found.setdefault(item.youtube_video_id, item)
                plan.visited_videos.add(item.youtube_video_id)
                plan.visited_channels.add(item.channel_id)
            if len(found) >= discovery_video_limit:
                break
            if plan.should_stop(len(found) - before, query_index + 1):
                break
        if portfolio_mode:
            for item in _fair_market_sample(
                portfolio_buckets, discovery_video_limit, channel_limit
            ):
                found[item.youtube_video_id] = item
                plan.visited_videos.add(item.youtube_video_id)
                plan.visited_channels.add(item.channel_id)
        return found

    def _profile_for_video(self, run_id: str, video_id: str) -> str:
        if self.settings.uses_fixture_sources:
            return "fixture-profile"
        return f"research-{run_id}-{sum(ord(char) for char in video_id) % self.settings.browser_max_tabs}"

    async def _inspect_video_with_partial_result(self, run_id: str, video: VideoRecord, capture_frames: bool = True) -> BrowserMediaRecord:
        """Convert one unavailable page into explicit missing browser evidence."""
        profile_id = self._profile_for_video(run_id, video.youtube_video_id)
        try:
            return await self.browser.inspect_video(
                video.youtube_video_id, video.canonical_url, profile_id, capture_frames
            )
        except NicheIntelError as exc:
            if exc.code not in {ErrorCode.SOURCE_UNAVAILABLE, ErrorCode.NOT_FOUND}:
                raise
            missing_fields = [
                "shorts_presentation", "visible_transcript", "thumbnail", "frames",
                "opening_visual", "captions", "observable_structure",
            ]
            observed_at = datetime.now(timezone.utc)
            self.repository.upsert_evidence(run_id, {
                "evidence_type": "browser_video_inspection_skipped",
                "source_type": "fixture_browser" if self.settings.uses_fixture_sources else "browser",
                "source_entity_id": video.youtube_video_id,
                "observed_at": observed_at,
                "payload": {
                    "video_id": video.youtube_video_id,
                    "channel_id": video.channel_id,
                    "source_url": video.canonical_url,
                    "source_profile": profile_id,
                    "reason": exc.message,
                    "error_code": exc.code.value,
                    "partial": True,
                    "missing_fields": missing_fields,
                },
                "confidence": 0.0,
                "human_readable_summary": f"Browser inspection unavailable for {video.title}; structured metadata remains usable with reduced confidence.",
            })
            return BrowserMediaRecord(
                source_profile=profile_id,
                is_short_presentation=False,
                visible_transcript=None,
                thumbnail_ref=None,
                frame_refs=[],
                opening_visual_summary=None,
                caption_style=None,
                observable_structure=[],
                observed_at=observed_at,
                confidence=0.0,
                visual_features={
                    "inspection_status": "unavailable",
                    "error_code": exc.code.value,
                    "missing_fields": missing_fields,
                },
            )

    async def _expand_channels(self, run_id: str, initial: list[VideoRecord], request: ResearchRunCreate) -> list[VideoRecord]:
        merged = {video.youtube_video_id: video for video in initial}
        if request.limits.max_expansion_depth <= 0:
            return list(merged.values())
        channel_limit = _bounded_channel_limit(request, self.settings)
        channels = list(dict.fromkeys(video.channel_id for video in initial))[:channel_limit]
        per_channel = _bounded_channel_result_limit(request, self.settings, len(channels))
        uploads_by_channel: list[list[VideoRecord]] = []
        for channel_id in channels:
            checkpoint_key = f"channel_uploads:{channel_id}"
            checkpoint = self.repository.get_checkpoint(run_id, checkpoint_key)
            if checkpoint is not None:
                uploads = [
                    preprocess_video(_video_from_payload(item))
                    for item in checkpoint.get("videos", [])
                ]
            else:
                uploads = await self.youtube.expand_channel_uploads(channel_id, per_channel)
                self._drain_source_diagnostics(run_id)
                self.repository.save_checkpoint(
                    run_id,
                    checkpoint_key,
                    {"videos": [_video_to_payload(video) for video in uploads]},
                    f"Channel expansion checkpoint retained {len(uploads)} uploads for {channel_id}.",
                )
            uploads_by_channel.append(uploads)

        # Allocate expansion slots round-robin. Source feeds may return more
        # unseen records than their nominal history reserve, so consuming one
        # feed completely would bias all downstream channel cohorts by
        # discovery order and starve later retained channels.
        cursors = [0] * len(uploads_by_channel)
        while len(merged) < request.limits.max_videos:
            made_progress = False
            for channel_index, uploads in enumerate(uploads_by_channel):
                while cursors[channel_index] < len(uploads):
                    video = uploads[cursors[channel_index]]
                    cursors[channel_index] += 1
                    if video.youtube_video_id in merged:
                        continue
                    merged[video.youtube_video_id] = video
                    made_progress = True
                    break
                if len(merged) >= request.limits.max_videos:
                    break
            if not made_progress:
                break
        return list(merged.values())

    def _drain_source_diagnostics(self, run_id: str) -> None:
        for diagnostic in getattr(self.youtube, "drain_diagnostics", lambda: [])():
            is_video_diagnostic = diagnostic.diagnostic_type in {
                "keyless_video_skipped", "youtube_api_video_skipped"
            }
            source_type = (
                SourceType.YOUTUBE_API.value
                if diagnostic.diagnostic_type.startswith("youtube_api_")
                else SourceType.KEYLESS_YTDLP.value
            )
            self.repository.upsert_evidence(run_id, {
                "evidence_type": diagnostic.diagnostic_type,
                "source_type": source_type,
                "source_entity_id": diagnostic.source_entity_id,
                "observed_at": diagnostic.observed_at,
                "payload": {
                    "source_entity_id": diagnostic.source_entity_id,
                    "video_id": diagnostic.source_entity_id if is_video_diagnostic else None,
                    "channel_id": diagnostic.channel_id,
                    "source_url": diagnostic.source_url,
                    "reason": diagnostic.reason,
                    "error_code": diagnostic.error_code,
                    "raw_payload": diagnostic.raw_payload,
                },
                "confidence": 1.0,
                "human_readable_summary": f"Skipped unusable source record {diagnostic.source_entity_id}: {diagnostic.reason}",
            })

    @staticmethod
    def _mechanism_dossier(videos: list[VideoRecord], media: dict[str, BrowserMediaRecord], vision: dict[str, dict[str, Any]], outliers: dict[str, Any], comparisons: list[dict[str, Any]]) -> str:
        selected_ids = _select_representative_media_ids(videos, 6)
        rows: list[dict[str, Any]] = []
        for video in videos:
            if video.youtube_video_id not in selected_ids:
                continue
            observed = media.get(video.youtube_video_id)
            rows.append({
                "video_id": video.youtube_video_id,
                "channel_id": video.channel_id,
                "title": video.title[:300],
                "topic": video.topic[:200],
                "format": video.format_label[:200],
                "views": video.view_count,
                "outlier_multiple": round(outliers[video.youtube_video_id].outlier_multiple, 2),
                "transcript_segments": transcript_segments(
                    observed.visible_transcript if observed else None,
                    max_segment_chars=500,
                    max_segments=2,
                ),
                "first_spoken_line": (observed.first_spoken_line or "")[:500] if observed else None,
                "opening_visual": (observed.opening_visual_summary or "")[:500] if observed else None,
                "caption_style": (observed.caption_style or "")[:300] if observed else None,
                "structure": [str(item)[:300] for item in (observed.observable_structure if observed else [])[:8]],
                "pacing_score": observed.pacing_score if observed else None,
                "music_cue_count": observed.music_cue_count if observed else None,
                "editing_pattern": (observed.editing_pattern or "")[:300] if observed else None,
                "frames": (observed.frame_refs if observed else [])[:6],
                "vision_analysis": _bounded_json_value(vision.get(video.youtube_video_id), 2500),
            })
        payload = {
            "observed_videos": rows,
            "matched_winner_loser_findings": [_bounded_json_value(item, 2500) for item in comparisons[:6]],
            "instruction_boundary": "Infer only mechanisms repeated across independent channels; separate observation from hypothesis.",
            "bounds": {"maximum_videos": 6, "maximum_transcript_segments_per_video": 2, "maximum_characters": 24000},
        }
        return _bounded_mechanism_document(payload, 24000)

    async def _trend_assessment(self, videos: list[VideoRecord], outliers: dict[str, Any], request: ResearchRunCreate) -> dict[str, Any]:
        current = [video for video in videos if outliers[video.youtube_video_id].recency_bucket == "current"]
        supporting = [video for video in videos if outliers[video.youtube_video_id].recency_bucket == "supporting"]
        threshold = self.settings.outlier_threshold
        current_outliers = sum(outliers[video.youtube_video_id].outlier_multiple >= threshold for video in current)
        channels = len({video.channel_id for video in current if outliers[video.youtube_video_id].outlier_multiple >= threshold})
        youtube_score = round(min(1, current_outliers / 3) * .6 + min(1, channels / 2) * .4, 3)
        external = await self.trends.assess(sorted({video.topic or video.title for video in videos})[:5], request.regions, min(90, request.recency_days))
        combined = youtube_score if external.get("score") is None else round(youtube_score * .85 + float(external["score"]) * .15, 3)
        windows = {days: {"uploads": sum(age_days(video.published_at) <= days for video in videos), "outliers": sum(age_days(video.published_at) <= days and outliers[video.youtube_video_id].outlier_multiple >= threshold for video in videos)} for days in (7, 30, 45, 90)}
        return {"youtube_current_window_days": min(45, request.recency_days), "youtube_baseline_window_days": min(90, max(45, request.recency_days)), "outlier_threshold": threshold, "windows": {str(key): value for key, value in windows.items()}, "current_uploads": len(current), "supporting_uploads": len(supporting), "current_outliers": current_outliers, "current_outlier_channels": channels, "youtube_score": youtube_score, "score": combined, "external_trends": external, "interpretation": "YouTube evidence carries at least 85% of the trend score; 7/30/45/90-day windows distinguish a spike from sustained momentum; external search trends are optional corroboration."}

    def cancel(self, run: ResearchRun) -> None:
        self.cancelled_runs.add(run.id)
        if run.status not in {"complete", "failed", "cancelled"}:
            self._transition(run, "cancelled", "research run cancelled by user")
        self.artifacts.cleanup_run_temporary(run.id)

    def _check_cancelled(self, run_id: str) -> None:
        self.repository.session.expire_all()
        persisted = self.repository.get_run(run_id)
        if persisted is not None and persisted.status == "cancelled":
            self.cancelled_runs.add(run_id)
        if run_id in self.cancelled_runs:
            raise NicheIntelError("research run cancelled")

    def _transition(self, run: ResearchRun, status: str, reason: str | None = None) -> None:
        self.repository.transition(run, status, reason)
        logger.info("research stage transition", extra={"research_run_id": run.id, "stage": status})


def _assemble_media_candidates(candidates: list[dict[str, Any]], requested_format: RequestedFormat) -> list[dict[str, Any]]:
    """Pair only semantically matching, independently assessed media cohorts."""
    if requested_format != RequestedFormat.BOTH:
        return sorted(candidates, key=lambda item: item["rank"])
    shorts = [item for item in candidates if item["_assessment_format"] == RequestedFormat.SHORTS.value]
    longform = [item for item in candidates if item["_assessment_format"] == RequestedFormat.LONG_FORM.value]
    unmatched_longform = set(range(len(longform)))
    assembled: list[dict[str, Any]] = []
    for short in shorts:
        matches = [
            (index, _vector_cosine(short["_cluster_centroid"], longform[index]["_cluster_centroid"]))
            for index in unmatched_longform
        ]
        best = max(matches, key=lambda item: item[1], default=None)
        if best is None or best[1] < .55:
            assembled.append(short)
            continue
        index, similarity = best
        unmatched_longform.remove(index)
        assembled.append(_merge_media_candidates(short, longform[index], similarity))
    assembled.extend(longform[index] for index in sorted(unmatched_longform))
    return sorted(assembled, key=lambda item: item["rank"])


_VERDICT_RANK = {
    Verdict.START_NOW.value: 0,
    Verdict.RUN_TEST.value: 1,
    Verdict.SHORTS_ONLY.value: 2,
    Verdict.LONG_FORM_ONLY.value: 2,
    Verdict.WATCH_MOMENTUM.value: 3,
    Verdict.FOOTAGE_CONSTRAINED.value: 4,
    Verdict.OVERSATURATED.value: 5,
    Verdict.INSUFFICIENT.value: 6,
    Verdict.REJECT.value: 7,
}


def _rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order only adjudicated candidates, never preliminary single-outlier signals."""
    def key(item: dict[str, Any]) -> tuple[Any, ...]:
        passed, total = _candidate_gate_counts(item)
        gate_ratio = passed / total if total else 0.0
        return (
            _VERDICT_RANK.get(str(item.get("verdict")), len(_VERDICT_RANK)),
            -gate_ratio,
            -float(item.get("confidence", 0)),
            -float(item.get("demand_assessment", {}).get("score", 0)),
            -float(item.get("momentum_assessment", {}).get("score", 0)),
            -int(item.get("clip_ceiling", {}).get("validated_count", 0)),
            int(item.get("rank", 0)),
            str(item.get("niche", "")),
        )

    return sorted(candidates, key=key)


def _candidate_gate_counts(candidate: dict[str, Any]) -> tuple[int, int]:
    demand = candidate.get("demand_assessment", {})
    media_assessments = demand.get("media_assessments")
    gate_sets = (
        [item.get("hard_gates", {}) for item in media_assessments.values() if isinstance(item, dict)]
        if isinstance(media_assessments, dict)
        else [demand.get("hard_gates", {})]
    )
    passed = total = 0
    for gates in gate_sets:
        records = [value for value in gates.values() if isinstance(value, dict) and isinstance(value.get("passed"), bool)]
        passed += int(gates.get("passed", sum(bool(value["passed"]) for value in records)))
        total += int(gates.get("total", len(records)))
    return passed, total


def _merge_media_candidates(short: dict[str, Any], longform: dict[str, Any], similarity: float) -> dict[str, Any]:
    shorts_fit = short["shorts_assessment"]["fit"] == "promising" and short["verdict"] in {Verdict.SHORTS_ONLY.value, Verdict.RUN_TEST.value, Verdict.START_NOW.value}
    longform_fit = longform["longform_assessment"]["fit"] == "promising" and longform["verdict"] in {Verdict.LONG_FORM_ONLY.value, Verdict.RUN_TEST.value, Verdict.START_NOW.value}
    if shorts_fit and longform_fit:
        bridge_fit = "strong_fit_for_both"
        verdict = Verdict.START_NOW.value
        reason = "Independent Shorts and long-form cohorts both pass their media-specific gates for the same semantic topic."
    elif shorts_fit:
        bridge_fit = "shorts_first_with_long_form_expansion"
        verdict = Verdict.SHORTS_ONLY.value
        reason = "Shorts gates pass, while the separately measured long-form cohort remains below a positive threshold."
    elif longform_fit:
        bridge_fit = "long_form_only"
        verdict = Verdict.LONG_FORM_ONLY.value
        reason = "Long-form gates pass, while the separately measured Shorts cohort remains below a positive threshold."
    else:
        bridge_fit = "watch"
        verdict = Verdict.INSUFFICIENT.value
        reason = "Neither independent media cohort currently passes every positive recommendation gate."
    short_score = short["shorts_assessment"].get("score")
    long_score = longform["longform_assessment"].get("score")
    scores = [float(score) for score in (short_score, long_score) if score is not None]
    bridge = {
        "fit": bridge_fit,
        "score": round(sum(scores) / len(scores), 3) if scores else None,
        "reason": reason,
        "topic_similarity": round(similarity, 3),
        "inputs": {
            "shorts_cluster": short["_cluster_label"],
            "long_form_cluster": longform["_cluster_label"],
            "shorts_evidence_ids": short["evidence_ids"],
            "long_form_evidence_ids": longform["evidence_ids"],
        },
    }
    short_gates = short["demand_assessment"]["hard_gates"]
    long_gates = longform["demand_assessment"]["hard_gates"]
    merged = {
        **short,
        "rank": min(short["rank"], longform["rank"]),
        "shorts_assessment": short["shorts_assessment"],
        "longform_assessment": longform["longform_assessment"],
        "bridge_assessment": bridge,
        "idea_ceiling": _combined_metric("idea ceiling", short["idea_ceiling"], longform["idea_ceiling"], "validated_count"),
        "clip_ceiling": _combined_metric("clip ceiling", short["clip_ceiling"], longform["clip_ceiling"], "validated_count"),
        "saturation_assessment": {"assessment_format": "both", "shorts": short["saturation_assessment"], "long_form": longform["saturation_assessment"]},
        "demand_assessment": {
            "assessment_format": "both",
            "media_assessments": {"shorts": short["demand_assessment"], "long_form": longform["demand_assessment"]},
            "hard_gates": {"shorts": short_gates, "long_form": long_gates, "all_passed": bool(short_gates.get("all_passed")) and bool(long_gates.get("all_passed"))},
            "score": round((float(short["demand_assessment"].get("score", 0)) + float(longform["demand_assessment"].get("score", 0))) / 2, 3),
        },
        "momentum_assessment": {"assessment_format": "both", "shorts": short["momentum_assessment"], "long_form": longform["momentum_assessment"], "score": round((float(short["momentum_assessment"].get("score", 0)) + float(longform["momentum_assessment"].get("score", 0))) / 2, 3)},
        "research_synthesis": {"assessment_format": "both", "shorts": short["research_synthesis"], "long_form": longform["research_synthesis"], "bridge": bridge},
        "critic_assessment": {"assessment_format": "both", "shorts": short["critic_assessment"], "long_form": longform["critic_assessment"]},
        "confidence": round(min(float(short["confidence"]), float(longform["confidence"])), 3),
        "verdict": verdict,
        "evidence_ids": list(dict.fromkeys([*short["evidence_ids"], *longform["evidence_ids"]])),
        "_assessment_format": RequestedFormat.BOTH.value,
    }
    if short["primary_viral_mechanism"] != longform["primary_viral_mechanism"]:
        merged["primary_viral_mechanism"] = f"Shorts: {short['primary_viral_mechanism']} | Long-form: {longform['primary_viral_mechanism']}"
    return merged


def _search_result_to_payload(item: SearchResult) -> dict[str, Any]:
    return {
        "youtube_video_id": item.youtube_video_id,
        "canonical_url": item.canonical_url,
        "title": item.title,
        "channel_id": item.channel_id,
        "channel_title": item.channel_title,
        "visible_views_text": item.visible_views_text,
        "visible_age_text": item.visible_age_text,
        "presented_as_short": item.presented_as_short,
        "result_position": item.result_position,
        "screenshot_ref": item.screenshot_ref,
        "raw_payload": item.raw_payload,
    }


def _search_result_from_payload(payload: dict[str, Any]) -> SearchResult:
    return SearchResult(
        youtube_video_id=str(payload["youtube_video_id"]),
        canonical_url=str(payload["canonical_url"]),
        title=str(payload.get("title") or "Untitled video"),
        channel_id=str(payload.get("channel_id") or "unknown-channel"),
        channel_title=str(payload.get("channel_title") or "Unknown channel"),
        visible_views_text=str(payload.get("visible_views_text") or ""),
        visible_age_text=str(payload.get("visible_age_text") or ""),
        presented_as_short=bool(payload.get("presented_as_short")),
        result_position=int(payload.get("result_position") or 0),
        screenshot_ref=payload.get("screenshot_ref"),
        raw_payload=dict(payload.get("raw_payload") or {}),
    )


def _channel_to_payload(channel: ChannelRecord) -> dict[str, Any]:
    return {
        "youtube_channel_id": channel.youtube_channel_id,
        "canonical_url": channel.canonical_url,
        "title": channel.title,
        "description": channel.description,
        "subscriber_count": channel.subscriber_count,
        "total_view_count": channel.total_view_count,
        "video_count": channel.video_count,
    }


def _channel_from_payload(payload: dict[str, Any]) -> ChannelRecord:
    return ChannelRecord(
        youtube_channel_id=str(payload["youtube_channel_id"]),
        canonical_url=str(payload.get("canonical_url") or ""),
        title=str(payload.get("title") or payload["youtube_channel_id"]),
        description=str(payload.get("description") or ""),
        subscriber_count=int(payload["subscriber_count"]) if payload.get("subscriber_count") is not None else None,
        total_view_count=int(payload["total_view_count"]) if payload.get("total_view_count") is not None else None,
        video_count=int(payload["video_count"]) if payload.get("video_count") is not None else None,
    )


def _video_to_payload(video: VideoRecord) -> dict[str, Any]:
    return {
        "youtube_video_id": video.youtube_video_id,
        "channel_id": video.channel_id,
        "canonical_url": video.canonical_url,
        "title": video.title,
        "description": video.description,
        "duration_seconds": video.duration_seconds,
        "published_at": video.published_at.isoformat(),
        "category_id": video.category_id,
        "tags": video.tags,
        "thumbnails": video.thumbnails,
        "view_count": video.view_count,
        "like_count": video.like_count,
        "comment_count": video.comment_count,
        "is_short": video.is_short,
        "format_label": video.format_label,
        "topic": video.topic,
        "shorts_evidence": video.shorts_evidence,
    }


def _video_from_payload(payload: dict[str, Any]) -> VideoRecord:
    published_at = _checkpoint_datetime(payload.get("published_at"))
    if published_at is None:
        raise ValueError(f"checkpoint video {payload.get('youtube_video_id')} has no publication time")
    return VideoRecord(
        youtube_video_id=str(payload["youtube_video_id"]),
        channel_id=str(payload.get("channel_id") or "unknown-channel"),
        canonical_url=str(payload.get("canonical_url") or f"https://www.youtube.com/watch?v={payload['youtube_video_id']}"),
        title=str(payload.get("title") or "Untitled video"),
        description=str(payload.get("description") or ""),
        duration_seconds=int(payload["duration_seconds"]) if payload.get("duration_seconds") is not None else None,
        published_at=published_at,
        category_id=str(payload["category_id"]) if payload.get("category_id") is not None else None,
        tags=[str(item) for item in payload.get("tags") or []],
        thumbnails=dict(payload.get("thumbnails") or {}),
        view_count=int(payload.get("view_count") or 0),
        like_count=int(payload["like_count"]) if payload.get("like_count") is not None else None,
        comment_count=int(payload["comment_count"]) if payload.get("comment_count") is not None else None,
        is_short=bool(payload.get("is_short")),
        format_label=str(payload.get("format_label") or ""),
        topic=str(payload.get("topic") or ""),
        shorts_evidence=str(payload.get("shorts_evidence") or "unspecified"),
    )


def _media_to_payload(media: BrowserMediaRecord) -> dict[str, Any]:
    return {
        "source_profile": media.source_profile,
        "is_short_presentation": media.is_short_presentation,
        "visible_transcript": media.visible_transcript,
        "thumbnail_ref": media.thumbnail_ref,
        "frame_refs": media.frame_refs,
        "opening_visual_summary": media.opening_visual_summary,
        "caption_style": media.caption_style,
        "observable_structure": media.observable_structure,
        "observed_at": media.observed_at.isoformat(),
        "confidence": media.confidence,
        "first_spoken_line": media.first_spoken_line,
        "duration_seconds": media.duration_seconds,
        "scene_change_count": media.scene_change_count,
        "average_shot_duration_seconds": media.average_shot_duration_seconds,
        "reveal_timestamp_seconds": media.reveal_timestamp_seconds,
        "caption_density": media.caption_density,
        "motion_score": media.motion_score,
        "pacing_score": media.pacing_score,
        "music_cue_count": media.music_cue_count,
        "editing_pattern": media.editing_pattern,
        "visual_features": media.visual_features,
    }


def _media_from_payload(payload: dict[str, Any]) -> BrowserMediaRecord:
    return BrowserMediaRecord(
        source_profile=str(payload.get("source_profile") or "research"),
        is_short_presentation=bool(payload.get("is_short_presentation")),
        visible_transcript=payload.get("visible_transcript"),
        thumbnail_ref=payload.get("thumbnail_ref"),
        frame_refs=[str(item) for item in payload.get("frame_refs") or []],
        opening_visual_summary=payload.get("opening_visual_summary"),
        caption_style=payload.get("caption_style"),
        observable_structure=[str(item) for item in payload.get("observable_structure") or []],
        observed_at=_checkpoint_datetime(payload.get("observed_at")) or datetime.now(timezone.utc),
        confidence=float(payload.get("confidence") or 0.0),
        first_spoken_line=payload.get("first_spoken_line"),
        duration_seconds=float(payload["duration_seconds"]) if payload.get("duration_seconds") is not None else None,
        scene_change_count=int(payload["scene_change_count"]) if payload.get("scene_change_count") is not None else None,
        average_shot_duration_seconds=float(payload["average_shot_duration_seconds"]) if payload.get("average_shot_duration_seconds") is not None else None,
        reveal_timestamp_seconds=float(payload["reveal_timestamp_seconds"]) if payload.get("reveal_timestamp_seconds") is not None else None,
        caption_density=float(payload["caption_density"]) if payload.get("caption_density") is not None else None,
        motion_score=float(payload["motion_score"]) if payload.get("motion_score") is not None else None,
        pacing_score=float(payload["pacing_score"]) if payload.get("pacing_score") is not None else None,
        music_cue_count=int(payload["music_cue_count"]) if payload.get("music_cue_count") is not None else None,
        editing_pattern=payload.get("editing_pattern"),
        visual_features=dict(payload.get("visual_features") or {}),
    )


def _persisted_media_records(repository: ResearchRepository, run_id: str) -> dict[str, BrowserMediaRecord]:
    records: dict[str, BrowserMediaRecord] = {}
    for row, youtube_video_id in repository.browser_media_rows(run_id):
        feature = dict(row.feature_payload or {})
        records[youtube_video_id] = _media_from_payload({
            "source_profile": row.source_profile,
            "is_short_presentation": row.is_short_presentation,
            "visible_transcript": row.visible_transcript,
            "thumbnail_ref": row.thumbnail_ref,
            "frame_refs": row.frame_refs,
            "opening_visual_summary": row.opening_visual_summary,
            "caption_style": row.caption_style,
            "observable_structure": row.observable_structure,
            "observed_at": row.observed_at,
            "confidence": row.confidence,
            **feature,
        })
    return records


def _persisted_video_records(repository: ResearchRepository, run_id: str) -> list[VideoRecord]:
    records: dict[str, VideoRecord] = {}
    for video, snapshot, channel in repository.video_rows_for_run(run_id):
        records[video.youtube_video_id] = preprocess_video(VideoRecord(
            youtube_video_id=video.youtube_video_id,
            channel_id=channel.youtube_channel_id if channel is not None else "unknown-channel",
            canonical_url=video.canonical_url,
            title=video.title,
            description=video.description,
            duration_seconds=video.duration_seconds,
            published_at=_checkpoint_datetime(video.published_at) or video.published_at,
            category_id=video.category_id,
            tags=list(video.tags or []),
            thumbnails=dict(video.thumbnails or {}),
            view_count=int(snapshot.view_count or 0),
            like_count=snapshot.like_count,
            comment_count=snapshot.comment_count,
        ))
    return list(records.values())


def _checkpoint_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    normalized = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _comparison_checkpoint_key(assessment_format: RequestedFormat, pair: dict[str, Any]) -> str:
    return f"{assessment_format.value}:{pair['winner']['id']}:{pair['loser']['id']}"


def _candidate_checkpoint_key(
    assessment_format: RequestedFormat,
    cluster_label: str,
    video_ids: list[str],
) -> str:
    identity = json.dumps(
        [assessment_format.value, cluster_label, sorted(video_ids)],
        separators=(",", ":"),
    )
    return f"{assessment_format.value}:{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:20]}"


def _combined_metric(label: str, shorts: dict[str, Any], longform: dict[str, Any], count_key: str) -> dict[str, Any]:
    values = [int(value.get(count_key, 0)) for value in (shorts, longform)]
    return {
        "assessment_format": "both",
        "shorts": shorts,
        "long_form": longform,
        count_key: min(values),
        "interpretation": f"The combined {label} is the conservative minimum; each media-specific calculation is preserved separately.",
    }


def _vector_cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def _outlier_cohort_key(video: VideoRecord, classification: Any) -> tuple[str, str]:
    media_class = "shorts" if classification.eligible else "long_form" if classification.status == ShortStatus.NOT_SHORT else "unknown"
    repeatable_format = video.format_label.strip() or "unclassified"
    return video.channel_id, f"{media_class}:{repeatable_format}"


def _assessment_video_groups(
    videos: list[VideoRecord],
    classifications: dict[str, Any],
    requested_format: RequestedFormat,
) -> list[tuple[RequestedFormat, list[VideoRecord]]]:
    """Return non-overlapping media-class inputs for every downstream assessment."""
    requested = [RequestedFormat.SHORTS, RequestedFormat.LONG_FORM] if requested_format == RequestedFormat.BOTH else [requested_format]
    groups: list[tuple[RequestedFormat, list[VideoRecord]]] = []
    for assessment_format in requested:
        if assessment_format == RequestedFormat.SHORTS:
            group = [video for video in videos if classifications[video.youtube_video_id].eligible]
        else:
            group = [video for video in videos if classifications[video.youtube_video_id].status == ShortStatus.NOT_SHORT]
        if group:
            groups.append((assessment_format, group))
    return groups


def _assessment_cluster_key(assessment_format: RequestedFormat, label: str) -> str:
    return f"{assessment_format.value}:{label}"


def _cluster_matched_pairs(
    assessed_clusters: list[tuple[RequestedFormat, Any, list[VideoRecord]]],
    multiples: dict[str, float],
    media: dict[str, BrowserMediaRecord],
) -> list[tuple[RequestedFormat, dict[str, Any]]]:
    """Select bounded controls independently inside every semantic candidate."""
    selected: list[tuple[RequestedFormat, dict[str, Any]]] = []
    for assessment_format, cluster, format_videos in assessed_clusters:
        cluster_records = [video for video in format_videos if video.youtube_video_id in cluster.video_ids]
        selected.extend(
            (assessment_format, pair)
            for pair in select_matched_pairs(cluster_records, multiples, media)
        )
    return selected


def _english_evidence_allows(transcript: str | None, minimum_likelihood: float = 0.55) -> bool:
    likelihood = english_likelihood(transcript)
    return likelihood is None or likelihood >= minimum_likelihood


def _current_outlier_videos(videos: list[VideoRecord], outliers: dict[str, Any], threshold: float) -> list[VideoRecord]:
    return [
        video for video in videos
        if outliers[video.youtube_video_id].recency_bucket == "current"
        and outliers[video.youtube_video_id].outlier_multiple >= threshold
    ]


def _candidate_video_evidence(
    videos: list[VideoRecord], outliers: dict[str, Any], limit: int = 12
) -> list[dict[str, Any]]:
    """Serialize the bounded public observations used by a candidate decision."""
    ordered = sorted(
        videos,
        key=lambda video: (
            outliers[video.youtube_video_id].outlier_multiple,
            outliers[video.youtube_video_id].metric_value,
        ),
        reverse=True,
    )[:limit]
    return [
        {
            "video_id": video.youtube_video_id,
            "channel_id": video.channel_id,
            "title": video.title,
            "canonical_url": video.canonical_url,
            "published_at": video.published_at.isoformat(),
            "view_count": video.view_count,
            "views_per_day": round(outliers[video.youtube_video_id].metric_value, 3),
            "baseline_views_per_day": round(
                outliers[video.youtube_video_id].baseline_metric, 3
            ),
            "outlier_multiple": round(
                outliers[video.youtube_video_id].outlier_multiple, 3
            ),
            "outlier_label": outliers[video.youtube_video_id].label,
            "recency_bucket": outliers[video.youtube_video_id].recency_bucket,
        }
        for video in ordered
    ]


def _current_major_outliers(
    supporting_videos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep 46–90-day major outliers as support, never as current demand."""
    return [
        item for item in supporting_videos
        if item.get("outlier_label") == "major outlier"
        and item.get("recency_bucket") == "current"
    ]


def _cluster_channel_profiles(profiles: dict[str, dict[str, Any]], videos: list[VideoRecord]) -> dict[str, dict[str, Any]]:
    """Restrict a channel's success evidence to formats represented by this candidate."""
    formats_by_channel: dict[str, set[str]] = defaultdict(set)
    for video in videos:
        formats_by_channel[video.channel_id].add(video.format_label.strip() or "unclassified")
    selected: dict[str, dict[str, Any]] = {}
    for channel_id, repeatable_formats in formats_by_channel.items():
        profile = profiles.get(channel_id)
        if profile is None:
            continue
        cohorts = [cohort for cohort in profile.get("cohorts", []) if cohort.get("repeatable_format") in repeatable_formats]
        selected[channel_id] = {
            **profile,
            "cohorts": cohorts,
            "uploads_analyzed": sum(int(cohort.get("uploads_analyzed", 0)) for cohort in cohorts),
            "outliers_2x": sum(int(cohort.get("outliers_2x", 0)) for cohort in cohorts),
            "outliers_3x": sum(sum(value >= 3 for value in cohort.get("outlier_multiples", [])) for cohort in cohorts),
            "successful": any(bool(cohort.get("successful")) for cohort in cohorts),
            "successful_cohort_count": sum(bool(cohort.get("successful")) for cohort in cohorts),
        }
    return selected


def _discovery_enrichment_context(item: Any) -> dict[str, Any]:
    return {
        "id": item.youtube_video_id,
        "url": item.canonical_url,
        "title": item.title,
        "channel_id": item.channel_id,
        "channel_title": item.channel_title,
        "visible_views_text": item.visible_views_text,
        "visible_age_text": item.visible_age_text,
        "presented_as_short": item.presented_as_short,
        "result_position": item.result_position,
        "screenshot_ref": item.screenshot_ref,
        "discovery_raw_payload": item.raw_payload,
    }


def _build_rate_cohorts(videos: list[VideoRecord], classifications: dict[str, Any], now: datetime, supporting_window_days: int) -> tuple[dict[str, float], dict[tuple[str, str], list[float]]]:
    """Calculate all candidate rates but admit only supporting-window uploads to baselines."""
    rates: dict[str, float] = {}
    cohorts: dict[tuple[str, str], list[float]] = defaultdict(list)
    for video in videos:
        rate = views_per_day(video.view_count, video.published_at, now)
        rates[video.youtube_video_id] = rate
        if age_days(video.published_at, now) <= supporting_window_days:
            cohorts[_outlier_cohort_key(video, classifications[video.youtube_video_id])].append(rate)
    return rates, cohorts


def _bounded_discovery_limits(request: ResearchRunCreate, settings: Settings) -> tuple[int, int]:
    """Intersect public request bounds with stricter operator browser limits."""
    return (
        min(request.limits.max_queries, settings.browser_max_queries_per_run),
        min(request.limits.max_results_per_query, settings.browser_max_results_per_query),
    )


def _fair_allocations(total: int, count: int) -> list[int]:
    """Split a hard external-work budget without favoring processing order."""
    if count <= 0:
        return []
    bounded_total = max(0, int(total))
    base, extras = divmod(bounded_total, count)
    allocations = [base] * count
    if extras:
        # Place remainder slots across the full ordered portfolio, including
        # later markets/clusters when there are fewer slots than recipients.
        for slot in range(extras):
            index = min(count - 1, ((2 * slot + 1) * count) // (2 * extras))
            allocations[index] += 1
    return allocations


def _fair_market_sample(
    buckets: list[list[Any]], video_limit: int, channel_limit: int
) -> list[Any]:
    """Round-robin market results, sampling the whole portfolio before depth."""
    if video_limit <= 0 or not buckets:
        return []
    selected: list[Any] = []
    selected_ids: set[str] = set()
    selected_channels: set[str] = set()
    cursors = [0] * len(buckets)

    def admit_from(bucket_index: int) -> bool:
        bucket = buckets[bucket_index]
        while cursors[bucket_index] < len(bucket):
            item = bucket[cursors[bucket_index]]
            cursors[bucket_index] += 1
            if item.youtube_video_id in selected_ids:
                continue
            if item.channel_id not in selected_channels and len(selected_channels) >= channel_limit:
                continue
            selected.append(item)
            selected_ids.add(item.youtube_video_id)
            selected_channels.add(item.channel_id)
            return True
        return False

    first_pass_count = min(video_limit, len(buckets))
    for index in _evenly_spaced_indices(len(buckets), first_pass_count):
        admit_from(index)
        if len(selected) >= video_limit:
            return selected

    while len(selected) < video_limit:
        made_progress = False
        for index in range(len(buckets)):
            if admit_from(index):
                made_progress = True
            if len(selected) >= video_limit:
                return selected
        if not made_progress:
            break
    return selected


def _evenly_spaced_indices(size: int, count: int) -> list[int]:
    if size <= 0 or count <= 0:
        return []
    if count >= size:
        return list(range(size))
    if count == 1:
        return [size // 2]
    return [round(index * (size - 1) / (count - 1)) for index in range(count)]


def _discovery_video_limit(request: ResearchRunCreate) -> int:
    """Reserve total-run capacity for two same-channel uploads per target channel."""
    total = request.limits.max_videos
    if request.limits.max_expansion_depth <= 0 or total <= 1:
        return total
    # One discovery record plus two unseen uploads is the smallest possible
    # three-record channel cohort. Never retain more discovery channels than
    # the total run capacity can support at that ratio.
    return min(request.limits.max_channels, max(1, total // 3))


def _bounded_channel_limit(request: ResearchRunCreate, settings: Settings) -> int:
    return min(request.limits.max_channels, settings.browser_max_channels_per_run)


def _bounded_channel_result_limit(request: ResearchRunCreate, settings: Settings, channel_count: int) -> int:
    proportional_limit = (
        request.limits.max_videos + max(channel_count, 1) - 1
    ) // max(channel_count, 1)
    # Upload feeds normally repeat the discovery hit. Request at least three
    # when operator bounds permit it so a merged feed can form the canonical
    # three-upload cohort. An explicit lower operator cap remains authoritative
    # and will honestly produce insufficient channel evidence.
    return max(
        1,
        min(30, settings.browser_max_results_per_query, max(3, proportional_limit)),
    )


def _select_representative_media_ids(videos: list[VideoRecord], limit: int = 6) -> set[str]:
    """Bound heavy media work while preserving channel diversity and current performance."""
    now = datetime.now(timezone.utc)
    ordered = sorted(videos, key=lambda video: (views_per_day(video.view_count, video.published_at, now), video.view_count), reverse=True)
    selected: list[VideoRecord] = []
    represented: set[str] = set()
    for video in ordered:
        if video.channel_id not in represented:
            selected.append(video)
            represented.add(video.channel_id)
            if len(selected) >= limit:
                return {item.youtube_video_id for item in selected}
    for video in ordered:
        if video not in selected:
            selected.append(video)
            if len(selected) >= limit:
                break
    return {item.youtube_video_id for item in selected}


def _select_vision_target_ids(
    videos: list[VideoRecord],
    heavy_media_targets: set[str],
    requires_download: bool,
    limit: int,
) -> set[str]:
    """Reuse the bounded, channel-diverse download cohort for live vision work."""
    available_ids = {video.youtube_video_id for video in videos}
    if requires_download:
        return heavy_media_targets & available_ids
    return _select_representative_media_ids(videos, limit)


def _deterministic_comparison_payload(
    pair: dict[str, Any],
    interpretation: dict[str, Any],
    assessment_format: RequestedFormat,
) -> dict[str, Any]:
    """Keep pair membership outside the model's interpretation boundary."""
    return {
        **interpretation,
        "winner_video_id": pair["winner"]["id"],
        "loser_video_id": pair["loser"]["id"],
        "match_basis": pair["match_basis"],
        "match_quality": pair["match_quality"],
        "comparison_purpose": pair["purpose"],
        "performance_ratio": pair["performance_ratio"],
        "performance_metric": pair["performance_metric"],
        "winner_performance_value": pair["winner_performance_value"],
        "loser_performance_value": pair["loser_performance_value"],
        "channel_id": pair["channel_id"],
        "assessment_format": assessment_format.value,
    }


def _mechanism_evidence_channel_count(evidence: list[Any], supporting_evidence_ids: list[str]) -> int:
    supporting = set(supporting_evidence_ids)
    channels = {
        item.payload.get("channel_id")
        for item in evidence
        if str(item.id) in supporting
        and _is_mechanism_bearing_evidence(item)
        and item.payload.get("channel_id")
    }
    return len(channels)


def _is_mechanism_bearing_evidence(item: Any) -> bool:
    if not isinstance(getattr(item, "payload", None), dict):
        return False
    if float(getattr(item, "confidence", 0.0) or 0.0) <= 0:
        return False
    payload = item.payload
    evidence_type = getattr(item, "evidence_type", "")
    fields_by_type = {
        "browser_media_observation": (
            "visible_transcript", "opening_visual_summary", "caption_style", "observable_structure"
        ),
        "visual_structure_analysis": (
            "hook_visual", "reveal_pattern", "composition_pattern", "observable_features"
        ),
        "video_ai_observation": (
            "observed_hook", "narrative_structure", "mechanism_signals", "editing_signals"
        ),
    }
    fields = fields_by_type.get(evidence_type)
    return bool(fields and any(payload.get(field) for field in fields))


def _validated_mechanism_support(
    evidence: list[Any],
    supporting_evidence_ids: list[str],
    citation_validation: dict[str, Any],
    confidence: float,
) -> tuple[float, int]:
    """An invalid citation set cannot contribute confidence or replication evidence."""
    if not citation_validation.get("passed"):
        return 0.0, 0
    valid_ids = list(citation_validation.get("valid_evidence_ids", supporting_evidence_ids))
    return float(confidence), _mechanism_evidence_channel_count(evidence, valid_ids)


def _evidence_confidence(evidence: list[Any]) -> float:
    """Combine evidence coverage and quality so missing page fields lower confidence."""
    coverage = min(1.0, .45 + len(evidence) * .02)
    observed = [float(item.confidence) for item in evidence if item.confidence is not None]
    quality = sum(observed) / len(observed) if observed else 0.0
    return round(coverage * quality, 3)


def _bounded_json_value(value: Any, maximum_chars: int) -> Any:
    if value is None:
        return None
    serialized = json.dumps(value, default=str, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) <= maximum_chars:
        return value
    excerpt_limit = max(0, maximum_chars - 100)
    return {"truncated": True, "bounded_excerpt": serialized[:excerpt_limit]}


def _bounded_mechanism_document(payload: dict[str, Any], maximum_chars: int) -> str:
    """Return valid JSON under a hard prompt-size ceiling."""
    def serialize() -> str:
        return json.dumps(payload, default=str, ensure_ascii=False, separators=(",", ":"))

    document = serialize()
    if len(document) <= maximum_chars:
        return document
    payload["bounds"]["truncated"] = True
    comparisons = payload["matched_winner_loser_findings"]
    while comparisons and len(document) > maximum_chars:
        comparisons.pop()
        document = serialize()
    for row in reversed(payload["observed_videos"]):
        while row["transcript_segments"] and len(document) > maximum_chars:
            row["transcript_segments"].pop()
            document = serialize()
        if len(document) <= maximum_chars:
            return document
    if len(document) > maximum_chars:
        for row in payload["observed_videos"]:
            row["vision_analysis"] = None
        document = serialize()
    while len(payload["observed_videos"]) > 2 and len(document) > maximum_chars:
        payload["observed_videos"].pop()
        document = serialize()
    if len(document) <= maximum_chars:
        return document
    payload["observed_videos"] = [
        {
            "video_id": row["video_id"],
            "channel_id": row["channel_id"],
            "title": row["title"][:160],
            "views": row["views"],
            "outlier_multiple": row["outlier_multiple"],
            "transcript_segments": [],
        }
        for row in payload["observed_videos"][:2]
    ]
    document = serialize()
    if len(document) > maximum_chars:  # defensive: fixed-size fallback remains valid JSON
        payload = {
            "observed_video_ids": [row["video_id"] for row in payload["observed_videos"][:2]],
            "instruction_boundary": "Infer only cross-channel mechanisms from supplied evidence IDs.",
            "bounds": {"truncated": True, "maximum_characters": maximum_chars},
        }
        document = json.dumps(payload, separators=(",", ":"))
    return document


def _annotate_production_ideas(
    ideas: list[str],
    clip: dict[str, Any],
    production_constraints: list[str],
) -> list[dict[str, Any]]:
    validated = set(clip.get("validated_ideas", []))
    constraints = list(dict.fromkeys(value.strip() for value in production_constraints if value.strip()))
    faceless_requested = any("faceless" in value.lower() for value in constraints)
    return [
        {
            "idea": idea,
            "faceless_suitability": (
                "high" if faceless_requested and idea in validated
                else "possible_with_original_graphics_or_stock" if faceless_requested
                else "not_requested"
            ),
            "production_constraints": constraints,
            "constraint_status": "specified" if constraints else "none_specified",
            "clip_validation_status": "validated" if idea in validated else "unsupported",
            "gates_recommendation": False,
        }
        for idea in ideas
    ]


def _competitor_range(profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    estimates = sorted(int(profile.get("estimated_30d_views", 0)) for profile in profiles.values())
    if not estimates:
        return {"low": 0, "high": 0, "method": "no observed competitor uploads"}
    return {"low": estimates[0], "high": estimates[-1], "median": estimates[len(estimates) // 2], "method": "public views/day run-rate projected over 30 days; range, not private analytics"}


def _revenue_proxy(videos: list[VideoRecord], profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    projected = [int(profile.get("estimated_30d_views", 0)) for profile in profiles.values()]
    return {
        "audience_scale_30d_views_range": {"low": min(projected, default=0), "high": max(projected, default=0)},
        "engagement_proxy": round(sum((video.like_count or 0) + (video.comment_count or 0) for video in videos) / max(sum(video.view_count for video in videos), 1), 4),
        "gates_recommendation": False,
        "note": "Revenue potential is shown only as public audience-scale and engagement evidence; no CPM/RPM or advertiser-suitability claim is invented.",
    }
