from datetime import datetime, timedelta, timezone

from apps.api.app.core.config import AppMode, Settings
from apps.api.app.db.session import Database
from apps.api.app.db.models import ChannelSnapshot, CommentSample, FormatCluster, VideoSnapshot, ViralMechanismAnalysis
from apps.api.app.domain.contracts import ResearchRunCreate
from apps.api.app.repositories.store import ResearchRepository
from apps.api.app.sources.fixture_youtube import FixtureYoutubeSource
from apps.api.app.sources.base import ChannelRecord, CommentRecord, VideoRecord
import asyncio
from sqlalchemy import func, select


def test_schema_run_and_idempotent_entities(tmp_path):
    db = Database(Settings(app_mode=AppMode.CLOSED_TEST, database_url=f"sqlite:///{tmp_path / 'test.db'}"))
    db.create_schema()
    repository = ResearchRepository(db.session())
    run = repository.create_run(ResearchRunCreate(seeds=["paper bridge"]))
    source = FixtureYoutubeSource("strong")
    channel_record = asyncio.run(source.enrich_channels(["ch-physics-lab"]))[0]
    channel = repository.upsert_channel(channel_record)
    video_record = asyncio.run(source.enrich_videos(["v-bridge-01"]))[0]
    first = repository.upsert_video(video_record, channel)
    second = repository.upsert_video(video_record, channel)
    assert first.id == second.id
    evidence = repository.add_evidence(run.id, {"evidence_type": "test", "source_type": "fixture_api", "source_entity_id": "v-bridge-01", "payload": {"video_id": "v-bridge-01"}, "confidence": 1.0, "human_readable_summary": "fixture"})
    assert repository.get_evidence(run.id)[0].id == evidence.id


def test_empty_keyless_channel_description_preserves_known_channel_metadata(tmp_path):
    db = Database(Settings(app_mode=AppMode.CLOSED_TEST, database_url=f"sqlite:///{tmp_path / 'channels.db'}"))
    db.create_schema()
    repository = ResearchRepository(db.session())
    known = ChannelRecord("channel-1", "https://youtube.com/channel/channel-1", "Known", "Channel-level description", 1, 2, 3)
    repository.upsert_channel(known, "youtube_api")
    keyless = ChannelRecord("channel-1", "https://youtube.com/channel/channel-1", "Known", "", None, None, None)
    updated = repository.upsert_channel(keyless, "keyless_ytdlp")
    assert updated.description == "Channel-level description"


def test_sparse_keyless_channel_identity_cannot_replace_known_title_or_handle_url(tmp_path):
    db = Database(Settings(app_mode=AppMode.CLOSED_TEST, database_url=f"sqlite:///{tmp_path / 'channel-identity.db'}"))
    db.create_schema()
    repository = ResearchRepository(db.session())
    repository.upsert_channel(
        ChannelRecord("channel-1", "https://www.youtube.com/@known-handle", "Known Channel", "Known description"),
        "youtube_api",
    )
    refreshed = repository.upsert_channel(
        ChannelRecord(
            "channel-1", "https://www.youtube.com/channel/channel-1", "channel-1", "",
            None, None, None,
        ),
        "keyless_ytdlp",
    )
    assert refreshed.title == "Known Channel"
    assert refreshed.canonical_url == "https://www.youtube.com/@known-handle"
    assert refreshed.description == "Known description"


