import asyncio

from apps.api.app.sources.base import DiscoveryRequest
from apps.api.app.sources.fixture_browser import FixtureBrowserSource


def test_bounded_fixture_browser_flow():
    source = FixtureBrowserSource("strong")
    result = asyncio.run(source.discover(DiscoveryRequest("paper bridge", max_results=3)))
    assert len(result.results) == 3
    assert result.screenshot_refs[0].startswith("fixture://")
    media = asyncio.run(source.inspect_video(result.results[0].youtube_video_id))
    assert media.frame_refs
    assert "proof" in media.observable_structure
    assert asyncio.run(source.inspect_channel("ch-physics-lab"))["videos"]

