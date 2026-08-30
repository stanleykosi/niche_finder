# AGENTS.md

## Mission
Build the YouTube Niche Intelligence Engine end-to-end.

## Canonical source
All authoritative product, architecture, implementation, and test instructions live in:

`/docs/canonical/`

Read these in order before changing code:
1. `Project request.md`
2. `Technical Specification.md`
3. `Implementation plan.md`
4. `Test plan.md`
5. `Build state.md`

If code, comments, old docs, or assumptions conflict with `/docs/canonical/`, the canonical docs win.

## Execution rules
- Implement the full architecture and all required files before running tests.
- Do not use live YouTube, Google, Ollama-cloud, or other external services during implementation or the closed test.
- After implementation is complete, run the full closed test suite once and repair until green.
- Only after the closed test is green may the live-test phase begin.
- Keep `docs/canonical/Build state.md` updated as work progresses.
- Never invent missing data. Preserve source, timestamp, and confidence for derived observations.
- Prefer deterministic code for metrics; use AI only for interpretation/classification.
- Do not add alternative architectures or duplicate source-of-truth documents.
