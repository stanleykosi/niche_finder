import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from apps.api.app.core.config import AppMode, Settings
from apps.api.app.core.errors import ErrorCode, NicheIntelError
from apps.api.app.db.session import Database
from apps.api.app.db.models import ResearchRun
from apps.api.app.repositories.store import ResearchRepository
from apps.api.app.sources.base import BrowserMediaRecord, VideoRecord
from apps.api.app.sources.media_analysis import DeepgramVideoAnalyzer
from apps.api.app.storage.artifacts import RuntimeArtifactManager


def setup(tmp_path, **overrides):
    values = {
        "app_mode": AppMode.CLOSED_TEST,
        "database_url": f"sqlite:///{tmp_path / 'artifacts.db'}",
        "media_work_root": str(tmp_path / "runtime" / "media"),
        "browser_profile_root": str(tmp_path / "runtime" / "browser_profiles"),
        "media_min_free_disk_gb": 0,
    }
    values.update(overrides)
    settings = Settings(**values)
    database = Database(settings)
    database.create_schema()
    repository = ResearchRepository(database.session())
    repository.session.add_all([
        ResearchRun(id=run_id, configuration={})
        for run_id in ("run-1", "run-2", "run-3", "run-4")
    ])
    repository.session.commit()
    return settings, repository, RuntimeArtifactManager(settings, repository)


def test_artifacts_retain_hash_and_deletion_state(tmp_path):
    _, repository, manager = setup(tmp_path)
    path = manager.run_workspace("run-1")["frames"] / "frame.jpg"
    path.write_bytes(b"derived-frame")
    record = manager.register(path, "analysis_frame", "run-1", 24)
    assert len(record["sha256"]) == 64
    assert record["size_bytes"] == 13
    manager.delete(path)
    stored = repository.runtime_artifacts("run-1")[0]
    assert stored.state == "deleted"
    assert stored.deleted_at is not None
    assert not path.exists()


def test_cleanup_deletes_expired_frames_and_stale_browser_images(tmp_path):
    settings, repository, manager = setup(tmp_path)
    frame = manager.run_workspace("run-2")["frames"] / "expired.jpg"
    frame.write_bytes(b"frame")
    manager.register(frame, "analysis_frame", "run-2", 1)
    artifact = repository.runtime_artifacts("run-2")[0]
    artifact.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    repository.session.commit()
    screenshot = Path(settings.browser_profile_root) / "profile" / "old.png"
    screenshot.parent.mkdir(parents=True)
    screenshot.write_bytes(b"screen")
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).timestamp()
    os.utime(screenshot, (old, old))
    result = manager.cleanup_expired()
    assert result.files_deleted == 2
    assert not frame.exists()
    assert not screenshot.exists()


def test_storage_ceiling_blocks_download_before_process_start(tmp_path):
    _, _, manager = setup(tmp_path, media_max_storage_gb=.00001, media_unknown_download_reserve_mb=10)
    with pytest.raises(Exception, match="storage ceiling"):
        manager.reserve_download()


def test_download_capacity_reservations_are_serialized_and_released(tmp_path):
    _, _, manager = setup(
        tmp_path,
        media_max_storage_gb=0.0000001,
        media_unknown_download_reserve_mb=10,
    )
    first = manager.reserve_download(expected_bytes=60)
    with pytest.raises(Exception, match="storage ceiling"):
        manager.reserve_download(expected_bytes=60)
    assert manager.status()["reserved_download_bytes"] == 60
    manager.release_download(first)
    second = manager.reserve_download(expected_bytes=60)
    manager.release_download(second)
    assert manager.status()["reserved_download_bytes"] == 0


def test_artifact_manager_refuses_to_delete_managed_roots(tmp_path):
    _, _, manager = setup(tmp_path)
    with pytest.raises(ValueError, match="artifact root"):
        manager.delete(manager.media_root)
    with pytest.raises(ValueError, match="artifact root"):
        manager.delete(manager.browser_root)


