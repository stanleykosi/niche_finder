# Project Request

## 1. Project name
**YouTube Niche Intelligence Engine**

## 2. Purpose
Build an autonomous research system that discovers and evaluates promising YouTube Shorts and long-form niches using free or locally controlled data sources.

The product is not a vidIQ clone and is not primarily a video-optimization tool. Its core job is **niche discovery and niche validation**.

It must answer:

> What YouTube niches or repeatable video formats show strong current demand, repeated outliers, sufficient content supply, manageable direct competition, and a reproducible viral mechanism right now?

## 3. Primary research model
The product uses a hybrid source architecture:

1. **Autonomous Chromium research worker**
   - Uses Playwright + Chromium.
   - Performs controlled YouTube discovery and visual inspection.
   - Uses persistent research profiles.
   - Collects browser observations such as visible search results, Shorts presentation, titles, channels, related videos, visible transcripts when available, thumbnails, hooks, and page context.

2. **YouTube Data API worker**
   - Enriches known videos and channels with exact structured public metadata.
   - Retrieves channel uploads efficiently.
   - Retrieves public statistics and comments.
   - Maintains one quota-unit ledger across search, video, channel, playlist, and comment calls plus repeated snapshots.
   - Is optional for the bounded live smoke; Chromium plus yt-dlp provides a keyless public-metadata path.

3. **AI analysis worker**
   - Uses startup capability selection that prefers configured OpenRouter, then configured Ollama, then an evidence-driven deterministic live provider that validates actual bounded image inputs. Closed/development fixture modes alone use the deterministic fake; live/production may select the zero-key provider explicitly with `AI_PROVIDER=deterministic` but cannot select fixture fake. Explicit provider selection is strict; transient calls retry but never switch provider mid-run.
   - Performs classification, pattern comparison, niche naming, viral-mechanism analysis, winner/loser comparison, and report synthesis.
   - Must never calculate authoritative numerical metrics that deterministic code can calculate.

4. **Deterministic analytics engine**
   - Calculates outliers, views-per-day, momentum, channel baselines, saturation signals, idea-ceiling metrics, clip-ceiling metrics, and confidence inputs.

5. **Evidence database**
   - Stores every observation with provenance, timestamp, research run, source type, and confidence where appropriate.

## 4. User workflow

### 4.1 Autonomous research
The user starts a research run with parameters such as:
- Shorts, long-form, or both.
- Target language.
- Target region.
- Seed topic(s), or broad discovery mode.
- Recency windows.
- Faceless production suitability (reported per idea, never used to hide ideas).
- Minimum idea ceiling.
- Maximum acceptable saturation.
- Number of channels/videos to inspect.
- Deep-research mode.

The system then:
1. Generates a bounded research plan.
2. Runs controlled Chromium discovery and YouTube API discovery/enrichment.
3. Expands promising queries and channels.
4. Builds channel baselines.
5. Detects recent outliers.
6. Groups videos into repeatable formats.
7. Compares winners and losers.
8. Identifies viral mechanisms.
9. Measures direct competitors and saturation.
10. Estimates idea ceiling.
11. Evaluates clip/footage availability through pluggable asset connectors.
12. Semantically validates candidate assets with a multimodal model and keyless/licensed web search where configured.
13. Produces ranked niche opportunities with evidence and risks.

### 4.2 Direct analysis
The user may provide:
- A YouTube video URL.
- A Shorts URL.
- A channel URL.
- A search query.
- A known niche.

The system must use the same research pipeline to validate the opportunity instead of producing a shallow one-off answer.

## 5. Niche quality criteria

Every niche must be evaluated on at least:

### 5.1 High idea ceiling
Questions:
- Can the format support dozens of distinct videos?
- Are new subjects appearing regularly?
- Can one successful mechanism be reused across many subjects?
- Can successful subtopics branch into related videos?

### 5.2 High clip ceiling
Questions:
- Is enough usable footage available?
- Can several examples be shown per video?
- Are new clips/assets appearing regularly?
- Can the visual payoff or reveal be shown clearly?

### 5.3 Proven audience demand
Evidence:
- Multiple high-view videos.
- Recent high-performing uploads.
- Repeated outliers.
- Multiple successful channels.
- Strong channel-level recent performance.

### 5.4 Relatively low saturation
Evidence:
- More than one successful channel.
- Manageable direct-format competitor set.
- Visible room for improvement.
- Weak/average execution among some competitors.
- Enough variation to create a recognizable differentiated version.

### 5.5 Recent momentum
Recent outliers are more valuable than historical virality.

### 5.6 Reproducible viral mechanism
The tool must identify the deeper mechanism, not only the broad subject.

Examples:
- Visual impossibility -> failed attempts -> correct attempt -> explanation.
- Mystery -> evidence -> reveal.
- Ranking -> escalation -> final winner.
- Mistake -> correction -> payoff.
- Before -> transformation -> result.

