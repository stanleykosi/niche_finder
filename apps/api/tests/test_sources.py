import asyncio
from datetime import datetime, timezone

import pytest
import httpx
import respx

from apps.api.app.core.config import AppMode, Settings
from apps.api.app.core.errors import ClosedModeViolation, ErrorCode, NicheIntelError
from apps.api.app.sources.fixture_browser import FixtureBrowserSource
from apps.api.app.sources.fixture_youtube import FixtureYoutubeSource
from apps.api.app.sources.quota import QuotaManager
from apps.api.app.sources.youtube_api import YouTubeDataApiSource, _parse_iso8601_duration
from apps.api.app.sources.ytdlp_youtube import YtDlpYoutubeSource
from apps.api.app.research.orchestrator import ResearchOrchestrator, _discovery_enrichment_context
from apps.api.app.domain.contracts import ResearchRunCreate
from apps.api.app.sources.base import SearchResult, VideoRecord


def test_live_youtube_constructor_is_blocked_in_closed_mode():
    with pytest.raises(ClosedModeViolation):
        YouTubeDataApiSource("secret", AppMode.CLOSED_TEST, QuotaManager())


def test_fixture_api_contract_covers_empty_and_enrichment():
    source = FixtureYoutubeSource("strong")
    assert asyncio.run(source.discover(__import__('apps.api.app.sources.base', fromlist=['DiscoveryRequest']).DiscoveryRequest('paper bridge', max_results=4))).results
    assert asyncio.run(source.enrich_videos([])) == []
    assert asyncio.run(source.enrich_channels(["ch-physics-lab"]))[0].title == "Physics Lab"
    assert asyncio.run(source.expand_channel_uploads("ch-physics-lab"))
    assert asyncio.run(source.sample_comments("v-bridge-01"))


def test_fixture_browser_contract_includes_transcript_and_missing_transcript():
    source = FixtureBrowserSource("strong")
    result = asyncio.run(source.discover(__import__('apps.api.app.sources.base', fromlist=['DiscoveryRequest']).DiscoveryRequest('paper bridge', max_results=3)))
    assert result.source.value == "fixture_browser"
    assert asyncio.run(source.inspect_video("v-bridge-01")).visible_transcript
    assert asyncio.run(source.inspect_video("v-paper-02")).visible_transcript is None
    observed = asyncio.run(source.inspect_video("v-bridge-01"))
    assert observed.confidence > 0
    assert observed.pacing_score is None
    assert observed.reveal_timestamp_seconds is None


def test_fixture_browser_missing_video_is_typed_unavailable_without_synthetic_features():
    missing = asyncio.run(FixtureBrowserSource("strong").inspect_video("absent-expanded-video"))
    assert missing.confidence == 0
    assert missing.visible_transcript is None
    assert missing.frame_refs == []
    assert missing.average_shot_duration_seconds is None
    assert missing.reveal_timestamp_seconds is None
    assert missing.motion_score is None
    assert missing.pacing_score is None
    assert missing.visual_features["inspection_status"] == "unavailable"
    assert "reveal" in missing.visual_features["missing_fields"]


def test_youtube_iso_duration_is_parsed_without_treating_it_as_short_confirmation():
    assert _parse_iso8601_duration("PT2M15S") == 135
    assert _parse_iso8601_duration("PT1H2M3S") == 3723
    assert _parse_iso8601_duration("not-a-duration") is None


def test_youtube_list_enrichment_batches_ids_at_fifty():
    source = YouTubeDataApiSource("fixture-key", AppMode.DEVELOPMENT, QuotaManager())
    calls: list[tuple[str, list[str]]] = []

    async def fake_get(resource, params, attempts=3):
        ids = params["id"].split(",")
        calls.append((resource, ids))
        if resource == "videos":
            return {"items": [{"id": item_id, "snippet": {"channelId": f"channel-{item_id}", "publishedAt": "2026-08-01T00:00:00Z"}, "contentDetails": {"duration": "PT1M"}, "statistics": {"viewCount": "1"}} for item_id in ids]}
        return {"items": [{"id": item_id, "snippet": {"title": item_id}, "statistics": {}} for item_id in ids]}

    source._get = fake_get
    ids = [f"id-{index}" for index in range(101)]
    assert len(asyncio.run(source.enrich_videos(ids))) == 101
    assert len(asyncio.run(source.enrich_channels(ids))) == 101
    assert [len(batch) for resource, batch in calls if resource == "videos"] == [50, 50, 1]
    assert [len(batch) for resource, batch in calls if resource == "channels"] == [50, 50, 1]