def test_non_owner_cannot_initialize_or_operate_on_worker_storage(tmp_path):
    settings = Settings(
        app_mode=AppMode.PRODUCTION,
        database_url=f"sqlite:///{tmp_path / 'control.db'}",
        media_work_root=str(tmp_path / "runtime" / "worker_media"),
        browser_profile_root=str(tmp_path / "runtime" / "worker_browser"),
    )
    manager = RuntimeArtifactManager(settings, storage_owner=False)
    assert not manager.media_root.exists()
    assert not manager.browser_root.exists()
    with pytest.raises(RuntimeError, match="mounted storage"):
        manager.cleanup_expired()


def test_raw_video_is_deleted_only_after_transcript_and_frames_are_extracted(tmp_path):
    settings, repository, manager = setup(tmp_path, deepgram_api_key="fixture-key")
    analyzer = DeepgramVideoAnalyzer(settings, manager)
    observed: list[tuple[str, bool]] = []

    download_call = {}

    async def fake_run(command, timeout, *, output_path=None, maximum_bytes=None):
        output = Path(command[command.index("-o") + 1]) if "-o" in command else Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video" if output.suffix == ".mp4" else b"frame")
        if output.suffix == ".mp4":
            download_call.update(command=command, output_path=output_path, maximum_bytes=maximum_bytes)

    def fake_transcribe(path):
        observed.append(("transcript", path.exists()))
        return "This is a complete transcript.", [{"word": "This", "start": 0, "end": .2}]

    original_frames = analyzer._frames

    async def tracked_frames(frame_root, media, run_id, video_id, duration):
        observed.append(("frames", media.exists()))
        return await original_frames(frame_root, media, run_id, video_id, duration)

    analyzer._run = fake_run
    analyzer._transcribe = fake_transcribe
    analyzer._frames = tracked_frames
    video = VideoRecord("v1", "c1", "https://youtube.com/watch?v=v1", "Test", "", 40, datetime.now(timezone.utc), None, [], {}, 10)
    browser = BrowserMediaRecord("fixture", True, None, None, [], None, None, [], datetime.now(timezone.utc), .7)
    result = asyncio.run(analyzer.analyze("run-3", video, browser))
    assert observed == [("transcript", True), ("frames", True)]
    assert result.visible_transcript == "This is a complete transcript."
    assert len(result.frame_refs) == 6
    assert result.average_shot_duration_seconds is None
    assert "--max-filesize" in download_call["command"]
    assert str(download_call["maximum_bytes"]) == download_call["command"][download_call["command"].index("--max-filesize") + 1]
    assert download_call["output_path"].name == "v1.mp4"
    assert not list((Path(settings.media_work_root) / "run-3" / "downloads").glob("*.mp4"))
    records = repository.runtime_artifacts("run-3")
    assert next(item for item in records if item.artifact_type == "raw_video").state == "deleted"
    assert sum(item.artifact_type == "analysis_frame" and item.state == "available" for item in records) == 6


