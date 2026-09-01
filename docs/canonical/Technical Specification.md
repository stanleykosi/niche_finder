# Technical Specification

## 1. Canonical architecture

```text
Web UI (Next.js)
        |
        v
FastAPI Control Plane
        |
        +-----------------------------+
        |                             |
        v                             v
Research Orchestrator            Query / Report API
        |
        +---------------+----------------+----------------+
        |               |                |                |
        v               v                v                v
Chromium Worker   YouTube API Worker   AI Worker    Asset Connectors
(Playwright)       (official API)      (OpenRouter/  (pluggable)
                                      Ollama/fake)
        |               |                |                |
        +---------------+----------------+----------------+
                        |
                        v
                Evidence + Domain Layer
                        |
              +---------+---------+
              |                   |
              v                   v
      PostgreSQL + pgvector    Redis
              |               queue/cache
              v
      Deterministic Analytics
              |
              v
      Recommendation Engine
              |
              v
        Research Reports
```

## 2. Required technology stack

### Frontend
- Next.js
- TypeScript
- App Router
- Tailwind CSS
- TanStack Query
- Zod for client-side schemas

### Backend/control plane
- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- httpx

### Database
- PostgreSQL
- pgvector
- Psycopg 3 sync driver, installed in every backend and worker image
- UUID primary keys
- UTC timestamps

### Queue/cache
- Redis
- ARQ or Celery; choose one and use it consistently.
- Preferred: **ARQ** for a smaller async Python surface.

### Browser
- Playwright for Python
- Chromium
- Persistent research profiles
- Headed and headless configuration
- Per-run browser limits
- Screenshot capture
- DOM/semantic extraction with vision fallback abstraction

### AI
- Provider interface: `AIProvider`
- Provider selection at startup: configured OpenRouter official SDK, then Ollama HTTP API, then the evidence-driven deterministic live provider; fixture modes use fake, explicit selection is strict, and there is no mid-run provider failover
- Optional OpenRouter structured-output provider
- One configurable total deadline per OpenRouter structured request, including
  its bounded retries, so a stalled upstream cannot hold a run indefinitely
- Deterministic fake provider for closed testing
- Structured Pydantic outputs only
- Embeddings provider interface
- Default embeddings: deterministic hashed lexical, bigram, and character-fragment vectors with no learned runtime

### Analytics
- Python deterministic functions
- Polars or Pandas; prefer Polars for larger tabular operations
- NumPy where needed
- scikit-learn for clustering utilities when appropriate

### Testing
- pytest
- pytest-asyncio
- pytest-socket or equivalent network blocker
- respx for HTTP mocks
- Playwright tests against hosted fixture pages
- Vitest for frontend unit tests
- Playwright frontend E2E against deployed Vercel and Railway services

All test execution occurs in hosted Vercel/Railway compute. Do not install
test, browser, ML, or GPU dependencies on the editing workstation and do not
start the stack there. A failing hosted build, deployment, test, or live run is
valid diagnostic evidence and must be repaired through hosted logs and a new
deployment; it is not grounds for creating a local prerequisite gate.

### Reference orchestration
- Docker Compose files are retained as architecture/reference artifacts but are not executed on the editing workstation.
- Services:
  - postgres
  - redis
  - backend
  - worker
  - frontend
  - optional ollama profile
  - fixture server for closed testing

## 3. Repository structure

```text
/
├── AGENTS.md
├── README.md
├── .env.example
├── docker-compose.yml
├── Makefile
├── docs/
│   └── canonical/
│       ├── Project request.md
│       ├── Technical Specification.md
│       ├── Implementation plan.md
│       ├── Test plan.md
│       └── Build state.md
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── core/
│   │   │   ├── db/
│   │   │   ├── domain/
│   │   │   ├── repositories/
│   │   │   ├── services/
│   │   │   ├── research/
│   │   │   ├── analytics/
│   │   │   ├── sources/
│   │   │   ├── ai/
│   │   │   └── reports/
│   │   ├── alembic/
│   │   └── tests/
│   └── web/
│       ├── app/
│       ├── components/
│       ├── lib/
│       └── tests/
├── workers/
│   ├── research/
│   └── browser/
├── packages/
│   └── contracts/
├── fixtures/
│   ├── youtube_api/
│   ├── browser/
│   └── ai/
├── scripts/
│   ├── closed_test.py
│   ├── live_smoke_test.py
│   └── seed_demo.py
└── tests/
    ├── integration/
    ├── contract/
    └── e2e/
```