def test_youtube_api_excludes_undated_videos_with_typed_diagnostics():
    source = YouTubeDataApiSource("fixture-key", AppMode.DEVELOPMENT, QuotaManager())

    async def fake_get(resource, params, attempts=3):  # noqa: ARG001
        return {"items": [
            {"id": "missing-date", "snippet": {"channelId": "c1"}, "statistics": {"viewCount": "999999"}},
            {"id": "invalid-date", "snippet": {"channelId": "c2", "publishedAt": "not-a-date"}, "statistics": {"viewCount": "999999"}},
            {"id": "dated", "snippet": {"channelId": "c3", "publishedAt": "2026-08-01T00:00:00Z"}, "statistics": {"viewCount": "10"}},
        ]}

    source._get = fake_get
    records = asyncio.run(source.enrich_videos(["missing-date", "invalid-date", "dated"]))
    assert [record.youtube_video_id for record in records] == ["dated"]
    diagnostics = source.drain_diagnostics()
    assert [item.source_entity_id for item in diagnostics] == ["missing-date", "invalid-date"]
    assert all(item.diagnostic_type == "youtube_api_video_skipped" for item in diagnostics)
    assert all(item.error_code == ErrorCode.VALIDATION.value for item in diagnostics)


def test_youtube_api_records_every_requested_video_omitted_from_response():
    source = YouTubeDataApiSource("fixture-key", AppMode.DEVELOPMENT, QuotaManager())

    async def fake_get(resource, params, attempts=3):  # noqa: ARG001
        return {"items": [{
            "id": "available",
            "snippet": {"channelId": "c1", "publishedAt": "2026-08-01T00:00:00Z"},
            "contentDetails": {"duration": "PT1M"},
            "statistics": {"viewCount": "10"},
        }]}

    source._get = fake_get
    records = asyncio.run(source.enrich_videos(
        ["removed", "available", "private"],
        {"private": {"url": "https://www.youtube.com/shorts/private", "channel_id": "known-channel"}},
    ))
    assert [record.youtube_video_id for record in records] == ["available"]
    diagnostics = source.drain_diagnostics()
    assert [item.source_entity_id for item in diagnostics] == ["removed", "private"]
    assert all(item.diagnostic_type == "youtube_api_video_omitted" for item in diagnostics)
    assert all(item.error_code == ErrorCode.NOT_FOUND.value for item in diagnostics)
    assert diagnostics[1].source_url == "https://www.youtube.com/shorts/private"
    assert diagnostics[1].channel_id == "known-channel"


def test_youtube_api_empty_channel_lookup_yields_no_uploads():
    source = YouTubeDataApiSource("fixture-key", AppMode.DEVELOPMENT, QuotaManager())

    async def fake_get(resource, params, attempts=3):  # noqa: ARG001
        assert resource == "channels"
        return {"items": []}

    source._get = fake_get
    assert asyncio.run(source.expand_channel_uploads("removed-channel")) == []


def test_youtube_client_retries_transient_server_statuses(monkeypatch):
    source = YouTubeDataApiSource("fixture-key", AppMode.DEVELOPMENT, QuotaManager())

    async def no_sleep(delay):
        return None

    monkeypatch.setattr("apps.api.app.sources.youtube_api.asyncio.sleep", no_sleep)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://www.googleapis.com/youtube/v3/videos").mock(side_effect=[
            httpx.Response(503),
            httpx.Response(502),
            httpx.Response(200, json={"items": []}),
        ])
        assert asyncio.run(source._get("videos", {"part": "snippet", "id": "v1"})) == {"items": []}
        assert route.call_count == 3
    assert source.quota.status().used_units == 3


@pytest.mark.parametrize("reason", ["quotaExceeded", "dailyLimitExceeded"])
def test_youtube_403_quota_reasons_preserve_quota_error_taxonomy(reason):
    source = YouTubeDataApiSource("fixture-key", AppMode.DEVELOPMENT, QuotaManager())
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://www.googleapis.com/youtube/v3/videos").mock(return_value=httpx.Response(
            403,
            json={"error": {"code": 403, "message": "Quota exceeded", "errors": [{"reason": reason}]}},
        ))
        with pytest.raises(NicheIntelError) as raised:
            asyncio.run(source._get("videos", {"part": "snippet", "id": "v1"}))
    assert raised.value.code == ErrorCode.QUOTA_EXHAUSTED


