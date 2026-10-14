# Sportsmodus implementation status

Updated 2026-10-14. In progress; not deployed.

## Agreed scope
Sportsmodus; one Shanklife product with BalleTour as its tour; web, API and native iOS together; no offline scoring. Keep existing tournament calculation/ranking and access/ownership boundaries. Preserve old URLs and historical results.

## Workspace and baseline
- Clone: /tmp/shanklife-sportsmodus.nqnY0T/repo
- Branch: codex/sportsmodus
- Baseline: 876745006f4b5390fefc04a0b0fd750debe5218a (1.9.66)
- Runtime for local tests: /tmp/shanklife-sportsmodus.nqnY0T/venv311
- Production source is the SMB checkout; all implementation is in this clone.
- Analysis/design and agreed plan are in the chat's durable artifact directory: /Users/kristianschiander/.codex/visualizations/2026/10/13/01a134c1-d370-7be0-a079-84e7fa60c717

## Implemented in staging
- Explicit BalleTour attachment, idempotent legacy migration, consistent tour/statistics/API queries and safe admin tour cleanup.
- Sportsmodus shell, personal home, combined owned rounds/TrackMan history, insight, common profile, progressive player setup and online quick scoring. Old URLs retained. Common PWA scope.
- Native five-area navigation, shared data and authenticated web functions, compact tour progress/rules and online score controls. Fixed initially blank native scoring loader; saved score tested through next/previous hole.
- Production remains baseline 1.9.66 and clean. Implementation checkpoint 1e51218 is pushed to codex/sportsmodus; final fixes still need commit/push before rollout. Read-only preflight: 101 rounds, 1233 score entries, 108 round players, 195 TrackMan projections, 60 legacy tour rounds, 20 required qualifying rounds. Migration selection matches existing tour selection. Database about 3.2 GB; never copy it into Git.

## Verification checkpoints
- Python 3.11: 165 tests passed, including migration/access/legacy series, complete web finish flow and pre-import maintenance guard. Exact production pre-unlock metric gate also passed on a legacy-schema fixture.
- Web: core views checked at 320, 393, 852 landscape, 1280 and 1440; no document-wide horizontal overflow. Local browser creation on Ballerud stayed a normal round and saved birdie/par across forward/backward hole navigation.
- iOS Release compilation passed. `native-ui-final.xcresult`: two UI tests passed, including next/previous, server save, full completion/read-only result and authenticated common profile. Final signed Release archive: `/tmp/shanklife-sportsmodus.nqnY0T/ShanklifeSportsmodusFinal.xcarchive`. TestFlight choice requested asynchronously; no upload authorized yet.
- Local QA server: `/tmp/shanklife-sportsmodus.nqnY0T/demo_server.py`, Python 3.11, 127.0.0.1:5057, disposable synthetic user demo/demo-demo. No mail/weather/integration writes. Stop exact server process when finished.
- Simulator: iOS 27.0 runtime installed; iPhone 18 Pro F0923B62-22AD-4A52-A784-4E8677589BF4. Full logs and results are in the staging parent directory; durable browser evidence is in the artifact directory.

## Required remaining work
1. Web success/503/retry now verified: retained 3 strokes, retry saved the same 3 and showed server confirmation. Evidence: sportsmodus-save-retry-qa.json. No offline storage. Finish final evidence export and roll out.
2. Rollout controller ready outside repository: `/tmp/shanklife-sportsmodus.nqnY0T/release_guard.py`. It pauses main app/its cron, takes consistent SQLite backup with SHA, gates legacy row digests and round selection before unlock, and arms 15-minute independent source rollback. The survey service also reads this DB and stays running; automatic rollback deliberately retains the additive schema/database to preserve other writers. Keep private runtime outside repository.
3. Deploy complete web/API change through Pi script only, confirm actual service/process/5055/public pro/app health and migration counts, then verified deployment email.
4. Native signed archive/distribution after checking available signing and Apple access. Report exact native delivery state; do not claim TestFlight based on an unsigned build.

## Resume
Read this file, git status and AGENTS.md before making changes. Check current usage limits and production state. Continue the first incomplete item. Never infer that a running command succeeded: obtain its exit code.

User resume command: Fortsett Shanklife Sportsmodus fra siste kontrollpunkt.
