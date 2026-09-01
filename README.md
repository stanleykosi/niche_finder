# YouTube Niche Intelligence Engine

The engine finds repeatable YouTube formats with current demand, repeated outliers, a workable idea and clip ceiling, manageable direct competition, and a defensible viral mechanism. It is deliberately evidence-first: browser observations and structured API observations remain separate, deterministic metrics are calculated by Python, and AI only interprets the evidence.

## Hosted development and validation

This workstation is editing/control-plane only. Do not install the project
dependency set or run builds, services, browsers, tests, fixture jobs, or live
research here. Deploy the frontend to Vercel and the API/worker to Railway;
perform all fixture, integration, browser, migration, smoke, and live checks in
those hosted environments. A hosted failure is a valid test result and should
be diagnosed from platform logs and persisted run evidence.

AI provider selection is automatic by default. Outside closed mode, a configured
OpenRouter key and installed SDK are preferred, then a configured Ollama model,
then an evidence-driven deterministic live provider that reads bounded image
inputs; only fixture-backed modes use fake AI. `AI_PROVIDER=deterministic`
selects that zero-key provider explicitly. `AI_PROVIDER=openrouter` or
`AI_PROVIDER=ollama` is strict: requests retry transient failures and exit
cleanly instead of switching providers during a run. Set `OPENROUTER_MODEL` to a specific model, or keep
`openrouter/free` for OpenRouter's free-model router; free-model availability and
rate limits can change, so a paid model is recommended for dependable runs.
Unknown provider names are rejected during typed startup validation instead of
silently entering automatic selection.

Fixture mode remains available for hosted isolated validation and is labelled
`CLOSED / FIXTURE DATA` in the dashboard.

## Architecture

`apps/api/app` contains the control plane, domain contracts, SQLAlchemy persistence models, source adapters, deterministic analytics, AI providers, report engine, and FastAPI routes. The worker packages are thin entry points around the same orchestrator. `fixtures/` is the closed-test source of truth for hosted fixture pages, API payloads, and AI outputs. `apps/web` is a Next.js App Router client for creating runs and reading reports.

The application selects sources through a quota-aware router. Development and
closed modes use visibly labelled fixtures and refuse live source construction.
Live mode requires explicit browser enablement; the YouTube Data API key is
optional because bounded yt-dlp metadata is the supported keyless path.

## How niche validation works

1. Discover candidates on YouTube, preserving whether YouTube actually presented each result as a Short.
2. Reject candidates that cannot show real clip supply, then expand retained channels and compute same-channel views/day baselines.
3. Judge current demand in a 45-day window, supported by a 90-day baseline; old viral hits cannot pass the current gate.
4. Require repeated outliers across multiple successful channels and reject evidence dominated by one channel.
5. Match winners and losers within the same channel, format, duration, and time period, then compare their hooks, openings, transcripts, structure, pacing, captions, reveals, and payoffs.
6. Analyze representative frames with the configured AI provider. Live media analysis follows the video-use pattern: Deepgram word timestamps plus a small selective filmstrip, not frame dumping.
7. Generate distinct ideas from the complete dossier, then run multimodal clip-fit validation across Pexels, Pixabay, Wikimedia Commons, and Internet Archive web search. At least ten ideas must survive. Licensing metadata is preserved but does not gate niche discovery; every idea carries non-gating faceless production notes.
8. Score saturation from active competitors, upload density, format similarity, weak copycats, and evidence concentration.
9. Build a bounded evidence packet for each candidate. The research-editor AI reconciles per-video transcript/visual observations, deterministic metrics, matched comparisons, mechanism replication, ideas, footage, and saturation into a cited thesis.
10. Run an independent AI critic against creator-specific advantage, stale virality, channel concentration, event dependence, saturation, footage supply, idea ceiling, and unsupported inference.
11. Deterministically validate every cited evidence ID and adjudicate the result. AI may lower confidence or block a recommendation; it cannot pass a failed hard gate or override a deterministic verdict.
12. Produce a portfolio-level synthesis and action plan. YouTube performance remains the primary trend signal; optional external trend data is corroborative.

The New Research screen exposes discovery scope, recency, depth, and production
constraints explicitly. Broad discovery may be empty (a deterministic 12-market
fast or 20-market deep portfolio) or anchored by seeds. Focused validation
requires a seed. Production constraints annotate ideas and the production plan;
they do not hide demand evidence or weaken hard gates.

For external corroboration, set `EXTERNAL_TRENDS_URL` to a user-controlled HTTP bridge (for example one wrapping Google Trends API alpha or an MCP trend server). The bridge accepts `queries`, `regions`, and `window_days`, and returns a normalized `score` from 0 to 1 plus source observations. Its weight is capped at 15%.

