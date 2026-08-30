import asyncio

import httpx
import respx

from apps.api.app.core.config import AppMode
from apps.api.app.ai.schemas import VisualStructureAnalysis
from apps.api.app.sources.assets import AssetResult, AssetRunSession, LiveAssetConnector, calculate_clip_ceiling
from apps.api.app.sources.trends import HttpTrendConnector


def test_asset_provider_failure_preserves_other_provider_results():
    commons_payload = {
        "query": {
            "pages": {
                str(index): {
                    "pageid": index,
                    "imageinfo": [{
                        "mime": "video/webm",
                        "descriptionurl": f"https://commons.test/{index}",
                        "thumburl": f"https://commons.test/{index}.jpg",
                        "extmetadata": {"LicenseShortName": {"value": "CC BY"}},
                    }],
                }
                for index in range(3)
            }
        }
    }
    archive_payload = {
        "response": {
            "docs": [
                {"identifier": f"clip-{index}", "licenseurl": "https://license.test/public-domain"}
                for index in range(3)
            ]
        }
    }
    connector = LiveAssetConnector(AppMode.LIVE_TEST, pexels_api_key="invalid")
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.pexels.com/videos/search").mock(return_value=httpx.Response(401))
        mock.get("https://commons.wikimedia.org/w/api.php").mock(
            return_value=httpx.Response(200, json=commons_payload)
        )
        mock.get("https://archive.org/advancedsearch.php").mock(
            return_value=httpx.Response(200, json=archive_payload)
        )
        result = asyncio.run(connector.search(["paper bridge"]))[0]

    assert result.video_count == 6
    assert result.sources == ["internet_archive_web_search", "wikimedia_commons_web_search"]
    assert result.visual_payoff_feasible is False
    assert result.reveal_clip_count == 0
    assert result.provider_errors == [{
        "provider": "pexels",
        "status": "unavailable",
        "error_type": "HTTPStatusError",
        "status_code": 401,
        "reason": "provider returned a non-success status",
    }]


def test_asset_search_hard_caps_ideas_and_bounds_concurrency(monkeypatch):
    connector = LiveAssetConnector(AppMode.LIVE_TEST, max_ideas=30, max_concurrency=3)
    active = 0
    maximum_active = 0

    async def fake_search(idea, client):  # noqa: ARG001
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0)
        active -= 1
        from apps.api.app.sources.assets import AssetResult
        return AssetResult(idea, 0, 0, [], False, False)

    monkeypatch.setattr(connector, "_search_one", fake_search)
    result = asyncio.run(connector.search([f"idea {index}" for index in range(100)]))
    assert len(result) == 30
    assert maximum_active == 3

    ceiling = asyncio.run(calculate_clip_ceiling([f"idea {index}" for index in range(100)], connector))
    assert ceiling["search_bounds"] == {
        "requested_ideas": 100,
        "searched_ideas": 30,
        "evaluated_ideas": 30,
        "deferred_ideas": 0,
        "maximum_ideas": 30,
        "truncated": True,
        "maximum_concurrency": 3,
        "phase": "final",
        "maximum_new_ideas": None,
        "run_budget": None,
    }


def test_asset_idea_budget_is_shared_across_every_search_in_one_run():
    class Connector:
        max_concurrency = 2

        def __init__(self):
            self.calls = []

        async def search(self, ideas):
            self.calls.append(list(ideas))
            return [AssetResult(idea, 3, 0, ["one", "two"], True, False) for idea in ideas]

    connector = Connector()
    session = AssetRunSession(connector, maximum_ideas=3)
    asyncio.run(session.search(["idea a", "idea b"]))
    second = asyncio.run(session.search(["idea b", "idea c", "idea d", "idea e"]))
    assert connector.calls == [["idea a", "idea b"], ["idea c"]]
    assert session.budget_status() == {
        "maximum_ideas": 3,
        "claimed_ideas": 3,
        "remaining_ideas": 0,
        "preflight_capacity": 0,
        "preflight_claimed_ideas": 0,
        "final_reserved_ideas": 3,
    }
    assert [item.video_count for item in second] == [3, 3, 0, 0]
    assert "budget unavailable" in second[-1].provider_errors[0]["reason"]


