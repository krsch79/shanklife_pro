# Starttider 2.1.1 delivery

Updated 2026-10-15. Implemented, tested, pushed, deployed and production-verified.

## Current refinement

User requested count-only availability search, then player identity selection after choosing a time. The signed-in account is fixed as player 1. Companions come from existing owner-scoped favorites or a live GolfBox directory search by name or membership number. Both booking and new automatic jobs use the same exact-count picker. Closing a picker discards temporary choices. AI only infers search criteria/count, never assigns a booking identity. Existing access, favorite data, reservations, active jobs and historical records are retained.

- Application source: b5abf0f5bd38b074075cad30a526e08b54075745, pushed to GitHub main and codex/starttider-players before cutover. Later documentation commits do not change the runtime.
- Baseline source: 83daca04d8b814e740174560c84ed6b69e5c3e22, version 2.1.0.
- Development: /tmp/shanklife-players.tUk7Ke/repo, Python 3.11 environment /tmp/shanklife-sportsmodus.nqnY0T/venv311.
- No database migration or native iOS build. Existing webview follows the new web flow; no TestFlight upload.
- Assets and shell cache: 2.1.1-r2, with exact CSS/JS URLs in the service-worker cache.
- Authenticated, CSRF-protected POST /starttider/players is read-only and no-store. Directory requests do not claim/change workspace revisions. Name lookup reuses existing GolfBox marker search; verified actual result labels start with a membership number, followed by name/club. Chosen membership numbers are looked up again before review. No client-supplied name is trusted for booking.
- 202 Python tests passed, including 37 Starttider cases: mandatory self-first identity, exact participant count, stable favorite ownership, name ambiguity, membership lookup, empty/error/CSRF/access behavior, old reviews without the account blocked, plus existing booking/idempotence/uncertainty/job/access regressions.
- Synthetic browser QA: count-only search, fixed self, favorite selection, name search across two club memberships, number lookup, full-count blocking, removing a companion, cancel/discard, one-player flow, combined three-player selection and new-job progression. Complete booking against a local simulator only. Real GolfBox read-only name lookup contract verified; no production reservation, cancellation or job activation used as QA.
- Responsive checks at 320/393/1440 px; no document-wide horizontal overflow. Screenshots under the current Codex visualization directory (starttider-211-*).
- Test runner is unittest, not an assumed pytest installation. Browser viewport override is a browser-level capability. These concrete corrections are documented in project AGENTS.md; shared /Volumes/Shared/AGENTS.md is unchanged.

## Production verification

- Completed 2026-10-15 at 13:36:32 Europe/Oslo. Guard shanklife-starttider-release-rzgxoa.service exited successfully (status 0). Its independent 25-minute rollback timer is inactive.
- Recovery material is private at /home/kristian/shanklife-release-backups/starttider.rzgxoa: consistent SQLite snapshot, double-verified checksum, baseline and release Git bundles, original cron, controller and verification script. Markers backup-ready, migration-verified, verified and mail-verified exist. Never commit runtime/backup files.
- Maintenance covered the entire stop/backup/deploy/restart window. Both pro.shanklife.no and app.shanklife.no returned the actual static maintenance HTML with HTTP 503 during downtime. Main service and project cron were paused; the other database service remained running. Core record counts/digests and tour selection matched before unlock. No migration was required.
- Actual systemd unit read before final health checks. Service enabled/active, exact /tmp/shanklife_pro_venv/bin/python app.py process, listening port 5055, removed maintenance flag and inactive rollback timer verified. Both public HTTPS health endpoints returned 2.1.1.
- Authenticated Starttider shell/state/favorites/jobs/history, home/rounds/insight, old redirect and native app host returned expected results. Actual read-only GolfBox lookups by a companion's full name and membership number both returned the expected membership. No production reservation, cancellation or automatic job was created for testing.
- Real authenticated Chrome showed Starttider with the count selector, no first-step participant picker, and exact starttider.js?v=2.1.1-r2. Original Chrome tab had been closed, so a new authenticated tab was used. Existing iOS binary uses this web flow; no new archive or TestFlight upload.
- Deployment email to Kristian confirmed by send_mail True and mail-log success entry. Production worktree was clean at exact application source b5abf0f before documentation-only handoff.
- Synthetic QA server stopped and process exit verified; responsive browser override reset. All required release work complete. See README.md for architecture and tests. Retain the historical 2.1.0 notes below for recovery context.

Resume command if quota interrupts: Fortsett Shanklife Sportsmodus fra siste kontrollpunkt.

---

# Historical: Starttider 2.1.0 delivery

Updated 2026-10-15. Implemented, pushed, deployed and verified. User approved Søk først after the visual/functional proposal. Existing BalleTour entitlement was retained; broader access was not included. No native binary or TestFlight upload was requested or produced.

## Source and runtime

