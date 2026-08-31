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
- This workstation is editing/control-plane only. Do not install project dependencies, start application services, run builds, run test suites, launch browsers, or execute research jobs locally.
- Run all builds, tests, browser checks, migrations, smoke tests, and research jobs only in the deployed Vercel and Railway environments using their configured services and MCP tooling.
- A local closed-test pass is not required before deployment or live validation. Hosted failures are valid test evidence: inspect hosted logs/status, repair the correct layer, redeploy, and verify again in the hosted environment.
- Do not add or restore heavyweight local ML/GPU dependencies. The workstation has no GPU and limited CPU capacity.
- Keep `docs/canonical/Build state.md` updated as work progresses.
- Never invent missing data. Preserve source, timestamp, and confidence for derived observations.
- Prefer deterministic code for metrics; use AI only for interpretation/classification.
- Do not add alternative architectures or duplicate source-of-truth documents.
