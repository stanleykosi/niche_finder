import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
import respx
from sqlalchemy import BigInteger

from apps.api.app.ai.fake import FakeAIProvider
from apps.api.app.ai.ollama import OllamaProvider
from apps.api.app.db.models import ChannelSnapshot, CommentSample, RuntimeArtifact, VideoSnapshot
from apps.api.app.domain.enums import RequestedFormat, SourceType, Verdict
from apps.api.app.core.config import AppMode, Settings
from apps.api.app.core.errors import ErrorCode, NicheIntelError
from apps.api.app.domain.contracts import ResearchRunCreate
from apps.api.app.research.orchestrator import (
    ResearchOrchestrator,
    _assemble_media_candidates,
    _bounded_channel_limit,
    _bounded_channel_result_limit,
    _bounded_discovery_limits,
    _deterministic_comparison_payload,
    _discovery_video_limit,
    _fair_allocations,
    _mechanism_evidence_channel_count,
    _rank_candidates,
    _select_representative_media_ids,
    _select_vision_target_ids,
    _validated_mechanism_support,
)
from apps.api.app.research.evidence_packets import validate_citations
from apps.api.app.sources.assets import AssetResult, _archive_assets, calculate_clip_ceiling
from apps.api.app.sources.base import BrowserMediaRecord, DiscoveryResult, SearchResult, VideoRecord
from apps.api.app.sources.browser import _attach_screenshot
from apps.api.app.sources.quota import QuotaManager
from apps.api.app.sources.router import SourceRouter
from scripts.seed_demo import demo_payload
from workers.research.worker import WorkerSettings, create_worker_context, run_research


def test_public_counters_use_64_bit_storage():
    columns = [
        ChannelSnapshot.__table__.c.subscriber_count,
        ChannelSnapshot.__table__.c.total_view_count,
        ChannelSnapshot.__table__.c.video_count,
        VideoSnapshot.__table__.c.view_count,
        VideoSnapshot.__table__.c.like_count,
        VideoSnapshot.__table__.c.comment_count,
        CommentSample.__table__.c.like_count,
        RuntimeArtifact.__table__.c.size_bytes,
    ]
    assert all(isinstance(column.type, BigInteger) for column in columns)


def test_ollama_visual_request_contains_image_bytes(tmp_path):
    image_path = tmp_path / "asset.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfixture-pixels")
    response_payload = {
        "hook_visual": "paper bridge",
        "composition_pattern": "cup above bridge",
        "caption_pattern": "none",
        "pacing_pattern": "single preview",
        "reveal_pattern": "load is visible",
        "observable_features": ["paper", "cup"],
        "uncertainty": "one still",
        "confidence": .9,
    }
    provider = OllamaProvider("http://ollama.test", "vision-model")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://ollama.test/api/generate").mock(
            return_value=httpx.Response(200, json={"response": json.dumps(response_payload)})
        )
        result = asyncio.run(provider.analyze_visuals("paper bridge idea", [str(image_path)], []))
    request_payload = json.loads(route.calls[0].request.content)
    assert request_payload["images"]
    assert request_payload["format"]["title"] == "VisualStructureAnalysis"
    assert "hook_visual" in request_payload["format"]["required"]
    assert "JSON Schema:" in request_payload["prompt"]
    assert "asset.png" not in request_payload["prompt"]
    assert result.confidence == .9


def test_seed_demo_payload_uses_python_booleans_and_validates():
    payload = demo_payload()
    request = ResearchRunCreate.model_validate(payload)
    assert payload["broad_discovery"] is False
    assert payload["limits"]["deep_research"] is False
    assert request.seeds == ["paper bridge"]


