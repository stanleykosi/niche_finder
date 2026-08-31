import pytest
from pydantic import ValidationError

from apps.api.app.core.config import AppMode, Settings


def test_closed_mode_forces_fixture_safe_ai_when_unconfigured():
    settings = Settings(app_mode=AppMode.CLOSED_TEST, ai_provider="ollama", ollama_model=None)
    assert settings.is_closed
    assert settings.ai_provider == "fake"


def test_live_mode_supports_keyless_metadata_but_requires_browser():
    settings = Settings(app_mode=AppMode.LIVE_TEST, browser_enabled=True)
    assert settings.youtube_api_key is None
    with pytest.raises(ValueError, match="BROWSER_ENABLED"):
        Settings(app_mode=AppMode.LIVE_TEST, youtube_api_key="key", browser_enabled=False)


def test_mvp_normalizes_language_and_preserves_bounded_production_constraints():
    from apps.api.app.domain.contracts import ResearchRunCreate
    request = ResearchRunCreate(language="en", production_constraints=["one hour per week"])
    assert request.language == "English"
    assert request.production_constraints == ["one hour per week"]
    with pytest.raises(ValueError, match="English-language"):
        ResearchRunCreate(language="French")


def test_unknown_ai_provider_names_fail_configuration_instead_of_falling_back():
    with pytest.raises(ValidationError, match="AI_PROVIDER must be one of"):
        Settings(ai_provider="ollmaa")
    assert Settings(ai_provider=" AUTO ").ai_provider == "auto"
    assert Settings(app_mode=AppMode.PRODUCTION, ai_provider="deterministic").ai_provider == "deterministic"
    with pytest.raises(ValidationError, match="fixture-only"):
        Settings(app_mode=AppMode.PRODUCTION, ai_provider="fake")


def test_closed_mode_protects_network_flag():
    settings = Settings(app_mode=AppMode.CLOSED_TEST, closed_test_block_network=False)
    assert settings.closed_test_block_network is True


def test_runtime_threshold_and_system_chromium_path_are_configurable():
    assert Settings().openrouter_request_timeout_seconds == 300
    settings = Settings.from_env({"OUTLIER_THRESHOLD": "3.5", "BROWSER_EXECUTABLE_PATH": "/usr/bin/chromium", "OLLAMA_MAX_RETRIES": "4", "OPENROUTER_REQUEST_TIMEOUT_SECONDS": "45"})
    assert settings.outlier_threshold == 3.5
    assert settings.browser_executable_path == "/usr/bin/chromium"
    assert settings.ollama_max_retries == 4
    assert settings.openrouter_request_timeout_seconds == 45


def test_hosted_runtime_parses_port_and_cors_configuration():
    settings = Settings.from_env({
        "PORT": "4321",
        "MIGRATION_WAIT_TIMEOUT_SECONDS": "45",
        "MIGRATION_POLL_INTERVAL_SECONDS": "0.5",
        "CORS_ALLOWED_ORIGINS": "https://niche.example, https://preview.example ",
        "CORS_ALLOWED_ORIGIN_REGEX": r"^https://.*\.vercel\.app$",
    })
    assert settings.api_port == 4321
    assert settings.migration_wait_timeout_seconds == 45
    assert settings.migration_poll_interval_seconds == 0.5
    assert settings.cors_allowed_origins == (
        "https://niche.example",
        "https://preview.example",
    )
    assert settings.cors_allowed_origin_regex == r"^https://.*\.vercel\.app$"


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://postgres:secret@postgres.railway.internal:5432/railway",
        "postgres://postgres:secret@postgres.railway.internal:5432/railway",
        "postgresql+asyncpg://postgres:secret@postgres.railway.internal:5432/railway",
    ],
)
def test_hosted_postgres_urls_use_the_installed_psycopg_driver(database_url):
    settings = Settings(app_mode=AppMode.LIVE_TEST, database_url=database_url)
    assert settings.database_sync_url.startswith("postgresql+psycopg://")
    assert settings.bootstrap_schema_on_startup is False


def test_raw_media_deletion_has_no_feature_flag_bypass():
    settings = Settings.from_env({"MEDIA_DELETE_RAW_AFTER_ANALYSIS": "false"})
    assert not hasattr(settings, "media_delete_raw_after_analysis")


def test_development_explicitly_reports_fixture_sources():
    assert Settings(app_mode=AppMode.DEVELOPMENT).uses_fixture_sources is True
    assert Settings(app_mode=AppMode.CLOSED_TEST).uses_fixture_sources is True
    assert Settings(app_mode=AppMode.LIVE_TEST).uses_fixture_sources is False
    assert Settings(app_mode=AppMode.DEVELOPMENT).metadata_source == "fixture_api"
    assert Settings(app_mode=AppMode.LIVE_TEST).metadata_source == "keyless_ytdlp"
    assert Settings(app_mode=AppMode.LIVE_TEST, youtube_api_key="configured").metadata_source == "youtube_api"


def test_zero_key_live_smoke_request_keeps_canonical_clip_gate(monkeypatch):
    from scripts.live_smoke_test import _build_smoke_request

    monkeypatch.setenv("LIVE_SMOKE_SEEDS", "visual science experiments")
    request = _build_smoke_request(Settings(app_mode=AppMode.LIVE_TEST))
    assert request.minimum_clip_coverage == .7
    assert request.limits.max_queries == 1


def test_heavy_media_limit_defaults_to_six_and_is_operator_configurable():
    assert Settings().media_max_videos_per_run == 6
    assert Settings(media_max_videos_per_run=12).media_max_videos_per_run == 12
    with pytest.raises(ValueError):
        Settings(media_max_videos_per_run=0)


def test_asset_fanout_limits_are_operator_configurable_but_hard_capped():
    settings = Settings.from_env({"ASSET_MAX_IDEAS_PER_RUN": "20", "ASSET_MAX_CONCURRENCY": "3"})
    assert settings.asset_max_ideas_per_run == 20
    assert settings.asset_max_concurrency == 3
    with pytest.raises(ValueError):
        Settings(asset_max_ideas_per_run=31)


@pytest.mark.parametrize("unsafe_root", [".", "..", "/", "/tmp", "/var/log"])
def test_artifact_roots_reject_broad_recursive_cleanup_targets(unsafe_root):
    with pytest.raises(ValidationError, match="artifact roots"):
        Settings(media_work_root=unsafe_root)


def test_artifact_roots_must_be_separate_and_non_nested(tmp_path):
    parent = tmp_path / "runtime" / "artifacts"
    with pytest.raises(ValidationError, match="separate, non-nested"):
        Settings(
            media_work_root=str(parent),
            browser_profile_root=str(parent / "browser"),
        )


@pytest.mark.parametrize("field,value", [
    ("minimum_clip_coverage", .69),
    ("minimum_successful_channels", 2),
    ("minimum_recent_outliers", 2),
    ("minimum_outlier_channels", 1),
    ("minimum_winner_loser_pairs", 2),
    ("maximum_saturation", .76),
])
def test_request_cannot_weaken_canonical_recommendation_gates(field, value):
    from apps.api.app.domain.contracts import ResearchRunCreate

    with pytest.raises(ValidationError):
        ResearchRunCreate.model_validate({field: value})
