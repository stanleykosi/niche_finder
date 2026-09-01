# Build State

## Current execution policy — 2026-08-31

This workstation is editing/control-plane only. Do not install project
dependencies, run builds or tests, start services or browsers, or execute
fixture/live research locally. All future migrations, builds, tests, browser
checks, smoke tests, and research runs execute in the deployed Vercel/Railway
environment. A local closed-test pass is no longer a deployment or live-run
gate; hosted failures are valid test evidence and are diagnosed from platform
logs and persisted run evidence. Historical local closed-test records below
are retained only as provenance and do not override this policy.

This file is the execution ledger for Codex. The canonical source remains the documents in this directory.

## Status values
- NOT_STARTED
- IN_PROGRESS
- COMPLETE
- BLOCKED
- CLOSED_TEST_GREEN
- LIVE_TEST_GREEN

## Overall
`CLOSED_TEST_GREEN`

Three-finding hosted migration/artifact/SQLite remediation is implemented and
the complete closed gate is green. Worker startup is now gated on the shared
database reaching Alembic head; artifact lifecycle and measurement are owned by
the mounted worker and shared with the API through Redis; and Alembic prepares
the configured SQLite parent before opening the database.

Five-finding candidate allocation, channel discovery, request-bound, direct
URL, and current-evidence remediation is implemented and the complete closed
gate is green. Live verification remains separately gated and has not run.

Vercel/Railway deployment preparation was completed on `2026-08-31`. The
hosted boundary is Next.js on Vercel plus FastAPI, ARQ, managed PostgreSQL, and
managed Redis on Railway. The complete closed gate is green after the changes;
no hosting provider or live research source was contacted in that preparation
phase.

The Vercel frontend production deployment completed on `2026-08-31`. Project
`niche-intel-web` is Git-linked to `stanleykosi/niche_finder`, builds from
`apps/web` on `main`, and serves `https://niche-intel-web.vercel.app` with a
verified `200 OK`. Production deployment
`dpl_8uBDRVP3nmSFRTYLD99BBAjYaKiX` is `READY`; its browser bundle contains
`NEXT_PUBLIC_API_BASE_URL=https://api-production-21e27.up.railway.app`; and the
Railway health route permits the exact canonical Vercel origin. The live gate
has not run.

Railway production deployment completed on `2026-08-31` in project
`merry-solace` after the user authorized permanent removal of its obsolete
`seeder`, `getway`, and `hydradb` services and HydraDB volume. The replacement
topology keeps FastAPI, ARQ, private PostgreSQL, and private Redis in one
project. All four services report `SUCCESS`; Alembic reached revision `0009`;
`https://api-production-21e27.up.railway.app/health` returns `live_test`; and
the worker publishes its mounted-volume status through Redis. The free-plan
500 MB worker volume uses a bounded hosted-smoke profile: 0.3 GB managed media,
0.05 GB free-space floor, 100 MB unknown-download reservation, two media videos,
and 600-second maximum duration.

Live credential configuration was verified on `2026-08-31` without exposing
secret values. The API and worker have matching nonempty YouTube Data API,
OpenRouter, Deepgram, Pexels, and Pixabay credentials; bounded authentication
or one-result metadata checks returned HTTP 200 from all five providers. The
configured OpenRouter text model supports JSON-schema structured output and
the configured vision model accepts images and structured output. Both code
services redeployed successfully, Chromium remains healthy, and the worker
publishes its mounted-volume status. The Railway workspace is on the Hobby
tier, whose 0.5 GB per-volume ceiling prevents expanding `worker-runtime` until
the workspace is upgraded; the live research gate itself has not run.

The heavy-media run limit remediation completed its closed gate on
`2026-08-31`. The operator default remains six, but configuration is no longer
rejected above six. Representative selection still applies the configured
bound before heavy work, while the worker continues to download, analyze, and
remove each raw video sequentially so the configured target count does not
multiply local disk occupancy. The complete gate passed with 245 backend
tests, 12 frontend tests, one Playwright end-to-end test, the strict Next.js
build, PostgreSQL migrations, Redis/API/ARQ/fixture/Chromium integration, and
zero live services contacted. The live `storytelling` run remains pending.

The first hosted `storytelling` attempt
`636b16d9-fd9e-4e1e-baad-bcf4b4528607` failed before media work on
`2026-08-31` because Chromium sampled YouTube immediately after
`domcontentloaded`, before its result cards hydrated. The retained worker
screenshot and a bounded DOM probe confirmed a normal HTTP 200 results page,
an optional `Before you continue` consent overlay, zero cards at 0 ms, four at
250 ms, and 15 at 750 ms. Remediation now rejects optional consent without
accepting personalized cookies, waits up to five seconds for cards, pauses
after bounded scrolls, rejects navigation-only Shorts links, and executes an
audited Data API fallback if the hydrated browser result remains empty. Closed
verification passed with 247 backend tests, 12 frontend tests, one Playwright
end-to-end test, the strict Next.js build, PostgreSQL migrations, and the full
local stack with zero live services contacted. The replacement live run is
pending.

The replacement hosted `storytelling` attempt
`cf477e6d-1b4b-42d3-9aeb-3b5595225059` confirmed the Chromium hydration
repair and advanced through discovery, clip preflight, enrichment, and
sequential browser inspection. It then failed on one representative video's
bounded yt-dlp download because YouTube challenged the Railway datacenter IP.
The run-isolated Chromium profile's safe rejected-consent cookies were tested
against metadata-only yt-dlp access and received the same challenge, so they
are not being reused as a false remedy. Remediation is in progress to preserve
the browser observation as explicit partial evidence and continue to later
videos while retaining fatal behavior for configuration errors. That repair
has now passed the complete closed gate with 249 backend tests, 12 frontend
tests, one Playwright end-to-end test, the strict Next.js build, PostgreSQL
migrations, and the full local stack with zero live services contacted;
Railway redeployment and the next live attempt are pending.

The third hosted `storytelling` attempt
`6e9a4976-47c5-44a0-bbf4-46884e0626bd` verified the media-source repair: the
same challenged video (`7oMKfej8b7s`) became explicit browser-only partial
evidence, released its reservation, and later targets continued. The run was
then deliberately cancelled after eight videos because every watch-page
inspection exposed a separate Playwright timeout and no Chromium frame file
was produced. Discovery remained hydrated and functional; the remaining fault
was isolated to video-page navigation/cleanup. The deployed repair now uses
response-commit navigation, bounded watch-surface hydration, bounded
per-operation frame work, and bounded Chromium context/driver shutdown.