Do not create a competing source-of-truth documentation tree.

## 4. Runtime modes

The application must have explicit runtime modes:

```text
APP_MODE=development
APP_MODE=closed_test
APP_MODE=live_test
APP_MODE=production
```

### closed_test
- External networking is blocked.
- All YouTube responses come from fixtures/mocks.
- Browser research uses a hosted fixture website that mimics the page states needed by the worker.
- AI always uses the deterministic fake provider in closed mode; OpenRouter and Ollama are never contacted there.
- No credentials are required.

### live_test
- YouTube Data API enabled.
- Chromium enabled against live YouTube.
- AI provider uses OpenRouter when configured and installed; automatic startup selection may choose a configured hosted Ollama endpoint next, but an active run never changes providers.
- Only bounded smoke research is allowed.
- Must never be invoked automatically by the hosted fixture-test runner.

## 5. Environment variables

Provide `.env.example` with at least:

```text
APP_MODE=development
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/nicheintel
REDIS_URL=redis://redis:6379/0

YOUTUBE_API_KEY=
YOUTUBE_API_DAILY_SEARCH_BUDGET=100
YOUTUBE_API_RESERVED_SEARCH_CALLS=20

BROWSER_ENABLED=true
BROWSER_HEADLESS=false
BROWSER_PROFILE_ROOT=.runtime/browser_profiles
BROWSER_MAX_TABS=4
BROWSER_MAX_QUERIES_PER_RUN=20
BROWSER_MAX_RESULTS_PER_QUERY=30
BROWSER_MAX_CHANNELS_PER_RUN=100

AI_PROVIDER=auto
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openrouter/free
OPENROUTER_HTTP_REFERER=
OPENROUTER_APP_TITLE=YouTube Niche Intelligence Engine
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=
CLOSED_TEST_BLOCK_NETWORK=true
```

Secrets must never be committed.

## 6. Core domain entities

### ResearchRun
Fields:
- id
- status
- requested_format
- language
- regions
- seeds
- recency configuration
- research limits
- configuration JSON
- started_at
- completed_at
- failure_reason

Statuses:
- queued
- planning
- discovering
- enriching
- analysing
- reporting
- complete
- failed
- cancelled

### SearchObservation
- id
- research_run_id
- source
- profile_id
- query
- result_position
- observed_url
- observed_title
- observed_channel
- visible_views_text
- visible_age_text
- presented_as_short
- screenshot_ref
- observed_at
- raw_payload JSON

### Channel
- id
- youtube_channel_id
- canonical_url
- title
- description
- created_at
- updated_at

### ChannelSnapshot
- channel_id
- observed_at
- subscriber_count
- total_view_count
- video_count
- source

### Video
- id
- youtube_video_id
- channel_id
- canonical_url
- title
- description
- duration_seconds
- published_at
- category_id
- tags
- thumbnails
- updated_at

### VideoSnapshot
- video_id
- observed_at
- view_count
- like_count
- comment_count
- source

### CommentSample
- video_id
- source_comment_id
- text
- like_count
- published_at
- observed_at
- is_pinned_if_known
- source

### BrowserMediaObservation
- video_id
- research_run_id
- source_profile
- is_short_presentation
- visible_transcript
- thumbnail_ref
- frame_refs
- opening_visual_summary
- caption_style
- observable_structure
- observed_at
- confidence

### FormatCluster
- id
- research_run_id
- label
- description
- embedding/centroid
- representative_video_ids
- confidence

### OutlierResult
- video_id
- research_run_id
- comparison_cohort
- baseline_metric
- metric_value
- outlier_multiple
- label
- calculation_version

### ViralMechanismAnalysis
- format_cluster_id
- primary_mechanism
- secondary_mechanisms
- viewer_question
- hook_pattern
- payoff_pattern
- evidence_refs
- alternative_explanation
- confidence
- model/provider/version

