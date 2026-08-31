"""Explicit, bounded live-test gate. Never imported or invoked by closed tests."""

from __future__ import annotations

import asyncio
import os
import traceback

from pydantic import ValidationError

from apps.api.app.core.config import AppMode, Settings
from apps.api.app.db.models import OutlierResult
from apps.api.app.db.session import Database
from apps.api.app.domain.contracts import ResearchLimits, ResearchRunCreate
from apps.api.app.domain.enums import RequestedFormat
from apps.api.app.reports.engine import ReportEngine
from apps.api.app.research.orchestrator import ResearchOrchestrator
from apps.api.app.repositories.store import ResearchRepository
from apps.api.app.services.factory import create_orchestrator


def _quota_line(label: str, orchestrator: ResearchOrchestrator) -> None:
    quota = orchestrator.quota.status()
    print(
        f"quota {label}: used_search_calls={quota.used_search_calls}, "
        f"remaining_search_calls={quota.remaining_search_calls}, reserve={quota.reserved_search_calls}"
        f", used_units={quota.used_units}, remaining_units={quota.remaining_units}"
    )


def _failure_class(exc: Exception) -> str:
    message = str(exc).lower()
    if isinstance(exc, ValidationError) or "required" in message or "config" in message:
        return "credentials/configuration"
    if "quota" in message or "429" in message:
        return "quota"
    if "ollama" in message or "openrouter" in message or "structured" in message or "model" in message:
        return "AI provider"
    if "playwright" in message or "chromium" in message or "selector" in message or "no candidate videos" in message:
        return "source page change"
    if "youtube api" in message or "response" in message or "400" in message:
        return "API response change"
    if "network" in message or "connect" in message or "timeout" in message or "dns" in message:
        return "networking"
    return "application bug"


async def _run(settings: Settings) -> dict[str, object]:
    request = _build_smoke_request(settings)
    database = Database(settings)
    if settings.bootstrap_schema_on_startup:
        database.create_schema()
    repository = ResearchRepository(database.session())
    orchestrator = create_orchestrator(settings, repository)
    run = repository.create_run(request)
    run.configuration = {
        **run.configuration,
        "fixture_mode": False,
        "live_smoke": True,
        "metadata_source": settings.metadata_source,
    }
    repository.session.commit()
    _quota_line("before", orchestrator)
    await orchestrator.execute(run, request)
    _quota_line("after", orchestrator)
    report = ReportEngine(repository).build(run.id)
    outlier_count = repository.session.query(OutlierResult).filter_by(research_run_id=run.id).count()
    summary = report["evidence_summary"]
    if run.status != "complete" or not report["candidates"]:
        raise RuntimeError("bounded live run did not produce a completed niche report")
    if summary["browser_observations"] < 1 or summary["api_observations"] < 1:
        raise RuntimeError("browser and structured metadata records were not both exposed through the evidence ledger")
    if summary["videos_examined"] < 1 or summary["channels_examined"] < 1:
        raise RuntimeError("API/browser records did not merge into canonical video and channel IDs")
    if outlier_count < 1:
        raise RuntimeError("outlier analytics did not execute")
    return {
        "run_id": run.id,
        "videos": summary["videos_examined"],
        "channels": summary["channels_examined"],
        "browser_observations": summary["browser_observations"],
        "api_observations": summary["api_observations"],
        "outliers_calculated": outlier_count,
        "candidates": len(report["candidates"]),
        "ai_provider": orchestrator.ai.name,
    }


def _build_smoke_request(settings: Settings) -> ResearchRunCreate:
    """Build the bounded smoke request without weakening production gates."""
    seeds = [seed.strip() for seed in os.getenv("LIVE_SMOKE_SEEDS", "visual science experiments").split(",") if seed.strip()][:2]
    requested_format = RequestedFormat(os.getenv("LIVE_SMOKE_FORMAT", RequestedFormat.BOTH.value))
    return ResearchRunCreate(
        requested_format=requested_format,
        seeds=seeds,
        recency_days=90,
        minimum_clip_coverage=.7,
        limits=ResearchLimits(
            max_queries=max(1, len(seeds)),
            max_results_per_query=8,
            max_channels=10,
            max_videos=20,
            max_expansion_depth=1,
            deep_research=False,
        ),
    )


def main() -> int:
    try:
        settings = Settings.from_env()
    except Exception as exc:
        print(f"LIVE TEST FAIL [{_failure_class(exc)}]: {exc}")
        return 2
    if settings.app_mode != AppMode.LIVE_TEST:
        print("LIVE TEST BLOCKED: set APP_MODE=live_test explicitly")
        return 2
    if settings.openrouter_api_key:
        print(f"AI provider selection: OpenRouter preferred ({settings.openrouter_model})")
    elif settings.ollama_model:
        print(f"AI provider selection: Ollama fallback ({settings.ollama_model})")
    else:
        print("AI provider selection: fake fallback (configure OPENROUTER_API_KEY or OLLAMA_MODEL for live AI)")
    if settings.youtube_api_key:
        print("YouTube metadata: Data API configured")
    else:
        print("YouTube metadata: keyless Chromium + yt-dlp mode")
    if settings.pexels_api_key or settings.pixabay_api_key:
        print("clip preflight: configured live rights-aware provider")
    else:
        print("clip preflight: keyless Wikimedia Commons web search (Pexels/Pixabay keys add coverage)")
    if settings.deepgram_api_key:
        print(f"video transcription: Deepgram {settings.deepgram_model}")
    else:
        print("video transcription: browser-visible transcripts only (set DEEPGRAM_API_KEY for full STT)")
    if settings.external_trends_url:
        print("external trend corroboration: configured (maximum 15% weight)")
    else:
        print("external trend corroboration: omitted; YouTube-only trend score will be used")
    print("live prerequisites accepted")
    print(f"limits: <={settings.browser_max_tabs} isolated browser profiles, <=2 queries, <=10 channels, <=20 videos, deep_research=false")
    try:
        result = asyncio.run(_run(settings))
    except Exception as exc:
        print(f"LIVE TEST FAIL [{_failure_class(exc)}]: {exc}")
        if os.getenv("LIVE_SMOKE_DEBUG", "false").lower() in {"1", "true", "yes"}:
            traceback.print_exc()
        return 1
    print("live smoke summary: PASS")
    for key, value in result.items():
        print(f" - {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
