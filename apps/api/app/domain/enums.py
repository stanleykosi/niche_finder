from enum import StrEnum


class RunStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    DISCOVERING = "discovering"
    ENRICHING = "enriching"
    ANALYSING = "analysing"
    REPORTING = "reporting"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RequestedFormat(StrEnum):
    SHORTS = "shorts"
    LONG_FORM = "long_form"
    BOTH = "both"


class SourceType(StrEnum):
    BROWSER = "browser"
    YOUTUBE_API = "youtube_api"
    KEYLESS_YTDLP = "keyless_ytdlp"
    FIXTURE_BROWSER = "fixture_browser"
    FIXTURE_API = "fixture_api"
    AI = "ai"
    DETERMINISTIC = "deterministic"
    ASSET_FIXTURE = "asset_fixture"


class Verdict(StrEnum):
    START_NOW = "Start now"
    RUN_TEST = "Run a 20-video test"
    WATCH_MOMENTUM = "Watch for momentum"
    SHORTS_ONLY = "Shorts only"
    LONG_FORM_ONLY = "Long-form only"
    FOOTAGE_CONSTRAINED = "Promising but footage-constrained"
    OVERSATURATED = "Demand exists but oversaturated"
    INSUFFICIENT = "Insufficient evidence"
    REJECT = "Reject"