### NicheCandidate
- id
- research_run_id
- broad_market
- niche
- sub_niche
- repeatable_format
- primary_viral_mechanism
- shorts_assessment
- longform_assessment
- idea_ceiling
- clip_ceiling
- saturation_assessment
- demand_assessment
- momentum_assessment
- confidence
- verdict

### EvidenceRecord
Every important claim must reference evidence.

Fields:
- id
- research_run_id
- evidence_type
- source_type
- source_entity_id
- observed_at
- payload
- confidence
- human_readable_summary

## 7. Source abstraction

Define a common source interface.

```python
class DiscoverySource(Protocol):
    async def discover(self, request: DiscoveryRequest) -> DiscoveryResult: ...

class EnrichmentSource(Protocol):
    async def enrich_videos(
        self,
        video_ids: list[str],
        context_by_video_id: dict[str, dict] | None = None,
    ) -> list[VideoRecord]: ...
    async def enrich_channels(self, channel_ids: list[str]) -> list[ChannelRecord]: ...
```

Implement:
- `ChromiumYouTubeSource`
- `YouTubeDataApiSource`
- `FixtureDiscoverySource`
- `FixtureEnrichmentSource`

Future sources must plug into the same orchestration layer.

## 8. Source router

The source router decides whether a task uses Chromium, API, or both.

Inputs:
- task type
- required fields
- current API search budget
- API reserve
- browser limits
- whether deterministic reproducibility is needed
- whether visual context is required
- whether IDs are already known
- source health

Example rules:
- Known video/channel IDs -> API first.
- Channel upload expansion -> API playlist path.
- Open-ended discovery -> Chromium first, API selectively.
- Exact date-window verification -> API.
- Visual/Shorts/page context -> Chromium.
- API search budget under reserve -> Chromium for discovery.
- closed_test -> fixture sources only.

The router must log every routing decision.

## 9. YouTube API worker

Implement clients for:
- `search.list`
- `videos.list`
- `channels.list`
- `playlistItems.list`
- `commentThreads.list`

Requirements:
- Batch IDs where supported.
- Central quota accounting.
- Per-run and daily search budgets.
- Reserved search-call floor.
- Retry with exponential backoff for transient failures.
- Idempotent persistence.
- No duplicate enrichment within a configured freshness window.
- Store raw API response fragments needed for audit/debugging.

## 10. Chromium research worker

### Browser profiles
Profiles are stored under `BROWSER_PROFILE_ROOT`.

A profile contains:
- retained screenshot evidence
- YouTube locale/language provenance where configured
- research profile metadata

Chromium user-data state is launch-isolated and disposable. Each discovery or
video inspection uses a unique temporary user-data directory, while retained
screenshots are written to the stable research profile directory. Container
replacement must therefore never carry a Chromium `SingletonLock`, cache, or
cookie database into a checkpoint-resume attempt. Startup cleanup removes
legacy non-image browser state from the persistent artifact root while
preserving unexpired screenshot evidence.

Do not store Google passwords in the application database.

### Browser tasks
Support:
- YouTube search query.
- Shorts search/filter observation.
- Channel page inspection.
- Video page inspection.
- Related-video extraction.
- Visible transcript extraction when the UI exposes it.
- Screenshot capture.
- Bounded scrolling.
- Search suggestion/autocomplete capture where stable.

### Extraction strategy
Use:
1. accessibility/semantic locators
2. visible text
3. stable link structure
4. DOM relations
5. configurable selectors
6. screenshot/vision fallback

Failures must return partial typed results with explicit missing fields.
After `domcontentloaded`, live YouTube discovery rejects the optional consent
prompt through its non-personalized `Reject all` control, waits a bounded five
seconds for asynchronously hydrated result cards, and pauses briefly after each
bounded scroll. If the hydrated browser surface is still empty, an available
YouTube Data API search is executed as an audited fallback rather than treating
an empty DOM snapshot as a conclusive zero-result market.

### Limits
Every browser task must respect:
- max queries
- max pages/results
- max channels
- max tabs
- max retry count
- total OpenRouter structured-request deadline
- max scroll iterations

