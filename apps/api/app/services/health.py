"""Truthful, bounded capability checks for the operator source-health view."""

from __future__ import annotations

import importlib.util
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..core.config import Settings
from ..domain.contracts import SourceHealth
from ..domain.enums import SourceType


async def collect_source_health(settings: Settings, ai_provider: Any) -> list[SourceHealth]:
    observed_at = datetime.now(timezone.utc)
    if settings.uses_fixture_sources:
        browser = SourceHealth(
            source=SourceType.FIXTURE_BROWSER,
            healthy=True,
            mode=settings.app_mode.value,
            detail="Bounded local fixture browser source is configured",
            last_checked_at=observed_at,
        )
        youtube = SourceHealth(
            source=SourceType.FIXTURE_API,
            healthy=True,
            mode=settings.app_mode.value,
            detail="Local fixture enrichment payloads are configured",
            last_checked_at=observed_at,
        )
    else:
        browser_ok, browser_detail = _browser_capability(settings)
        browser = SourceHealth(
            source=SourceType.BROWSER,
            healthy=browser_ok,
            mode=settings.app_mode.value,
            detail=browser_detail,
            last_checked_at=observed_at,
        )
        youtube_ok, youtube_detail = _youtube_capability(settings)
        youtube = SourceHealth(
            source=SourceType.YOUTUBE_API if settings.youtube_api_key else SourceType.KEYLESS_YTDLP,
            healthy=youtube_ok,
            mode=settings.app_mode.value,
            detail=youtube_detail,
            last_checked_at=observed_at,
        )
    ai_ok, ai_detail = await _ai_capability(settings, ai_provider)
    return [
        browser,
        youtube,
        SourceHealth(
            source=SourceType.AI,
            healthy=ai_ok,
            mode=settings.app_mode.value,
            detail=ai_detail,
            last_checked_at=observed_at,
        ),
    ]


def _browser_capability(settings: Settings) -> tuple[bool, str]:
    if not settings.browser_enabled:
        return False, "Chromium research is disabled by BROWSER_ENABLED"
    if importlib.util.find_spec("playwright") is None:
        return False, "Python Playwright is not installed"
    executable = _browser_executable(settings)
    if executable is None:
        return False, "No executable Chromium installation was found"
    return True, f"Chromium executable is available at {executable}"


def _browser_executable(settings: Settings) -> str | None:
    if settings.browser_executable_path:
        resolved = shutil.which(settings.browser_executable_path) or settings.browser_executable_path
        return resolved if _is_executable(resolved) else None
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        candidate = shutil.which(name)
        if candidate:
            return candidate
    roots = [
        Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")) if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else None,
        Path.home() / ".cache" / "ms-playwright",
    ]
    for root in (item for item in roots if item is not None and item.is_dir()):
        for pattern in ("chromium-*/chrome-linux*/chrome", "chromium_headless_shell-*/chrome-linux*/headless_shell"):
            for candidate in sorted(root.glob(pattern), reverse=True):
                if _is_executable(str(candidate)):
                    return str(candidate)
    return None


def _youtube_capability(settings: Settings) -> tuple[bool | None, str]:
    if settings.youtube_api_key:
        return None, "YouTube Data API is configured; credentials remain unverified until a bounded API request succeeds"
    executable = shutil.which(settings.ytdlp_executable)
    if executable is None:
        return False, f"Keyless metadata executable is unavailable: {settings.ytdlp_executable}"
    return True, f"Keyless yt-dlp metadata executable is available at {executable}"


async def _ai_capability(settings: Settings, provider: Any) -> tuple[bool | None, str]:
    name = str(getattr(provider, "name", "unknown"))
    if name == "fake":
        return True, "Deterministic local fake AI provider is active"
    if name == "deterministic_live":
        return True, "Evidence-driven deterministic zero-key provider is active; visual calls require decodable image inputs"
    if name == "openrouter":
        if not settings.openrouter_api_key or importlib.util.find_spec("openrouter") is None:
            return False, "OpenRouter configuration or SDK is unavailable"
        return None, "OpenRouter is configured; credentials remain unverified until a bounded model request succeeds"
    if name == "ollama":
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
                response.raise_for_status()
            available = [str(item.get("name") or item.get("model") or "") for item in response.json().get("models", [])]
            configured = settings.ollama_model or str(getattr(provider, "model", ""))
            if configured and not any(
                name == configured or name.removesuffix(":latest") == configured.removesuffix(":latest")
                for name in available
            ):
                return False, f"Ollama is reachable but configured model {configured!r} is not installed"
            return True, f"Ollama is reachable and model {configured!r} is installed"
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return False, f"Ollama health probe failed: {type(exc).__name__}"
    return False, f"Unknown AI provider capability: {name}"


def _is_executable(path: str) -> bool:
    candidate = Path(path)
    return candidate.is_file() and os.access(candidate, os.X_OK)