def test_ollama_retries_transport_rate_limit_and_server_failures_without_switching_provider(monkeypatch):
    attempts = [
        httpx.ConnectError("connection reset"),
        httpx.Response(429, text="busy"),
        httpx.Response(503, text="starting"),
        httpx.Response(200, json={"response": json.dumps({
            "broad_market": "Education", "niche": "Tests", "sub_niche": "Paper",
            "repeatable_format": "Proof", "confidence": .8,
        })}),
    ]

    def respond(request):
        result = attempts.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def no_sleep(delay):
        return None

    monkeypatch.setattr("apps.api.app.ai.ollama.asyncio.sleep", no_sleep)
    provider = OllamaProvider("http://ollama.retry", "model", max_retries=3)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://ollama.retry/api/generate").mock(side_effect=respond)
        result = asyncio.run(provider.classify_niche("evidence", []))
    assert result.niche == "Tests"
    assert len(route.calls) == 4
    assert attempts == []


def test_ollama_repairs_schema_invalid_output_with_same_requested_schema(monkeypatch):
    responses = [
        httpx.Response(200, json={"response": '{"niche":"missing required fields"}'}),
        httpx.Response(200, json={"response": json.dumps({
            "broad_market": "Education", "niche": "Tests", "sub_niche": "Paper",
            "repeatable_format": "Proof", "confidence": .8,
        })}),
    ]

    async def no_sleep(delay):
        return None

    monkeypatch.setattr("apps.api.app.ai.ollama.asyncio.sleep", no_sleep)
    provider = OllamaProvider("http://ollama.repair", "model", max_retries=1)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://ollama.repair/api/generate").mock(side_effect=responses)
        result = asyncio.run(provider.classify_niche("evidence", []))
    assert result.niche == "Tests"
    assert len(route.calls) == 2
    request_payloads = [json.loads(call.request.content) for call in route.calls]
    assert all(payload["format"]["title"] == "NicheClassification" for payload in request_payloads)
    assert "previous response" in request_payloads[1]["prompt"].lower()


def test_clip_gate_rejects_text_only_validator_for_live_previews():
    class Connector:
        async def search(self, ideas):
            return [AssetResult(
                ideas[0], 3, 0, ["one", "two"], True, True, 1, 1,
                [{"preview_ref": "https://assets.test/preview.png"}],
            )]

    result = asyncio.run(calculate_clip_ceiling(["paper bridge"], Connector(), visual_validator=FakeAIProvider()))
    assert result["validated_count"] == 0
    assert result["semantic_fit_share"] == 0
    assert result["results"][0]["semantic_fit_reason"] == "configured validator is not image-capable"


def test_archive_assets_with_absent_license_remain_unknown_and_non_reusable():
    assets = _archive_assets({
        "response": {"docs": [
            {"identifier": "unknown-rights", "title": "Unknown"},
            {"identifier": "known-rights", "licenseurl": "https://creativecommons.org/licenses/by/4.0/"},
        ]}
    })
    assert assets[0]["license"] is None
    assert assets[0]["rights_status"] == "unknown"
    assert assets[0]["reusable"] is None
    assert assets[1]["rights_status"] == "known"
    assert assets[1]["reusable"] is True


def test_search_screenshot_is_bound_to_each_result():
    item = SearchResult("v1", "https://youtube/v1", "title", "c1", "channel", "1 view", "today", True, 1)
    attached = _attach_screenshot([item], "/runtime/search.png")
    assert attached[0].screenshot_ref == "/runtime/search.png"
    assert item.screenshot_ref is None


def test_worker_context_has_no_shared_session_or_orchestrator(monkeypatch):
    class Engine:
        def dispose(self):
            pass

    class DatabaseDouble:
        engine = Engine()

        def __init__(self, settings):
            self.settings = settings

        def create_schema(self):
            pass

    monkeypatch.setattr("workers.research.worker.Database", DatabaseDouble)
    context = create_worker_context()
    assert set(context) == {"settings", "database"}
    assert WorkerSettings.max_jobs == 2
    assert WorkerSettings.allow_abort_jobs is True