def test_fuller_video_enrichment_refreshes_all_normalized_metadata(tmp_path):
    db = Database(Settings(app_mode=AppMode.CLOSED_TEST, database_url=f"sqlite:///{tmp_path / 'videos.db'}"))
    db.create_schema()
    repository = ResearchRepository(db.session())
    channel = repository.upsert_channel(ChannelRecord("channel-1", "https://youtube/channel/1", "Channel"))
    published = datetime(2026, 8, 1, tzinfo=timezone.utc)
    sparse = VideoRecord(
        "video-1", "channel-1", "https://youtube/shorts/video-1", "Sparse title", "", None,
        published - timedelta(days=3), None, [], {}, 10,
    )
    repository.upsert_video(sparse, channel, "browser")
    enriched = VideoRecord(
        "video-1", "channel-1", "https://www.youtube.com/watch?v=video-1", "Authoritative title",
        "Full channel-level description", 601, published, "27", ["paper", "bridge"],
        {"high": {"url": "https://img/video-1.jpg"}}, 1000,
    )
    updated = repository.upsert_video(enriched, channel, "youtube_api")
    assert updated.canonical_url == enriched.canonical_url
    assert updated.title == enriched.title
    assert updated.description == enriched.description
    assert updated.duration_seconds == 601
    assert updated.published_at == published
    assert updated.category_id == "27"
    assert updated.tags == ["paper", "bridge"]
    assert updated.thumbnails == enriched.thumbnails

    # A later sparse observation may update its snapshot without erasing the
    # authoritative metadata already persisted on the video entity.
    preserved = repository.upsert_video(
        VideoRecord("video-1", "channel-1", "", "", "", None, published, None, [], {}, 1200),
        channel,
        "browser",
    )
    assert preserved.canonical_url == enriched.canonical_url
    assert preserved.duration_seconds == 601
    assert preserved.tags == ["paper", "bridge"]
    assert preserved.thumbnails == enriched.thumbnails


def test_recoverable_retry_atomically_removes_partial_run_outputs(tmp_path):
    db = Database(Settings(app_mode=AppMode.CLOSED_TEST, database_url=f"sqlite:///{tmp_path / 'retry.db'}"))
    db.create_schema()
    repository = ResearchRepository(db.session())
    run = repository.create_run(ResearchRunCreate(seeds=["paper bridge"]))
    repository.transition(run, "analysing")
    repository.add_search_observation(run.id, {
        "source": "fixture_browser", "profile_id": "fixture", "query": "paper bridge",
        "result_position": 1, "observed_url": "https://youtube/video-1", "observed_title": "Video",
        "observed_channel": "Channel", "visible_views_text": "100 views", "visible_age_text": "today",
        "presented_as_short": True, "screenshot_ref": None, "raw_payload": {},
    })
    repository.add_evidence(run.id, {
        "evidence_type": "partial", "source_type": "fixture_api", "source_entity_id": "video-1",
        "payload": {}, "confidence": 1.0, "human_readable_summary": "partial output",
    })
    cluster = repository.add_cluster(run.id, {
        "label": "shorts: proof", "description": "partial cluster", "centroid": [1.0],
        "representative_video_ids": ["video-1"], "confidence": .8,
    })
    repository.add_mechanism(cluster.id, {
        "primary_mechanism": "proof", "secondary_mechanisms": [], "viewer_question": "will it work?",
        "hook_pattern": "question", "payoff_pattern": "proof", "evidence_refs": [],
        "alternative_explanation": "novelty", "confidence": .5, "provider": "fake", "version": "v1",
    })
    repository.add_candidate(run.id, {
        "rank": 1, "broad_market": "Education", "niche": "Tests", "sub_niche": "Paper",
        "repeatable_format": "proof", "primary_viral_mechanism": "proof", "shorts_assessment": {},
        "longform_assessment": {}, "bridge_assessment": {}, "idea_ceiling": {}, "clip_ceiling": {},
        "saturation_assessment": {}, "demand_assessment": {}, "momentum_assessment": {},
        "research_synthesis": {}, "critic_assessment": {}, "confidence": .5,
        "verdict": "Insufficient evidence", "evidence_ids": [],
    })
    reset = repository.reset_run_outputs_for_retry(run.id)
    assert reset.status == "queued"
    assert reset.started_at is None and reset.completed_at is None and reset.failure_reason is None
    assert repository.get_observations(run.id) == []
    assert repository.get_evidence(run.id) == []
    assert repository.get_candidates(run.id) == []
    assert repository.session.scalar(select(func.count()).select_from(FormatCluster)) == 0
    assert repository.session.scalar(select(func.count()).select_from(ViralMechanismAnalysis)) == 0