The fourth hosted `storytelling` attempt
`87ade25c-371e-4046-80eb-af86be2a1bfa` began on the hosted Chromium repair and
was deliberately cancelled after one in-process OpenRouter-backed preflight
left the evidence ledger unchanged for more than ten minutes. No Chromium,
yt-dlp, or ffmpeg child was active and the worker remained healthy, isolating
the missing boundary to the SDK request. A fifth hosted attempt
`1755652c-3772-4037-968f-0ee89f087095` then failed cleanly at the original
60-second request deadline during initial idea generation. Hosted probes
confirmed the key, model, structured-output schema, and connectivity were
valid: classification completed in 17.5 seconds and a ten-idea response took
about 56 seconds, while a thirty-idea response reproduced the deadline. The
request remains bounded against a dead upstream, but its configurable default
is now five minutes (with a thirty-minute validated upper range) so normal
large structured generations can finish before the final live attempt.

The subsequent hosted attempts exposed two independent durability faults. Run
`e79d2381-d785-4ee7-bfb6-a17190faad90` persisted thirteen completed video
observations before the 1 GB worker reached its memory ceiling; raw downloads
had already been deleted sequentially and worker disk usage remained about
0.12 GB, so this was memory pressure rather than a storage leak. A requested
Railway 2 GB replica override did not persist: hosted metrics continued to show
a 1 GB limit after the config commit and restart. Replacement run
`660496c9-4cab-44f0-8413-38cd6c2ee61c` then received a complete OpenRouter idea
list at the JSON root instead of the requested object wrapper.

Checkpoint/resume remediation is now implemented pending hosted verification.
The destructive retry reset has been replaced with versioned evidence-backed
checkpoints for discovery, expanded enrichment, each completed video, every
structured AI step, candidate asset/trend work, comparisons, and final
synthesis. Active runs are requeued after worker restart, failed runs have a
same-ID resume endpoint, completed model/video work is replay-safe, and only
incomplete derived relational rows are rebuilt. OpenRouter deterministically
normalizes the observed root idea-list shape and retries other malformed
structured responses within the existing five-minute total deadline. Worker
concurrency is one, the ARQ job timeout is four hours, and `tini` is PID 1 for
hosted child-process reaping. The thirteen persisted videos in run `e79d...`
remain the intended resume source; they are not scheduled for re-download.

The first checkpoint-resume deployment reached attempt 2 and proved that the
same run ID and thirteen completed videos were retained, then exposed a legacy
Chromium profile lock from the replaced container. The persistent volume still
contained a `SingletonLock` naming dead PID 3225, so Chromium refused to open
the first unfinished video. The browser adapter now separates stable evidence
directories from unique disposable user-data directories, startup cleanup
removes legacy browser locks/caches but preserves screenshots, and a transient
Chromium launch failure degrades one video to explicit partial evidence instead
of failing the full run. Hosted redeployment and same-ID attempt 3 verification
are pending; no local test or research workload was run.

Attempt 3 then confirmed the production worker still had a 1 GB memory limit:
baseline usage reached about 0.87 GB while disk usage fell to about 0.058 GB.
The live sentence-transformers adapter was the unnecessary resident-memory and
image-size cost. Hosted and fixture clustering now share a deterministic
384-dimensional lexical/bigram/character-fragment provider, and unused
sentence-transformers, Torch/CUDA, NumPy, scikit-learn, and Polars dependencies
have been removed. This preserves reproducible cosine clustering/deduplication
without loading learned weights. Hosted verification is pending; no local test,
build, browser, or research process was run.

The Railway agent's forced restart during the unsuccessful memory-limit change
then exposed a cancellation/redelivery ambiguity: ARQ scheduled the interrupted
attempt again, but the old worker persisted `cancelled` for the deployment
SIGTERM, causing the redelivery to no-op. The worker now refreshes authoritative
run state on `CancelledError`, preserves API-requested cancellation, and marks
platform interruption queued for redelivery. The explicit resume endpoint now
also permits a cancelled run to be resumed under its existing ID; complete runs
remain immutable. Hosted verification is pending.

Attempt 4 ran on the lightweight worker and reached the next structured-AI
boundary without a memory or Chromium failure, then OpenRouter returned
truncated JSON with `Unterminated string`. The retry classifier previously
matched selected decoder message fragments rather than `JSONDecodeError`
itself, so this valid retry case failed after one attempt. JSON decode and
Pydantic validation failures are now typed retryable within the existing
five-minute total deadline. The same-ID run remains checkpointed for the next
hosted attempt.

## Implementation checklist