def test_aborted_worker_job_finishes_cancelled_with_job_scoped_state(monkeypatch):
    run = SimpleNamespace(id="run-1", status="queued", failure_reason=None)

    class Session:
        closed = False

        def close(self):
            self.closed = True

    session = Session()

    class Repository:
        task_updates = []

        def __init__(self, _session):
            self.session = _session

        def get_run(self, run_id):
            assert run_id == run.id
            return run

        def update_task_job(self, run_id, status, error=None, increment_attempt=False):
            self.task_updates.append((run_id, status, increment_attempt))

        def transition(self, item, status, reason=None):
            item.status = status

    repository = Repository(session)

    class Orchestrator:
        async def execute(self, item):
            raise asyncio.CancelledError

    monkeypatch.setattr("workers.research.worker.ResearchRepository", lambda _session: repository)
    monkeypatch.setattr("workers.research.worker.create_orchestrator", lambda settings, repo: Orchestrator())
    ctx = {"settings": SimpleNamespace(), "database": SimpleNamespace(session=lambda: session)}
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_research(ctx, run.id))
    assert run.status == "cancelled"
    assert repository.task_updates[-1][1] == "cancelled"
    assert session.closed is True


def test_terminal_worker_redelivery_is_a_noop(monkeypatch):
    run = SimpleNamespace(id="run-complete", status="complete", failure_reason=None)
    updates = []

    class Session:
        def close(self):
            pass

    class Repository:
        session = Session()

        def get_run(self, run_id):
            return run

        def update_task_job(self, run_id, status, error=None, increment_attempt=False):
            updates.append((status, increment_attempt))

    monkeypatch.setattr("workers.research.worker.ResearchRepository", lambda session: Repository())
    monkeypatch.setattr(
        "workers.research.worker.create_orchestrator",
        lambda settings, repository: pytest.fail("terminal redelivery must not construct or execute an orchestrator"),
    )
    ctx = {"settings": SimpleNamespace(), "database": SimpleNamespace(session=Session)}
    assert asyncio.run(run_research(ctx, run.id)) == run.id
    assert updates == [("complete", False)]


def test_nonterminal_worker_retry_replaces_partial_outputs_before_execution(monkeypatch):
    events = []
    run = SimpleNamespace(id="run-retry", status="analysing", failure_reason=None)

    class Session:
        def close(self):
            events.append("session_closed")

    class Repository:
        session = Session()

        def get_run(self, run_id):
            return run

        def reset_run_outputs_for_retry(self, run_id):
            events.append("outputs_reset")
            run.status = "queued"
            return run

        def update_task_job(self, run_id, status, error=None, increment_attempt=False):
            events.append(f"task_{status}")

        def transition(self, item, status, reason=None):
            item.status = status

    class Orchestrator:
        artifacts = SimpleNamespace(cleanup_run_temporary=lambda run_id: events.append("temporary_cleaned"))

        async def execute(self, item):
            events.append("executed")
            item.status = "complete"

    monkeypatch.setattr("workers.research.worker.ResearchRepository", lambda session: Repository())
    monkeypatch.setattr("workers.research.worker.create_orchestrator", lambda settings, repository: Orchestrator())
    ctx = {"settings": SimpleNamespace(), "database": SimpleNamespace(session=Session)}
    assert asyncio.run(run_research(ctx, run.id)) == run.id
    assert events.index("outputs_reset") < events.index("executed")
    assert events.count("executed") == 1
    assert events[-2:] == ["task_complete", "session_closed"]


def test_live_vision_reuses_bounded_channel_diverse_download_cohort():
    now = datetime.now(timezone.utc)
    videos = [
        VideoRecord(f"video-{index}", f"channel-{index}", f"https://youtube/{index}", "title", "", 45, now, None, [], {}, 1000 - index)
        for index in range(8)
    ]
    downloaded = {f"video-{index}" for index in range(6)}
    assert _select_vision_target_ids(videos, downloaded, True, 6) == downloaded
    selected_fixture = _select_vision_target_ids(videos, set(), False, 6)
    assert len(selected_fixture) == 6
    assert len({video.channel_id for video in videos if video.youtube_video_id in selected_fixture}) == 6
    filmstrip_targets = _select_representative_media_ids(videos, 6)
    assert len(filmstrip_targets) == 6
    assert len({video.channel_id for video in videos if video.youtube_video_id in filmstrip_targets}) == 6