def test_retry_updates_same_run_snapshots_without_inventing_temporal_observations(tmp_path):
    db = Database(Settings(app_mode=AppMode.CLOSED_TEST, database_url=f"sqlite:///{tmp_path / 'snapshot-retry.db'}"))
    db.create_schema()
    repository = ResearchRepository(db.session())
    first_run = repository.create_run(ResearchRunCreate(seeds=["paper bridge"]))
    second_run = repository.create_run(ResearchRunCreate(seeds=["paper bridge follow-up"]))
    published = datetime(2026, 8, 1, tzinfo=timezone.utc)
    channel_record = ChannelRecord(
        "channel-1", "https://youtube.com/channel/channel-1", "Channel", "Description",
        100, 10_000, 20,
    )
    video_record = VideoRecord(
        "video-1", "channel-1", "https://youtube.com/watch?v=video-1", "Paper bridge", "Proof",
        60, published, "27", ["paper"], {}, 1_000, 100, 10,
    )

    channel = repository.upsert_channel(channel_record, "youtube_api", first_run.id)
    repository.upsert_video(video_record, channel, "youtube_api", first_run.id)
    retry_channel = ChannelRecord(
        "channel-1", channel_record.canonical_url, channel_record.title, channel_record.description,
        101, 10_100, 20,
    )
    retry_video = VideoRecord(
        "video-1", "channel-1", video_record.canonical_url, video_record.title, video_record.description,
        video_record.duration_seconds, published, video_record.category_id, video_record.tags,
        video_record.thumbnails, 1_010, 101, 11,
    )
    repository.upsert_channel(retry_channel, "youtube_api", first_run.id)
    repository.upsert_video(retry_video, channel, "youtube_api", first_run.id)

    channel_snapshots = list(repository.session.scalars(select(ChannelSnapshot)))
    video_snapshots = list(repository.session.scalars(select(VideoSnapshot)))
    assert len(channel_snapshots) == 1
    assert channel_snapshots[0].subscriber_count == 101
    assert len(video_snapshots) == 1
    assert video_snapshots[0].view_count == 1_010
    assert len(repository.video_snapshot_history("video-1")) == 1

    repository.upsert_channel(retry_channel, "youtube_api", second_run.id)
    repository.upsert_video(retry_video, channel, "youtube_api", second_run.id)
    assert repository.session.scalar(select(func.count()).select_from(ChannelSnapshot)) == 2
    assert repository.session.scalar(select(func.count()).select_from(VideoSnapshot)) == 2
    assert len(repository.video_snapshot_history("video-1")) == 2


def test_retried_comment_samples_update_one_public_observation(tmp_path):
    db = Database(Settings(app_mode=AppMode.CLOSED_TEST, database_url=f"sqlite:///{tmp_path / 'comments.db'}"))
    db.create_schema()
    repository = ResearchRepository(db.session())
    channel = repository.upsert_channel(ChannelRecord("channel-1", "https://youtube/channel/1", "Channel"))
    published = datetime(2026, 8, 1, tzinfo=timezone.utc)
    video = repository.upsert_video(VideoRecord(
        "video-1", "channel-1", "https://youtube/watch?v=video-1", "Video", "", 60,
        published, None, [], {}, 100,
    ), channel)
    repository.add_comment_samples(video.id, [CommentRecord("comment-1", "first", 1, published)], "youtube_api")
    repository.add_comment_samples(video.id, [CommentRecord("comment-1", "refreshed", 4, published)], "youtube_api")
    comments = list(repository.session.scalars(select(CommentSample)))
    assert len(comments) == 1
    assert comments[0].text == "refreshed"
    assert comments[0].like_count == 4


def test_shared_channel_and_video_upserts_use_database_conflict_identity(tmp_path):
    db = Database(Settings(app_mode=AppMode.CLOSED_TEST, database_url=f"sqlite:///{tmp_path / 'entities.db'}"))
    db.create_schema()
    first = ResearchRepository(db.session())
    second = ResearchRepository(db.session())
    channel_record = ChannelRecord("shared-channel", "https://youtube/channel/shared", "Shared")
    channel_a = first.upsert_channel(channel_record)
    channel_b = second.upsert_channel(channel_record)
    video_record = VideoRecord(
        "shared-video", "shared-channel", "https://youtube/watch?v=shared-video", "Shared video", "",
        60, datetime(2026, 8, 1, tzinfo=timezone.utc), None, [], {}, 10,
    )
    video_a = first.upsert_video(video_record, channel_a)
    video_b = second.upsert_video(video_record, channel_b)
    assert channel_a.id == channel_b.id
    assert video_a.id == video_b.id
