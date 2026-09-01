# Implementation Plan

## Execution model
Codex uses this workstation only to inspect and edit the repository. Every
build, test, migration, browser check, smoke test, and research run executes in
the deployed Vercel/Railway environment. No project dependency installation,
local service startup, local browser execution, or local test execution is
permitted on this workstation.

**Important sequence:**
1. Read all canonical documents.
2. Inspect repository.
3. Write architecture, production code, fixtures, test code, scripts, configuration, and documentation.
4. Do not run unit, integration, E2E, browser, or live tests locally.
5. Deploy completed changes to Vercel/Railway and run the relevant validation there.
6. Treat hosted failures as test results, repair the correct layer, redeploy, and verify in hosted compute.
7. A closed-suite pass is not a prerequisite for deployment or live validation.
8. Use live APIs only in explicitly configured hosted live-test or production runs.

Static inspection and source edits are allowed locally. Dependency resolution,
builds, tests, browsers, services, and application runs are hosted-only.

---

## Phase 0 — Repository bootstrap

Create:
- root `AGENTS.md`
- `README.md`
- `.gitignore`
- `.env.example`
- `docker-compose.yml`
- `Makefile`
- Python project configuration
- frontend project configuration
- canonical docs path
- application folders from Technical Specification

Configure:
- Python 3.12+
- FastAPI
- SQLAlchemy/Alembic
- Redis/ARQ
- PostgreSQL/pgvector
- Next.js/TypeScript
- Playwright
- pytest
- frontend testing

Deliverable:
Repository boots structurally with all dependencies declared.

Do not run tests.

---

## Phase 1 — Shared configuration and contracts

Implement:
- typed application settings
- runtime-mode validation
- source enums
- research-run enums
- shared Pydantic contracts
- API response contracts
- AI output schemas
- error taxonomy
- source health schema
- quota schema

Add safeguards:
- `closed_test` cannot instantiate live source clients.
- `live_test` requires explicit live configuration.
- browser profile paths are outside source control.

Deliverable:
A single shared contract layer used by sources, orchestration, analytics, and API.

Do not run tests.

---

## Phase 2 — Persistence layer

Implement SQLAlchemy models and migrations for:
- ResearchRun
- SearchObservation
- Channel
- ChannelSnapshot
- Video
- VideoSnapshot
- CommentSample
- BrowserMediaObservation
- FormatCluster
- OutlierResult
- ViralMechanismAnalysis
- WinnerLoserComparison
- NicheCandidate
- EvidenceRecord
- source routing/quota audit records
- task/job records if required

Implement repositories:
- research runs
- channels
- videos
- observations
- evidence
- analytics results
- candidates

Requirements:
- idempotent upserts for YouTube entities
- UTC timestamps
- provenance fields
- freshness helpers
- transaction boundaries in service layer

Do not run tests.

---

## Phase 3 — YouTube Data API source

Implement a typed async client supporting:
- search
- video enrichment
- channel enrichment
- channel uploads playlist traversal
- comment thread sampling

Implement:
- API key configuration
- request batching
- quota accounting
- daily search budget
- reserved search-call floor
- retries/backoff
- response normalization
- freshness-aware cache/persistence hooks
- fixture adapter with the same interface

Create representative fixture payloads for:
- search results
- videos
- channels
- playlist items
- comments
- empty results
- unavailable comments
- transient error
- quota error

Do not call the live API.

Do not run tests.

---

## Phase 4 — Chromium source

Implement the Playwright research worker.

Required capabilities:
- launch a persistent Chromium context against a unique disposable user-data
  directory for each operation
- choose research profile
- bounded query execution
- collect search-result observations
- inspect channel pages
- inspect video pages
- inspect Shorts presentation
- capture related-video links
- capture visible transcripts where available
- capture screenshots
- partial-result handling
- source provenance
- retry limits
- tab limits
- scroll limits
- preserve screenshots separately from browser session state and sweep legacy
  locks/caches without deleting unexpired evidence images

Build a local fixture web application/server that simulates:
- YouTube search page
- channel page
- video page
- Shorts page
- related videos
- visible transcript
- missing transcript
- lazy-loaded results
- page variation / selector fallback

The live and fixture browser adapters must share a common interface.

Do not navigate to live YouTube during this phase.

Do not run tests.

---

## Phase 5 — Source router and research planner

Implement the source router.

Inputs:
- task
- runtime mode
- search quota state
- browser limits
- required fields
- known IDs
- reproducibility requirements
- source health