def test_model_cannot_change_deterministic_pair_identity():
    pair = {
        "winner": {"id": "real-winner"},
        "loser": {"id": "real-loser"},
        "match_basis": "same channel",
        "match_quality": {"same_topic": True},
        "purpose": "controlled comparison",
        "performance_ratio": 4.2,
        "performance_metric": "outlier_multiple",
        "winner_performance_value": 4.2,
        "loser_performance_value": 1.0,
        "channel_id": "channel-1",
    }
    payload = _deterministic_comparison_payload(
        pair,
        {"winner_video_id": "hallucinated", "loser_video_id": "renamed", "hypothesis": "hook"},
        RequestedFormat.SHORTS,
    )
    assert payload["winner_video_id"] == "real-winner"
    assert payload["loser_video_id"] == "real-loser"
    assert payload["assessment_format"] == "shorts"
    assert payload["performance_metric"] == "outlier_multiple"


def test_clip_validation_requires_two_sources_for_each_idea():
    class Connector:
        async def search(self, ideas):
            return [AssetResult(ideas[0], 4, 0, ["pexels"], True, True, 2, 3, [], True, .95)]

    result = asyncio.run(calculate_clip_ceiling(["paper bridge"], Connector()))
    assert result["source_diversity"] == 1
    assert result["validated_count"] == 0
    assert result["source_diversity_coverage"] == 0
    assert result["results"][0]["source_diversity_passed"] is False


def test_operator_browser_limits_bound_discovery_and_channel_expansion():
    settings = Settings(
        app_mode=AppMode.LIVE_TEST,
        browser_max_queries_per_run=2,
        browser_max_results_per_query=3,
        browser_max_channels_per_run=4,
    )
    request = ResearchRunCreate.model_validate({
        "limits": {
            "max_queries": 20,
            "max_results_per_query": 30,
            "max_channels": 100,
            "max_videos": 100,
        }
    })
    assert _bounded_discovery_limits(request, settings) == (2, 3)
    assert _bounded_channel_limit(request, settings) == 4
    assert _bounded_channel_result_limit(request, settings, 4) == 3


def test_channel_expansion_fetches_at_least_three_feed_records_for_cohorts():
    request = ResearchRunCreate.model_validate({
        "limits": {"max_videos": 100, "max_channels": 50}
    })
    assert _bounded_channel_result_limit(request, Settings(), 34) == 3
    assert _bounded_channel_result_limit(
        request, Settings(browser_max_results_per_query=2), 34
    ) == 2


def test_fair_allocations_include_late_recipients_when_budget_is_smaller():
    allocations = _fair_allocations(10, 12)
    assert sum(allocations) == 10
    assert allocations[-1] == 1
    assert allocations[0] == 1


def test_discovery_reserves_capacity_for_same_channel_upload_history():
    now = datetime.now(timezone.utc)
    initial = [
        VideoRecord(f"seed-{index}", f"channel-{index}", f"https://youtube/seed-{index}", "seed", "", 45, now, None, [], {}, 100)
        for index in range(4)
    ]

    class Youtube:
        async def expand_channel_uploads(self, channel_id, limit):
            return [
                VideoRecord(f"{channel_id}-upload-{index}", channel_id, f"https://youtube/{channel_id}-{index}", "upload", "", 45, now, None, [], {}, 80 - index)
                for index in range(3)
            ]

        def drain_diagnostics(self):
            return []

    orchestrator = object.__new__(ResearchOrchestrator)
    orchestrator.settings = Settings()
    orchestrator.youtube = Youtube()
    orchestrator.repository = SimpleNamespace(add_evidence=lambda *args, **kwargs: None)
    request = ResearchRunCreate(limits={"max_channels": 4, "max_videos": 12, "max_expansion_depth": 1})
    assert _discovery_video_limit(request) == 4
    expanded = asyncio.run(orchestrator._expand_channels("run-1", initial, request))
    assert len(expanded) == 12
    assert all(sum(video.channel_id == f"channel-{index}" for video in expanded) == 3 for index in range(4))


