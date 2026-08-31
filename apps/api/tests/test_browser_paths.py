from datetime import datetime, timezone
from pathlib import Path
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
    VIDEO_PAGE_HYDRATION_SELECTOR,
    VIDEO_PAGE_HYDRATION_TIMEOUT_MS,
    _direct_video_id,
    _discovery_target,
    _prepare_search_results,
    _prepare_video_page,
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


def test_browser_rejects_optional_consent_and_waits_for_video_hydration():
    events = []

    class Locator:
        @property
        def first(self):
            return self

        def get_by_role(self, role, name):
            assert role == "button"
            assert name.search("Reject all")
            return self

        async def count(self):
            return 0

        async def wait_for(self, state, timeout):
            events.append((state, timeout))

    class Page:
        def locator(self, selector):
            if selector == VIDEO_PAGE_HYDRATION_SELECTOR:
                events.append(("selector", selector))
            return Locator()

    assert asyncio.run(_prepare_video_page(Page())) is True
    assert ("selector", VIDEO_PAGE_HYDRATION_SELECTOR) in events
    assert events[-1] == ("attached", VIDEO_PAGE_HYDRATION_TIMEOUT_MS)


def test_video_inspection_uses_commit_navigation_and_bounded_frame_operations(tmp_path):
    events = []

    class Locator:
        def __init__(self, kind="generic"):
            self.kind = kind

        @property
        def first(self):
            return self

        def get_by_role(self, *args, **kwargs):  # noqa: ARG002
            return Locator("absent")

        async def count(self):
            return 1 if self.kind in {"video", "hydration"} else 0

        async def wait_for(self, state, timeout):
            events.append((self.kind, state, timeout))

        async def evaluate(self, expression, *args):
            if "Number.isFinite" in expression:
                return {"duration": 60, "width": 1280, "height": 720}
            events.append(("seek", args[0]))

    class Response:
        ok = True
        status = 200

    class Page:
        def set_default_timeout(self, timeout):
            events.append(("default", timeout))

        def set_default_navigation_timeout(self, timeout):
            events.append(("navigation_default", timeout))

        async def goto(self, url, wait_until, timeout):
            events.append(("goto", url, wait_until, timeout))
            return Response()

        def locator(self, selector):
            if selector == VIDEO_PAGE_HYDRATION_SELECTOR:
                return Locator("hydration")
            if selector == "video":
                return Locator("video")
            return Locator()

        def get_by_text(self, *args, **kwargs):  # noqa: ARG002
            return Locator()

        async def wait_for_timeout(self, timeout):
            events.append(("wait", timeout))

        async def screenshot(self, path, animations, timeout):
            events.append(("screenshot", Path(path).name, animations, timeout))

    class Context:
        async def new_page(self):
            return Page()

    source = PlaywrightBrowserSource(Settings(
        app_mode=AppMode.LIVE_TEST,
        browser_profile_root=str(tmp_path / "runtime" / "browser_profiles"),
    ))
    result = asyncio.run(source._inspect_video_context(
        Context(), "video-1", "https://www.youtube.com/watch?v=video-1", "profile", True
    ))

    assert ("goto", "https://www.youtube.com/watch?v=video-1", "commit", 15000) in events
    assert len(result.frame_refs) == 5
    assert result.visual_features["width"] == 1280
    assert all(event[-1] == 5000 for event in events if event[0] == "screenshot")