def test_keyless_ytdlp_source_normalizes_public_metadata_without_process():
    source = YtDlpYoutubeSource()
    async def fake_json(args):
        return {"id": "v1", "channel_id": "c1", "channel": "Channel", "title": "Why this coin test works", "description": "proof", "duration": 42, "timestamp": 1786406400, "view_count": 1200, "tags": ["coin", "test"], "aspect_ratio": .56}
    source._json = fake_json
    video = asyncio.run(source.enrich_videos(["v1"]))[0]
    assert video.channel_id == "c1"
    assert video.topic == "coin test"
    assert video.is_short is True
    channel = asyncio.run(source.enrich_channels(["c1"]))[0]
    assert channel.title == "Channel"
    assert channel.description == ""


def test_keyless_ytdlp_uses_upload_date_and_excludes_unknown_publication_date():
    source = YtDlpYoutubeSource()

    async def dated_json(args):
        return {"id": "dated", "channel_id": "c1", "title": "Dated", "upload_date": "20260804", "view_count": 10}

    source._json = dated_json
    dated = asyncio.run(source.enrich_videos(["dated"]))[0]
    assert dated.published_at == datetime(2026, 8, 4, tzinfo=timezone.utc)

    async def undated_json(args):
        return {"id": "undated", "channel_id": "c1", "title": "Undated", "view_count": 10}

    source._json = undated_json
    assert asyncio.run(source.enrich_videos(["undated"])) == []
    diagnostic = source.drain_diagnostics()[0]
    assert diagnostic.source_entity_id == "undated"
    assert diagnostic.error_code == "validation_error"
    assert "publication date is unavailable" in diagnostic.reason


def test_keyless_initial_enrichment_isolates_unusable_candidates():
    source = YtDlpYoutubeSource()

    async def fake_json(args):
        video_id = args[-1].split("v=")[-1]
        if video_id == "private":
            raise NicheIntelError("yt-dlp metadata failed: private", ErrorCode.SOURCE_UNAVAILABLE)
        item = {"id": video_id, "channel_id": "c1", "title": video_id, "view_count": 10}
        if video_id == "good":
            item.update({"upload_date": "20260804", "duration": 40, "aspect_ratio": .56})
        return item

    source._json = fake_json
    records = asyncio.run(source.enrich_videos(["private", "good", "undated"]))
    assert [item.youtube_video_id for item in records] == ["good"]
    diagnostics = source.drain_diagnostics()
    assert [item.source_entity_id for item in diagnostics] == ["private", "undated"]
    assert diagnostics[0].channel_id is None
    assert diagnostics[1].channel_id == "c1"


def test_keyless_configuration_failure_propagates_without_skip_diagnostic():
    source = YtDlpYoutubeSource()

    async def missing_tool(args):
        raise NicheIntelError("yt-dlp is required", ErrorCode.CONFIGURATION)

    source._json = missing_tool
    with pytest.raises(NicheIntelError) as raised:
        asyncio.run(source.enrich_videos(["candidate-a", "candidate-b"]))
    assert raised.value.code == ErrorCode.CONFIGURATION
    assert "yt-dlp is required" in raised.value.message
    assert source.drain_diagnostics() == []


def test_initial_keyless_diagnostic_retains_browser_discovery_context():
    source = YtDlpYoutubeSource()
    search = SearchResult(
        "private", "https://www.youtube.com/shorts/private", "Known title",
        "known-channel", "Known Channel", "12K views", "2 days ago", True, 4,
        screenshot_ref="fixture://search.png",
        raw_payload={"surface": "shorts", "card_text": "Known visible card"},
    )

    async def inaccessible(args):
        raise NicheIntelError("members-only", ErrorCode.SOURCE_UNAVAILABLE)

    source._json = inaccessible
    context = {"private": _discovery_enrichment_context(search)}
    assert asyncio.run(source.enrich_videos(["private"], context)) == []
    diagnostic = source.drain_diagnostics()[0]
    assert diagnostic.channel_id == "known-channel"
    assert diagnostic.source_url == "https://www.youtube.com/shorts/private"
    assert diagnostic.raw_payload == {
        "id": "private",
        "title": "Known title",
        "url": "https://www.youtube.com/shorts/private",
        "channel_id": "known-channel",
        "channel_title": "Known Channel",
        "visible_views_text": "12K views",
        "visible_age_text": "2 days ago",
        "presented_as_short": True,
        "result_position": 4,
        "screenshot_ref": "fixture://search.png",
        "discovery_raw_payload": {"surface": "shorts", "card_text": "Known visible card"},
    }


