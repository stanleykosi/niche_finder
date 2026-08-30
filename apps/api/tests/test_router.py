import pytest

from apps.api.app.core.config import AppMode
from apps.api.app.core.errors import ErrorCode, NicheIntelError
from apps.api.app.domain.enums import SourceType
from apps.api.app.sources.quota import QuotaManager
from apps.api.app.sources.router import RoutingTask, SourceRouter


def test_closed_known_id_routes_fixture_api():
    decision = SourceRouter(AppMode.CLOSED_TEST, QuotaManager()).route(RoutingTask("video", known_id=True))
    assert decision.source == SourceType.FIXTURE_API


def test_visual_task_routes_browser_fixture():
    decision = SourceRouter(AppMode.CLOSED_TEST, QuotaManager()).route(RoutingTask("video", visual_context_required=True))
    assert decision.source == SourceType.FIXTURE_BROWSER


def test_development_routes_audit_the_fixture_adapters_it_constructs():
    router = SourceRouter(AppMode.DEVELOPMENT, QuotaManager())
    assert router.route(RoutingTask("discovery")).source == SourceType.FIXTURE_BROWSER
    assert router.route(RoutingTask("video", known_id=True)).source == SourceType.FIXTURE_API


def test_live_open_discovery_prefers_browser_until_reserve():
    router = SourceRouter(AppMode.LIVE_TEST, QuotaManager(10, 2))
    assert router.route(RoutingTask("discovery")).source == SourceType.BROWSER
    quota = QuotaManager(2, 1)
    quota.consume_search(reserve=True)
    assert SourceRouter(AppMode.LIVE_TEST, quota).route(RoutingTask("discovery")).source == SourceType.BROWSER


def test_live_discovery_uses_api_when_actual_browser_health_is_down():
    router = SourceRouter(AppMode.LIVE_TEST, QuotaManager(10, 2))
    router.update_health(browser_healthy=False, api_healthy=True)
    decision = router.route(RoutingTask("discovery"))
    assert decision.source == SourceType.YOUTUBE_API
    assert "browser unavailable" in decision.reason


def test_live_discovery_fails_typed_when_no_capability_exists():
    router = SourceRouter(AppMode.LIVE_TEST, QuotaManager(10, 2))
    router.update_health(browser_healthy=False, api_healthy=False)
    with pytest.raises(NicheIntelError) as raised:
        router.route(RoutingTask("discovery"))
    assert raised.value.code == ErrorCode.SOURCE_UNAVAILABLE