| Area | Status | Notes |
|---|---|---|
| Repository bootstrap | COMPLETE | Root config, Compose, Makefile, Python and Next.js manifests |
| Shared config/contracts | COMPLETE | Typed runtime gates, strict fixture/live AI separation, bounded raw seeds, resource-specific direct YouTube URLs, keyless aspect provenance, and Pydantic contracts |
| Database models/migrations | COMPLETE | UUID schema, 64-bit counters, and batch-safe fresh plus existing SQLite/PostgreSQL upgrades through 0009 |
| Runtime storage lifecycle | COMPLETE | Dedicated-root validation, worker-only mounted-filesystem ownership, Redis-published worker measurements, raw finally-deletion, retention, artifact ledger, atomic cross-process reservations, reservation-sized yt-dlp limits, output monitoring, and cancellation-safe child reaping |
| Repositories | COMPLETE | Database-native conflict handling for shared channels/videos/snapshots/comments plus retry-idempotent run output |
| YouTube API source | COMPLETE | Typed optional adapter, every-attempt quota accounting, 403 quota taxonomy, diagnostics, retries, and <=50-ID batching |
| Keyless YouTube metadata | COMPLETE | Channel-feed isolation, sparse channel identity/title retention, canonical diagnostic URLs, typed failures, strict dates, and positive aspect validation |
| YouTube fixture source | COMPLETE | Strong, one-hit, saturated, stale fixtures |
| Chromium source | COMPLETE | Disposable launch-isolated user-data directories, retained evidence-only profiles, locale/region/recency discovery, channel rich/grid extraction, disabled-browser API routing, query-safe direct URLs, bounded captures, and partial results |
| Browser fixture source/site | COMPLETE | Local YouTube-shaped pages and semantic fixture adapter |
| Quota manager | COMPLETE | Atomic database-backed daily ledger shared by API and every ARQ worker; Pacific-midnight rollover and one status view for search/video/channel/playlist/comment units |
| Source router | COMPLETE | Development/closed fixture provenance plus live rules that consume probed browser/API capability health and execute audited API fallback |
| Research planner | COMPLETE | Explicit seeds remain focused and bounded before lazy expansion; API and UI empty inputs default consistently to deterministic 12/20-market concrete portfolio sweeps |
| Discovery pipeline | COMPLETE | Every bounded portfolio market is observed before cross-market round-robin selection; total capacity reserves two history slots per retained discovery channel |
| Enrichment pipeline | COMPLETE | Channel feeds request at least three records when operator bounds permit and merge uploads round-robin into three-record performance cohorts |
| Deterministic analytics | COMPLETE | Separate media cohorts, configured labels/gates, and display-only historical uploads excluded from downstream decision cohorts |
| Embeddings/clustering | COMPLETE | Shared deterministic 384-dimensional lexical/bigram/character-fragment vectors for topic-within-format clustering and idea deduplication; no learned runtime or heavyweight ML dependency |
| AI provider abstraction | COMPLETE | Semantic image validation is an explicit capability; structure-only deterministic inspection reports semantics/reveal as unavailable and cannot pass the clip gate |
| OpenRouter provider | COMPLETE | Optional SDK provider with structured schemas, bounded transient retries, and clean failure |
| Ollama provider | COMPLETE | Exact Pydantic JSON-Schema HTTP provider with mandatory base64 image inputs, bounded transient retries, and same-provider structured repair |
| Fake AI provider | COMPLETE | Deterministic evidence-bound closed-test provider |
| Winner/loser analysis | COMPLETE | Independent no-reuse pairs per semantic candidate, bounded transcripts, two-channel spanning, and outlier-multiple-consistent ratios |
| Viral-mechanism analysis | COMPLETE | Replication is limited to valid citations of positive-confidence mechanism-bearing observations across channels |
| Idea-ceiling engine | COMPLETE | Hard minimum of 10 semantically distinct, clip-validated ideas |
| Clip-ceiling abstraction | COMPLETE | Preliminary work stays shared and bounded, while every retained candidate receives an independent authoritative final budget of at least ten checks |
| Saturation engine | COMPLETE | Active competitors, retained-window upload density, performance, title/format similarity, weak copycats, concentration, and explicit evidence-window provenance |
| Recommendation engine | COMPLETE | Eight auditable gates plus independent media assessments and a semantic Shorts-to-long-form bridge |
| Report engine | COMPLETE | Evidence-bound candidate/report synthesis, critic output, citation validation, post-adjudication candidate ranking, evidence summary, and action plan |
| FastAPI endpoints | COMPLETE | Request-scoped repository sessions use an async generator, all repository consumers stay on the async boundary, and teardown closes each session |
| Redis/ARQ jobs | COMPLETE | Idempotent Redis submission and redelivery, atomic partial-output replacement, terminal no-ops, per-job sessions/orchestrators, abort-enabled cancellation, and run-isolated browser profiles |
| Next.js dashboard | COMPLETE | App Router dashboard with truthful fixture/Data-API/keyless provenance and an independently selected latest successful signal |
| Research-run UI | COMPLETE | Next.js 15 async params/search params, terminal-aware one-second polling, truthful source labeling, evidence-tab initialization, and media-safe combined assessments |
| Niche-detail UI | COMPLETE | Media-safe detail route renders supporting channels/videos, filters major outliers to the current bucket, and renders synthesis risks, differentiation, critic output, and candidate-specific actions |
| Evidence UI | COMPLETE | Source/timestamp/confidence ledger including browser transcripts, frames, and provenance |
| Docker Compose | COMPLETE | Internally network-isolated Postgres, Redis, migrated API, healthy ARQ worker, frontend, fixture server, and optional Ollama profile |
| Vercel/Railway deployment | COMPLETE | Vercel app-root config, one-shot Railway migration plus worker revision gate, Railway-compatible API image/port, hosted Postgres URL normalization, configurable CORS, worker-owned volume/status boundary, and deployment runbook verified by the complete closed gate |
| Vercel frontend production | COMPLETE | Git-linked `apps/web` project is deployed from `main`; production is `READY`; canonical domain returned `200 OK`; Railway API URL is embedded in the browser bundle and exact-origin CORS is verified |
| Railway production runtime | COMPLETE | API, private ARQ worker, private PostgreSQL, and private Redis are healthy in one project; migration reached 0009, API health is verified, and worker storage status is published |
| Makefile/scripts | COMPLETE | Closed/live tooling plus a schema-valid Python seed-demo payload with no request on import |
| README/environment docs | COMPLETE | Setup, live gate, evidence and safety docs |
| Test fixtures | COMPLETE | Date-anchored API/browser/AI/assets plus rejection scenarios |
| Unit tests written | COMPLETE | Config, quota, routing, analytics, dedup, AI, sources, persistence, legacy SQLite upgrades, and operational payloads |
| Integration tests written | COMPLETE | Pipeline, API boundary, stable run pagination, and browser fixture flow |
| Browser tests written | COMPLETE | Semantic fixture contract and bounded browser flow |
| Frontend tests written | COMPLETE | Vitest contracts, static UI smoke, Playwright E2E specs |
| E2E tests written | COMPLETE | Frontend dashboard path and full-system path |
| Closed-test runner | COMPLETE | Implementation/precondition checks plus focused regressions passed in the complete gate |
| Live-smoke runner | COMPLETE | Explicit zero-key-capable live gate with schema-valid canonical thresholds plus bounded Chromium/API/analytics/AI/report execution and classified failures |

## Gates

### Implementation complete
`YES — VERIFIED BY CURRENT CLOSED GATE`

The niche-finding accuracy expansion, keyless live path, Deepgram/selective-filmstrip media analysis, multimodal clip validation, unified quota accounting, date-anchored fixtures, production code, tests, scripts, and canonical documentation are implemented.

Required implementation files, fixtures, tests, scripts, UI, and docs have been written. Live sources are gated from closed mode.

### Closed test
`HISTORICAL_LOCAL_RESULT — NON-GATING`

Current OpenRouter deadline remediation verification record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-31`;
- result: `252 Python tests passed; frontend smoke passed; 12 Vitest tests
  passed; strict Next.js 15 production build/type checking passed; fresh
  PostgreSQL migrations through 0009 passed; PostgreSQL, Redis, FastAPI, ARQ,
  fixture, and Next.js boundaries passed; Chromium fixture-site probe passed;
  1 full-stack Playwright UI submission/report/candidate/evidence E2E passed;
  live services contacted 0`;
- the OpenRouter SDK receives the configured timeout and one application-level
  total deadline covers every retry for a structured request;
- a client coroutine that never returns is cancelled at that deadline rather
  than holding an ARQ research job indefinitely;
- Docker was unavailable in this WSL environment, so the strict local
  six-process fallback verified the same service boundaries.

Prior verified gate:

Current Chromium video-page remediation verification record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-31`;
- result: `251 Python tests passed; frontend smoke passed; 12 Vitest tests
  passed; strict Next.js 15 production build/type checking passed; fresh
  PostgreSQL migrations through 0009 passed; PostgreSQL, Redis, FastAPI, ARQ,
  fixture, and Next.js boundaries passed; Chromium fixture-site probe passed;
  1 full-stack Playwright UI submission/report/candidate/evidence E2E passed;
  live services contacted 0`;
- watch-page navigation stops at response commit and then requires a bounded
  hydrated watch/Shorts surface rather than waiting indefinitely for
  `domcontentloaded`;
- frame operations and Chromium context/driver shutdown are bounded, and one
  unavailable frame cannot discard other successful samples;