There must be no unbounded loop.

## 11. Deterministic analytics

### Views per day

```text
views_per_day = current_views / max(video_age_days, 1)
```

Use precise fractional age after the first day when useful, but cap denominator to avoid extreme newborn-video distortion.

### Channel baseline
For each cohort:
- same channel
- same format class where known
- configured recency window
- exclude current candidate when calculating its baseline
- use median, not mean

### Outlier multiple

```text
outlier_multiple = candidate_views_per_day / median_cohort_views_per_day
```

Default labels:
- <1.0 = below normal
- 1.0–1.99 = normal
- 2.0–2.99 = strong
- 3.0–4.99 = outlier
- >=5.0 = major outlier

Thresholds must be configuration-driven.

### Momentum
Use snapshot deltas when multiple observations exist:
- absolute view growth
- views gained/day
- acceleration/deceleration
- age-adjusted growth percentile

Never claim historical growth that was not actually observed.

### Saturation signals
Calculate:
- direct competitor count
- active direct competitor count
- recent upload density
- high-performing competitor share
- low-performing copycat share
- title/format similarity
- cluster concentration

### Idea ceiling
Pipeline:
1. Extract successful subject/topic units.
2. Create topic clusters.
3. Generate structured candidate ideas through AI.
4. Embed ideas.
5. Deduplicate by similarity.
6. Require semantic distinctness.
7. Report unique viable count and cluster coverage.

### Clip ceiling
Implement as a connector-based subsystem.
Initial MVP may use fixture/local asset results.
Provide interfaces for future Pexels, Pixabay, Wikimedia, and other approved sources.

The live connector supports optional Pexels and Pixabay video searches plus keyless Wikimedia Commons API web search. Each observation retains provider, page URL, licence label, orientation where available, reusability, preview reference, and multimodal semantic-fit confidence. The deterministic decision requires at least three reusable clips, one reveal-capable clip, and no negative semantic-fit judgment per counted idea. Closed mode uses fixture parity only.

Run this as a two-pass system. The initial clip preflight executes immediately after lightweight video enrichment and before channel expansion, comments, transcripts, or competitor-video analysis. It performs bounded semantic asset checks and actually removes failed clusters. After all retained evidence is gathered, regenerate ideas from the complete dossier and run final clip validation; only this final pass supplies reported ceilings.

Authoritative final asset validation is candidate-scoped. Every retained
candidate receives an independent bounded capacity of at least ten final idea
checks; one candidate's checks must never reduce another candidate below the
ten validated ideas required for a positive verdict. Candidate count remains
bounded by the run's video/candidate limits, and each candidate remains capped
at 30 asset ideas.

Live video analysis uses Deepgram prerecorded STT (`nova-3`, English) over a bounded yt-dlp download and six selective ffmpeg frames. This adopts video-use's transcript-first/on-demand-visual principle without coupling the engine to its editing CLI. Missing Deepgram configuration is explicit and falls back only to visible browser transcripts; it is never represented as a full transcript.
An individual source-level download challenge, private video, or otherwise
unavailable media stream becomes explicit browser-only partial evidence and
does not abort analysis of later videos. Missing media executables and other
configuration failures remain fatal rather than being mislabeled as source
unavailability.

Chromium video inspection navigates to the response-commit boundary, rejects
optional consent without accepting personalized cookies, and then waits a
bounded interval for a real watch/Shorts surface to hydrate. Per-operation
locator, seek, and screenshot timeouts plus bounded context/driver shutdown
prevent a single partially loaded YouTube page from multiplying into several
minutes of empty observations. Successful frame samples are retained even if
another sample is unavailable.

### Runtime media lifecycle

- Scope every download and frame to `.runtime/media/<research-run-id>/`.
- Keep raw media until transcription, word timestamps, selective frames, and
  deterministic media features are captured.
- Delete raw video in `finally` on success, source failure, cancellation, or
  partial processing. Never rely only on a successful terminal run state.
- Retain selected frames for a configurable 24-hour default. Persist transcript,
  timestamps, checksums, size, expiry, derived observations, and deletion state.
