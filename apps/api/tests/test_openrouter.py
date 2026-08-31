import asyncio
import base64
import json

from apps.api.app.ai.deterministic_live import DeterministicLiveAIProvider, _image_observation
from apps.api.app.ai.fake import FakeAIProvider
from apps.api.app.ai.openrouter import OpenRouterProvider
from apps.api.app.sources.assets import AssetResult, calculate_clip_ceiling
from apps.api.app.core.config import AppMode, Settings
from apps.api.app.services import factory
from apps.api.app.services.factory import create_ai_provider


def _live_settings(**overrides):
    values = {
        "app_mode": AppMode.LIVE_TEST,
        "youtube_api_key": "fixture-key",
        "browser_enabled": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_closed_mode_never_constructs_openrouter():
    settings = Settings(
        app_mode=AppMode.CLOSED_TEST,
        ai_provider="auto",
        openrouter_api_key="not-used",
        openrouter_model="openrouter/free",
    )
    assert isinstance(create_ai_provider(settings), FakeAIProvider)
    assert settings.ai_provider == "fake"


def test_auto_prefers_configured_openrouter(monkeypatch):
    class StubOpenRouter:
        name = "openrouter"

    monkeypatch.setattr(factory, "_openrouter_sdk_available", lambda: True)
    monkeypatch.setattr(factory, "OpenRouterProvider", lambda **kwargs: StubOpenRouter())
    settings = _live_settings(
        ai_provider="auto",
        openrouter_api_key="fixture-openrouter-key",
        openrouter_model="openrouter/free",
        ollama_model="llama3.2",
    )
    assert create_ai_provider(settings).name == "openrouter"


def test_auto_falls_back_to_ollama_without_openrouter(monkeypatch):
    monkeypatch.setattr(factory, "_openrouter_sdk_available", lambda: False)
    settings = _live_settings(ai_provider="auto", ollama_model="llama3.2", ollama_max_retries=5)
    provider = create_ai_provider(settings)
    assert provider.name == "ollama"
    assert provider.max_retries == 5


def test_live_auto_falls_back_to_non_fixture_deterministic_provider(monkeypatch):
    monkeypatch.setattr(factory, "_openrouter_sdk_available", lambda: False)
    settings = _live_settings(ai_provider="auto", ollama_model=None)
    provider = create_ai_provider(settings)
    assert isinstance(provider, DeterministicLiveAIProvider)
    assert not isinstance(provider, FakeAIProvider)
    assert provider.supports_image_inputs is True
    assert provider.supports_semantic_image_validation is False


def test_explicit_deterministic_live_provider_is_strict_and_zero_key():
    provider = create_ai_provider(_live_settings(ai_provider="deterministic", ollama_model=None))
    assert isinstance(provider, DeterministicLiveAIProvider)


def test_deterministic_live_visual_validation_reads_real_image_bytes(tmp_path):
    image = tmp_path / "observed.png"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    result = asyncio.run(DeterministicLiveAIProvider().analyze_visuals(
        "exact-query paper bridge asset evidence", [str(image)], []
    ))
    assert result.confidence < .45
    assert "parsed" in result.hook_visual
    assert "semantic" in result.uncertainty.lower()
    assert "cannot be verified" in result.reveal_pattern.lower()


def test_deterministic_live_image_structure_cannot_pass_semantic_or_reveal_gate(tmp_path):
    image = tmp_path / "unrelated.png"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))

    class Connector:
        async def search(self, ideas):
            return [AssetResult(
                ideas[0], 5, 0, ["source-a", "source-b"], True, True, 3, 3,
                [{"preview_ref": str(image)}], True, .95,
            )]

    result = asyncio.run(calculate_clip_ceiling(
        ["paper bridge supporting a mug"],
        Connector(),
        visual_validator=DeterministicLiveAIProvider(),
    ))
    assert result["validated_count"] == 0
    assert result["semantic_fit_share"] == 0
    assert result["reveal_coverage"] == 0
    assert "cannot establish semantic" in result["results"][0]["semantic_fit_reason"]


def test_deterministic_live_critic_reads_nested_candidate_packet_gates():
    provider = DeterministicLiveAIProvider()
    passing = asyncio.run(provider.critique(json.dumps({
        "candidate_packet": {
            "deterministic_decision": {"hard_gates": {"all_passed": True}},
        },
        "editor_synthesis": {"executive_summary": "bounded fixture"},
    }), ["evidence-1"]))
    failing = asyncio.run(provider.critique(json.dumps({
        "candidate_packet": {
            "deterministic_decision": {"hard_gates": {"all_passed": False}},
        },
    }), ["evidence-1"]))
    assert passing.blocking_issues == []
    assert failing.blocking_issues == ["One or more deterministic recommendation gates did not pass."]


