# Sportsmodus delivery and continuation

Updated 2026-10-14. Web/API 2.0.0 deployed and verified. Signed iOS 2.0.0 (21) archive delivered; user explicitly selected archive delivery only, so no TestFlight upload is pending.

## Agreed scope
One Shanklife product in Sportsmodus with BalleTour as its tour; web, API and native iOS together. Online scoring only. Preserve tournament calculation/ranking, historical results, old URLs, ownership and central access boundaries. Qualification (20 rounds) is displayed separately from ranking.

## Delivered
- Shared five-area navigation: home, rounds, insight, tour and profile, with desktop sidebar and mobile navigation.
- Personal home, combined owned outdoor/TrackMan history, shared profile/integrations, progressive player setup and quick score controls. Existing functions remain reachable through the common shell.
- Explicit tour attachment and idempotent legacy migration. A new private Ballerud round stays private. Legacy tour history, statistics/API queries and admin cleanup use consistent selection.
- Online saves retain the current input on failure and allow retry. No persistent offline queue. Full completion presents the result before optional GolfBox submission.
- Native five-area navigation, owned API data, authenticated web functions and score controls. Embedded web functions show one navigation bar. PWA resources are versioned and private responses are not cached.

## Production
- Application source commit: 9e51d6c7c5068a7435e26cf0d4d4475dffcef933, pushed to GitHub main and codex/sportsmodus before deployment. Later documentation-only commits do not change this application version.
- Previous source: 876745006f4b5390fefc04a0b0fd750debe5218a (1.9.66).
- Pi: SSH alias shanklife-pi; source /home/kristian/shanklife_pro, also mounted at /Volumes/Shared/shanklife_pro. Develop in a clean clone, never directly in the SMB production source.
- Deployment finished 2026-10-14 at 08:51 Pi journal time. Controller shanklife-sportsmodus-release-KnVXYm.service exited successfully. Its independent rollback timer was disarmed after verification.
- Private recovery directory: /home/kristian/shanklife-release-backups/sportsmodus.KnVXYm. Contains consistent SQLite backup, double-checked SHA-256, baseline Git bundle and controller state. Never commit or publish this directory or database.
- Maintenance covered the stop, backup, migration and restart. Before unlocking, full core-row digests and the legacy 60-round tour selection matched the baseline: 101 rounds, 1233 score entries, 108 round players, 195 TrackMan projections. Existing core records were preserved.
- shanklife-pro.service enabled and active; expected /tmp/shanklife_pro_venv/bin/python app.py process and port 5055 verified; maintenance flag absent. Both public HTTPS health endpoints reported 2.0.0.
- Authenticated production home, rounds, insight, tour and overview API returned 200. Private simulator history ownership and scorecard access verified. Real Chrome displayed the authenticated Sportsmodus home.
- Deployment email to Kristian confirmed by both mailer return value and success log. Controller markers backup-ready, migration-verified, verified and mail-verified exist.

## Validation and limits
- Python 3.11: 165 tests passed, including migration/data preservation, access/ownership, legacy series, full web finish flow and maintenance guards.
- Browser: checked 320, 393, 852 landscape, 1280 and 1440 widths; no document-wide horizontal overflow. Synthetic full round flow and saved navigation verified. Controlled 503 retained 3 strokes; retry saved the same 3 and displayed server confirmation.
- Native: 2 XCTest UI tests passed, including server save, next/previous, completion/read-only result and authenticated shared profile with no duplicate tab bar. Signed Release archive succeeded and signature verified. Simulator-only login/test hooks absent from Release; no runtime database or environment files bundled.
- Physical-device GPS, real start-time bookings/cancellations, GolfBox score submission and invitation delivery were not exercised against external services. Do not claim those external actions were performed.
- Other service balletour-survey.service also uses the SQLite database. The release rollback restores source while retaining additive schema and current data; never blindly replace the live database while other writers run. Recovery tooling remains private in the backup directory.

## Artifacts and development
- Staging clone: /tmp/shanklife-sportsmodus.nqnY0T/repo; Python 3.11 test environment: /tmp/shanklife-sportsmodus.nqnY0T/venv311.
- Durable artifact directory: /Users/kristianschiander/.codex/visualizations/2026/10/13/01a134c1-d370-7be0-a079-84e7fa60c717.
- Final signed native archive: Shanklife-2.0.0-21-final-xcarchive.zip in that artifact directory. This is an Xcode archive, not a TestFlight release or an installable App Store distribution.
- Actual web/native screenshots and browser QA JSON evidence are in the same artifact directory. Native detailed results: /tmp/shanklife-sportsmodus.nqnY0T/native-ui-polished.xcresult; build logs and archive also in that staging parent.
- Local synthetic QA server is no longer required; stop only its exact process when closing QA. It is not production.
- No further implementation or publication is pending within the approved delivery. Future native distribution requires a user request and appropriate Apple distribution/export workflow.

## Continuation
Read AGENTS.md, this file, git status and current production state before further changes. Temporary paths may disappear; production and GitHub are the source of truth for code. Never infer success from a running session: obtain its exit code.

User resume command if a future quota interruption occurs: Fortsett Shanklife Sportsmodus fra siste kontrollpunkt.