def test_keyless_sparse_success_preserves_discovery_channel_and_title():
    source = YtDlpYoutubeSource()
    context = {"sparse": {
        "id": "sparse",
        "url": "https://www.youtube.com/shorts/sparse",
        "title": "Discovery title",
        "channel_id": "discovery-channel",
        "channel_title": "Discovery Channel",
        "presented_as_short": True,
    }}

    async def sparse_json(args):
        return {
            "id": "sparse", "upload_date": "20260804", "duration": 40,
            "aspect_ratio": .56, "view_count": 100,
            "channel_id": None, "title": "",
        }

    source._json = sparse_json
    record = asyncio.run(source.enrich_videos(["sparse"], context))[0]
    assert record.channel_id == "discovery-channel"
    assert record.title == "Discovery title"
    assert record.is_short is True
    channel = asyncio.run(source.enrich_channels(["discovery-channel"]))[0]
    assert channel.title == "Discovery Channel"


def test_keyless_sparse_expanded_upload_is_seeded_with_traversed_channel():
    source = YtDlpYoutubeSource()
    source._metadata["seed"] = {
        "id": "seed", "channel_id": "known-channel",
        "channel_url": "https://www.youtube.com/@known",
    }

    async def sparse_json(args, *, playlist=False):
        if playlist:
            return {"entries": [{"id": "sparse-upload", "title": "Feed title"}]}
        return {
            "id": "sparse-upload", "upload_date": "20260804", "duration": 40,
            "aspect_ratio": .56, "view_count": 100,
        }

    source._json = sparse_json
    record = asyncio.run(source.expand_channel_uploads("known-channel", 1))[0]
    assert record.channel_id == "known-channel"
    assert record.title == "Feed title"


def test_keyless_rejected_extraction_keeps_canonical_diagnostic_url():
    source = YtDlpYoutubeSource()
    context = {"rejected": {
        "id": "rejected",
        "url": "https://www.youtube.com/shorts/rejected",
        "title": "Discovery title",
        "channel_id": "known-channel",
    }}

    async def temporary_media_json(args):
        video_id = args[-1].split("v=")[-1]
        return {
            "id": video_id, "title": "Extracted title", "view_count": 10,
            "url": "https://rr1.googlevideo.com/videoplayback?expire=temporary",
        }

    source._json = temporary_media_json
    assert asyncio.run(source.enrich_videos(["rejected"], context)) == []
    diagnostic = source.drain_diagnostics()[0]
    assert diagnostic.source_url == "https://www.youtube.com/shorts/rejected"
    assert diagnostic.raw_payload["url"].startswith("https://rr1.googlevideo.com/")

    assert asyncio.run(source.enrich_videos(["reconstructed"])) == []
    diagnostic = source.drain_diagnostics()[0]
    assert diagnostic.source_url == "https://www.youtube.com/watch?v=reconstructed"


def test_keyless_null_or_invalid_aspect_ratio_is_unknown_not_short():
    source = YtDlpYoutubeSource()

    async def fake_json(args):
        video_id = args[-1].split("v=")[-1]
        ratios = {
            "null-ratio": None, "invalid-ratio": "unknown", "zero-ratio": 0,
            "negative-ratio": -0.5, "portrait": "0.56",
        }
        return {
            "id": video_id, "channel_id": "c1", "title": video_id,
            "upload_date": "20260804", "duration": 40,
            "aspect_ratio": ratios[video_id], "view_count": 10,
        }

    source._json = fake_json
    records = asyncio.run(source.enrich_videos(["null-ratio", "invalid-ratio", "zero-ratio", "negative-ratio", "portrait"]))
    assert [item.is_short for item in records] == [False, False, False, False, True]
    assert [item.shorts_evidence for item in records] == [
        "aspect_ratio_unknown", "aspect_ratio_unknown", "aspect_ratio_invalid",
        "aspect_ratio_invalid", "portrait",
    ]
    assert source.drain_diagnostics() == []