- Keep Chromium user-data/cache on ephemeral storage and delete it after every
  browser operation; persist only registered screenshot evidence.
- Sweep expired media/browser artifacts at startup, after terminal runs, and
  through `make cleanup-runtime`.
- Reject a download before starting when its reserve would exceed the runtime
  storage ceiling or configured minimum free-space floor.
- Artifact paths may only resolve beneath the configured media or browser roots.
- In a split hosted deployment, only the worker process mounted to the runtime
  volume may initialize, sweep, reserve, delete, or measure artifact storage.
  It publishes timestamped storage measurements through shared Redis for the
  API status endpoint. The API must report that worker measurement or an
  explicit unavailable response; it must never inspect its isolated local disk.

### Shorts classification

Use the following ordered evidence model:
1. `confirmed_short`: browser-rendered Shorts surface, `/shorts/` observation, or an equivalent explicit YouTube presentation.
2. `probable_short`: source label or duration no longer than three minutes without presentation evidence.
3. `not_short`: duration longer than three minutes or explicit incompatible evidence.
4. `unknown`: insufficient evidence.

Do not map Data API `videoDuration=short` to `confirmed_short`; that search filter means under four minutes and is not a Shorts identifier.

### Channel performance and current outliers

- Expand the uploads playlist for each retained channel, bounded by run limits.
- Primary current window: 45 days. Supporting baseline window: 90 days.
- Admit only uploads observed inside the configured supporting window to the
  same-channel/format median baseline. Older uploads may remain visible as
  historical evidence, but must never affect an outlier multiple.
- Compare views/day within the same channel, media class (Shorts, long-form,
  unknown), and repeatable format; exclude the candidate from its median
  baseline. Media class remains part of the key even when preprocessing has
  already supplied a nonempty repeatable-format label.
- Persist cohort size, age, recency bucket, confidence, and calculation version.
- Public competitor profiles are proxies based on upload and public view observations. Never claim private retention, traffic source, or exact channel analytics.

### Matched winner/loser analysis

Select pairs deterministically before AI interpretation. A valid pair shares a channel and topic/format family, has similar duration and publication timing, and has a material performance gap. Retain match basis and a performance ratio calculated from the same outlier-multiple metric that selected the winner. Pair videos without reuse, permit multiple independent pairs from one channel, and require only that the bounded set spans at least two channels. AI compares topic, hook, opening visual, bounded transcript excerpts/structure, pacing, captions, reveal, and payoff, and must preserve uncertainty.

### Visual and viral-mechanism analysis

Browser media observations persist first spoken line, transcript, frame references, opening visual, captions, structure, duration, scene/pacing proxies, reveal timing, motion and visual features. Analyze an operator-configured number of representative videos per run, defaulting to six. OpenRouter may receive local screenshots as multimodal image inputs and must return the `VisualStructureAnalysis` JSON schema. Fake AI supplies deterministic closed fixtures; Ollama receives actual bounded image bytes and fails cleanly when no decodable image is available. The deterministic zero-key live provider likewise reads actual bounded image inputs and limits its claims to decoded/query-provenance facts.

The configured heavy-media limit applies before any download, Deepgram request,
ffmpeg extraction, or other heavy media work. It has no hard-coded six-video
ceiling; the research request's bounded video set remains the outer limit.
Representative selection is deterministic: prioritize views/day while taking
one video per channel before filling remaining slots. Heavy targets execute
sequentially and raw media is deleted after each analysis. Lightweight browser
observations may still cover the bounded upload set.

### Keyless channel traversal and direct inputs

When `YOUTUBE_API_KEY` is absent, yt-dlp traverses each retained channel's
public `/videos` feed with a hard playlist bound, de-duplicates video IDs, and
then enriches only those IDs. This preserves the same-channel history required
for 45/90-day baselines, channel profiles, and winner/loser comparisons.

Publication time is mandatory for performance analytics. Normalize
`timestamp`, `release_timestamp`, `upload_date`, or `release_date`; if none is
valid, exclude the video rather than substituting observation time. A private,
members-only, removed, malformed, or undated playlist entry must not discard
the other usable uploads. Record each skipped entry as bounded evidence with
channel/video identifiers, source URL, observation time, reason, error code,
and available playlist metadata.

