# Test Plan

## 1. Testing philosophy
The repository is implemented completely before tests are executed.

All test code and fixtures may be written during implementation, but execution begins only after the implementation-complete gate is satisfied.

Testing has two strict phases:

1. **Closed test**
   - No external network.
   - No live YouTube.
   - No live external APIs.
   - No credentials.
   - Full architecture exercised using fixtures/local services.

2. **Live test**
   - Begins only after closed test is fully green.
   - Explicitly enabled.
   - Uses tightly bounded real calls.

## 2. Implementation-complete precheck
`scripts/closed_test.py` must first verify that required files/modules exist.

Required categories:
- backend
- frontend
- migrations
- DB models
- repositories
- YouTube API source
- Chromium source
- fixture sources
- source router
- planner/orchestrator
- analytics
- embeddings
- AI provider + fake provider
- recommendation engine
- reports
- frontend pages
- fixtures
- unit tests
- integration tests
- E2E tests
- Docker Compose
- `.env.example`
- README
- live smoke test script

If required implementation is missing, closed testing stops with a clear error.

## 3. Closed-network guarantee
When `APP_MODE=closed_test`:
- external HTTP clients must use mocks/fixtures
- DNS/network access from test process is blocked where practical
- pytest network blocker is enabled
- browser fixture uses localhost only
- live YouTube source constructors fail fast
- live asset source constructors fail fast

Include a test that deliberately attempts an external connection and proves it is blocked.

## 4. Unit tests

### Configuration
- runtime modes
- missing credentials in live mode
- closed-mode source protection
- environment parsing

### Quota manager
- decrement
- reserve floor
- daily budget
- denied search call
- reset boundary logic
- concurrency safety

### Source router
- known ID -> API
- visual task -> browser
- discovery -> browser
- exact verification -> API
- reserve reached -> browser discovery
- closed test -> fixtures only
- unhealthy source -> alternate source

### Analytics
- views/day
- age edge cases
- median baseline
- candidate excluded from its own baseline
- zero/empty cohort
- outlier multiple
- configurable thresholds
- snapshot growth
- acceleration
- repeated outliers

### Deduplication
- video ID
- channel ID
- URL canonicalization
- semantic idea duplicates

### Clustering
- deterministic fixture embeddings
- stable cluster assignment
- representative selection

### Recommendation gates
- single creator rejected/low confidence
- stale-only evidence rejected
- high saturation penalty
- insufficient idea ceiling
- insufficient evidence
- qualifying candidate produces expected verdict

### AI schema
- valid structured output
- invalid output rejection
- repair path
- evidence IDs retained
- prompt content separated from system instructions
- transcript excerpts never invent unavailable timestamps
- per-video, candidate, critic, and report outputs validate as structured schemas
- unknown evidence citations are rejected
- critic/adjudicator can lower confidence or block a verdict but cannot promote a failed deterministic gate

## 5. Source contract tests
Every source implementation must satisfy shared contracts.

### YouTube fixture source
- search
- video enrichment
- channel enrichment
- playlist expansion
- comment sampling
- empty cases
- partial fields
- errors

### Browser fixture source
- search results
- channel inspection
- video inspection
- Shorts observation
- transcript available
- transcript missing
- lazy loading
- selector fallback
- screenshot reference
- bounded scrolling

## 6. Persistence tests
- migrations from empty DB
- create/update research run
- idempotent video upsert
- idempotent channel upsert
- snapshot append
- evidence lineage
- transaction rollback
- unique constraints
- pgvector field operations where used

## 7. Orchestrator integration tests

### Scenario A — Strong niche
Fixture data contains:
- multiple channels
- multiple recent outliers
- repeated format
- manageable competitors
- sufficient idea ceiling

Expected:
- pipeline completes
- outliers detected
- cluster created
- mechanism produced
- positive/experiment verdict
- evidence links valid
- candidate synthesis, critic, and final report synthesis cite only run-ledger evidence

### Scenario B — One-hit wonder
Fixture data:
- one viral video
- normal surrounding uploads
- no cross-channel confirmation

Expected:
- low confidence
- no strong recommendation

### Scenario C — Oversaturated format
Fixture:
- many direct competitors
- heavy upload density
- poor average results
- few recent outliers

Expected:
- saturation warning
- `Demand exists but oversaturated` or rejection

### Scenario D — Stale niche
Fixture:
- historical huge videos
- weak recent videos

Expected:
- no current-momentum recommendation

### Scenario E — Strong Shorts, weak long-form
Expected separate assessments.

### Scenario F — Cancellation/resume
- cancel active run
- idempotent resume/retry where designed

## 8. Browser integration test
Run Chromium against the local fixture site.

Exercise:
1. search
2. bounded scroll
3. open channel
4. collect candidate videos
5. open video
6. detect Shorts presentation
7. read transcript fixture
8. capture related videos
9. capture screenshot
10. persist observations