The public APIs cannot provide private competitor retention or exact analytics. Channel profiles are labelled public-data proxies, and YouTube competitor footage is evidence-only—not reusable clip inventory.

## Operations

Operational migrations, cleanup, fixture checks, and live smoke commands are
executed only inside the appropriate Railway/Vercel service or hosted build
job. Do not invoke the Make targets on the editing workstation.

## Vercel + Railway deployment

The hosted layout preserves the canonical process boundaries:

- Vercel runs only the Next.js application from `apps/web`.
- Railway runs one public FastAPI service and one private ARQ worker from
  `Dockerfile.api`.
- Railway managed PostgreSQL and Redis are shared by the API and worker over
  Railway's private network.
- The worker owns browser/media execution. Attach a Railway volume at
  `/app/.runtime` so the persistent browser profile and retained derived media
  survive worker redeploys. Size it above the configured media ceiling plus
  free-space floor (at least 10 GB with the example defaults).
- Only the worker mounts that volume. It performs startup/terminal cleanup and
  publishes measured usage to Redis for `GET /api/system/storage`; the API does
  not sweep or inspect its isolated container filesystem.

Configure the Railway services in this order:

1. Provision managed PostgreSQL and Redis.
2. Create the API service from the repository root with
   `RAILWAY_DOCKERFILE_PATH=Dockerfile.api`, one replica, public networking,
   and health check path `/health`. Configure the one-shot Railway Pre-deploy
   Command as `python -m apps.api.app.db.migrate`, and set the Start Command to
   `sh -c 'exec uvicorn apps.api.app.main:app --host 0.0.0.0 --port "$PORT"'`.
   Railway must only promote the API revision when the pre-deploy migration
   succeeds. The image's default command retains the same migration-first
   behavior for direct Docker use.
3. Create the private worker service from the same repository and Dockerfile.
   Override its start command with
   `arq workers.research.worker.WorkerSettings`; do not assign it a public
   domain. Attach the `/app/.runtime` volume to this service. Worker startup
   polls the shared Alembic revision and cannot dequeue a job until it matches
   the code's migration head. A failed or missing API migration therefore
   makes the worker exit without consuming queued research.
4. Give both code services reference variables for the managed database URLs:
   `DATABASE_URL=${{Postgres.DATABASE_URL}}` and
   `REDIS_URL=${{Redis.REDIS_URL}}` (adjust service names if Railway generated
   different names).

For the first bounded hosted run, set these shared runtime variables on the API
and worker. Keep credentials in Railway, never in the repository:

```text
APP_MODE=live_test
BROWSER_ENABLED=true
BROWSER_HEADLESS=true
AI_PROVIDER=auto
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
BROWSER_PROFILE_ROOT=.runtime/browser_profiles
MEDIA_WORK_ROOT=.runtime/media
MIGRATION_WAIT_TIMEOUT_SECONDS=300
MIGRATION_POLL_INTERVAL_SECONDS=2
```

Set the optional YouTube, OpenRouter, Deepgram, Pexels, Pixabay, and trend
variables from the live configuration below when available. The API service
also needs `CORS_ALLOWED_ORIGINS` set to the exact Vercel production origin,
for example `https://niche-intel.vercel.app`. Preview origins can be listed as
additional comma-separated values; the optional
`CORS_ALLOWED_ORIGIN_REGEX` exists for intentionally enabling a controlled
preview-domain pattern.

Create the Vercel project with Root Directory `apps/web`. Its checked-in
`vercel.json` pins the Next.js framework and deterministic install/build
commands. Set this build-time variable for Production (and Preview when used),
then redeploy whenever it changes:

```text
NEXT_PUBLIC_API_BASE_URL=https://<railway-api-domain>
```

The frontend variable is public by design and must contain only the API origin,
never a credential. CORS is a browser boundary, not authentication; the current
canonical MVP has no public-user authentication. Use Vercel/Railway access
controls or keep the live-validation deployment short-lived until application
authentication is explicitly added.

Live smoke can run without API keys. At minimum it needs Chromium, `yt-dlp`,
`ffmpeg`, and network access; it uses keyless public metadata, Commons search,
and deterministic AI. The recommended accurate configuration is:

```text
APP_MODE=live_test
YOUTUBE_API_KEY=... # optional; otherwise yt-dlp metadata is used
BROWSER_ENABLED=true
AI_PROVIDER=auto
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openrouter/free
OPENROUTER_VISION_MODEL=<optional vision-capable model; defaults to the main model>
OPENROUTER_MAX_RETRIES=3
OPENROUTER_REQUEST_TIMEOUT_SECONDS=900
DEEPGRAM_API_KEY=... # optional but required for full word-timestamp transcripts
DEEPGRAM_MODEL=nova-3
# Optional live clip preflight. Configure both for the required two-source diversity.
PEXELS_API_KEY=...
PIXABAY_API_KEY=...
ASSET_MAX_IDEAS_PER_RUN=30
ASSET_MAX_CONCURRENCY=4
EXTERNAL_TRENDS_URL=<optional API/MCP HTTP bridge>
EXTERNAL_TRENDS_API_KEY=<optional bridge bearer token>
# Optional alternative selected at startup (not a mid-run fallback):
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=<local model supporting JSON output>
OLLAMA_MAX_RETRIES=3
```