- Docker was unavailable in this WSL environment, so the strict local
  six-process fallback verified the same service boundaries.

Prior verified gate:

Current media source-failure remediation verification record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-31`;
- result: `249 Python tests passed; frontend smoke passed; 12 Vitest tests
  passed; strict Next.js 15 production build/type checking passed; fresh
  PostgreSQL migrations through 0009 passed; PostgreSQL, Redis, FastAPI, ARQ,
  fixture, and Next.js boundaries passed; Chromium fixture-site probe passed;
  1 full-stack Playwright UI submission/report/candidate/evidence E2E passed;
  live services contacted 0`;
- per-video yt-dlp source unavailability is retained as explicit browser-only
  partial evidence and releases its download reservation before later targets;
- missing media executables retain their typed fatal configuration boundary;
- Docker was unavailable in this WSL environment, so the strict local
  six-process fallback verified the same service boundaries.

Prior verified gate:

Current three-finding deployment remediation verification record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-31`;
- result: `245 Python tests passed; frontend smoke passed; 12 Vitest tests
  passed; strict Next.js 15 production build/type checking passed; fresh
  PostgreSQL migrations through 0009 passed; PostgreSQL, Redis, FastAPI, ARQ,
  fixture, and Next.js boundaries passed; Chromium fixture-site probe passed;
  1 full-stack Playwright UI submission/report/candidate/evidence E2E passed;
  live services contacted 0`;
- Railway runs Alembic as an API pre-deploy command, while ARQ startup polls
  the shared database and cannot dequeue until its revision equals code head;
- non-closed API processes construct a non-owner artifact boundary that cannot
  initialize, clean, reserve, delete, or measure worker storage;
- worker startup and terminal jobs clean/measure the mounted filesystem and
  publish timestamped status through shared Redis for the API endpoint;
- the SQLite migration entrypoint creates the configured database parent, and
  the image also contains `/app/runtime` for its built-in default;
- focused deployment, storage-owner, and API-boundary regressions passed;
- Docker was unavailable in this WSL environment, so the strict local
  six-process fallback verified the same service boundaries;
- live gate: not run.

Prior verified gate:

Vercel/Railway deployment-preparation verification record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-31`;
- result: `239 Python tests passed; frontend smoke passed; 12 Vitest tests passed; strict Next.js 15 production build/type checking passed; fresh PostgreSQL migrations through 0009 passed; PostgreSQL, Redis, FastAPI, ARQ, fixture, and Next.js boundaries passed; Chromium fixture-site probe passed; 1 full-stack Playwright UI submission/report/candidate/evidence E2E passed; live services contacted 0`;
- hosted behavior: plain Railway `postgresql://`/`postgres://` URLs select the
  installed Psycopg 3 driver, Railway's injected `PORT` controls Uvicorn,
  Alembic runs before the hosted API starts, and live PostgreSQL startup never
  races the worker by implicitly creating an unstamped schema;
- browser boundary: exact Vercel origins and an optional controlled origin
  regex are runtime configuration, while `NEXT_PUBLIC_API_BASE_URL` is the
  explicitly public Vercel build-time API origin;
- service boundary: Vercel builds only `apps/web`; Railway uses one public API
  service, one private ARQ worker, managed PostgreSQL/Redis references, and a
  worker-mounted `/app/.runtime` volume;
- live gate: not run.

Current five-finding remediation implementation record:
- authoritative clip validation uses a new bounded session for every retained
  candidate, so each candidate can check at least ten dossier-driven ideas and
  no cluster consumes another cluster's final capacity;
- live Chromium discovery recognizes rich/grid channel cards and
  `#video-title-link` in addition to search and reel renderers;
- requests reject more than 20 raw seeds or any seed over 2,048 characters
  before normalization, while expanded query generation stops lazily at the
  configured query bound;
- direct video and channel contracts accept only HTTPS YouTube URLs matching
  the endpoint's declared resource type and reject blanks before run creation;
- backend candidate payloads and frontend normalization exclude supporting
  46–90-day major outliers from collections labelled current;
- focused contract, source, planner, asset-budget, pipeline, API, analytics,
  and frontend regressions are written; live services have not been contacted.
- first complete-gate attempt on `2026-08-30`: PostgreSQL migrations and the
  strict Next.js production build passed, but the local Chromium probe timed
  out because the developer shell's proxy configuration intercepted the
  isolated fixture navigation. The probe now explicitly bypasses proxies for
  localhost and prints local service logs on failure; a complete rerun is
  required.
- second complete-gate attempt on `2026-08-30`: the repaired Chromium probe
  passed and 230 Python tests passed. The strong integration fixture then
  asserted that every fairly sampled preliminary cluster must pass, even when
  its documented sampling coverage is inconclusive and explicitly deferred.
  The regression now accepts only a genuine preliminary pass or that typed
  deferral, while still requiring the authoritative final pass to validate at
  least ten ideas with zero budget deferrals; a complete rerun is required.
- third complete-gate attempt on `2026-08-30`: the Chromium probe, 231 Python
  tests, frontend smoke, and 12 Vitest tests passed. The final browser loaded
  the local Next.js form but its cross-port localhost API request inherited the
  same shell proxy and remained pending. Playwright E2E now bypasses proxies,
  failed E2E runs print service logs, and the local runner terminates/reaps its
  own process groups deterministically; a complete rerun is required.