No request may leave localhost.

## 9. API integration test
Start FastAPI against test DB/Redis.

Test:
- create run
- get run
- wait/poll local worker
- get candidates
- get evidence
- get report
- cancel run
- source-health
- quota endpoint

## 10. Frontend test
Unit:
- forms
- status components
- candidate cards
- evidence rendering
- error states

E2E:
1. open dashboard
2. create fixture research run
3. observe stage changes
4. open completed report
5. inspect niche detail tabs
6. verify evidence and outlier data
7. verify demo/fixture label

## 11. Full closed-system test
The final closed test must boot:

- PostgreSQL
- Redis
- backend
- worker
- frontend
- fixture server

Then execute one complete research job from the UI/API boundary through:
- planning
- browser fixture discovery
- fixture API enrichment
- persistence
- deterministic analytics
- fake AI analysis
- recommendation
- report
- UI retrieval

Pass criteria:
- all services healthy
- no external network
- all automated tests green
- one complete strong-niche fixture run succeeds
- one rejection fixture run succeeds
- evidence lineage complete
- no unhandled errors
- no required TODO placeholders
- Shorts classification distinguishes confirmed, probable, not-short, and unknown without treating duration as confirmation
- strong fixture expands three channels, retains at least three matched comparisons, and finds at least ten clip-validated ideas
- every recommendation exposes eight auditable hard gates
- visual analysis uses fixture frames only and external networking remains blocked
- competitor channel performance is explicitly labelled as a public-data proxy
- stale, one-hit, and saturated fixtures fail the relevant current-demand, replication, or saturation gates

## 12. Closed-test command
Provide a single command, for example:

```bash
make closed-test
```

It must:
1. validate implementation-complete gate
2. build/start closed-test services
3. apply migrations
4. run backend/unit/integration tests
5. run browser fixture tests
6. run frontend tests
7. run full E2E
8. print final pass/fail summary
9. tear down cleanly unless a debug flag is supplied

## 13. Live test

The live smoke is a genuine bounded end-to-end path and accepts zero API
keys. With no keys it uses Chromium discovery, yt-dlp public metadata,
keyless web asset search, and deterministic AI. OpenRouter, Deepgram, YouTube
Data API, Pexels, and Pixabay are optional accuracy/coverage upgrades. The
closed runner must never invoke this live path.

The closed suite additionally verifies date-anchored fixtures, unified API
quota units, keyless metadata normalization, English/faceless normalization,
transcript-first selective filmstrips, semantic clip-fit and early rejection,
OpenRouter retries/no mid-run failover, competitor ranges, multi-window
momentum, and observational winner/loser caveats.

Storage lifecycle tests prove that raw video exists during transcription and
frame extraction, disappears afterward, is also deleted on transcription
failure, retained frames carry SHA-256/size/expiry metadata, expired browser
and media artifacts are removed, and storage ceilings reject work before a
download process starts.

Review-remediation regressions additionally prove that uploads older than the
supporting window cannot enter outlier baselines; non-closed API requests return
in queued state without invoking the orchestrator; ARQ submission is
idempotently keyed and closes its Redis pool; keyless channel expansion is
playlist-bounded; heavy media target selection never exceeds six and preserves
channel diversity; and direct URL screenshot names cannot create nested paths.
The suite also constructs the Compose PostgreSQL dialect without connecting,
proving the Psycopg driver is installed; verifies `upload_date` normalization
and rejection of unknown publication dates; proves video descriptions never
become channel descriptions; and confirms inaccessible/undated channel entries
are skipped individually with evidence while usable uploads survive.
Initial keyless enrichment receives the same partial-result test: one private
or undated search candidate cannot abort usable peers, diagnostics retain their
source identity, and a null/nonnumeric aspect ratio remains non-confirming
without raising while a finite portrait ratio can supply probable evidence.
Configuration-boundary tests prove a missing yt-dlp executable propagates its
typed configuration error and creates no per-candidate diagnostics. Discovery
context tests prove a failed initial candidate retains its known URL, title,
channel, visible age/views, Shorts presentation, position, screenshot, and raw
browser payload.
Cross-media cohort tests prove Shorts and long-form videos with the same channel
and repeatable-format label still receive separate baselines. Channel-feed
tests prove one unavailable feed creates evidence while later channels expand,
and configuration errors still propagate. Sparse-success tests retain known
discovery channel/title fields. Zero and negative aspect ratios are explicitly
non-confirming.
Sparse channel-expansion tests additionally prove a successful record inherits
the traversed channel ID when both feed and extraction omit it, and channel
profiles retain a discovery-observed title. Rejected post-extraction records
must cite the original canonical YouTube URL, or reconstruct a canonical watch
URL when no discovery URL exists; a temporary yt-dlp media-stream URL may only
appear inside bounded raw diagnostic context.