def test_invalid_mechanism_citation_set_has_zero_recommendation_support():
    evidence = [
        SimpleNamespace(id="ev-1", payload={"channel_id": "channel-a"}),
        SimpleNamespace(id="ev-2", payload={"channel_id": "channel-b"}),
    ]
    citations = validate_citations(["ev-1", "ev-2", "unknown"], ["ev-1", "ev-2"])
    confidence, channel_count = _validated_mechanism_support(
        evidence,
        ["ev-1", "ev-2", "unknown"],
        citations,
        .95,
    )
    assert citations["passed"] is False
    assert confidence == 0
    assert channel_count == 0


def test_mechanism_replication_counts_only_mechanism_bearing_evidence():
    evidence = [
        SimpleNamespace(
            id="outlier-a", evidence_type="deterministic_outlier", confidence=1.0,
            payload={"channel_id": "channel-a", "outlier_multiple": 5.0},
        ),
        SimpleNamespace(
            id="outlier-b", evidence_type="deterministic_outlier", confidence=1.0,
            payload={"channel_id": "channel-b", "outlier_multiple": 4.0},
        ),
        SimpleNamespace(
            id="browser-a", evidence_type="browser_media_observation", confidence=.8,
            payload={"channel_id": "channel-a", "observable_structure": ["question then proof"]},
        ),
        SimpleNamespace(
            id="browser-b", evidence_type="browser_media_observation", confidence=.8,
            payload={"channel_id": "channel-b", "opening_visual_summary": "visible failed attempt"},
        ),
    ]
    assert _mechanism_evidence_channel_count(evidence, ["outlier-a", "outlier-b"]) == 0
    assert _mechanism_evidence_channel_count(evidence, ["browser-a", "browser-b"]) == 2


def test_orchestrator_discovery_obeys_health_router_and_uses_api_fallback():
    observations = []
    audits = []
    run = SimpleNamespace(id="run-1", status="queued")

    class Repository:
        def get_run(self, run_id):
            assert run_id == run.id
            return run

        def transition(self, item, status, reason=None):  # noqa: ARG002
            item.status = status

        def add_routing_audit(self, run_id, task, source, reason, quota_delta=0):
            audits.append((source, reason, quota_delta))

        def add_search_observation(self, run_id, payload):
            observations.append(payload)

    class Browser:
        async def discover(self, request):  # noqa: ARG002
            pytest.fail("unhealthy browser must not be called")

    class Youtube:
        async def discover(self, request):
            return DiscoveryResult(SourceType.YOUTUBE_API, request.query, [
                SearchResult(
                    "video-1", "https://youtube.com/watch?v=video-1", "Video", "channel-1",
                    "Channel", "unknown", "2026-08-01", False, 1,
                )
            ])

    orchestrator = object.__new__(ResearchOrchestrator)
    orchestrator.settings = Settings(app_mode=AppMode.LIVE_TEST, youtube_api_key="configured")
    orchestrator.repository = Repository()
    orchestrator.router = SourceRouter(AppMode.LIVE_TEST, QuotaManager(10, 2))
    orchestrator.source_health = lambda: (False, True)
    orchestrator.browser = Browser()
    orchestrator.youtube = Youtube()
    orchestrator.artifacts = SimpleNamespace(register=lambda *args, **kwargs: None)
    plan = SimpleNamespace(
        queries=["paper bridge"], visited_queries=set(), visited_channels=set(),
        visited_videos=set(), should_stop=lambda new_results, attempted: False,
        discovery_strategy="seeded",
    )
    request = ResearchRunCreate(
        seeds=["paper bridge"],
        limits={"max_queries": 1, "max_results_per_query": 2, "max_channels": 2, "max_videos": 4},
    )
    found = asyncio.run(orchestrator._discover(run.id, request, plan))
    assert list(found) == ["video-1"]
    assert observations[0]["source"] == SourceType.YOUTUBE_API.value
    assert audits[0][0] == SourceType.YOUTUBE_API.value