- final complete-gate run on `2026-08-30`:
  `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
  231 Python tests passed, frontend smoke passed, 12 Vitest tests passed,
  strict Next.js 15 production build/type checking passed, fresh PostgreSQL
  migrations through 0009 passed, PostgreSQL/Redis/FastAPI/ARQ/fixture/Next.js
  boundaries passed, the system Chromium fixture probe passed, and one
  full-stack Playwright UI submission/report/candidate/evidence E2E passed;
  live services contacted 0.

Current six-finding remediation implementation record:
- request repository dependencies and repository-backed endpoints stay on one async execution boundary with deterministic session cleanup;
- asset search budgets are phase-aware, preflight work is fairly distributed, inconclusive samples are deferred instead of rejected, and at least ten idea slots are reserved for authoritative final validation;
- deterministic zero-key image inspection preserves decoded structure/provenance but explicitly cannot establish semantic match or reveal capability, so it cannot support a positive clip gate;
- empty-seed portfolios execute every bounded planned market before evenly spaced first-pass selection and round-robin depth allocation;
- discovery capacity and upload-feed depth permit a three-record cohort for each retained channel when operator limits allow;
- candidate demand payloads and the media-safe detail route expose supporting channels/videos, major outliers, risks, and differentiation;
- focused Python, integration, and frontend regressions are written; live services have not been contacted.
- first complete-gate attempt on `2026-08-28`: fresh PostgreSQL migrations passed, then the strict Next.js type check rejected an under-specified generic record type in the new evidence normalizer; the helper type was made explicit without changing runtime behavior, and a complete rerun is required.
- second complete-gate attempt on `2026-08-28`: strict frontend build and 205 Python tests passed, while the strong pipeline regression showed that deferred preflight ideas were being included as failures in preliminary coverage; preliminary decisions now report coverage over evaluated ideas and retain all-idea coverage for the authoritative final pass, and a complete rerun is required.

Seven-finding remediation is implemented before the gate: deterministic live
criticism reads the actual nested candidate packet; JPEG/WebP inputs require a
structurally valid parsed container; Ollama receives and validates the exact
requested JSON Schema with bounded same-provider repair; revisions 0008 and
0009 use SQLite batch operations and are exercised from a genuine revision
0007 schema; the seed demo uses schema-valid Python booleans; channel history
is allocated round-robin; and the run collection exposes bounded stable
pagination with total and navigation metadata. Live services have not been
contacted.

Current seven-finding remediation verification record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-25`;
- result: `201 Python tests passed; frontend smoke passed; 11 Vitest tests passed; strict Next.js 15 production build/type check passed; fresh PostgreSQL migrations through 0009 passed; genuine existing SQLite revision 0007 upgraded through batch-safe 0008/0009; PostgreSQL, Redis, FastAPI, ARQ, fixture, and Next.js boundaries passed; Chromium fixture-site probe passed; 1 full-stack Playwright UI submission/report/evidence E2E passed; live services contacted 0`;
- provider behavior: nested immutable gates control the deterministic critic, malformed image containers cannot become visual evidence, and Ollama receives the requested schema on every bounded network or structured-output retry without provider switching;
- persistence/control behavior: both constraint migrations work against a legacy SQLite schema, duplicate legacy comments collapse before uniqueness is applied, channel history is fair across retained channels, and run history is discoverable through stable bounded pages and navigation metadata;
- tooling behavior: importing the demo payload performs no request and its native Python booleans validate against `ResearchRunCreate`;
- repair behavior: the first complete gate passed 200 tests and correctly rejected the old positive PNG fixture because its IDAT length/CRC boundary was malformed. The fixture was replaced with a `file`-verified valid 1×1 PNG without weakening production validation, and the entire gate was rerun successfully;
- live gate: not run.

Twenty-finding portability and evidence-integrity remediation is implemented
and the complete closed gate is green. Live `auto` now selects a distinct
evidence-driven deterministic provider when OpenRouter/Ollama are absent;
fixture media never fabricates missing observations; keyless aspect evidence
survives Shorts classification; comparison inputs and identities are bounded;
SQLite migrations/durability, browser routing/parameters, child-process
reaping, ffmpeg configuration propagation, media duration bounds, Archive
rights, production controls, API quota classification/accounting, and sparse
channel identity have focused regressions.

Current twenty-finding remediation verification record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-25`;
- result: `195 Python tests passed; frontend smoke passed; 11 Vitest tests passed; strict Next.js 15 production build/type check passed; fresh PostgreSQL migrations through 0009 passed; PostgreSQL, Redis, FastAPI, ARQ, fixture, and Next.js boundaries passed; Chromium fixture-site probe passed; 1 full-stack Playwright UI submission/report/evidence E2E passed; live services contacted 0`;
- repair behavior: the first complete gate exposed eight focused-regression issues. SQLite foreign-key enforcement correctly rejected artifact tests whose synthetic run IDs had no parent row, so those tests now create relationally valid runs; three assertion/mocking regressions were corrected without weakening production behavior. The entire gate then passed;
- zero-key behavior: live/production `auto` no longer returns fixture fake, explicit deterministic selection is supported, fixture fake is rejected outside fixture modes, and positive visual fallback judgments require actual bounded decodable image input;
- evidence behavior: missing fixture fields remain unknown, keyless aspect evidence survives duration normalization, comparison prompts/ratios match their bounded authoritative metric, Archive rights remain tri-state, and submitted production constraints are preserved verbatim;
- operations behavior: SQLite migration and durability paths, locale/region/recency browser routing, disabled-browser API fallback, YouTube quota floors/taxonomy, subprocess reaping, ffmpeg configuration propagation, and pre-reservation duration limits are all covered;
- live gate: not run.

Thirteen-finding live-path remediation is complete and the full closed gate is
green. The zero-key smoke payload keeps canonical gate minima; explicit AI
provider selection is typo-safe and strict; omitted Data API video IDs retain
typed provenance; media output cannot exceed its reservation unnoticed and
subprocesses are killed/reaped before cancellation releases storage; language
normalization distinguishes marker-free Latin unknowns from affirmative
non-Latin evidence; pairs are selected independently inside semantic
clusters; saturation uses and reports the retained supporting window;
development routes audit fixture sources; and quota rollover follows Pacific
midnight. The UI now carries actual fixture/Data-API/keyless provenance,
exposes broad discovery, recency, and production controls, and opens evidence
deep links on the Evidence tab.

Current thirteen-finding remediation verification record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-25`;
- result: `175 Python tests passed; frontend smoke passed; 10 Vitest tests passed; strict Next.js 15 production build/type check passed; fresh PostgreSQL migrations through 0009 passed; PostgreSQL, Redis, FastAPI, ARQ, fixture, and Next.js boundaries passed; Chromium fixture-site probe passed; 1 full-stack Playwright UI submission/candidate/evidence-deep-link E2E passed; live services contacted 0`;
- repair behavior: the first gate correctly caught a non-Latin language-classification regression; predominantly non-Latin script remains affirmative non-English evidence while marker-free Latin technical transcripts remain unknown, and the entire gate passed after repair;
- media behavior: yt-dlp receives the reservation byte cap, progressive output is monitored, all download artifacts are deleted, and cancellation/timeout waits for child reaping before capacity release;
- evidence behavior: omitted API IDs, metadata adapter type, supporting saturation window, per-cluster comparisons, fixture routing, and Pacific quota dates all have focused deterministic regressions;
- UI behavior: source provenance is never inferred from fixture mode alone, required research controls submit their actual values, and candidate evidence links initialize the Evidence tab;
- live gate: not run.

Fifteen-finding safety, concurrency, routing, and evidence-gate remediation is complete and the full closed gate is green. Cleanup roots are dedicated, separate runtime children and recursive root deletion is rejected; cross-process download reservations prevent concurrent capacity overcommit. Canonical recommendation minima are enforced at both request and deterministic recommendation boundaries. Shared channels/videos use database-native conflict handling, comments have stable source identity through migration 0009, and retry observations remain idempotent. Discovery executes the health router's selected source with audited API fallback, while browser filmstrips and heavy media are capped before capture at six channel-diverse videos. Asset searches share one run-wide idea budget and reveal coverage requires image-capable observation. Historical uploads are retained for display but excluded from decision cohorts, labels follow the configured threshold, mechanism replication accepts only mechanism-bearing evidence, YouTube API undated/removed records become typed partial diagnostics, and keyless health has distinct provenance.