def test_deterministic_live_rejects_magic_only_jpeg_and_webp():
    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10" + (b"\x00" * 20) + b"\xff\xd9"
    fake_webp = b"RIFF" + (18).to_bytes(4, "little") + b"WEBPVP8L" + (5).to_bytes(4, "little") + b"\x2f\x00\x00\x00\x00\x00"
    assert _image_observation(fake_jpeg) is None
    assert _image_observation(fake_webp) is None


def test_openrouter_provider_uses_structured_schema_without_network():
    captured = {}

    class FakeChat:
        async def send_async(self, **request):
            captured.update(request)
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"broad_market":"Education","niche":"Tests","sub_niche":"Household","repeatable_format":"Proof","confidence":0.8}'
                        }
                    }
                ]
            }

    class FakeClient:
        chat = FakeChat()

    provider = OpenRouterProvider(api_key="fixture-key", client=FakeClient())
    result = asyncio.run(provider.classify_niche("fixture evidence", ["evidence-1"]))

    assert result.niche == "Tests"
    assert captured["model"] == "openrouter/free"
    assert captured["stream"] is False
    assert captured["timeout_ms"] == 300000
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["provider"]["require_parameters"] is True


def test_openrouter_visual_analysis_sends_local_frames_as_data_urls(tmp_path):
    captured = {}

    class FakeChat:
        async def send_async(self, **request):
            captured.update(request)
            return {"choices": [{"message": {"content": '{"hook_visual":"proof first","composition_pattern":"single object","caption_pattern":"large labels","pacing_pattern":"fast attempts","reveal_pattern":"held proof","observable_features":["vertical"],"uncertainty":"single frame","confidence":0.7}'}}]}

    class FakeClient:
        chat = FakeChat()

    frame = tmp_path / "frame.png"
    frame.write_bytes(b"fixture-image")
    provider = OpenRouterProvider(api_key="fixture-key", client=FakeClient())
    result = asyncio.run(provider.analyze_visuals("observable context", [str(frame)], ["evidence-1"]))
    assert result.hook_visual == "proof first"
    content = captured["messages"][1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_explicit_openrouter_does_not_fall_through_to_another_provider(monkeypatch):
    monkeypatch.setattr(factory, "_openrouter_sdk_available", lambda: False)
    settings = _live_settings(ai_provider="openrouter", openrouter_api_key="key", ollama_model="llama3.2")
    import pytest
    with pytest.raises(RuntimeError, match="no runtime provider failover"):
        create_ai_provider(settings)


def test_openrouter_retries_transient_failure_then_returns_structured_output():
    class FakeChat:
        calls = 0
        async def send_async(self, **request):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("429 rate limit")
            return {"choices": [{"message": {"content": '{"broad_market":"Education","niche":"Tests","sub_niche":"Household","repeatable_format":"Proof","confidence":0.8}'}}]}

    class FakeClient:
        chat = FakeChat()

    provider = OpenRouterProvider(api_key="fixture-key", client=FakeClient(), max_retries=1)
    assert asyncio.run(provider.classify_niche("evidence", [])).niche == "Tests"
    assert FakeClient.chat.calls == 2


def test_openrouter_normalizes_provider_idea_array_without_losing_fields():
    class FakeChat:
        async def send_async(self, **request):
            return {"choices": [{"message": {"content": json.dumps([
                {"idea": "Monthly emotional story", "repeatable_format": "narrated arc", "series_suggestion": "One per month"},
                {"title": "Unexpected reunion", "format": "narrated arc"},
            ])}}]}

    class FakeClient:
        chat = FakeChat()

    provider = OpenRouterProvider(api_key="fixture-key", client=FakeClient())
    result = asyncio.run(provider.generate_ideas("storytelling evidence", []))
    assert result.ideas == ["Monthly emotional story", "Unexpected reunion"]
    assert result.repeatable_formats == ["narrated arc"]
    assert result.series_suggestions == ["One per month"]


def test_openrouter_structured_request_has_one_total_deadline():
    class FakeChat:
        async def send_async(self, **request):  # noqa: ARG002
            await asyncio.Event().wait()

    class FakeClient:
        chat = FakeChat()

    provider = OpenRouterProvider(
        api_key="fixture-key",
        client=FakeClient(),
        max_retries=8,
        request_timeout_seconds=.01,
    )
    import pytest
    with pytest.raises(RuntimeError, match="total deadline"):
        asyncio.run(provider.classify_niche("evidence", []))
