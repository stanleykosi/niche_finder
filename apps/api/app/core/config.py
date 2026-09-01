"""Typed runtime configuration and closed/live safety gates."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class AppMode(StrEnum):
    DEVELOPMENT = "development"
    CLOSED_TEST = "closed_test"
    LIVE_TEST = "live_test"
    PRODUCTION = "production"


class Settings(BaseModel):
    app_mode: AppMode = AppMode.DEVELOPMENT
    database_url: str = "sqlite:///./runtime/nicheintel.db"
    redis_url: str = "redis://localhost:6379/0"
    youtube_api_key: str | None = None
    youtube_api_daily_search_budget: int = Field(default=100, ge=0)
    youtube_api_reserved_search_calls: int = Field(default=20, ge=0)
    youtube_api_daily_unit_budget: int = Field(default=10000, ge=0)
    youtube_api_reserved_units: int = Field(default=500, ge=0)
    outlier_threshold: float = Field(default=3.0, ge=1.0, le=20.0)
    browser_enabled: bool = True
    browser_headless: bool = False
    browser_executable_path: str | None = None
    browser_profile_root: str = ".runtime/browser_profiles"
    browser_max_tabs: int = Field(default=4, ge=1, le=32)
    browser_max_queries_per_run: int = Field(default=20, ge=1, le=100)
    browser_max_results_per_query: int = Field(default=30, ge=1, le=100)
    browser_max_channels_per_run: int = Field(default=100, ge=1, le=500)
    # ``auto`` prefers a configured OpenRouter SDK/key, then Ollama, then the
    # evidence-driven deterministic live provider. Fixture modes use fake.
    ai_provider: str = "auto"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/free"
    openrouter_vision_model: str | None = None
    openrouter_http_referer: str | None = None
    openrouter_app_title: str = "YouTube Niche Intelligence Engine"
    openrouter_max_retries: int = Field(default=3, ge=0, le=8)
    openrouter_request_timeout_seconds: float = Field(default=1800.0, ge=5, le=1800)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str | None = None
    ollama_max_retries: int = Field(default=3, ge=0, le=8)
    pexels_api_key: str | None = None
    pixabay_api_key: str | None = None
    wikimedia_user_agent: str = "NicheIntel/1.0 (research tool)"
    asset_max_ideas_per_run: int = Field(default=30, ge=10, le=30)
    asset_max_concurrency: int = Field(default=4, ge=1, le=16)
    deepgram_api_key: str | None = None
    deepgram_model: str = "nova-3"
    media_download_enabled: bool = True
    media_max_duration_seconds: int = Field(default=900, ge=30, le=7200)
    media_max_videos_per_run: int = Field(default=6, ge=1)
    media_work_root: str = ".runtime/media"
    media_derived_retention_hours: int = Field(default=24, ge=1, le=720)
    media_max_storage_gb: float = Field(default=5.0, gt=0, le=1024)
    media_min_free_disk_gb: float = Field(default=2.0, ge=0, le=1024)
    media_unknown_download_reserve_mb: int = Field(default=150, ge=10, le=4096)
    browser_artifact_retention_hours: int = Field(default=24, ge=1, le=720)
    browser_profile_retention_days: int = Field(default=7, ge=1, le=365)
    ytdlp_executable: str = "yt-dlp"
    ffmpeg_executable: str = "ffmpeg"
    external_trends_url: str | None = None
    external_trends_api_key: str | None = None
    closed_test_block_network: bool = True
    fixture_scenario: str = "strong"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    migration_wait_timeout_seconds: float = Field(default=300.0, ge=0, le=3600)
    migration_poll_interval_seconds: float = Field(default=2.0, gt=0, le=60)
    cors_allowed_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )
    cors_allowed_origin_regex: str | None = None

    @field_validator("ai_provider")
    @classmethod
    def ai_provider_is_explicit(cls, value: str) -> str:
        provider = value.strip().lower()
        supported = {"auto", "deterministic", "fake", "openrouter", "ollama"}
        if provider not in supported:
            choices = ", ".join(sorted(supported))
            raise ValueError(f"AI_PROVIDER must be one of: {choices}")
        return provider

    @field_validator("browser_profile_root", "media_work_root")
    @classmethod
    def artifact_root_is_scoped(cls, value: str) -> str:
        raw = Path(value).expanduser()
        resolved = raw.resolve()
        forbidden = {
            Path(resolved.anchor),
            Path.cwd().resolve(),
            Path.home().resolve(),
            Path("/tmp").resolve(),
        }
        if resolved in forbidden or raw in {Path("."), Path("..")}:
            raise ValueError("artifact roots must be dedicated child directories")
        if raw.is_absolute() and len(resolved.parts) < 3:
            raise ValueError("absolute artifact roots must be dedicated child directories")
        if not raw.is_absolute() and len(raw.parts) < 2:
            raise ValueError("relative artifact roots must include a dedicated parent directory")
        if not any(part in {"runtime", ".runtime"} for part in resolved.parts[:-1]):
            raise ValueError("artifact roots must live beneath a dedicated runtime directory")
        return value

    @model_validator(mode="after")
    def validate_runtime(self) -> "Settings":
        browser_root = Path(self.browser_profile_root).expanduser().resolve()
        media_root = Path(self.media_work_root).expanduser().resolve()
        if browser_root == media_root or browser_root in media_root.parents or media_root in browser_root.parents:
            raise ValueError("browser and media artifact roots must be separate, non-nested directories")
        if self.app_mode == AppMode.LIVE_TEST:
            if not self.browser_enabled:
                raise ValueError("BROWSER_ENABLED=true is required in live_test mode")
        if self.app_mode in {AppMode.LIVE_TEST, AppMode.PRODUCTION} and self.ai_provider == "fake":
            raise ValueError("AI_PROVIDER=fake is fixture-only; use auto or deterministic for zero-key live research")
        if self.app_mode == AppMode.CLOSED_TEST:
            self.closed_test_block_network = True
            # This protects closed mode even when a developer has cloud
            # credentials in their shell and even if a future provider is
            # added to the factory.
            self.ai_provider = "fake"
        return self

    @property
    def is_closed(self) -> bool:
        return self.app_mode == AppMode.CLOSED_TEST

    @property
    def is_live(self) -> bool:
        return self.app_mode == AppMode.LIVE_TEST

    @property
    def uses_fixture_sources(self) -> bool:
        """Whether research observations come from the local synthetic fixtures."""
        return self.app_mode in {AppMode.DEVELOPMENT, AppMode.CLOSED_TEST}

    @property
    def metadata_source(self) -> str:
        """The structured video-metadata adapter configured for this run."""
        if self.uses_fixture_sources:
            return "fixture_api"
        return "youtube_api" if self.youtube_api_key else "keyless_ytdlp"

    @property
    def database_sync_url(self) -> str:
        """Use the sync SQLAlchemy driver for the compact MVP control plane."""
        if self.database_url.startswith("postgresql+asyncpg://"):
            return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        return self.database_url

    @property
    def bootstrap_schema_on_startup(self) -> bool:
        """Keep fixture convenience while requiring Alembic for hosted live databases."""
        fixture_mode = self.app_mode in {AppMode.DEVELOPMENT, AppMode.CLOSED_TEST}
        return fixture_mode or self.database_sync_url.startswith("sqlite")

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "Settings":
        env = environ if environ is not None else os.environ
        values: dict[str, Any] = {
            "app_mode": env.get("APP_MODE", "development"),
            "database_url": env.get("DATABASE_URL", "sqlite:///./runtime/nicheintel.db"),
            "redis_url": env.get("REDIS_URL", "redis://localhost:6379/0"),
            "youtube_api_key": env.get("YOUTUBE_API_KEY") or None,
            "youtube_api_daily_search_budget": env.get("YOUTUBE_API_DAILY_SEARCH_BUDGET", 100),
            "youtube_api_reserved_search_calls": env.get("YOUTUBE_API_RESERVED_SEARCH_CALLS", 20),
            "youtube_api_daily_unit_budget": env.get("YOUTUBE_API_DAILY_UNIT_BUDGET", 10000),
            "youtube_api_reserved_units": env.get("YOUTUBE_API_RESERVED_UNITS", 500),
            "outlier_threshold": env.get("OUTLIER_THRESHOLD", 3.0),
            "browser_enabled": _as_bool(env.get("BROWSER_ENABLED", "true")),
            "browser_headless": _as_bool(env.get("BROWSER_HEADLESS", "false")),
            "browser_executable_path": env.get("BROWSER_EXECUTABLE_PATH") or None,
            "browser_profile_root": env.get("BROWSER_PROFILE_ROOT", ".runtime/browser_profiles"),
            "browser_max_tabs": env.get("BROWSER_MAX_TABS", 4),
            "browser_max_queries_per_run": env.get("BROWSER_MAX_QUERIES_PER_RUN", 20),
            "browser_max_results_per_query": env.get("BROWSER_MAX_RESULTS_PER_QUERY", 30),
            "browser_max_channels_per_run": env.get("BROWSER_MAX_CHANNELS_PER_RUN", 100),
            "ai_provider": env.get("AI_PROVIDER") or "auto",
            "openrouter_api_key": env.get("OPENROUTER_API_KEY") or None,
            "openrouter_base_url": env.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1",
            "openrouter_model": env.get("OPENROUTER_MODEL") or "openrouter/free",
            "openrouter_vision_model": env.get("OPENROUTER_VISION_MODEL") or None,
            "openrouter_http_referer": env.get("OPENROUTER_HTTP_REFERER") or None,
            "openrouter_app_title": env.get("OPENROUTER_APP_TITLE") or "YouTube Niche Intelligence Engine",
            "openrouter_max_retries": env.get("OPENROUTER_MAX_RETRIES", 3),
            "openrouter_request_timeout_seconds": env.get("OPENROUTER_REQUEST_TIMEOUT_SECONDS", 1800),
            "ollama_base_url": env.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            "ollama_model": env.get("OLLAMA_MODEL") or None,
            "ollama_max_retries": env.get("OLLAMA_MAX_RETRIES", 3),
            "pexels_api_key": env.get("PEXELS_API_KEY") or None,
            "pixabay_api_key": env.get("PIXABAY_API_KEY") or None,
            "wikimedia_user_agent": env.get("WIKIMEDIA_USER_AGENT") or "NicheIntel/1.0 (research tool)",
            "asset_max_ideas_per_run": env.get("ASSET_MAX_IDEAS_PER_RUN", 30),
            "asset_max_concurrency": env.get("ASSET_MAX_CONCURRENCY", 4),
            "deepgram_api_key": env.get("DEEPGRAM_API_KEY") or None,
            "deepgram_model": env.get("DEEPGRAM_MODEL") or "nova-3",
            "media_download_enabled": _as_bool(env.get("MEDIA_DOWNLOAD_ENABLED", "true")),
            "media_max_duration_seconds": env.get("MEDIA_MAX_DURATION_SECONDS", 900),
            "media_max_videos_per_run": env.get("MEDIA_MAX_VIDEOS_PER_RUN", 6),
            "media_work_root": env.get("MEDIA_WORK_ROOT") or ".runtime/media",
            "media_derived_retention_hours": env.get("MEDIA_DERIVED_RETENTION_HOURS", 24),
            "media_max_storage_gb": env.get("MEDIA_MAX_STORAGE_GB", 5),
            "media_min_free_disk_gb": env.get("MEDIA_MIN_FREE_DISK_GB", 2),
            "media_unknown_download_reserve_mb": env.get("MEDIA_UNKNOWN_DOWNLOAD_RESERVE_MB", 150),
            "browser_artifact_retention_hours": env.get("BROWSER_ARTIFACT_RETENTION_HOURS", 24),
            "browser_profile_retention_days": env.get("BROWSER_PROFILE_RETENTION_DAYS", 7),
            "ytdlp_executable": env.get("YTDLP_EXECUTABLE") or "yt-dlp",
            "ffmpeg_executable": env.get("FFMPEG_EXECUTABLE") or "ffmpeg",
            "external_trends_url": env.get("EXTERNAL_TRENDS_URL") or None,
            "external_trends_api_key": env.get("EXTERNAL_TRENDS_API_KEY") or None,
            "closed_test_block_network": _as_bool(env.get("CLOSED_TEST_BLOCK_NETWORK", "true")),
            "fixture_scenario": env.get("FIXTURE_SCENARIO", "strong"),
            "api_host": env.get("API_HOST", "0.0.0.0"),
            "api_port": env.get("PORT", env.get("API_PORT", 8000)),
            "migration_wait_timeout_seconds": env.get("MIGRATION_WAIT_TIMEOUT_SECONDS", 300),
            "migration_poll_interval_seconds": env.get("MIGRATION_POLL_INTERVAL_SECONDS", 2),
            "cors_allowed_origins": _as_csv(
                env.get(
                    "CORS_ALLOWED_ORIGINS",
                    "http://localhost:3000,http://127.0.0.1:3000",
                )
            ),
            "cors_allowed_origin_regex": env.get("CORS_ALLOWED_ORIGIN_REGEX") or None,
        }
        return cls.model_validate(values)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_csv(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return tuple(item.strip() for item in str(value).split(",") if item.strip())


def load_settings() -> Settings:
    return Settings.from_env()


def ensure_database_dir(settings: Settings) -> None:
    """Create only a file-backed SQLite database's parent directory.

    Artifact roots are intentionally initialized by the process that owns the
    mounted runtime filesystem, not as a side effect of constructing an API
    database connection.
    """
    if not settings.database_sync_url.startswith("sqlite"):
        return
    from sqlalchemy.engine import make_url

    database_path = make_url(settings.database_sync_url).database
    if not database_path or database_path == ":memory:":
        return
    Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