def test_keyless_ytdlp_timeout_and_cancellation_kill_and_reap_children(monkeypatch):
    async def exercise(cancel: bool):
        started = asyncio.Event()
        reaped = asyncio.Event()

        class Process:
            returncode = None

            async def communicate(self):
                started.set()
                while self.returncode is None:
                    await asyncio.sleep(.001)
                reaped.set()
                return b"{}", b""

            def kill(self):
                self.returncode = -9

        process = Process()

        async def create_process(*args, **kwargs):  # noqa: ARG001
            return process

        monkeypatch.setattr(
            "apps.api.app.sources.ytdlp_youtube.asyncio.create_subprocess_exec",
            create_process,
        )
        source = YtDlpYoutubeSource(timeout=.01)
        task = asyncio.create_task(source._json(["https://youtube.test/video"]))
        await started.wait()
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(NicheIntelError, match="timed out"):
                await task
        assert process.returncode == -9
        assert reaped.is_set()

    asyncio.run(exercise(False))
    asyncio.run(exercise(True))


def test_keyless_ytdlp_expands_bounded_channel_video_feed():
    source = YtDlpYoutubeSource()
    source._metadata["seed"] = {"id": "seed", "channel_id": "c1", "channel_url": "https://www.youtube.com/@channel"}
    calls = []

    async def fake_json(args, *, playlist=False):
        calls.append((args, playlist))
        if playlist:
            return {"entries": [{"id": f"upload-{index}"} for index in range(10)]}
        video_id = args[-1].split("v=")[-1]
        return {"id": video_id, "channel_id": "c1", "title": f"Upload {video_id}", "duration": 40, "timestamp": 1786406400, "view_count": 100}

    source._json = fake_json
    uploads = asyncio.run(source.expand_channel_uploads("c1", 3))
    assert [item.youtube_video_id for item in uploads] == ["upload-0", "upload-1", "upload-2"]
    assert calls[0][1] is True
    assert calls[0][0][-1] == "https://www.youtube.com/@channel/videos"
    assert "--playlist-end" in calls[0][0]


def test_keyless_channel_expansion_skips_bad_entries_and_retains_diagnostics():
    source = YtDlpYoutubeSource()
    source._metadata["seed"] = {"id": "seed", "channel_id": "c1", "channel_url": "https://www.youtube.com/@channel"}

    async def fake_json(args, *, playlist=False):
        if playlist:
            return {"entries": [
                {"id": "good", "title": "Public"},
                {"id": "private", "title": "Members only", "availability": "subscriber_only"},
                {"id": "undated", "title": "No reliable date"},
            ]}
        video_id = args[-1].split("v=")[-1]
        if video_id == "private":
            raise NicheIntelError("yt-dlp metadata failed: members-only", ErrorCode.SOURCE_UNAVAILABLE)
        item = {"id": video_id, "channel_id": "c1", "title": video_id, "view_count": 10}
        if video_id == "good":
            item["upload_date"] = "20260804"
        return item

    source._json = fake_json
    uploads = asyncio.run(source.expand_channel_uploads("c1", 3))
    assert [item.youtube_video_id for item in uploads] == ["good"]
    diagnostics = source.drain_diagnostics()
    assert [item.source_entity_id for item in diagnostics] == ["private", "undated"]
    assert diagnostics[0].raw_payload["availability"] == "subscriber_only"
    assert diagnostics[1].error_code == "validation_error"
    assert source.drain_diagnostics() == []


def test_keyless_unavailable_channel_feed_is_skipped_but_configuration_propagates():
    source = YtDlpYoutubeSource()

    async def unavailable(args, *, playlist=False):
        raise NicheIntelError("channel feed unavailable", ErrorCode.SOURCE_UNAVAILABLE)

    source._json = unavailable
    assert asyncio.run(source.expand_channel_uploads("channel-a", 5)) == []
    diagnostic = source.drain_diagnostics()[0]
    assert diagnostic.diagnostic_type == "keyless_channel_feed_skipped"
    assert diagnostic.source_entity_id == "channel-a"
    assert diagnostic.channel_id == "channel-a"
    assert diagnostic.source_url.endswith("/channel/channel-a/videos")
    assert diagnostic.raw_payload["requested_limit"] == 5

    async def missing_tool(args, *, playlist=False):
        raise NicheIntelError("yt-dlp missing", ErrorCode.CONFIGURATION)

    source._json = missing_tool
    with pytest.raises(NicheIntelError) as raised:
        asyncio.run(source.expand_channel_uploads("channel-b", 5))
    assert raised.value.code == ErrorCode.CONFIGURATION
    assert source.drain_diagnostics() == []