Implement routing rules from Technical Specification.

Implement research planner:
- accepts seeds or broad discovery
- generates bounded query tree
- sets target candidate counts
- sets expansion depth
- tracks already-visited queries/channels/videos
- prevents cycles
- defines stop conditions

Stop conditions include:
- query budget exhausted
- target candidate count reached
- diminishing new-candidate rate
- maximum expansion depth
- evidence threshold reached
- run cancelled

Log every routing decision.

Do not run tests.

---

## Phase 6 — Discovery and enrichment pipeline

Implement orchestration stages:

1. `planning`
2. `discovering`
3. `enriching`

Discovery:
- Chromium candidate collection
- optional API search according to router
- deduplicate videos/channels
- query expansion using deterministic extraction + AI where configured
- persist observations

Enrichment:
- batch video IDs
- enrich video metadata
- enrich channels
- traverse uploads playlist
- obtain recent comparable uploads
- sample comments for shortlisted videos

Requirements:
- resumable/idempotent jobs
- versioned checkpoints after discovery, expansion, each video, structured AI
  steps, candidate asset validation, and report synthesis
- automatic active-run recovery after a hosted worker restart plus an explicit
  same-run resume control for failed jobs
- retries preserve evidence and completed media derivations while rebuilding
  only incomplete relational analysis output
- no duplicate work in same run
- clear stage transitions
- evidence records for major observations

Do not run tests.

---

## Phase 7 — Deterministic analytics engine

Implement:
- video age calculation
- views/day
- cohort construction
- channel median baseline
- outlier multiple
- outlier labels
- snapshot growth
- momentum
- recent-outlier count
- repeated-outlier analysis
- competitor activity metrics
- upload density
- cluster concentration
- title/topic similarity helpers
- confidence input calculations

Keep analytics pure where possible.

Every calculation output must include:
- version
- inputs/evidence refs
- output
- timestamp/config

Do not run tests.

---

## Phase 8 — Clustering and niche construction

Implement:
- text normalization
- embeddings provider
- local sentence-transformers adapter
- deterministic fake embeddings for closed testing
- video/topic clustering
- format clustering
- representative-video selection
- direct vs adjacent competitor classification inputs

Construct hierarchy:
- broad market
- niche
- sub-niche
- repeatable format
- viral mechanism

Do not run tests.

---

## Phase 9 — AI analysis layer

Implement:
- `AIProvider` protocol
- OpenRouter provider with structured JSON schema output
- Ollama provider fallback
- deterministic fixture provider
- structured-schema enforcement
- retry/repair for invalid structured output
- prompt-injection-safe data delimiters
- evidence-bound prompts

Implement analyses:
- niche classification
- query expansion
- winner/loser comparison
- viral-mechanism hypothesis
- format explanation
- competitor differentiation
- idea generation
- report synthesis
- research critic

The completed reasoning flow must use bounded per-video evidence packets, candidate-level research-editor synthesis, an independent critic call, deterministic evidence-ID validation/adjudication, and portfolio report synthesis. Persist all four stages in the evidence ledger with provider, version, confidence, and provenance. AI can only interpret or lower confidence; deterministic analytics and recommendation gates retain decision authority.

The research critic must challenge:
- creator-specific advantage
- stale virality
- insufficient channel diversity
- insufficient recent outliers
- temporary-event dependence
- saturation
- weak footage path
- weak idea ceiling
- unsupported AI inference

Do not run tests.

---

## Phase 10 — Winner/loser and mechanism engine

Implement winner/loser matching:
- same channel where possible
- similar age window
- same format class
- similar duration bucket
- strong performance separation

Use:
- deterministic metrics
- browser observations
- comments
- AI structured comparison

Implement viral-mechanism taxonomy and classifier.

Persist:
- mechanism
- viewer question
- hook pattern
- payoff pattern
- evidence refs
- alternative explanation
- confidence

Do not run tests.

---

## Phase 11 — Idea ceiling

Implement:
1. extract topics from successful videos
2. group subjects/topic families
3. generate candidate ideas
4. embed candidates
5. deduplicate semantically
6. classify viable/non-viable
7. count distinct surviving ideas
8. measure cluster diversity

Expose:
- generated count
- unique count
- duplicate ratio
- cluster count
- format reuse
- series suggestions

Do not run tests.

---

## Phase 12 — Clip ceiling abstraction

Build connector protocol.

MVP implementations:
- deterministic fixture connector
- local/manual asset manifest connector