The live smoke run is bounded to two seed queries, ten channels, twenty enriched videos, rotating isolated browser profiles, and `deep_research=false`. It prints unified YouTube quota units before and after, then verifies metadata/browser evidence merging, outlier analytics, AI output, and final report generation. It is never invoked by closed tests.

## Evidence and safety

Every derived claim keeps its source, observation timestamp, calculation version, and evidence IDs. Transcript text is chunked into bounded excerpts; when YouTube does not expose timestamps, the record explicitly stores that timing is unavailable. AI outputs are stored as evidence records with provider/version, confidence, and citation-validation results. Browser navigation has an allowed-host guard. Runtime browser profiles and screenshots are ignored by git. Do not place credentials in committed files.

## Runtime storage lifecycle

Each live run uses `.runtime/media/<run-id>/downloads`, `frames`, and `temporary`.
The downloaded MP4 remains available until Deepgram transcription, word
timestamps, selective-frame extraction, and deterministic media metrics are
complete. A `finally` cleanup then deletes it on success, failure, or
cancellation. Selected frames default to 24-hour retention; transcripts,
timestamps, checksums, sizes, derived observations, and deletion state remain
in the database. Worker startup and terminal-run cleanup remove expired
artifacts, while `make cleanup-runtime` provides a manual sweep when invoked
from the worker service shell (and therefore on its mounted volume). Downloads
are rejected before they start if the configured runtime ceiling or minimum
free-space floor would be crossed. Each yt-dlp request receives the exact reserved byte ceiling,
uses a single bounded progressive download, and is monitored for actual output
growth. Capacity is reserved atomically across worker processes and released
only after raw cleanup and media subprocess reaping, so concurrent runs cannot
both claim the same free space and cancellation cannot leave a downloader
running against released capacity. Artifact roots must be separate child directories beneath a `runtime`
or `.runtime` directory; broad, equal, nested, or symlink-escaped roots are
rejected before cleanup can run. Raw deletion is unconditional; configure derived retention
and storage bounds with `MEDIA_DERIVED_RETENTION_HOURS`, `MEDIA_MAX_STORAGE_GB`,
`MEDIA_MIN_FREE_DISK_GB`, `BROWSER_ARTIFACT_RETENTION_HOURS`, and
`BROWSER_PROFILE_RETENTION_DAYS`. The worker publishes its filesystem
measurement through shared Redis, and that state is exposed at
`GET /api/system/storage`; the endpoint returns 503 until a worker has
published a measurement rather than reporting the API container's unmounted
disk. Per-run artifact history is available at
`GET /api/research-runs/{run_id}/artifacts`.

In keyless mode, yt-dlp traverses a bounded `/videos` feed for every retained
channel so channel baselines and winner/loser comparisons do not depend on
search coincidences. Browser filmstrip capture, video download, transcription,
and derived-frame work defaults to six channel-diverse representative videos
per run and is operator-configurable. Heavy media is processed sequentially and
each raw download is removed before the next target. Closed runs execute
synchronously; all other modes enqueue Redis/ARQ work and immediately return a
pollable run ID.

All analytics require a real publication timestamp; undated YouTube API and
yt-dlp entries are excluded with source-typed diagnostics, never treated as
newly published. Private,
members-only, removed, and malformed uploads are skipped independently and
recorded in the evidence ledger. Video descriptions are retained only on video
records and are never reused as channel descriptions.

This isolation applies to both initial discovery results and later channel
uploads. Missing or invalid aspect ratio is treated as unknown—not portrait and
not Shorts evidence—so incomplete dimension metadata cannot abort enrichment.

Source-wide configuration failures such as a missing yt-dlp executable are not
converted into candidate skips; they fail with the original actionable error.
When an individual initial candidate fails, its browser-observed channel,
title, URL, age/views, Shorts surface, position, screenshot, and raw card
context remain attached to the skip evidence.

Sparse channel-feed records inherit the channel being traversed and retain any
known discovery channel title. Skip evidence always cites a canonical YouTube
page URL; temporary yt-dlp CDN/media URLs never replace that source identity.

Outlier baselines are keyed by channel, media class, and repeatable format, so
Shorts and long-form uploads never share a cohort merely because their format
label matches. One unavailable channel feed produces evidence and does not stop
later channels. Sparse successful extraction retains known discovery metadata,
and aspect ratio must be positive, finite, and below one to support portrait
Shorts evidence.
