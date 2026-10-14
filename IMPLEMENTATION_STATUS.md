# Sportsmodus implementation status

Updated 2026-10-14. In progress; not deployed.

## Agreed scope
Sportsmodus; one Shanklife product with BalleTour as its tour; web, API and native iOS together; no offline scoring. Keep existing tournament calculation/ranking and access/ownership boundaries. Preserve old URLs and historical results.

## Workspace and baseline
- Clone: /tmp/shanklife-sportsmodus.nqnY0T/repo
- Branch: codex/sportsmodus
- Baseline: 876745006f4b5390fefc04a0b0fd750debe5218a (1.9.66)
- Runtime for local tests: /tmp/shanklife-sportsmodus.nqnY0T/venv
- Production source is the SMB checkout; all implementation is in this clone.
- Analysis/design and agreed plan are in the chat's durable artifact directory: /Users/kristianschiander/.codex/visualizations/2026/10/13/01a134c1-d370-7be0-a079-84e7fa60c717

## State
Production unchanged. Initial architecture review underway. Fresh dependencies being installed. Xcode 27 available; simulator access requires unsandboxed xcrun. No simulator was booted at start.

## Required remaining work
1. Explicit tour attachment preserving legacy classification; consistent web/API queries and role checks.
2. Sportsmodus shell and home with real personal data; unified round history/profile, round setup/scoring, tour, insight/start times and all retained features.
3. Native Sportsmodus five-area navigation and shared data/API presentation.
4. Meaningful migration/access/regression tests; browser desktop/mobile and native build/simulator checks.
5. Documentation, both changelogs and version. Safe release with rollback, maintenance, GitHub and notification. No partial deployment.

## Resume
Read this file, git status and AGENTS.md before making changes. Check current usage limits and production state. Continue the first incomplete item. Never infer that a running command succeeded: obtain its exit code.

User resume command: Fortsett Shanklife Sportsmodus fra siste kontrollpunkt.