Failure to fetch one channel's bounded `/videos` feed is channel scoped. A
typed non-configuration source failure produces one
`keyless_channel_feed_skipped` diagnostic and expansion continues with the
remaining channels. Configuration and unexpected failures still propagate.

Per-video fault isolation applies equally to initial search-result enrichment
and channel-upload expansion. Drain and persist source diagnostics immediately
after each enrichment boundary, before failing a run that has no usable videos.
An unavailable initial candidate must not discard its usable peers.

Fault isolation must not hide source-wide configuration failures. Missing
executables, invalid provider configuration, and equivalent `CONFIGURATION`
errors propagate immediately with their original typed code and message;
candidate-specific typed validation and extraction/source failures become skip
diagnostics. Unexpected implementation exceptions are never swallowed. Invalid
yt-dlp JSON is normalized to a typed source-response failure at the adapter
boundary.

Initial enrichment receives the corresponding discovery record as optional
context. If extraction fails before yt-dlp returns metadata, the diagnostic
must retain every already-observed bounded field: canonical URL, title,
channel ID/title, visible views/age, Shorts presentation, result position,
screenshot reference, and raw discovery payload.

When extraction succeeds with sparse metadata, overlay its nonempty values on
the bounded discovery context. Null or empty extracted fields must not erase a
known discovery channel, title, or other provenance field. During channel-feed
traversal, seed the traversed channel ID into that context so a sparse feed
entry and sparse video extraction cannot collapse into `unknown-channel`.
Channel presentation falls back to an already-observed discovery
`channel_title` when video extraction omits `channel` and `uploader`.

Capture the canonical YouTube discovery URL before per-video extraction.
Post-extraction validation diagnostics must use that captured URL, or a
reconstructed canonical watch URL when none was observed. Temporary CDN/media
stream URLs returned in yt-dlp's `url` field may remain in bounded raw payload
diagnostics but must never replace the diagnostic's authoritative source URL.

Treat missing, null, nonnumeric, nonpositive, NaN, or infinite aspect ratio as unknown and
non-confirming. Keyless metadata may mark a video as probable-Short input only
when duration is bounded and a positive finite portrait aspect ratio is present;
YouTube-rendered Shorts presentation remains the stronger confirmation.

Video-level yt-dlp metadata must never populate channel-only fields. In
particular, a video's `description` is not a channel description; preserve the
channel description as unknown unless a channel-level response supplies it.

Direct YouTube watch, Shorts, short-link, and channel URLs bypass search-query
encoding. Browser artifact names are generated from a sanitized readable
prefix plus a stable hash; user input is never used as a path component.
The video and channel direct-analysis endpoints validate HTTPS YouTube hosts
and reject blank, external, search-page, and wrong-resource-type URLs before a
run is created. Channel discovery extracts normal rich/grid video renderers,
including `#video-title-link`, in addition to search and Shorts renderers.

### Research job execution

Closed-test runs execute synchronously in the API process to keep the fixture
gate self-contained. Development, live-test, and production requests persist a
queued task and submit an idempotent `research:<run_id>:attempt:<n>` ARQ job before
returning HTTP 201. The research worker owns stage transitions and terminal
task status. Cancellation aborts the queued/running job and records a cancelled
task without requiring the request to wait for the research pipeline.

Every non-terminal run is resumable under the same research-run ID. The
orchestrator persists versioned checkpoints after discovery, expanded
enrichment, every completed video, each structured AI operation, candidate
asset validation, comparative analysis, and final synthesis. A retry keeps
search/browser/media/evidence records, deletes only incomplete derived
relational output, and replays unfinished steps. Worker startup requeues runs
left active by a container restart, while `POST /api/research-runs/{id}/resume`
allows an operator to resume a failed run after a code/configuration repair.
Completed model responses remain schema-validated when loaded from a
checkpoint. Raw video is still deleted in the per-video `finally` boundary;
checkpoint state contains normalized metadata and derived observations, never
the downloaded media file.

