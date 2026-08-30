from __future__ import annotations

from dataclasses import dataclass

from ..core.config import AppMode
from ..core.errors import ErrorCode, NicheIntelError
from ..domain.enums import SourceType
from .quota import QuotaManager


@dataclass(frozen=True)
class RoutingTask:
    task_type: str
    known_id: bool = False
    visual_context_required: bool = False
    exact_verification: bool = False
    reproducible: bool = False


@dataclass(frozen=True)
class RoutingDecision:
    source: SourceType
    reason: str
    quota_delta: int = 0


class SourceRouter:
    def __init__(self, mode: AppMode, quota: QuotaManager, browser_healthy: bool = True, api_healthy: bool = True) -> None:
        self.mode = mode
        self.quota = quota
        self.browser_healthy = browser_healthy
        self.api_healthy = api_healthy

    def update_health(self, *, browser_healthy: bool, api_healthy: bool) -> None:
        self.browser_healthy = bool(browser_healthy)
        self.api_healthy = bool(api_healthy)

    def route(self, task: RoutingTask) -> RoutingDecision:
        if self.mode in {AppMode.DEVELOPMENT, AppMode.CLOSED_TEST}:
            if task.known_id and not task.visual_context_required:
                return RoutingDecision(SourceType.FIXTURE_API, "fixture-backed mode: known ID uses fixture API")
            return RoutingDecision(SourceType.FIXTURE_BROWSER, "fixture-backed mode: reproducible browser fixture")
        if task.visual_context_required:
            if self.browser_healthy:
                return RoutingDecision(SourceType.BROWSER, "visual/page context required")
            if self.api_healthy:
                return RoutingDecision(SourceType.YOUTUBE_API, "browser unhealthy; structured fallback")
            raise NicheIntelError("browser and YouTube API capabilities are unavailable", ErrorCode.SOURCE_UNAVAILABLE)
        if task.known_id or task.exact_verification:
            if self.api_healthy:
                return RoutingDecision(SourceType.YOUTUBE_API, "known ID or exact verification uses API", 0)
            if self.browser_healthy:
                return RoutingDecision(SourceType.BROWSER, "API unhealthy; browser fallback")
            raise NicheIntelError("browser and YouTube API capabilities are unavailable", ErrorCode.SOURCE_UNAVAILABLE)
        if self.browser_healthy:
            return RoutingDecision(SourceType.BROWSER, "open discovery preserves API search budget")
        if self.api_healthy and self.quota.can_search():
            return RoutingDecision(SourceType.YOUTUBE_API, "browser unavailable; API discovery", 1)
        if self.api_healthy:
            raise NicheIntelError("YouTube API reserve reached and browser is unavailable", ErrorCode.QUOTA_EXHAUSTED)
        raise NicheIntelError("browser and YouTube API capabilities are unavailable", ErrorCode.SOURCE_UNAVAILABLE)