Current fifteen-finding remediation verification record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-25`;
- result: `165 Python tests passed; frontend smoke passed; 8 Vitest tests passed; strict Next.js 15 production build/type check passed; fresh PostgreSQL migrations through 0009 passed; PostgreSQL, Redis, FastAPI, ARQ, fixture, and Next.js boundaries passed; Chromium fixture-site probe passed; 1 full-stack Playwright UI submission/overview-link/candidate-detail/action-plan/evidence E2E passed; live services contacted 0`;
- storage behavior: broad/equal/nested/symlink-escaped roots are rejected, managed roots cannot be deleted, and worker reservations are serialized and released after unconditional raw cleanup;
- integrity behavior: shared entity inserts cannot race into unique-key failures, snapshots/comments remain retry-idempotent, and missing publication timestamps never become artificial current observations;
- evidence behavior: configured outlier labels agree with gates, historical media cannot influence multiplier consumers, reveal requires inspected pixels, and mechanism replication excludes deterministic outlier/count-only citations;
- routing behavior: probed capability health controls source selection, API fallback is actually executed, and keyless yt-dlp health is not mislabeled as Data API capability;
- live gate: not run.

Eleven-finding live-path/data-integrity remediation is implemented and the complete closed gate is green. The remediation ranks only after recommendation and critic adjudication; converts isolated browser page failures into persisted zero-confidence partial evidence; makes cancellation conditional after abort races; isolates optional asset-provider outages; bounds asset ideas and concurrency at both schema and connector layers; treats trend-bridge failures as unavailable corroboration; keys public snapshots by run/entity/source for retry idempotency; normalizes combined Shorts/long-form synthesis, critic, and candidate actions; selects the latest successful dashboard run independently; and deep-links every overview opportunity.

Current remediation verification record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-25`;
- result: `138 Python tests passed; frontend smoke passed; 8 Vitest tests passed; strict Next.js 15 production build/type check passed; fresh PostgreSQL migrations through 0008 passed; PostgreSQL, Redis, FastAPI, ARQ, fixture, and Next.js boundaries passed; Chromium fixture-site probe passed; 1 full-stack Playwright UI submission/overview-link/candidate-detail/action-plan/evidence E2E passed; live services contacted 0`;
- resilience behavior: one unavailable video page becomes timestamped zero-confidence partial evidence, optional asset/trend providers cannot fail the whole report, and asset fan-out is capped at 30 ideas with bounded concurrency;
- integrity behavior: candidates are persisted in adjudicated order, cancellation cannot overwrite a racing worker terminal commit, and one run/job can own only one snapshot per entity/source while later runs remain genuine temporal observations;
- UI behavior: nested combined-media synthesis/critic/action slices remain separate, single-media candidates render only their available cohort, dashboard last-signal selection ignores newer non-complete runs, and overview cards deep-link to the selected candidate;
- live gate: not run.

Eight-finding live-path correctness remediation and focused regressions are implemented and the complete closed gate is green. The remediation reserves expansion capacity, makes worker redelivery idempotent, rejects invalid mechanism citation sets at the hard gate, bounds transcript-bearing dossiers and idea prompts, aligns API empty-seed defaults with the 12/20-market portfolios, preserves terminal cancellation states, reports probed/unknown source health instead of hard-coded green, and retries transient Ollama failures without provider switching.

Current eight-finding live-path correctness remediation record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-25`;
- result: `127 Python tests passed; frontend smoke passed; 5 Vitest tests passed; strict Next.js 15 production build/type check passed; fresh PostgreSQL migrations through 0007 passed; PostgreSQL, Redis, FastAPI, ARQ, fixture, and Next.js boundaries passed; Chromium fixture-site probe passed; 1 full-stack Playwright UI submission/report/evidence E2E passed; live services contacted 0`;
- idempotency behavior: terminal deliveries no-op, while non-terminal redeliveries atomically replace run-scoped partial report output before one job-scoped execution;
- evidence behavior: unknown mechanism citations zero confidence and replication support before recommendation; mechanism/classification/idea prompts use bounded channel-diverse transcript segments;
- operations behavior: discovery reserves total-run capacity for expanded upload history; cancellation preserves terminal outcomes; source health probes local capabilities and distinguishes unverified credentials; Ollama retries only bounded transient failures without changing provider;
- live gate: not run.

Twelve-finding runtime/workflow remediation and focused regressions are implemented and the complete closed gate is green. The remediation covers fixture/demo labeling and source provenance, abort-enabled ARQ cancellation, combined-media rendering on run and niche-detail surfaces, service/worker closed-network guards, request-session cleanup, operator browser/channel caps, an absolute six-video heavy-media ceiling, channel-diverse vision targets, per-idea asset-source diversity, sparse-safe full video metadata refresh, deterministic comparison identities, and missing-candidate 404 behavior.

Current twelve-finding runtime/workflow remediation record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-25`;
- result: `115 Python tests passed; frontend smoke passed; 5 Vitest tests passed; strict Next.js 15 production build/type check passed; fresh PostgreSQL migrations through 0007 passed; Chromium fixture-site probe passed; 1 full-stack Playwright UI submission/report/evidence E2E passed; live services contacted 0`;
- Docker was unavailable in this WSL environment, so the strict local six-process fallback verified PostgreSQL, Redis, FastAPI, ARQ, fixture, Next.js, and Chromium boundaries;
- live gate: not run.