## 6. Shorts and long-form
Shorts and long-form must have separate opportunity assessments.

The application must support:
- Shorts-only niche.
- Long-form-only niche.
- Shorts-first with long-form expansion.
- Strong fit for both.
- Strong demand but poor production feasibility.

## 7. Required outputs

Each research run must produce:

### 7.1 Ranked niche opportunities
For each niche:
- Niche name.
- Sub-niche.
- Repeatable format.
- Shorts suitability.
- Long-form suitability.
- Confidence.
- Recommendation verdict.

### 7.2 Evidence
- Channels examined.
- Videos examined.
- Recent outliers.
- Median/channel baseline.
- Outlier multiples.
- Recent momentum.
- Direct competitors.
- Browser observations.
- API observations.
- Research timestamps.

### 7.3 Viral-mechanism analysis
- Primary mechanism.
- Secondary mechanism.
- Viewer question.
- Hook structure.
- Reveal/payoff structure.
- Evidence.
- Alternative explanation.
- Confidence.

### 7.4 Winner-versus-loser analysis
Compare strong and weak uploads on:
- Topic.
- Hook.
- Opening visual.
- Script/presentation structure.
- Curiosity question.
- Clip count.
- Pacing.
- Reveal.
- Length.
- Captions.
- Ending/payoff.

### 7.5 Idea ceiling
- Topic clusters.
- Generated candidate ideas.
- Unique ideas after semantic deduplication.
- Repeatable formats.
- Viable series.

The reported ceiling is the number of ideas that survive semantic deduplication **and** the clip preflight. A positive recommendation requires at least 10 such ideas. Generated text without evidence-backed, semantically matching visual supply does not count.

### 7.6 Clip ceiling
- Asset coverage.
- Source diversity.
- Video/image availability.
- Rights/source metadata where connectors provide it.
- Unsupported topics.

Clip feasibility is the first candidate hard gate. At least 70% of proposed ideas must have three or more available clips, a reveal/payoff asset, multimodal semantic fit, and adequate source diversity. Licensing metadata is preserved but does not gate niche discovery.

### 7.7 Saturation
- Direct competitor count.
- Active competitor count.
- Recent upload density.
- Format similarity.
- Evidence of poor-performing copycats.
- Improvement gaps.

### 7.7.1 Current-demand and replication gates
- Use a 45-day primary outlier window and a 90-day supporting baseline by default.
- Require current outliers on at least two independent channels and at least three current outlier videos overall.
- Expand each discovered channel through its uploads playlist and compute channel-level upload frequency, median views/day, outlier frequency, consistency, and largest-video concentration.
- Require at least three independently successful channels; no one channel should dominate the positive evidence.
- Match at least three winner/loser pairs across at least two channels before claiming a packaging or mechanism difference.
- Identify Shorts through a YouTube-rendered Shorts surface where possible. Duration alone is only probable evidence.
- Extract viral mechanisms from transcripts, opening visuals, captions, observable structure, pacing, reveal, and matched performance. The mechanism must repeat across at least two channels.
- YouTube current performance is the primary trend signal. External search-trend data is optional corroboration and must be labelled separately.

### 7.8 Action plan
- Why now.
- Primary risk.
- Suggested differentiation.
- Initial Shorts test.
- Initial long-form test.
- Continue/reject criteria.

## 8. Core product principles
1. **Evidence before conclusion.**
2. **Current performance before historical fame.**
3. **Formats and viral mechanisms before broad niche labels.**
4. **Multiple-channel confirmation before recommendation.**
5. **Deterministic metrics before AI judgment.**
6. **Every derived claim must retain provenance.**
7. **No invented analytics.**
8. **Browser and API observations are distinct data types.**
9. **Research must be bounded and reproducible.**
10. **The system must work locally before live services are enabled.**

## 9. MVP success criteria
The MVP is complete when it can:

1. Start a research run from a seed query.
2. Execute a bounded Chromium discovery plan against the local closed-test fixture.
3. Route mock YouTube API requests through a quota-aware source router.
4. Discover candidate videos/channels.
5. Expand channels into recent uploads.
6. Compute channel baselines and outliers.
7. Group videos into format/topic clusters.
8. Generate winner/loser comparisons.
9. Generate viral-mechanism hypotheses using the local AI interface or deterministic test double.
10. Produce ranked niche recommendations with evidence.
11. Display results in the web dashboard.
12. Preserve all observations and provenance in the database.
13. Pass the complete closed-test suite with external networking disabled.
14. Support a separately gated live-test mode for real APIs and Chromium after closed testing passes.

## 10. Explicit non-goals for the first build
- Becoming a general YouTube SEO suite.
- Thumbnail A/B testing.
- Creator revenue estimation.
- Subscriber-growth prediction.
- Automatic video production.
- Uploading videos to YouTube.
- Scraping thousands of pages without bounded research objectives.
- Building a browser extension.
- Building paid-data-provider integrations.
- Training a custom foundation model.