Prepare adapters/interfaces for future:
- Pexels
- Pixabay
- Wikimedia Commons

Calculate:
- asset coverage by idea
- source diversity
- video vs image coverage
- rights metadata presence
- visual payoff feasibility
- unsupported-idea share

Do not require live asset APIs for MVP completion.

Do not run tests.

---

## Phase 13 — Saturation engine

Implement:
- direct competitor clustering
- adjacent competitor clustering
- active competitor definition
- recent upload density
- direct-format similarity
- title similarity
- repeated-footage metadata placeholder interface
- successful competitor share
- weak copycat share
- improvement-gap inputs

Return a structured saturation assessment with evidence.

Do not run tests.

---

## Phase 14 — Recommendation and reporting engine

Implement separate:
- Shorts assessment
- long-form assessment
- Shorts-to-long bridge assessment

Implement hard gates.

Implement verdict engine:
- Start now
- Run a 20-video test
- Watch for momentum
- Shorts only
- Long-form only
- Promising but footage-constrained
- Demand exists but oversaturated
- Insufficient evidence
- Reject

Report must contain:
- why now
- evidence summary
- demand
- recent outliers
- competitors
- viral mechanism
- winner/loser findings
- idea ceiling
- clip ceiling
- saturation
- risks
- alternative explanation
- differentiation
- recommended initial content test
- continue/reject criteria

Do not run tests.

---

## Phase 15 — API/control plane

Implement FastAPI endpoints from Technical Specification.

Add:
- pagination
- typed errors
- run cancellation
- run status
- source health
- quota status
- report retrieval

Add background job submission through Redis/ARQ.

Do not run tests.

---

## Phase 16 — Frontend

Implement:
- Dashboard
- New Research form
- Research Run view
- Ranked Niches
- Niche Detail
- Demand tab
- Outliers tab
- Competitors tab
- Viral Mechanisms tab
- Winners vs Losers tab
- Idea Ceiling tab
- Clip Ceiling tab
- Evidence tab
- Source health/quota display

Requirements:
- responsive
- clear loading/failure states
- no fake data in normal modes
- demo/fixture mode visibly labelled

Do not run tests.

---

## Phase 17 — Operational tooling and documentation

Implement:
- Makefile commands
- Docker Compose
- migrations entrypoint
- one-shot hosted migration command and worker Alembic-head startup gate
- worker start script
- frontend start
- seed demo
- closed-test runner
- live smoke-test runner
- README setup
- environment docs
- browser profile bootstrap instructions
- worker-owned artifact cleanup and shared storage-status publication
- troubleshooting

Write all test files but do not run them yet.

Update `Build state.md`.

---

# HOSTED VALIDATION POLICY

There is no mandatory local closed-test gate. When validation is useful, deploy
the revision and execute the relevant fixture, integration, browser, or live
check inside Vercel/Railway. Inspect platform build/runtime logs and persisted
run evidence. A failed hosted check is a test result; repair, redeploy, and
repeat without reproducing the stack on this workstation.

## Niche-finding accuracy expansion

Implement before the next relevant hosted validation:
1. Conservative Shorts classification and source evidence.
2. Channel upload expansion, public performance profiles, and 45/90-day outlier cohorts.
3. Deterministic matched winner/loser selection plus structured AI comparison.
4. Transcript, frame, caption, pacing, reveal, and optional multimodal OpenRouter analysis.
5. Rights-aware Pexels/Pixabay live clip preflight with fixture parity.
6. Ten-idea validated ceiling and explicit recommendation hard gates.
7. Multi-factor saturation and evidence-concentration analysis.
8. YouTube-primary trend assessment with optional external corroboration status.
9. Dashboard panels for gates, channel profiles, Shorts status, comparisons, trends, idea validation, clip rights, and saturation.
10. Keyless live-smoke metadata via Chromium/yt-dlp, optional Deepgram word-timestamp transcription, selective-filmstrip visual analysis, multimodal asset-fit checks, unified API-unit accounting, repeated snapshot momentum, competitor ranges, and per-idea faceless annotations.
10. Closed fixtures and tests for each deterministic decision.

## Review remediation before the next hosted validation

1. Filter same-channel/format baseline cohorts to uploads no older than the
   90-day supporting window while retaining rates for candidate reporting.
2. Submit every non-closed run to Redis/ARQ with an idempotent run job; keep
   only closed fixture runs synchronous.
3. Expand a bounded channel `/videos` feed through yt-dlp when no YouTube Data
   API key is configured, then enrich the de-duplicated upload IDs.