Nine-finding semantic/production remediation record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`;
- date: `2026-08-24`;
- result: `105 Python tests passed; frontend smoke passed; 4 Vitest tests passed; strict Next.js 15 production build/type check passed; fresh PostgreSQL migrations through 0007 passed; Chromium fixture-site probe passed; 1 full-stack Playwright UI submission/report/evidence E2E passed; live services contacted 0`;
- semantic topic membership is applied inside repeatable-format buckets, and AI ideas are deduplicated by embedding cosine similarity;
- `both` runs retain independent media evidence, expose `not_assessed` for absent cohorts, and create a combined bridge only from semantically matching Shorts and long-form clusters;
- public YouTube counters and artifact byte sizes use 64-bit columns with ordered migrations;
- Ollama sends actual image bytes and clip validation requires a positive image-capable semantic judgment;
- concurrent ARQ jobs own separate SQLAlchemy sessions/orchestrators and run-specific Chromium profile namespaces;
- every retried YouTube request reserves quota, Latin-script non-English transcripts require lexical language evidence, and each persisted search result references its captured screenshot;
- Docker was unavailable in this WSL environment, so the strict local six-process fallback verified PostgreSQL, Redis, FastAPI, ARQ, fixture, Next.js, and Chromium boundaries; live gate not run.

Twelve-finding full-stack review remediation record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`
- date: `2026-08-24`
- result: `95 Python tests passed; frontend smoke passed; 4 Vitest tests passed; strict Next.js 15 production build/type check passed; Chromium fixture-site probe passed; 1 full-stack Playwright UI submission/report/evidence E2E passed; live services contacted 0`;
- the API and every worker now reserve YouTube units atomically in one database-backed daily quota ledger, and the quota endpoint reads that same ledger;
- `both` requests create non-overlapping Shorts and long-form preflight, comparison, clustering, saturation, demand, trend, and recommendation inputs;
- successful-channel evidence is limited to 90-day channel/media-class/repeatable-format cohorts, and candidate success cannot come from an unrelated format;
- current-outlier hard gates use the configured `OUTLIER_THRESHOLD` with a 3x default;
- the closed gate starts PostgreSQL, Redis, FastAPI, ARQ, the fixture server, and the production Next.js server, applies Alembic, launches Chromium against fixture search/video/transcript pages, and submits a run from the UI through its rendered evidence report;
- Docker Compose is preferred when available; this WSL environment lacks Docker integration, so the same six boundaries were booted with the strict temporary local-process fallback using fresh PostgreSQL/Redis state;
- production Chromium uses the explicit `BROWSER_EXECUTABLE_PATH=/usr/bin/chromium` shipped by the API image;
- queued run pages poll until complete, failed, or cancelled; the form advertises English only;
- transient YouTube 500/502/503/504 responses retry with bounded backoff;
- explicit `0.0` non-English evidence is preserved, raw media deletion is unconditional, and empty keyless descriptions cannot erase known channel metadata;
- live gate: not run.

Sparse keyless identity remediation record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`
- date: `2026-08-16`
- result: `85 Python tests passed; frontend smoke passed; 2 Vitest tests passed; strict Next.js 15 build/type check passed; 1 Playwright Chromium E2E passed; live services contacted 0`;
- channel traversal seeds successful sparse uploads with the known channel ID;
- retained discovery channel titles supply sparse channel presentation;
- diagnostic source identity is captured before extraction and cannot be
  overwritten by a temporary media-stream URL;
- canonical watch URLs are reconstructed when discovery supplied no canonical
  video-page URL;
- live gate: not run.

Cohort and keyless channel-boundary remediation record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`
- date: `2026-08-16`
- result: `83 Python tests passed; frontend smoke passed; 2 Vitest tests passed; strict Next.js 15 build/type check passed; 1 Playwright Chromium E2E passed; live services contacted 0`
- outlier cohorts always include media class and repeatable format;
- one typed unavailable channel feed creates evidence and later channels
  continue expanding;
- successful sparse metadata is merged over known discovery provenance;
- only positive finite portrait ratios can support Shorts evidence;
- live gate: not run.

Keyless failure-boundary and provenance remediation record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`
- date: `2026-08-16`
- result: `79 Python tests passed; frontend smoke passed; 2 Vitest tests passed; strict Next.js 15 build/type check passed; 1 Playwright Chromium E2E passed; live services contacted 0`
- source-wide configuration failures propagate unchanged and do not create
  misleading candidate diagnostics;
- initial enrichment receives bounded browser discovery context;
- failed initial diagnostics retain known channel/title/URL/visible metadata,
  Shorts presentation, position, screenshot, and raw browser payload;
- unexpected implementation exceptions are not swallowed as candidate skips;
- live gate: not run.

Uniform keyless enrichment remediation record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`
- date: `2026-08-16`
- result: `77 Python tests passed; frontend smoke passed; 2 Vitest tests passed; strict Next.js 15 build/type check passed; 1 Playwright Chromium E2E passed; live services contacted 0`
- initial and channel-expansion videos use the same per-item fault boundary;
- initial diagnostics are persisted before the no-usable-candidates check;
- null, invalid, NaN, and infinite aspect ratios are unknown/non-confirming;
- mixed initial batches retain usable videos and ordered skip diagnostics;
- live gate: not run.