The latest live-path regression set additionally proves that the zero-key
smoke request remains schema-valid without weakening the 70% clip gate;
unknown AI provider names fail typed startup validation; every requested video
ID omitted by `videos.list` creates a provenance-bearing diagnostic; yt-dlp is
given the exact reserved byte ceiling and an in-process file-size monitor; and
cancelled or timed-out media subprocesses are killed and reaped before storage
reservations are released. Marker-free technical transcripts remain unknown
rather than being treated as non-English. Winner/loser limits apply inside
each semantic cluster, saturation reports the retained 90-day evidence window,
development routing records fixture adapters, and quota days roll over at
midnight America/Los_Angeles across standard and daylight time. Frontend
contract/E2E coverage verifies explicit broad-discovery, recency, and
production controls; distinct fixture/Data-API/keyless provenance labels; and
an evidence deep link that opens the Evidence tab directly.
The current portability and evidence-integrity regression set additionally
proves that zero-key live auto-selection is not the fixture AI and reads real
bounded image inputs; absent fixture media remains zero-confidence unavailable;
keyless landscape/unknown aspect observations cannot be promoted by duration;
comparison transcripts are bounded and three independent pairs may span two
channels; winner ratios use the same outlier-multiple metric as pair selection;
SQLite reaches Alembic head without PostgreSQL-only type DDL and development
SQLite retains durable journal/synchronous behavior; browser discovery applies
locale, region, and an anchored recency filter while query-bearing channel URLs
append `/videos` to the path; a disabled production browser starts cleanly for
API routing; yt-dlp cancellation/timeout kills and reaps its child; missing
ffmpeg remains a configuration failure; selective frame counts never become
shot-duration estimates; absent Archive licences remain unknown/non-reusable;
idea annotations retain the submitted production constraints; search routing
requires the complete 100-unit cost plus reserve; YouTube 403 quota reasons keep
the quota taxonomy; sparse keyless channel placeholders cannot erase known
identity; and browser-observed duration blocks paid media before reservation.
The current provider/migration/control-plane regression set additionally proves
that the deterministic zero-key critic reads immutable gates from the nested
candidate packet; malformed JPEG/WebP magic cannot become visual evidence;
Ollama receives the exact Pydantic JSON Schema and repairs one invalid response
without changing providers; an actual SQLite database stamped at revision 0007
upgrades through the batch-safe 0008/0009 constraints with comment de-duplication;
the Python seed-demo payload imports and validates without executing a request;
channel upload slots are distributed round-robin so every retained channel
receives history before any channel consumes a third slot; and run-list limit/
offset pages expose stable ordering, totals, navigation links, and validation.
The current allocation and evidence regression set additionally proves that
request-scoped repository sessions use an async generator and close within a
bounded API request; preliminary asset searches cannot spend the authoritative
final-pass reserve or permanently reject deferred ideas; final-pass capacity
is independently bounded for every candidate and never falls below ten checks;
structure-only image parsing cannot pass
semantic-fit or reveal gates; empty-seed discovery executes every bounded
portfolio query and samples markets before taking additional results; channel
feeds request at least three records when operator bounds permit; and niche
detail normalization renders supporting channel/video observations, current
major outliers, synthesis risks, and media-specific differentiation.
The latest input and channel-discovery regression set additionally proves that
raw seed count and item length are rejected before normalization, variant
generation stops at the query bound, direct video/channel endpoints reject
blank, external, and wrong-resource URLs, Chromium channel discovery includes
rich/grid title links, and a 46–90-day major outlier cannot enter any UI or API
collection labelled current.
Deployment-boundary regressions additionally prove that file-backed SQLite
creates its configured parent before Alembic connects; an ARQ worker cannot
complete startup against a revision below Alembic head; a one-shot Railway
pre-deploy migration is documented independently from the worker command; and
only the mounted worker initializes, cleans, measures, and publishes runtime
artifact storage while the API reads the shared measurement without touching
its isolated artifact roots.
The live test is separate and never invoked by `make closed-test`.

Command:

```bash
make live-smoke
```

Required explicit environment:
```text
APP_MODE=live_test
YOUTUBE_API_KEY=...
BROWSER_ENABLED=true
```

Live smoke limits:
- 1 browser profile
- <=2 seed queries
- <=10 candidate channels
- <=50 enriched videos unless implementation chooses a lower limit
- no deep asset search
- no large comment crawl
- bounded scroll
- visible quota report before/after

Verify:
- Chromium opens and can complete a bounded discovery task
- YouTube API returns structured enrichment
- API/browser records are merged by canonical IDs
- outlier analytics execute
- local AI provider returns valid structured output
- a final niche report is generated

## 14. Live-test failure rule
A live failure must not be "fixed" by weakening the closed tests.

Classify the failure:
- credentials/configuration
- source page change
- API response change
- quota
- networking
- AI provider
- application bug

Repair the correct layer, rerun closed test, then rerun live smoke.