4. Select an operator-configured number of channel-diverse, high-velocity
   representative videos, defaulting to six, before download, transcription,
   and filmstrip extraction; process them sequentially with per-video cleanup.
5. Route direct YouTube video/channel URLs without search encoding and hash all
   browser screenshot filenames.
6. Add deterministic unit/integration regressions for every item above, update
   the implementation precheck, then execute relevant validation in hosted compute.

## Keyless provenance and Compose remediation

1. Install Psycopg 3 as a core runtime dependency so both Compose backend and
   ARQ worker can construct the configured SQLAlchemy PostgreSQL engine.
2. Parse yt-dlp publication timestamps and date strings explicitly; reject
   undated videos before recency or views/day calculations.
3. Keep video descriptions out of channel records when only video-level
   metadata is available.
4. Isolate channel expansion failures per upload, continue with usable public
   videos, and drain structured skip diagnostics into the run evidence ledger.
5. Verify driver construction, date parsing/rejection, metadata separation,
   partial-feed resilience, and persisted diagnostics in a hosted fixture suite.

## Uniform keyless enrichment remediation

1. Move per-video exception isolation into the shared yt-dlp enrichment
   boundary used by both initial candidates and channel uploads.
2. Drain initial-enrichment diagnostics into evidence before the no-candidate
   failure check.
3. Normalize duration and aspect ratio defensively; null or nonnumeric aspect
   ratio is unknown and cannot contribute Shorts evidence.
4. Verify mixed usable/inaccessible/undated initial batches survive with
   ordered diagnostics and nullable aspect ratio never raises.

## Keyless failure-boundary and provenance remediation

1. Re-raise typed source-wide `CONFIGURATION` failures before candidate-level
   diagnostic conversion.
2. Extend the enrichment protocol with an optional per-video discovery-context
   map while preserving adapter compatibility.
3. Pass bounded browser discovery fields into initial enrichment and retain
   them when yt-dlp fails before returning metadata.
4. Test exact configuration error propagation, absence of misleading skip
   records, and complete known discovery provenance in initial diagnostics.

## Cohort and keyless channel-boundary remediation

1. Build outlier keys from channel ID, media class, and repeatable format so a
   `both` run cannot mix Shorts and long-form baselines.
2. Convert a typed non-configuration channel-feed failure into a channel-level
   diagnostic and continue expanding later channels.
3. Merge successful sparse extraction over nonempty discovery context so known
   channel/title provenance survives null or absent yt-dlp fields.
4. Require `0 < aspect_ratio < 1` before keyless metadata supplies portrait
   Shorts evidence.
5. Test same-label cross-media cohorts, one-bad-channel continuation, sparse
   success provenance, and zero/negative aspect ratios.

## Sparse keyless identity remediation

1. Seed each channel-feed enrichment context with the channel ID being
   traversed before sparse yt-dlp metadata is merged.
2. Resolve channel display names from retained discovery `channel_title` before
   falling back to an identifier.
3. Capture canonical YouTube source URLs before extraction and keep temporary
   media-stream URLs out of the authoritative diagnostic URL field.
4. Verify sparse expanded uploads, sparse channel titles, preserved Shorts
   URLs, and reconstructed watch URLs in the closed source-adapter suite.

## Candidate allocation, channel discovery, and input-bound remediation

1. Give every retained candidate an independent final clip-validation budget
   of at least ten ideas while preserving bounded per-candidate work.
2. Extract watch and Shorts links from channel rich/grid renderers as well as
   search-result and reel renderers.
3. Reject more than 20 raw seeds or seed strings over 2,048 characters before
   normalization, and lazily stop variant generation at `max_queries`.
4. Validate `/analyse/video` and `/analyse/channel` inputs as HTTPS YouTube
   URLs of the endpoint's declared resource type before creating a run.
5. Keep 46–90-day major outliers as supporting evidence, but exclude them from
   backend and frontend collections labelled as current.
6. Add backend, contract, integration, and frontend regressions for all five
   behaviors before running the relevant hosted validation.

---

# HOSTED LIVE VALIDATION

Live validation does not depend on a local or closed-suite pass:

1. update `Build state.md`
2. confirm the exact hosted prerequisites
3. prepare Vercel/Railway configuration
4. run the bounded live smoke or requested research run in hosted compute

The first live run must be intentionally small:
- one research profile
- one or two seed queries
- limited channel count
- limited API calls
- no unbounded browsing

After live smoke success, a larger research run may be performed.