Worker coroutine cancellation is not itself proof of user intent: Railway
deployment SIGTERM and ARQ retry use the same asyncio signal as an explicit job
abort. The worker refreshes the database and records a terminal cancellation
only when the API has already persisted `cancelled`; otherwise it leaves the
task queued/recoverable for checkpoint redelivery. The explicit resume endpoint
may resume a failed or cancelled run under the same ID; completed runs remain
immutable.

Hosted schema changes run as a one-shot/pre-deploy Alembic migration. Before
ARQ can dequeue any job, worker startup polls the shared database and requires
its recorded Alembic revision set to equal the code's migration heads. A failed,
missing, or still-running migration therefore prevents worker startup instead
of exposing queued research to an old schema.

### Recommendation hard gates

A positive Shorts recommendation requires all of:
- 10 clip-validated distinct ideas;
- at least 70% clip and semantic-fit coverage, 60% reveal coverage, and two independent source origins; licensing metadata is informative and non-gating;
- three successful independent channels;
- three current outlier videos across at least two channels;
- three matched winner/loser pairs;
- mechanism replication across two channels;
- saturation risk at or below the configured maximum.

Every gate reports observed value, threshold, comparison, pass/fail, and unit in `demand_assessment.hard_gates`.

## 12. AI contracts

AI output must be structured.

### Niche classification
```json
{
  "broad_market": "",
  "niche": "",
  "sub_niche": "",
  "repeatable_format": "",
  "confidence": 0.0
}
```

### Viral mechanism
```json
{
  "primary_mechanism": "",
  "secondary_mechanisms": [],
  "viewer_question": "",
  "hook_pattern": "",
  "payoff_pattern": "",
  "supporting_evidence_ids": [],
  "alternative_explanation": "",
  "confidence": 0.0
}
```

### Winner/loser comparison
```json
{
  "winner_video_id": "",
  "loser_video_id": "",
  "topic_difference": "",
  "hook_difference": "",
  "opening_visual_difference": "",
  "structure_difference": "",
  "pacing_difference": "",
  "payoff_difference": "",
  "hypothesis": "",
  "confidence": 0.0
}
```

### Evidence-bound synthesis pipeline

The AI worker operates in four bounded stages:
1. Per-video extraction from a source-labelled packet containing public metadata, deterministic outlier facts, transcript excerpts, browser observations, and visual analysis.
2. Cross-video candidate synthesis from deterministic demand/gate results, per-video observations, matched comparisons, mechanism evidence, ideas, clip preflight, saturation, and production constraints.
3. Independent research criticism that challenges creator advantage, recency, channel diversity, event dependence, saturation, footage supply, idea ceiling, and unsupported inference.
4. Portfolio-level report synthesis across adjudicated candidates.

Every synthesis and critic output must cite `EvidenceRecord` IDs supplied in its packet. Deterministic validation rejects unknown citations. AI may explain evidence, reduce confidence, or block a positive recommendation, but it may not calculate authoritative metrics, pass a failed hard gate, promote a deterministic verdict, or invent transcript timestamps. When timestamps are unavailable, transcript excerpts retain null timing and explicit provenance.

The AI service must reject responses that do not validate against the schema.

## 13. Research orchestration

State machine:

```text
QUEUED
  -> PLANNING
  -> DISCOVERING
  -> ENRICHING
  -> ANALYSING
  -> REPORTING
  -> COMPLETE
```

Failures record the stage and error.

### Planning
Create:
- seed queries
- query budget
- browser budget
- target candidate count
- recency windows
- required evidence threshold

Raw research input accepts at most 20 seed entries of at most 2,048 characters
each. These bounds apply before whitespace normalization, de-duplication, or
query expansion. Expanded queries are generated only up to the configured
`max_queries` limit rather than materializing every seed/variant combination.

### Discovery
Collect candidate:
- videos
- channels
- queries
- format hints

### Enrichment
Populate exact structured metadata.

### Analysis
Run:
- channel baselines
- outliers
- format clustering
- winner/loser matching
- viral-mechanism analysis
- saturation
- idea ceiling
- clip ceiling
- Shorts/long-form fit

### Reporting
Rank candidates, preserve evidence lineage, synthesize a cited portfolio conclusion, and expose independent critic findings.

## 14. Recommendation model

