import asyncio

import httpx
import respx

from apps.api.app.ai.fake import FakeAIProvider
from apps.api.app.ai.ollama import OllamaProvider
from apps.api.app.core.config import AppMode, Settings
from apps.api.app.domain.enums import SourceType
from apps.api.app.services.health import collect_source_health


def _by_source(items):
    return {item.source: item for item in items}


def test_live_health_does_not_mark_missing_executables_or_unverified_credentials_green():
    missing = Settings(
        app_mode=AppMode.LIVE_TEST,
        browser_executable_path="/missing/chromium",
        ytdlp_executable="missing-yt-dlp-health-test",
    )
    status = _by_source(asyncio.run(collect_source_health(missing, FakeAIProvider())))
    assert status[SourceType.BROWSER].healthy is False
    assert status[SourceType.KEYLESS_YTDLP].healthy is False
    assert SourceType.YOUTUBE_API not in status

    api_configured = Settings(
        app_mode=AppMode.LIVE_TEST,
        browser_executable_path="/missing/chromium",
        youtube_api_key="unverified-key",
    )
    status = _by_source(asyncio.run(collect_source_health(api_configured, FakeAIProvider())))
    assert status[SourceType.YOUTUBE_API].healthy is None
    assert "unverified" in status[SourceType.YOUTUBE_API].detail


def test_keyless_health_uses_distinct_provenance_label(monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.services.health.shutil.which",
        lambda executable: "/usr/local/bin/yt-dlp" if executable == "yt-dlp" else None,
    )
    settings = Settings(
        app_mode=AppMode.LIVE_TEST,
        browser_executable_path="/missing/chromium",
    )
    status = _by_source(asyncio.run(collect_source_health(settings, FakeAIProvider())))
    assert status[SourceType.KEYLESS_YTDLP].healthy is True
    assert "Keyless yt-dlp" in status[SourceType.KEYLESS_YTDLP].detail
    assert SourceType.YOUTUBE_API not in status


def test_ollama_health_probes_reachability_and_configured_model():
    settings = Settings(
        app_mode=AppMode.LIVE_TEST,
        ai_provider="ollama",
        ollama_base_url="http://ollama.health",
        ollama_model="llama3.2",
    )
    provider = OllamaProvider(settings.ollama_base_url, settings.ollama_model)
    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://ollama.health/api/tags").mock(
            return_value=httpx.Response(200, json={"models": [{"name": "llama3.2:latest"}]})
        )
        status = _by_source(asyncio.run(collect_source_health(settings, provider)))
    assert status[SourceType.AI].healthy is True

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://ollama.health/api/tags").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        status = _by_source(asyncio.run(collect_source_health(settings, provider)))
    assert status[SourceType.AI].healthy is False
    assert "probe failed" in status[SourceType.AI].detail


def test_closed_health_is_local_and_deterministically_healthy():
    settings = Settings(app_mode=AppMode.CLOSED_TEST)
    status = asyncio.run(collect_source_health(settings, FakeAIProvider()))
    assert [item.source for item in status[:2]] == [SourceType.FIXTURE_BROWSER, SourceType.FIXTURE_API]
    assert all(item.healthy is True for item in status)