def test_asset_preflight_cannot_consume_final_reserve_or_permanently_reject_ideas():
    class Connector:
        max_concurrency = 2

        def __init__(self):
            self.calls = []

        async def search(self, ideas):
            self.calls.append(list(ideas))
            return [AssetResult(idea, 3, 0, ["one", "two"], True, False) for idea in ideas]

    connector = Connector()
    session = AssetRunSession(connector, maximum_ideas=6, final_reserve=3)
    first = asyncio.run(session.search(
        ["idea a", "idea b", "idea c", "idea d"],
        phase="preflight",
        maximum_new_ideas=2,
    ))
    second = asyncio.run(session.search(
        ["idea c", "idea d"], phase="preflight", maximum_new_ideas=2
    ))
    final = asyncio.run(session.search(
        ["idea d", "idea e", "idea f"], phase="final", maximum_new_ideas=3
    ))

    assert connector.calls == [
        ["idea a", "idea b"],
        ["idea c"],
        ["idea d", "idea e", "idea f"],
    ]
    assert first[-1].video_count == 0
    assert second[-1].video_count == 0
    assert [result.video_count for result in final] == [3, 3, 3]
    assert session.budget_status()["remaining_ideas"] == 0


def test_authoritative_final_budget_is_independent_for_each_candidate():
    class Connector:
        def __init__(self):
            self.calls = []

        async def search(self, ideas):
            self.calls.append(list(ideas))
            return [AssetResult(
                idea, 3, 0, ["one", "two"], True, True,
                reveal_clip_count=1, semantic_fit=True,
            ) for idea in ideas]

    connector = Connector()
    ideas = [f"idea {index}" for index in range(10)]
    candidates = []
    for _ in range(2):
        session = AssetRunSession.for_final_candidate(connector, maximum_ideas=10)
        candidates.append(asyncio.run(calculate_clip_ceiling(
            ideas,
            session,
            phase="final",
            maximum_new_ideas=10,
        )))

    assert [len(call) for call in connector.calls] == [10, 10]
    assert [candidate["validated_count"] for candidate in candidates] == [10, 10]
    assert all(candidate["search_bounds"]["deferred_ideas"] == 0 for candidate in candidates)


def test_reveal_gate_requires_image_capable_observation_not_clip_count():
    class Connector:
        async def search(self, ideas):
            return [AssetResult(
                ideas[0], 6, 0, ["one", "two"], True, False, 0, 4,
                [{"preview_ref": "https://assets.test/preview.png"}],
            )]

    class Validator:
        supports_image_inputs = True
        supports_semantic_image_validation = True

        async def analyze_visuals(self, context, frame_refs, evidence_ids):  # noqa: ARG002
            return VisualStructureAnalysis(
                hook_visual="paper bridge supporting a mug",
                composition_pattern="bridge centered beneath the load",
                caption_pattern="none",
                pacing_pattern="single observed state",
                reveal_pattern="the final result is visibly held on screen",
                observable_features=["visible final state", "outcome shown"],
                uncertainty="one preview sequence",
                confidence=.9,
            )

    result = asyncio.run(calculate_clip_ceiling(["paper bridge"], Connector(), visual_validator=Validator()))
    assert result["validated_count"] == 1
    assert result["reveal_coverage"] == 1
    assert result["results"][0]["reveal_validation_confidence"] == .9


def test_trend_bridge_http_failure_is_typed_unavailable_corroboration():
    connector = HttpTrendConnector(AppMode.LIVE_TEST, "https://trends.test/assess")
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://trends.test/assess").mock(return_value=httpx.Response(503))
        result = asyncio.run(connector.assess(["paper bridge"], ["US"], 90))
    assert result["enabled"] is True
    assert result["status"] == "unavailable"
    assert result["score"] is None
    assert result["weight"] == 0
    assert result["error"] == {"type": "HTTPStatusError", "status_code": 503}


def test_trend_bridge_malformed_payload_is_typed_unavailable_corroboration():
    connector = HttpTrendConnector(AppMode.LIVE_TEST, "https://trends.test/assess")
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://trends.test/assess").mock(
            return_value=httpx.Response(200, json={"score": "not-a-number"})
        )
        result = asyncio.run(connector.assess(["paper bridge"], ["US"], 90))
    assert result["status"] == "unavailable"
    assert result["score"] is None
    assert result["observations"] == []
