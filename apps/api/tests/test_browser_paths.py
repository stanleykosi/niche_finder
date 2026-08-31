from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import asyncio
import pytest

from apps.api.app.core.config import AppMode, Settings
from apps.api.app.core.errors import ErrorCode, NicheIntelError
from apps.api.app.sources.base import DiscoveryRequest
from apps.api.app.sources.browser import (
    VIDEO_CARD_CONTAINER_XPATH,
    VIDEO_CARD_SELECTOR,
    PlaywrightBrowserSource,
    _direct_video_id,
    _discovery_target,
    _prepare_search_results,
    _safe_name,
)


def test_direct_video_and_channel_inputs_are_navigated_without_search_encoding():
    video_url = "https://www.youtube.com/watch?v=abc123"
    shorts_url = "https://www.youtube.com/shorts/short123"
    channel_url = "https://www.youtube.com/@example"
    assert _discovery_target(video_url, "both") == (video_url, "video")
    assert _discovery_target(shorts_url, "shorts") == (shorts_url, "video")
    assert _discovery_target(channel_url, "both") == (channel_url + "/videos", "channel")
    assert _direct_video_id(video_url) == "abc123"
    assert _direct_video_id(shorts_url) == "short123"


def test_channel_videos_path_is_inserted_before_query_parameters():
    target, kind = _discovery_target(
        "https://www.youtube.com/@example?sub_confirmation=1", "both"
    )
    parsed = urlparse(target)
    assert kind == "channel"
    assert parsed.path == "/@example/videos"
    assert parse_qs(parsed.query) == {"sub_confirmation": ["1"]}


def test_browser_search_target_applies_locale_region_and_requested_recency():
    target, kind = _discovery_target(
        "paper bridge",
        "shorts",
        language="en",
        region="NG",
        recency_days=30,
        observed_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )
    params = parse_qs(urlparse(target).query)
    assert kind is None
    assert params["hl"] == ["en"]
    assert params["gl"] == ["NG"]
    assert params["search_query"] == ["paper bridge shorts after:2026-07-26"]


def test_disabled_production_browser_constructs_for_api_routing_but_cannot_navigate():
    source = PlaywrightBrowserSource(Settings(app_mode=AppMode.PRODUCTION, browser_enabled=False))
    with pytest.raises(NicheIntelError) as raised:
        asyncio.run(source.discover(DiscoveryRequest("paper bridge")))
    assert raised.value.code == ErrorCode.SOURCE_UNAVAILABLE


def test_screenshot_name_is_flat_safe_and_stable_for_urls():
    value = _safe_name("https://www.youtube.com/watch?v=abc/../../unsafe")
    assert "/" not in value
    assert "\\" not in value
    assert value == _safe_name("https://www.youtube.com/watch?v=abc/../../unsafe")
    assert len(value) <= 43


def test_channel_grid_renderers_are_included_in_video_card_extraction():
    assert "ytd-rich-item-renderer a#video-title-link" in VIDEO_CARD_SELECTOR
    assert "ytd-grid-video-renderer a#video-title" in VIDEO_CARD_SELECTOR
    assert "ancestor::ytd-rich-item-renderer" in VIDEO_CARD_CONTAINER_XPATH
    assert "ancestor::ytd-grid-video-renderer" in VIDEO_CARD_CONTAINER_XPATH


def test_browser_rejects_optional_consent_and_waits_for_card_hydration():
    events = []

    class Locator:
        def __init__(self, kind):
            self.kind = kind

        @property
        def first(self):
            return self

        def get_by_role(self, role, name):
            assert role == "button"
            assert name.search("Reject all")
            return Locator("reject")

        async def count(self):
            return 1

        async def click(self, timeout):
            events.append(("reject", timeout))

        async def wait_for(self, state, timeout):
            events.append((self.kind, state, timeout))

    class Page:
        def locator(self, selector):
            return Locator("consent" if "consent" in selector else "results")

    assert asyncio.run(_prepare_search_results(Page())) is True
    assert events[0] == ("consent", "attached", 750)
    assert ("reject", 2000) in events
    assert events[-1] == ("results", "attached", 5000)