def test_empty_browser_discovery_executes_audited_api_fallback():
    observations = []
    audits = []
    run = SimpleNamespace(id="run-empty-browser", status="queued")

    class Repository:
        def get_run(self, run_id):
            assert run_id == run.id
            return run

        def transition(self, item, status, reason=None):  # noqa: ARG002
            item.status = status

        def add_routing_audit(self, run_id, task, source, reason, quota_delta=0):
            audits.append((source, reason, quota_delta))

        def add_search_observation(self, run_id, payload):
            observations.append(payload)

    class Browser:
        async def discover(self, request):
            return DiscoveryResult(SourceType.BROWSER, request.query, [])

    class Youtube:
        async def discover(self, request):
            return DiscoveryResult(SourceType.YOUTUBE_API, request.query, [
                SearchResult(
                    "video-1", "https://youtube.com/watch?v=video-1", "Video", "channel-1",
                    "Channel", "unknown", "2026-08-01", False, 1,
                )
            ])

    orchestrator = object.__new__(ResearchOrchestrator)
    orchestrator.settings = Settings(app_mode=AppMode.LIVE_TEST, youtube_api_key="configured")
    orchestrator.repository = Repository()
    orchestrator.router = SourceRouter(AppMode.LIVE_TEST, QuotaManager(10, 2))
    orchestrator.source_health = lambda: (True, True)
    orchestrator.browser = Browser()
    orchestrator.youtube = Youtube()
    orchestrator.artifacts = SimpleNamespace(register=lambda *args, **kwargs: None)
    plan = SimpleNamespace(
        queries=["storytelling"], visited_queries=set(), visited_channels=set(),
        visited_videos=set(), should_stop=lambda new_results, attempted: False,
        discovery_strategy="seeded",
    )
    request = ResearchRunCreate(
        seeds=["storytelling"],
        limits={"max_queries": 1, "max_results_per_query": 2, "max_channels": 2, "max_videos": 4},
    )
    found = asyncio.run(orchestrator._discover(run.id, request, plan))
    assert list(found) == ["video-1"]
    assert observations[0]["source"] == SourceType.YOUTUBE_API.value
    assert [audit[0] for audit in audits] == [SourceType.BROWSER.value, SourceType.YOUTUBE_API.value]
    assert "no hydrated result cards" in audits[-1][1]


def test_cross_market_discovery_samples_every_planned_market_before_depth():
    calls = []
    observations = []
    run = SimpleNamespace(id="run-portfolio", status="queued")

    class Repository:
        def get_run(self, run_id):  # noqa: ARG002
            return run

        def transition(self, item, status, reason=None):  # noqa: ARG002
            item.status = status

        def add_routing_audit(self, *args, **kwargs):  # noqa: ARG002
            return None

        def add_search_observation(self, run_id, payload):  # noqa: ARG002
            observations.append(payload)

    class Browser:
        async def discover(self, request):
            calls.append(request.query)
            market = int(request.query.split("-")[-1])
            return DiscoveryResult(SourceType.FIXTURE_BROWSER, request.query, [
                SearchResult(
                    f"video-{market}-{index}",
                    f"https://youtube.com/watch?v=video-{market}-{index}",
                    f"Market {market} video {index}",
                    f"channel-{market}-{index}",
                    f"Channel {market}-{index}",
                    "100 views",
                    "1 day ago",
                    True,
                    index + 1,
                )
                for index in range(2)
            ])

    orchestrator = object.__new__(ResearchOrchestrator)
    orchestrator.settings = Settings(app_mode=AppMode.CLOSED_TEST)
    orchestrator.repository = Repository()
    orchestrator.router = SourceRouter(AppMode.CLOSED_TEST, QuotaManager(10, 2))
    orchestrator.source_health = None
    orchestrator.browser = Browser()
    orchestrator.youtube = SimpleNamespace()
    orchestrator.artifacts = SimpleNamespace(register=lambda *args, **kwargs: None)
    plan = SimpleNamespace(
        queries=[f"market-{index}" for index in range(12)],
        visited_queries=set(),
        visited_channels=set(),
        visited_videos=set(),
        should_stop=lambda new_results, attempted: True,
        discovery_strategy="cross_market_portfolio",
    )
    request = ResearchRunCreate.model_validate({
        "seeds": [],
        "broad_discovery": True,
        "limits": {
            "max_queries": 12,
            "max_results_per_query": 20,
            "max_channels": 30,
            "max_videos": 30,
        },
    })

    found = asyncio.run(orchestrator._discover(run.id, request, plan))
    assert calls == [f"market-{index}" for index in range(12)]
    assert len(observations) == 24
    assert len(found) == 10
    assert any(video_id.startswith("video-11-") for video_id in found)
    assert len({video_id.split("-")[1] for video_id in found}) == 10


