from __future__ import annotations

import importlib.util
import logging

from ..ai.fake import FakeAIProvider
from ..ai.deterministic_live import DeterministicLiveAIProvider
from ..ai.openrouter import OpenRouterProvider
from ..ai.ollama import OllamaProvider
from ..ai.embeddings import DeterministicEmbeddingsProvider, FakeEmbeddingsProvider
from ..core.config import AppMode, Settings
from ..repositories.store import ResearchRepository
from ..sources.assets import FixtureAssetConnector, LiveAssetConnector
from ..sources.browser import PlaywrightBrowserSource
from ..sources.fixture_browser import FixtureBrowserSource
from ..sources.fixture_youtube import FixtureYoutubeSource
from ..sources.quota import QuotaManager
from ..sources.youtube_api import YouTubeDataApiSource
from ..sources.ytdlp_youtube import YtDlpYoutubeSource
from ..sources.media_analysis import DeepgramVideoAnalyzer, PassthroughMediaAnalyzer
from ..sources.trends import DisabledTrendConnector, HttpTrendConnector
from ..research.orchestrator import ResearchOrchestrator
from ..storage.artifacts import RuntimeArtifactManager
from .health import _browser_capability, _browser_executable

logger = logging.getLogger(__name__)


def _openrouter_sdk_available() -> bool:
    """Return whether the optional SDK is importable without making a request."""
    return importlib.util.find_spec("openrouter") is not None


def _provider_order(settings: Settings) -> list[str]:
    requested = settings.ai_provider.strip().lower()
    if requested == "fake":
        return ["fake"]
    if requested == "openrouter":
        return ["openrouter"]
    if requested == "ollama":
        return ["ollama"]
    if requested == "deterministic":
        return ["deterministic_live"]
    if requested == "auto":
        return ["openrouter", "ollama", "deterministic_live"]
    # Settings validates this at startup. Keep a defensive boundary here for
    # callers that may construct a settings-like object in integrations.
    raise ValueError(f"Unsupported AI provider: {settings.ai_provider!r}")


def create_ai_provider(settings: Settings):
    if settings.uses_fixture_sources:
        return FakeAIProvider()

    for provider_name in _provider_order(settings):
        try:
            if provider_name == "openrouter":
                if settings.openrouter_api_key and settings.openrouter_model and _openrouter_sdk_available():
                    return OpenRouterProvider(
                        api_key=settings.openrouter_api_key,
                        model=settings.openrouter_model,
                        vision_model=settings.openrouter_vision_model,
                        base_url=settings.openrouter_base_url,
                        http_referer=settings.openrouter_http_referer,
                        app_title=settings.openrouter_app_title,
                        max_retries=settings.openrouter_max_retries,
                        request_timeout_seconds=settings.openrouter_request_timeout_seconds,
                    )
            elif provider_name == "ollama":
                if settings.ollama_model:
                    return OllamaProvider(
                        settings.ollama_base_url,
                        settings.ollama_model,
                        max_retries=settings.ollama_max_retries,
                    )
            elif provider_name == "deterministic_live":
                return DeterministicLiveAIProvider()
            elif provider_name == "fake":
                return FakeAIProvider()
        except Exception as exc:  # startup auto-selection may inspect the next configured capability
            logger.warning("AI provider %s unavailable; trying the next provider: %s", provider_name, exc)

    raise RuntimeError(f"Configured AI provider {settings.ai_provider!r} is unavailable; no runtime provider failover was attempted")


def create_orchestrator(
    settings: Settings,
    repository: ResearchRepository,
    *,
    owns_runtime_storage: bool = True,
) -> ResearchOrchestrator:
    quota = QuotaManager(
        settings.youtube_api_daily_search_budget,
        settings.youtube_api_reserved_search_calls,
        settings.youtube_api_daily_unit_budget,
        settings.youtube_api_reserved_units,
        engine=repository.session.get_bind() if not settings.is_closed else None,
    )
    artifact_manager = RuntimeArtifactManager(
        settings,
        repository,
        storage_owner=owns_runtime_storage,
    )
    if settings.app_mode in {AppMode.LIVE_TEST, AppMode.PRODUCTION}:
        if not settings.browser_executable_path:
            settings.browser_executable_path = _browser_executable(settings)
        browser = PlaywrightBrowserSource(settings)
        youtube = YouTubeDataApiSource(settings.youtube_api_key, settings.app_mode, quota) if settings.youtube_api_key else YtDlpYoutubeSource(settings.ytdlp_executable)
        media_analyzer = DeepgramVideoAnalyzer(settings, artifact_manager)
        assets = LiveAssetConnector(
            settings.app_mode,
            settings.pexels_api_key,
            settings.pixabay_api_key,
            settings.wikimedia_user_agent,
            settings.asset_max_ideas_per_run,
            settings.asset_max_concurrency,
        )
        trends = HttpTrendConnector(settings.app_mode, settings.external_trends_url, settings.external_trends_api_key) if settings.external_trends_url else DisabledTrendConnector()
    else:
        browser = FixtureBrowserSource(settings.fixture_scenario)
        youtube = FixtureYoutubeSource(settings.fixture_scenario)
        assets = FixtureAssetConnector()
        trends = DisabledTrendConnector()
        media_analyzer = PassthroughMediaAnalyzer()
    embeddings = (
        FakeEmbeddingsProvider()
        if settings.uses_fixture_sources
        else DeterministicEmbeddingsProvider()
    )
    source_health = None
    if settings.app_mode in {AppMode.LIVE_TEST, AppMode.PRODUCTION}:
        source_health = lambda: (_browser_capability(settings)[0], bool(settings.youtube_api_key))
    return ResearchOrchestrator(
        settings, repository, create_ai_provider(settings), assets, browser, youtube,
        trends, quota, media_analyzer, artifact_manager, embeddings,
        source_health=source_health,
    )