def test_raw_and_partial_download_are_deleted_when_transcription_fails(tmp_path):
    settings, repository, manager = setup(tmp_path, deepgram_api_key="fixture-key")
    analyzer = DeepgramVideoAnalyzer(settings, manager)

    async def fake_run(command, timeout, *, output_path=None, maximum_bytes=None):  # noqa: ARG001
        output = Path(command[command.index("-o") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"partial-video")

    def fail_transcribe(path):
        assert path.exists()
        raise RuntimeError("fixture transcription failure")

    analyzer._run = fake_run
    analyzer._transcribe = fail_transcribe
    video = VideoRecord("v2", "c1", "https://youtube.com/watch?v=v2", "Test", "", 40, datetime.now(timezone.utc), None, [], {}, 10)
    browser = BrowserMediaRecord("fixture", True, None, None, [], None, None, [], datetime.now(timezone.utc), .7)
    with pytest.raises(RuntimeError, match="transcription failure"):
        asyncio.run(analyzer.analyze("run-4", video, browser))
    assert not list((Path(settings.media_work_root) / "run-4" / "downloads").glob("*"))
    assert repository.runtime_artifacts("run-4")[0].state == "deleted"


def test_media_process_is_killed_and_reaped_before_cancellation_propagates(monkeypatch):
    started = asyncio.Event()
    reaped = asyncio.Event()

    class Process:
        returncode = None

        async def communicate(self):
            started.set()
            while self.returncode is None:
                await asyncio.sleep(.001)
            reaped.set()
            return b"", b"cancelled"

        def kill(self):
            self.returncode = -9

    process = Process()

    async def create_process(*args, **kwargs):  # noqa: ARG001
        return process

    monkeypatch.setattr("apps.api.app.sources.media_analysis.asyncio.create_subprocess_exec", create_process)

    async def scenario():
        task = asyncio.create_task(DeepgramVideoAnalyzer._run(["yt-dlp", "url"], 30))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert reaped.is_set()

    asyncio.run(scenario())


def test_media_process_aborts_when_output_crosses_reserved_bytes(tmp_path, monkeypatch):
    output = tmp_path / "runtime" / "media" / "oversized.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"0123456789")
    reaped = asyncio.Event()

    class Process:
        returncode = None

        async def communicate(self):
            while self.returncode is None:
                await asyncio.sleep(.001)
            reaped.set()
            return b"", b"too large"

        def kill(self):
            self.returncode = -9

    async def create_process(*args, **kwargs):  # noqa: ARG001
        return Process()

    monkeypatch.setattr("apps.api.app.sources.media_analysis.asyncio.create_subprocess_exec", create_process)
    with pytest.raises(NicheIntelError, match="exceeded its 5-byte reservation"):
        asyncio.run(DeepgramVideoAnalyzer._run(["yt-dlp", "url"], 30, output_path=output, maximum_bytes=5))
    assert reaped.is_set()


def test_missing_ffmpeg_configuration_propagates_instead_of_becoming_partial_frames(tmp_path):
    settings, _, manager = setup(tmp_path, deepgram_api_key="fixture-key")
    analyzer = DeepgramVideoAnalyzer(settings, manager)

    async def missing_ffmpeg(*args, **kwargs):  # noqa: ARG001
        raise NicheIntelError("required media tool is missing: ffmpeg", ErrorCode.CONFIGURATION)

    analyzer._run = missing_ffmpeg
    frame_root = manager.run_workspace("run-ffmpeg")["frames"]
    media = manager.run_workspace("run-ffmpeg")["downloads"] / "video.mp4"
    media.write_bytes(b"video")
    with pytest.raises(NicheIntelError) as raised:
        asyncio.run(analyzer._frames(frame_root, media, "run-ffmpeg", "v1", 60))
    assert raised.value.code == ErrorCode.CONFIGURATION


def test_browser_observed_duration_blocks_paid_media_before_reservation(tmp_path):
    settings, _, manager = setup(
        tmp_path,
        deepgram_api_key="fixture-key",
        media_max_duration_seconds=60,
    )
    analyzer = DeepgramVideoAnalyzer(settings, manager)
    manager.reserve_download = lambda *args, **kwargs: pytest.fail("duration limit must run before reservation")
    video = VideoRecord(
        "v-long", "c1", "https://youtube.com/watch?v=v-long", "Long", "", None,
        datetime.now(timezone.utc), None, [], {}, 10,
    )
    browser = BrowserMediaRecord(
        "browser", False, None, None, [], None, None, [], datetime.now(timezone.utc), .7,
        duration_seconds=120,
    )
    result = asyncio.run(analyzer.analyze("run-duration", video, browser))
    assert result.visual_features["deepgram_status"] == "duration_limit"