def test_mechanism_dossier_bounds_videos_transcripts_and_total_size():
    now = datetime.now(timezone.utc)
    videos = [
        VideoRecord(f"video-{index}", f"channel-{index}", f"https://youtube/{index}", "title " * 100, "", 600, now, None, [], {}, 1000 - index)
        for index in range(20)
    ]
    media = {
        video.youtube_video_id: BrowserMediaRecord(
            "fixture", False, "transcript sentence " * 5000, None, [f"frame-{index}" for index in range(20)],
            "opening " * 300, "caption " * 100, ["structure " * 100] * 20, now, .9,
            first_spoken_line="spoken " * 300,
        )
        for video in videos
    }
    outliers = {video.youtube_video_id: SimpleNamespace(outlier_multiple=4.0) for video in videos}
    vision = {video.youtube_video_id: {"features": ["visual " * 1000] * 10} for video in videos}
    dossier = ResearchOrchestrator._mechanism_dossier(videos, media, vision, outliers, [{"hypothesis": "x" * 5000}] * 20)
    parsed = json.loads(dossier)
    assert len(dossier) <= 24000
    assert len(parsed["observed_videos"]) <= 6
    assert all(len(item.get("transcript_segments", [])) <= 2 for item in parsed["observed_videos"])
    assert all("transcript" not in item for item in parsed["observed_videos"])


def test_one_unavailable_browser_page_becomes_partial_zero_confidence_evidence():
    now = datetime.now(timezone.utc)
    video = VideoRecord("video-1", "channel-1", "https://youtube.com/watch?v=video-1", "Usable metadata", "", 60, now, None, [], {}, 100)
    persisted = []

    class Browser:
        async def inspect_video(self, *args):
            raise NicheIntelError("page timed out", ErrorCode.SOURCE_UNAVAILABLE)

    orchestrator = object.__new__(ResearchOrchestrator)
    orchestrator.settings = Settings(app_mode=AppMode.LIVE_TEST)
    orchestrator.browser = Browser()
    orchestrator.repository = SimpleNamespace(add_evidence=lambda run_id, payload: persisted.append(payload))
    media = asyncio.run(orchestrator._inspect_video_with_partial_result("run-1", video))
    assert media.confidence == 0
    assert media.visible_transcript is None
    assert media.frame_refs == []
    assert persisted[0]["evidence_type"] == "browser_video_inspection_skipped"
    assert persisted[0]["payload"]["partial"] is True
    assert "visible_transcript" in persisted[0]["payload"]["missing_fields"]


def test_browser_configuration_failure_is_not_hidden_as_a_partial_page():
    now = datetime.now(timezone.utc)
    video = VideoRecord("video-1", "channel-1", "https://youtube.com/watch?v=video-1", "Video", "", 60, now, None, [], {}, 100)

    class Browser:
        async def inspect_video(self, *args):
            raise NicheIntelError("Chromium missing", ErrorCode.CONFIGURATION)

    orchestrator = object.__new__(ResearchOrchestrator)
    orchestrator.settings = Settings(app_mode=AppMode.LIVE_TEST)
    orchestrator.browser = Browser()
    orchestrator.repository = SimpleNamespace(add_evidence=lambda *args: pytest.fail("configuration failures must not create page diagnostics"))
    with pytest.raises(NicheIntelError) as raised:
        asyncio.run(orchestrator._inspect_video_with_partial_result("run-1", video))
    assert raised.value.code == ErrorCode.CONFIGURATION