Keyless provenance and Compose remediation record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`
- date: `2026-08-16`
- result: `75 Python tests passed; frontend smoke passed; 2 Vitest tests passed; strict Next.js 15 build/type check passed; 1 Playwright Chromium E2E passed; live services contacted 0`
- Psycopg 3 is a core runtime dependency used by the Compose API and worker.
- yt-dlp dates are parsed from timestamp/date fields; undated videos are
  excluded rather than assigned the observation time.
- video descriptions are not copied into channel descriptions.
- inaccessible and invalid channel uploads are isolated per entry, with
  structured skip diagnostics persisted to the run evidence ledger.
- keyless enrichment uses an explicit provenance label and remains included in
  report observation totals.
- live gate: not run.

Review findings remediation record:
- command: `PATH=/home/stanley/niche_finder/.venv/bin:/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`
- date: `2026-08-13`
- result: `71 Python tests passed; frontend smoke passed; 2 Vitest tests passed; strict Next.js 15 build/type check passed; 1 Playwright Chromium E2E passed; live services contacted 0`
- verified behavior: supporting-window-only outlier baselines, immediate ARQ submission for non-closed requests, bounded keyless channel upload traversal, pre-download six-video media cap, safe direct YouTube URL routing/artifact names, raw-media lifecycle, and deterministic closed-mode source isolation.
- environment repairs: installed the declared ARQ and closed-test dependencies; constrained setuptools discovery to application/worker packages; replaced the executor completion dependency around blocking Deepgram calls with a cooperative daemon-thread bridge.
- live gate: not run.

Runtime-storage lifecycle record:
- command: `PATH=/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`
- date: `2026-08-13`
- result: `64 Python tests passed; 2 Vitest tests passed; frontend smoke passed; strict Next.js 15 build/type check passed; 1 Playwright Chromium E2E passed; live services contacted 0`
- verified ordering: raw MP4 exists during Deepgram transcription and all six selective frame extractions, then is deleted in `finally`.
- verified failure behavior: raw/partial downloads are deleted when transcription raises; derived frames retain SHA-256, size, run, expiry, and availability state.
- operations: storage ceilings and free-space floors apply before download; cleanup runs at startup and terminal run states; `make cleanup-runtime`, `/api/system/storage`, and per-run artifact history are available.
- live gate: not run.

Final niche-accuracy remediation record:
- command: `PATH=/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`
- date: `2026-08-12`
- result: `59 Python tests passed; 2 Vitest tests passed; frontend smoke passed; strict Next.js 15 build/type check passed; 1 Playwright Chromium E2E passed; live services contacted 0`
- first-run repair: focused explicit seeds were incorrectly diversified; follow-up query variants are now limited to broad/deep research, preserving exact focused validation.
- installed optional runtime tooling: `deepgram-sdk==7.7.0`, `yt-dlp==2026.7.4`; ffmpeg remains an external executable requirement for live media analysis.
- live gate: not run. The smoke accepts a zero-key keyless mode, while OpenRouter, Deepgram, YouTube Data API, Pexels, Pixabay, and the trend bridge remain optional accuracy/coverage upgrades.

Record:
- command: `make closed-test`
- date: `2026-08-10`
- result: `41 passed; frontend dependency-free smoke PASS; live services contacted 0`
- repair notes: The first run produced 40 passes and correctly rejected a channel-profile test fixture whose largest upload held 83% of observed channel views. The fixture was corrected to model repeated performance. Final audits moved rights-aware clip preflight ahead of channel expansion/media/vision work, retained a second full-evidence validation pass, and made two-source diversity plus rights/reveal coverage part of the clip gate. The complete suite was rerun after each production change and passed. The build includes conservative Shorts classification, channel expansion/performance proxies, current outlier cohorts, matched winner/loser analysis, multimodal visual analysis, ten-idea clip validation, optional OpenRouter/Pexels/Pixabay/trend-bridge providers, improved saturation, and eight recommendation gates.
- prior record retained for history only; it is superseded by the review remediation below and cannot establish the current gate.

Review remediation implemented on `2026-08-12`:
- the closed gate now fails on missing frontend prerequisites and requires Vitest, a strict Next.js build, and Playwright E2E;
- live smoke now executes one bounded live research job and validates browser/API merging, analytics, AI output, and report generation;
- long-form profiles select long-form uploads, and outlier cohorts are partitioned by known format;
- mechanism replication is derived only from channels referenced by mechanism-supporting evidence;
- browser media observations are exposed through the evidence ledger;
- YouTube `videos.list` and `channels.list` enrichment is batched at 50 IDs;
- Next.js 15 route params are unwrapped asynchronously and the client run schema retains lifecycle timestamps.

The full closed suite was run after these changes; the final record follows.

Final review-remediation record:
- command: `PATH=/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`
- date: `2026-08-12`
- result: `45 Python tests passed; 2 Vitest tests passed; dependency-free UI smoke passed; strict Next.js 15 production build/type check passed; 1 Playwright Chromium E2E passed; live services contacted 0`
- environment repairs: pinned the supported Node 20 runtime in `.nvmrc`, declared missing TypeScript/jsdom dependencies, separated Vitest unit discovery from Playwright specs, verified the exact Playwright Chromium executable in the prerequisite gate, scoped Next output tracing to the web app, and made the fixture form label accessible to browser automation and assistive technology.
- gate behavior: missing `node_modules`, required frontend executables, supported Node runtime, or matching Chromium now fails the gate before any test is reported green.

Empty-input market-sweep record:
- command: `PATH=/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`
- date: `2026-08-12`
- result: `48 Python tests passed; 2 Vitest tests passed; strict Next.js build/type check passed; 1 Playwright Chromium E2E passed; live services contacted 0`
- behavior: an empty seed now selects a deterministic portfolio of 12 concrete markets in fast mode or 20 in deep mode. The plan persists its strategy, covered markets, and exact bounded queries as evidence; it never substitutes a generic "best niche" or "emerging formats" query.

Evidence-bound LLM reasoning record:
- command: `PATH=/home/stanley/.nvm/versions/node/v20.19.4/bin:$PATH make closed-test`
- date: `2026-08-12`
- result: `51 Python tests passed; 2 Vitest tests passed; frontend smoke passed; strict Next.js build/type check passed; 1 Playwright Chromium E2E passed; live services contacted 0`
- behavior: each representative video now receives a bounded structured interpretation over public metadata, deterministic outlier facts, transcript excerpts, browser observations, and visual analysis. Candidate packets reconcile those observations with matched comparisons, replicated mechanisms, idea/clip ceilings, saturation, and immutable hard gates. A separate critic challenges the conclusion, evidence IDs are validated deterministically, and a final portfolio synthesis supplies the cited report and action plan.
- authority boundary: AI can interpret evidence, reduce confidence, or block a positive result. It cannot calculate authoritative metrics, pass a failed gate, promote a deterministic verdict, cite records outside the run ledger, or invent unavailable transcript timestamps.

### Live test
`IN_PROGRESS`

The closed gate was green before each live attempt. Hosted run
`636b16d9-fd9e-4e1e-baad-bcf4b4528607` exposed the Chromium hydration race;
hosted run `cf477e6d-1b4b-42d3-9aeb-3b5595225059` verified that repair and then
exposed a per-video yt-dlp bot challenge. Hosted run
`6e9a4976-47c5-44a0-bbf4-46884e0626bd` verified the media partial-evidence
repair and then isolated cumulative watch-page Chromium timeouts. The
video-page remediation passed its hosted five-frame probe; run
`87ade25c-371e-4046-80eb-af86be2a1bfa` then exposed an unbounded OpenRouter SDK
wait. Its deadline remediation is verified through the next hosted deployment
and live attempt under the current execution policy.

## Current blockers
None in the editing environment. Local dependency installation and local
execution are prohibited by the current policy. Live verification continues
only on Vercel/Railway. A zero-key hosted smoke requires Chromium, yt-dlp,
ffmpeg, and network access; the recommended accurate run also configures
OpenRouter and Deepgram, with the YouTube Data API and asset/trend providers
optional.

## Architectural deviations
- The control plane uses synchronous SQLAlchemy sessions with a SQLite closed-mode fallback so the complete fixture suite can run without Docker/PostgreSQL drivers. PostgreSQL/pgvector URLs, SQLAlchemy models, and the Compose service remain the deployment path. Affected files: `apps/api/app/db/session.py`, `apps/api/app/repositories/store.py`.
- Closed runs execute the orchestrator synchronously from the FastAPI request. Development, live-test, and production requests enqueue an idempotent ARQ job and return immediately; `workers/research/worker.py` owns execution and task status. This keeps the closed test deterministic without Redis while preventing live HTTP requests from blocking for the research duration. Affected files: `apps/api/app/api/routes.py`, `apps/api/app/services/jobs.py`, `workers/research/worker.py`.

### Review remediation verified by closed test

- Same-channel/format baselines now admit only uploads inside the 90-day
  supporting cohort.
- The keyless yt-dlp source performs a bounded channel `/videos` traversal,
  restoring channel history without a YouTube API key.
- Heavy download/Deepgram/ffmpeg analysis is selected before execution and is
  capped at six channel-diverse representative videos.
- Direct YouTube inputs bypass search encoding and browser screenshot paths use
  sanitized, hashed filenames.
- Non-closed requests are enqueued before returning; closed fixture requests
  retain the documented synchronous exception.
- Regression tests are written and passed as part of the complete 71-test
  Python gate plus frontend build and browser E2E.
- Python package discovery is explicitly limited to `apps*` and `workers*`, so
  editable installation cannot mistake runtime data, fixtures, or shared
  non-Python directories for distributable packages.
- Blocking Deepgram SDK work uses a bounded daemon-thread bridge with
  cooperative event-loop polling, preserving worker responsiveness in
  constrained runtimes that suppress executor completion notifications.