def test_orchestrator_persists_keyless_skip_diagnostics_as_evidence():
    class Repository:
        def __init__(self):
            self.evidence = []

        def add_evidence(self, run_id, payload):
            self.evidence.append((run_id, payload))

    class Youtube:
        channel_id = None

        async def expand_channel_uploads(self, channel_id, limit):
            self.channel_id = channel_id
            return []

        def drain_diagnostics(self):
            from apps.api.app.sources.base import SourceDiagnostic
            return [SourceDiagnostic(
                "keyless_video_skipped", "private", self.channel_id,
                "https://www.youtube.com/watch?v=private", "members-only",
                "source_unavailable", datetime(2026, 8, 16, tzinfo=timezone.utc),
                {"availability": "subscriber_only"},
            )]

    orchestrator = object.__new__(ResearchOrchestrator)
    orchestrator.settings = Settings()
    orchestrator.youtube = Youtube()
    orchestrator.repository = Repository()
    initial = [VideoRecord("seed", "c1", "https://youtube.com/watch?v=seed", "Seed", "", 40, datetime(2026, 8, 1, tzinfo=timezone.utc), None, [], {}, 100)]
    request = ResearchRunCreate(limits={"max_channels": 1, "max_videos": 3, "max_expansion_depth": 1})
    assert asyncio.run(orchestrator._expand_channels("run-1", initial, request)) == initial
    run_id, evidence = orchestrator.repository.evidence[0]
    assert run_id == "run-1"
    assert evidence["evidence_type"] == "keyless_video_skipped"
    assert evidence["payload"]["error_code"] == "source_unavailable"


def test_orchestrator_continues_after_one_channel_feed_is_unavailable():
    from apps.api.app.sources.base import SourceDiagnostic

    class Repository:
        def __init__(self):
            self.evidence = []

        def add_evidence(self, run_id, payload):
            self.evidence.append(payload)

    class Youtube:
        def __init__(self):
            self.calls = []
            self.diagnostics = []

        async def expand_channel_uploads(self, channel_id, limit):
            self.calls.append(channel_id)
            if channel_id == "channel-a":
                self.diagnostics.append(SourceDiagnostic(
                    "keyless_channel_feed_skipped", channel_id, channel_id,
                    "https://www.youtube.com/channel/channel-a/videos",
                    "feed unavailable", "source_unavailable",
                    datetime(2026, 8, 16, tzinfo=timezone.utc), {},
                ))
                return []
            return [VideoRecord(
                "upload-b", channel_id, "https://youtube.com/watch?v=upload-b",
                "Upload B", "", 40, datetime(2026, 8, 5, tzinfo=timezone.utc),
                None, [], {}, 200,
            )]

        def drain_diagnostics(self):
            result, self.diagnostics = self.diagnostics, []
            return result

    orchestrator = object.__new__(ResearchOrchestrator)
    orchestrator.settings = Settings()
    orchestrator.youtube = Youtube()
    orchestrator.repository = Repository()
    initial = [
        VideoRecord("seed-a", "channel-a", "https://youtube.com/watch?v=seed-a", "A", "", 40, datetime(2026, 8, 1, tzinfo=timezone.utc), None, [], {}, 100),
        VideoRecord("seed-b", "channel-b", "https://youtube.com/watch?v=seed-b", "B", "", 40, datetime(2026, 8, 1, tzinfo=timezone.utc), None, [], {}, 100),
    ]
    request = ResearchRunCreate(limits={"max_channels": 2, "max_videos": 4, "max_expansion_depth": 1})
    expanded = asyncio.run(orchestrator._expand_channels("run-1", initial, request))
    assert orchestrator.youtube.calls == ["channel-a", "channel-b"]
    assert [item.youtube_video_id for item in expanded] == ["seed-a", "seed-b", "upload-b"]
    assert orchestrator.repository.evidence[0]["evidence_type"] == "keyless_channel_feed_skipped"
    assert orchestrator.repository.evidence[0]["payload"]["video_id"] is None