def _candidate(media_format: RequestedFormat, rank: int, centroid: list[float], promising: bool) -> dict:
    fit = "promising" if promising else "watch"
    assessed = {"fit": fit, "score": .8 if promising else .4, "reason": media_format.value, "evidence_ids": [f"ev-{media_format.value}"]}
    missing = {"fit": "not_assessed", "score": None, "reason": "separate", "evidence_ids": []}
    gates = {"all_passed": promising}
    return {
        "rank": rank,
        "broad_market": "Education",
        "niche": "Paper bridge tests",
        "sub_niche": "folded paper",
        "repeatable_format": "attempt then proof",
        "primary_viral_mechanism": "question then reveal",
        "shorts_assessment": assessed if media_format == RequestedFormat.SHORTS else missing,
        "longform_assessment": assessed if media_format == RequestedFormat.LONG_FORM else missing,
        "bridge_assessment": {},
        "idea_ceiling": {"validated_count": 12},
        "clip_ceiling": {"validated_count": 11},
        "saturation_assessment": {"risk_score": .3},
        "demand_assessment": {"hard_gates": gates, "score": .8 if promising else .4},
        "momentum_assessment": {"score": .8 if promising else .4},
        "research_synthesis": {"media": media_format.value},
        "critic_assessment": {"media": media_format.value},
        "confidence": .85,
        "verdict": (Verdict.SHORTS_ONLY if media_format == RequestedFormat.SHORTS else Verdict.LONG_FORM_ONLY).value if promising else Verdict.INSUFFICIENT.value,
        "evidence_ids": [f"ev-{media_format.value}"],
        "_assessment_format": media_format.value,
        "_cluster_centroid": centroid,
        "_cluster_label": f"{media_format.value}: paper bridge",
    }


def test_both_assembles_real_media_specific_and_bridge_assessments():
    combined = _assemble_media_candidates([
        _candidate(RequestedFormat.SHORTS, 1, [1.0, 0.0], True),
        _candidate(RequestedFormat.LONG_FORM, 2, [1.0, 0.0], False),
    ], RequestedFormat.BOTH)
    assert len(combined) == 1
    candidate = combined[0]
    assert candidate["shorts_assessment"]["reason"] == "shorts"
    assert candidate["longform_assessment"]["reason"] == "long_form"
    assert candidate["bridge_assessment"]["fit"] == "shorts_first_with_long_form_expansion"
    assert candidate["verdict"] == Verdict.SHORTS_ONLY.value
    assert candidate["demand_assessment"]["media_assessments"]["shorts"]["score"] == .8
    assert candidate["demand_assessment"]["media_assessments"]["long_form"]["score"] == .4


def test_both_does_not_pair_unrelated_media_topics():
    candidates = _assemble_media_candidates([
        _candidate(RequestedFormat.SHORTS, 1, [1.0, 0.0], True),
        _candidate(RequestedFormat.LONG_FORM, 2, [0.0, 1.0], True),
    ], RequestedFormat.BOTH)
    assert len(candidates) == 2
    assert candidates[0]["longform_assessment"]["fit"] == "not_assessed"
    assert candidates[1]["shorts_assessment"]["fit"] == "not_assessed"


def test_candidate_ranking_uses_adjudicated_verdict_before_preliminary_outlier_order():
    one_hit = _candidate(RequestedFormat.SHORTS, 1, [1.0, 0.0], False)
    one_hit["niche"] = "Largest isolated outlier"
    one_hit["confidence"] = .99
    one_hit["demand_assessment"]["score"] = .95
    qualified = _candidate(RequestedFormat.SHORTS, 2, [0.8, 0.2], True)
    qualified["niche"] = "All gates passed"
    qualified["confidence"] = .78
    ranked = _rank_candidates([one_hit, qualified])
    assert [item["niche"] for item in ranked] == ["All gates passed", "Largest isolated outlier"]