Use separate Shorts and long-form assessments.

Do not expose an unexplained magic number as if it were a YouTube metric.

Internally, the engine may calculate configurable composite scores.

Recommended Shorts components:
- audience demand
- recent momentum
- repeated outliers
- idea ceiling
- clip ceiling
- saturation/entry gap
- production feasibility

Recommended long-form components:
- audience demand
- recent momentum
- repeated outliers
- idea ceiling
- saturation/entry gap
- production feasibility
- topic depth/durability

Use hard gates before a positive verdict:
- multiple-channel evidence
- multiple recent outliers
- sufficient idea ceiling
- identifiable mechanism
- reproducible production path
- manageable saturation
- sufficient evidence confidence

Verdicts:
- Start now
- Run a 20-video test
- Watch for momentum
- Shorts only
- Long-form only
- Promising but footage-constrained
- Demand exists but oversaturated
- Insufficient evidence
- Reject

## 15. API surface

Minimum endpoints:

```text
POST   /api/research-runs
GET    /api/research-runs
GET    /api/research-runs/{id}
POST   /api/research-runs/{id}/cancel
POST   /api/research-runs/{id}/resume
GET    /api/research-runs/{id}/candidates
GET    /api/research-runs/{id}/evidence
GET    /api/research-runs/{id}/report

POST   /api/analyse/video
POST   /api/analyse/channel
POST   /api/analyse/niche

GET    /api/channels/{id}
GET    /api/videos/{id}
GET    /api/system/source-health
GET    /api/system/quota
```

Use OpenAPI generated by FastAPI.

The run collection is ordered deterministically by newest creation timestamp
and ID, accepts bounded `limit` (1–100) and nonnegative `offset` query
parameters, and returns total/limit/offset metadata plus RFC 8288 next/previous
links in response headers. The default remains the newest 50 runs so existing
dashboard clients retain their list response contract while older runs remain
discoverable.

## 16. Frontend requirements

Pages:

### Dashboard
- Recent research runs
- New research button
- Source health
- quota status
- last successful run

### New Research
Inputs:
- Shorts / long-form / both
- regions
- language
- seed topic(s)
- broad discovery toggle
- recency
- research depth
- production constraints

### Research Run
Show live stage/status and final results.

Tabs:
- Overview
- Niches
- Demand
- Outliers
- Competitors
- Viral Mechanisms
- Winners vs Losers
- Idea Ceiling
- Clip Ceiling
- Evidence

### Niche detail
Show:
- niche hierarchy
- verdict
- Shorts/long-form fit
- supporting channels/videos
- major outliers
- mechanism
- risks
- differentiation
- first test ideas

## 17. Observability
Use structured JSON logs.

Every run must include:
- research_run_id
- task_id
- source
- stage
- routing decision
- quota delta
- browser profile
- durations
- errors

Expose `/health` and source-health endpoints.

## 18. Security and data handling
- Never commit secrets.
- Browser profile directories must be gitignored.
- Screenshots/runtime browser artifacts must be outside source control.
- Validate URLs before browser navigation.
- Use explicit allowed host rules in live browser tasks.
- Treat browser-extracted text as untrusted input.
- AI prompts must separate instructions from retrieved page content.
- Hosted fixture validation must prove external networking is blocked when isolation is under test.

## 19. Coding constraints
- Full type hints in Python.
- TypeScript strict mode.
- Small modules with clear ownership.
- No business logic in route handlers or UI components.
- No direct DB access from source connectors.
- No AI calls from deterministic analytics.
- No hidden global mutable state.
- Configuration through typed settings.
- Migrations for schema changes.
- Idempotent background tasks.
- No TODO placeholders in required MVP paths at completion.

## 20. Definition of implementation complete
Implementation is ready for hosted validation when:
- repository structure exists
- application code exists
- migrations exist
- source adapters exist
- source router exists
- browser worker exists
- API worker exists
- analytics exist
- AI contracts/provider exist
- orchestrator exists
- report engine exists
- frontend exists
- fixtures exist
- test files exist
- Docker Compose exists
- scripts exist
- README exists
- `.env.example` exists
- closed/live test runners exist
- canonical docs and Build state are updated
