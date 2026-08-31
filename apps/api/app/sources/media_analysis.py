"""Deepgram + selective-filmstrip analysis inspired by browser-use/video-use.

The adapter downloads only bounded representative videos, transcribes their
audio with word timestamps, and extracts a small set of decision-point frames.
It never dumps every frame into model context.
"""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

from ..core.config import Settings
from ..core.errors import ErrorCode, NicheIntelError
from ..research.preprocessing import english_likelihood
from ..storage.artifacts import RuntimeArtifactManager
from .base import BrowserMediaRecord, VideoRecord


class MediaAnalyzer(Protocol):
    async def analyze(self, run_id: str, video: VideoRecord, browser: BrowserMediaRecord) -> BrowserMediaRecord: ...


class PassthroughMediaAnalyzer:
    requires_download = False

    async def analyze(self, run_id: str, video: VideoRecord, browser: BrowserMediaRecord) -> BrowserMediaRecord:
        return replace(browser, visual_features={**browser.visual_features, "english_likelihood": english_likelihood(browser.visible_transcript), "analysis_method": "fixture_selective_filmstrip"})


class DeepgramVideoAnalyzer:
    requires_download = True

    def __init__(self, settings: Settings, artifacts: RuntimeArtifactManager) -> None:
        self.settings = settings
        self.artifacts = artifacts

    async def analyze(self, run_id: str, video: VideoRecord, browser: BrowserMediaRecord) -> BrowserMediaRecord:
        if not self.settings.media_download_enabled or not self.settings.deepgram_api_key:
            return replace(browser, visual_features={**browser.visual_features, "deepgram_status": "not_configured", "english_likelihood": english_likelihood(browser.visible_transcript)})
        observed_duration = (
            float(video.duration_seconds)
            if video.duration_seconds is not None
            else float(browser.duration_seconds) if browser.duration_seconds is not None else None
        )
        if observed_duration is not None and observed_duration > self.settings.media_max_duration_seconds:
            return replace(browser, visual_features={**browser.visual_features, "deepgram_status": "duration_limit"})
        workspace = self.artifacts.run_workspace(run_id)
        media_path = workspace["downloads"] / f"{video.youtube_video_id}.mp4"
        reservation = self.artifacts.reserve_download()
        try:
            try:
                await self._run([
                    self.settings.ytdlp_executable,
                    "--no-playlist",
                    "--no-part",
                    "--max-filesize",
                    str(reservation.reserved_bytes),
                    "-f",
                    "b[height<=720][ext=mp4]/b[height<=720]",
                    "-o",
                    str(media_path),
                    video.canonical_url,
                ], 300, output_path=media_path, maximum_bytes=reservation.reserved_bytes)
                if not media_path.is_file():
                    raise NicheIntelError(
                        "media download was unavailable within the reserved size limit",
                        ErrorCode.SOURCE_UNAVAILABLE,
                    )
            except NicheIntelError as exc:
                if exc.code == ErrorCode.CONFIGURATION:
                    raise
                return replace(
                    browser,
                    visual_features={
                        **browser.visual_features,
                        "deepgram_status": "download_unavailable",
                        "heavy_media_analysis": "partial_browser_only",
                        "media_download_error_code": exc.code.value,
                        "media_download_error": exc.message,
                        "english_likelihood": english_likelihood(browser.visible_transcript),
                    },
                )
            self.artifacts.register(media_path, "raw_video", run_id, None, {"video_id": video.youtube_video_id, "purpose": "Deepgram transcription and selective frame extraction"})
            # The raw file remains present through every operation below.
            transcript, words = await _run_blocking(self._transcribe, media_path)
            duration = observed_duration or 60.0
            frame_refs = await self._frames(workspace["frames"], media_path, run_id, video.youtube_video_id, duration)
            phrase_count = max(len([line for line in transcript.split(".") if line.strip()]), 1)
            return replace(
                browser,
                visible_transcript=transcript or browser.visible_transcript,
                frame_refs=frame_refs or browser.frame_refs,
                first_spoken_line=(transcript.split(".", 1)[0] or browser.first_spoken_line) if transcript else browser.first_spoken_line,
                pacing_score=round(min(1.0, phrase_count / max(duration / 3, 1)), 3),
                # Selective samples are not scene detections. Preserve an
                # independently observed value or leave this metric unknown.
                average_shot_duration_seconds=browser.average_shot_duration_seconds,
                music_cue_count=_audio_event_count(words, {"music", "singing"}),
                editing_pattern="transcript phrase boundaries plus six decision-point frames; vision model interprets visible cut/pacing pattern",
                visual_features={**browser.visual_features, "analysis_method": "deepgram_word_timestamps_plus_selective_filmstrip", "deepgram_status": "observed", "raw_video_retention": "deleted_after_extraction", "word_timestamps": words[:500], "english_likelihood": english_likelihood(transcript)},
                confidence=max(browser.confidence, .86),
            )
        finally:
            # Success, provider failure, cancellation, and partial downloads all
            # converge here. Derived frames are retained; raw media is not.
            try:
                self.artifacts.cleanup_run_temporary(run_id)
            finally:
                self.artifacts.release_download(reservation)

    def _transcribe(self, path: Path) -> tuple[str, list[dict[str, Any]]]:
        try:
            from deepgram import DeepgramClient
        except ImportError as exc:
            raise NicheIntelError("Install the media extra for Deepgram transcription", ErrorCode.CONFIGURATION) from exc
        client = DeepgramClient(api_key=self.settings.deepgram_api_key)
        response = client.listen.v1.media.transcribe_file(
            request=path.read_bytes(), model=self.settings.deepgram_model, language="en", smart_format=True,
            utterances=True, punctuate=True, request_options={"timeout_in_seconds": 300, "max_retries": 3},
        )
        payload = response.model_dump() if hasattr(response, "model_dump") else json.loads(response.to_json())
        alternative = payload.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0]
        return str(alternative.get("transcript") or ""), list(alternative.get("words") or [])

    async def _frames(self, frame_root: Path, media: Path, run_id: str, video_id: str, duration: float) -> list[str]:
        refs: list[str] = []
        for index, fraction in enumerate((.02, .12, .3, .55, .8, .95)):
            output = frame_root / f"{video_id}-{index}.jpg"
            try:
                await self._run([self.settings.ffmpeg_executable, "-y", "-ss", str(duration * fraction), "-i", str(media), "-frames:v", "1", "-vf", "scale=640:-2", str(output)], 40)
            except NicheIntelError as exc:
                if exc.code == ErrorCode.CONFIGURATION:
                    raise
                continue
            if output.exists():
                self.artifacts.register(output, "analysis_frame", run_id, self.settings.media_derived_retention_hours, {"video_id": video_id, "sample_fraction": fraction})
                refs.append(str(output))
        return refs

    @staticmethod
    async def _run(
        command: list[str],
        timeout: float,
        *,
        output_path: Path | None = None,
        maximum_bytes: int | None = None,
    ) -> None:
        try:
            process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        except FileNotFoundError as exc:
            raise NicheIntelError(f"required media tool is missing: {command[0]}", ErrorCode.CONFIGURATION) from exc
        communicate = asyncio.create_task(process.communicate())
        deadline = asyncio.get_running_loop().time() + timeout
        try:
            while not communicate.done():
                if output_path is not None and maximum_bytes is not None:
                    try:
                        if output_path.stat().st_size > maximum_bytes:
                            raise NicheIntelError(
                                f"media download exceeded its {maximum_bytes}-byte reservation",
                                ErrorCode.SOURCE_UNAVAILABLE,
                            )
                    except FileNotFoundError:
                        pass
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError
                await asyncio.wait({communicate}, timeout=min(.1, remaining))
            _, stderr = communicate.result()
        except BaseException as exc:
            if process.returncode is None:
                process.kill()
            # Reap the child before propagating timeout/cancellation/error so
            # the caller cannot release storage while the process still runs.
            try:
                await communicate
            except BaseException:
                pass
            if isinstance(exc, TimeoutError):
                raise NicheIntelError(f"media tool timed out: {command[0]}", ErrorCode.SOURCE_UNAVAILABLE) from exc
            raise
        if process.returncode:
            raise NicheIntelError(f"media tool failed: {stderr.decode(errors='replace')[-400:]}", ErrorCode.SOURCE_UNAVAILABLE)


def _audio_event_count(words: list[dict[str, Any]], events: set[str]) -> int | None:
    labels = [str(word.get("word") or word.get("punctuated_word") or "").lower().strip("()[]") for word in words]
    if not labels:
        return None
    return sum(label in events for label in labels)


async def _run_blocking(function: Any, *args: Any) -> Any:
    """Run SDK work off-loop without relying on executor wake-up callbacks.

    Some constrained runtimes execute ``asyncio.to_thread`` successfully but
    suppress the cross-thread event-loop notification. Polling a thread-safe
    event keeps the worker responsive and behaves consistently in those
    environments. The Deepgram request itself retains its bounded timeout.
    """
    completed = threading.Event()
    result: list[Any] = []
    error: list[BaseException] = []

    def invoke() -> None:
        try:
            result.append(function(*args))
        except BaseException as exc:
            error.append(exc)
        finally:
            completed.set()

    threading.Thread(target=invoke, name="media-sdk-call", daemon=True).start()
    while not completed.is_set():
        await asyncio.sleep(.01)
    if error:
        raise error[0]
    return result[0]