- Application source commit: ca3b8477b60c953c201c5cd85ff2ad26d20cdab5, published to GitHub main and codex/starttider before deployment. Later documentation-only commits do not change this runtime version.
- Baseline: f3ba8a75b7a066081251afb6f99b18747a7edc14, version 2.0.0.
- Work clone: /tmp/shanklife-starttider.o6EiSi/repo. Verified local Python 3.11 dependencies: /tmp/shanklife-sportsmodus.nqnY0T/venv311.
- Production SSH alias shanklife-pi; /home/kristian/shanklife_pro is also mounted at /Volumes/Shared/shanklife_pro. Never develop directly in this SMB production source.
- Production service shanklife-pro.service is enabled and active; expected /tmp/shanklife_pro_venv/bin/python app.py and port 5055 verified. Server timezone is Europe/Oslo.

## Delivered behavior

Finn tid, Mine tider, Automatikk and paginated Historikk replace the long mixed page. Favorites are selected in a searchable picker; five initial rows are shown, with the full list on request. Existing favorites remain unchanged. Search can use just a number of places before all players are selected. Member numbers scoped to the account provide stable references across favorite-sync row replacement.

Search drafts/results and bounded AI history are server-owned. AI can only propose validated search changes, never execute bookings or activate jobs. A local fallback handles common requests when AI is unavailable. Old results are invalidated after a search change. Single-use, expiring owner-bound reviews protect reservations, own-place cancellations, stop actions and all three existing job types. Unknown external outcomes are not replayed. Recurring reviews show the first actual play date; automatic jobs remain distinct from confirmed reservations.

The shell renders without external reads. Coming bookings load separately with a 90-second owner cache and visible fetch time; failed fetches retain the last known data with a warning. Private responses are no-store. Static Starttider CSS/JS and the PWA shell cache use 2.1.0-r4. No offline booking queue exists.

/starttider is canonical. Legacy /balletour/ai GET links redirect; old POST forms cannot replay previous actions. Existing iOS SportsWebScreen opens the same new flow through that legacy URL. Full data/access/schema details and test commands are in README.md.

## Production rollout and recovery

- Completed 2026-10-15 at 13:06:35 Europe/Oslo. Independent controller shanklife-starttider-release-ZYdOh0.service exited successfully. Its 25-minute rollback timer was disarmed after verification.
- Private recovery directory: /home/kristian/shanklife-release-backups/starttider.ZYdOh0. Contains a consistent roughly 4.1 GiB SQLite snapshot, double-verified SHA-256, baseline Git bundle, release bundle, original cron and controller. Never commit or publish this directory or any runtime database/credentials.
- Maintenance covered application stop, paused project cron, backup, schema creation, restart and pre-unlock checks. Existing source was clean before cutover.
- Before opening the app, row counts/digests for rounds, round_players, score_entries, trackman_rounds, golfbox_favorites, golfbox_scheduled_bookings, golfbox_recurring_bookings, golfbox_watch_bookings and golfbox_booking_runs matched the baseline. Tour round selection also matched. New additive workspace/action tables were verified.
- balletour-survey.service is another database user and stayed running. Rollback restores source while retaining additive schema and current data. Never blindly restore the database over another service's writes.
- Public pro.shanklife.no and app.shanklife.no health returned 2.1.0; maintenance flag absent; timer inactive. Markers backup-ready, migration-verified, verified and mail-verified exist.
- Deployment email to Kristian confirmed by mailer return and success log.

## Evidence and limits

- 195 Python tests passed, including 30 new functional cases for access/CSRF/revision protection, stable favorites across reordered sync, incomplete player selection, AI context/fallback, expired or repeated reviews, lost slots, payment, timeout uncertainty, own-place cancellation, all three job types and separate confirmation when a watch finds an immediate slot.
- Browser QA used a disposable synthetic DB with local GolfBox responses. Verified search, player picker, review/confirm, own cancellation, watch activation/stop/history, controlled HTTP 503 with retained input and successful retry, and AI after-17 updates preserving other fields.
- Responsive views 320/393/852 landscape/1440 had no document-wide horizontal overflow. At 393px the primary search action was visible around y=588. Rendered versioned asset URLs matched the shell cache.
- Authenticated production shell, state/favorites/jobs/history data, home/rounds/insight and native-host route returned 200; legacy redirect verified. Real Chrome displayed the new page, the real account's 18 favorites behind the five-row picker, and a successful GolfBox upcoming-booking read with zero reservations. No production booking, cancellation, AI search or job activation was performed as QA.
- Physical iPhone keyboard/safe area and actual reservations/cancellations remain separate acceptance checks. Do not claim those actions were tested against live GolfBox.

Durable screenshots and starttider-implementering-qa.json are in /Users/kristianschiander/.codex/visualizations/2026/10/13/01a134c1-d370-7be0-a079-84e7fa60c717. Detailed test logs and private controller source are in the staging parent. Synthetic QA server stopped and viewport overrides reset.

## Continuation

No remaining release work. Read AGENTS.md, README.md, this status and current Git/runtime state before a new change. Temporary staging paths may disappear. Preserve actual users' data and never use live reservations as casual tests. Project AGENTS.md records stable favorite references and the correct fixture setup procedure; shared /Volumes/Shared/AGENTS.md was not changed.

User resume command after a future quota interruption: Fortsett Shanklife Sportsmodus fra siste kontrollpunkt.
