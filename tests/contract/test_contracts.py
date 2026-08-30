import pytest
from pydantic import ValidationError

from apps.api.app.domain.contracts import (
    ChannelAnalysisRequest,
    MAX_SEED_COUNT,
    MAX_SEED_LENGTH,
    ResearchLimits,
    ResearchRunCreate,
    VideoAnalysisRequest,
)


def test_shared_contracts_normalize_seeds_and_limits():
    payload = ResearchRunCreate(seeds=[" paper bridge ", "paper bridge", ""])
    assert payload.seeds == ["paper bridge"]
    assert ResearchLimits(max_queries=2).max_queries == 2


def test_seed_work_is_bounded_before_normalization_and_planning():
    with pytest.raises(ValidationError):
        ResearchRunCreate(seeds=["duplicate"] * (MAX_SEED_COUNT + 1))
    with pytest.raises(ValidationError):
        ResearchRunCreate(seeds=["x" * (MAX_SEED_LENGTH + 1)])


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc123",
        "https://www.youtube.com/shorts/abc123",
        "https://youtu.be/abc123",
    ],
)
def test_video_analysis_accepts_only_direct_youtube_video_urls(url):
    assert VideoAnalysisRequest(url=f" {url} ").url == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "https://example.com/watch?v=abc123",
        "http://www.youtube.com/watch?v=abc123",
        "https://www.youtube.com/@channel",
        "https://www.youtube.com/results?search_query=paper",
    ],
)
def test_video_analysis_rejects_blank_external_and_wrong_resource_urls(url):
    with pytest.raises(ValidationError):
        VideoAnalysisRequest(url=url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/@example",
        "https://www.youtube.com/@example/videos?view=0",
        "https://www.youtube.com/channel/channel-a",
        "https://www.youtube.com/c/example",
        "https://www.youtube.com/user/example",
    ],
)
def test_channel_analysis_accepts_only_direct_youtube_channel_urls(url):
    assert ChannelAnalysisRequest(url=f" {url} ").url == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://example.com/@channel",
        "https://www.youtube.com/watch?v=abc123",
        "https://youtu.be/abc123",
        "https://www.youtube.com/@channel/about",
    ],
)
def test_channel_analysis_rejects_blank_external_and_wrong_resource_urls(url):
    with pytest.raises(ValidationError):
        ChannelAnalysisRequest(url=url)
