# Starttider 2.1.4 checkpoint

Updated 2026-10-15. In isolated clone /tmp/shanklife-booking-count.H2pg9J/repo. Baseline 8c36c317813bbd8b70ae84c9025b6c1c28c6e798, production2.1.3.

User authorized booking fewer participants than search capacity, and full database backups only when release changes schema/existing data. selected_members accepts 1..searched count with self first; review/capacity confirmation and new automatic jobs use actual named participants. Search count retained. Existing payment flow audited: positive price or returned payment requirement stops booking, releases temporary lock, never pays; user completes manually in GolfBox. Added mocked price-before-submit/cleanup regression. 230 Python tests pass; shell syntax/invalid release flag checked. No schema/data migration.

Deploy script now defaults SHANKLIFE_DATABASE_CHANGES=0; set1 for schema/migration/bulk data changes. This release must NOT take a full database backup. Keep source rollback, maintenance, row/schema verification and health checks. Existing private backups retained. Do not run the old wrapper with unconditional SQLite snapshot. Source-only controller prepared at /tmp/shanklife-booking-count.H2pg9J/release_guard.py; private state /home/kristian/shanklife-release-backups/starttider.2DZC7Z. It validates unchanged schema/core rows and unchanged full-backup file set, retains source rollback and independent timer.

Browser QA passed synthetic 2places->1player complete booking and4places->2players review at393/1440. iPhone request added: existing native2.0.0(21) has Profil->Starttider via authenticated webview and legacy GET redirect. Native UI test passed on iPhone18Pro/iOS27: Profil->Starttider opened authenticated web page, chose a time from a two-place search and reviewed a booking for player1 only. Do not reset/change fixture during XCTest. Xcode driver exited0; result /tmp/shanklife-booking-count.H2pg9J/starttider-iphone.xcresult. Obtain explicit process exit before another Xcode run. No TestFlight upload authorized.

Shared AGENTS.md unchanged; project guidance documents new backup and participant-count rules.
Resume command: Fortsett Shanklife Sportsmodus fra siste kontrollpunkt.

---

# Starttider 2.1.3 delivery

Updated 2026-10-15. Implemented, tested, pushed, deployed and production-verified.

## Single-course club selection fix

GolfBox redirects clubs with one course from chooseclub.asp directly to grid.asp. The redirected page uses ddlRessource_GUID instead of the multi-course selector ddlRessoruce. Starttider and the booking resolver previously read only the latter. A shared parser now supports both and discards placeholder/non-GUID values such as x (Velg fasilitet). Clubs with one course add directly; clubs with several courses retain explicit selection. Exact resource resolution and removed-resource refusal remain unchanged. No schema change or new native iOS build.

- Baseline 1fb8f405302b56675fdd910eeb08c8e97439be97, version 2.1.2. Application source 9ddd3fa9b04095535987e00e411808cc1df492e8, pushed to GitHub main and codex/starttider-single-course before deployment. Later documentation-only commits do not change the runtime.
- Development /tmp/shanklife-single-course.b7Z1zX/repo; Python 3.11 environment /tmp/shanklife-sportsmodus.nqnY0T/venv311. 61 targeted and 226 total tests passed. Five new regressions cover redirected markup, invalid placeholder rejection, multi-course preservation, exact single-course resolution, authenticated resource endpoint/cache and downstream search.
- Live read-only verification before and after deploy: Ballerud and Grini each return one real resource and resolve that exact resource. Haga still returns two distinct resources. Real catalog154 entries, both account memberships with original-club restore and name/member directory lookups passed. No booking window, reservation, cancellation or automatic job created for QA.
- Synthetic browser QA at 320/393/1440 px: Grini adds directly, Haga retains two course choices, selected Grini plus Haga shareholder course survive reload and reach the availability request. No document-wide horizontal overflow. Screenshots starttider-213-mobile.png and starttider-213-desktop.png visually inspected; starttider-213-qa.json in the current visualization directory records checks. Synthetic server stopped with confirmed exit143; viewport override reset.
- Assets/cache version2.1.3. Real authenticated production Chrome rendered v2.1.3 and exact starttider.js?v=2.1.3. Existing user course selections were preserved during production verification. Physical-device testing and real booking authorization are not claimed.

## Production rollout

- Controller shanklife-starttider-release-2cwAxi.service exited successfully; independent rollback timer inactive. Private recovery state /home/kristian/shanklife-release-backups/starttider.2cwAxi retains consistent SQLite snapshot, double-verified checksum, baseline/release bundles, original cron and controllers. Markers backup-ready, migration-verified, verified and mail-verified confirmed. Do not publish runtime or recovery files.
- Both public hosts showed actual static maintenance HTML and HTTP503 during downtime. Main app/project cron paused for backup. Standard deploy script also took its normal backup. Existing core rows, GolfBox favorites/jobs/history and tour selection matched before unlock. Other shared DB service remained running; source rollback preserves current shared data.
- Actual systemd unit read; enabled/active shanklife-pro.service, exact /tmp/shanklife_pro_venv/bin/python app.py process, listening5055 and removed maintenance flag verified. Both pro.shanklife.no and app.shanklife.no public health returned2.1.3. Authenticated Starttider state/favorites/jobs/history, home/rounds/insight, legacy redirect and native host passed. Production worktree clean at exact application source before documentation handoff.
- Deployment email confirmed by mailer return True plus matching success log. No new iOS archive or TestFlight upload.
- Disk reserve after this release is about3.5GiB. Retained existing backups; do not delete them automatically. Before another release requiring snapshots, arrange sufficient capacity and rerun disk preflight (current reserve cannot accommodate another full4.7GB snapshot).
- Shared /Volumes/Shared/AGENTS.md unchanged. Project AGENTS.md records redirected single-course handling with real markup regression fixtures, plus consuming complete streamed maintenance responses before printing status.

All requested work complete. Read current Git/runtime state before another change. Temporary staging paths may disappear.
Resume command if quota interrupts a future continuation: Fortsett Shanklife Sportsmodus fra siste kontrollpunkt.

---

# Starttider 2.1.2 delivery

Updated 2026-10-15. Implemented, tested, pushed, deployed and production-verified.

## Current requested refinement

User requested prefix filtering (H, Ha), click-to-add course selection and removable selected courses. Follow-up clarified that clubs can have multiple courses (Haga main course/shareholder loop) and players can have multiple memberships. Development used the isolated clone; production code changed only under the guarded maintenance rollout.

- Baseline 3e0dcacf07e910f7240e5fd508afa0eb49ad34f9, version 2.1.1. Isolated clone /tmp/shanklife-courses.sjhFYM/repo. Python 3.11 test environment /tmp/shanklife-sportsmodus.nqnY0T/venv311.
- Authenticated real GolfBox club selector has 154 entries; Haga/Hauger verified. Club resources are fetched on selection; one course adds directly, multiple courses require an explicit choice. Qualified names preserve the exact resource through search, review and new jobs. Removed explicit resources fail; no fallback to the first course. Existing legacy club-only jobs keep their original behavior; new jobs require one explicit course. Legacy/AI club-only searches expand resources with a maximum of eight actual courses.
- Owner-scoped catalog/resource caches use existing workspace cache_json, expire after 24 hours and preserve bookings cache/revision. Known fallback clubs plus retry on first failure, last good list on later failure. No new tables or data migration.
- Existing membership discovery parsed only the POST acknowledgement after switchClub. GolfBox does not include updated identity there. Refreshing myFrontPage.asp after a switch verifies actual club/member number. The exact corrected functions were read-only probed on the Pi: two memberships found, Haga present, original club restored, both memberships share one GolfBox player GUID. No DB writes, booking window, reservation or cancellation used in this probe.
- Availability switches to the account's membership for the playing club where available. Review always keeps account first and shows each player's chosen membership. Membership numbers are verified together before review; duplicate person GUIDs across different memberships are rejected. Companion membership choice is explicit. GolfBox remains authoritative for booking rights and existing payment/access stops remain.
- 221 Python tests passed, including 49 Starttider tests and 7 dedicated GolfBox resource/membership tests. Includes correct second-resource resolution, no fallback when removed, preserved legacy jobs, fresh membership identity/restore on failure, resource-specific availability, duplicate people, owner membership display and rejection without resource fallback.
- Native iOS uses the existing authenticated webview; no new binary or TestFlight upload. Static assets/cache use 2.1.2-r3.

## Production rollout and evidence

- Application source 9a3654a21fc23a03d3838453595cced9c02d8136, pushed to main and codex/starttider-courses before deployment. Later documentation-only commits do not change this runtime version.
- Completed 2026-10-15 at 21:44:46 Europe/Oslo. Controller shanklife-starttider-release-5KM9o2.service exited successfully; independent 25-minute rollback timer is inactive.
- Private recovery state /home/kristian/shanklife-release-backups/starttider.5KM9o2 contains consistent SQLite snapshot, double-verified checksum, baseline/release bundles, original cron and controllers. Markers backup-ready, migration-verified, verified and mail-verified exist. Never publish the recovery directory or runtime files.
- Both public hosts returned actual static maintenance HTML with HTTP 503 during the entire stop/backup/restart window. Existing core row counts/digests and tour selection matched before unlock. No schema migration. Other shared database service stayed running; rollback preserves current data rather than overwriting its changes.
- Actual systemd unit read, service enabled/active, exact /tmp/shanklife_pro_venv/bin/python app.py process and listening port 5055 verified. Maintenance flag absent; both pro.shanklife.no and app.shanklife.no public health returned 2.1.2. Production worktree was clean at exact application source before documentation-only handoff.
- Authenticated shell/state/favorites/jobs/history, home/rounds/insight, legacy redirect and native host passed. Real read-only GolfBox name/member lookups still work. Catalog API returned154 clubs including Haga/Hauger. Haga resource API returned both main/shareholder courses. Actual resolver returned distinct resource GUIDs for those two courses under the same club GUID. New membership read found2 memberships including Haga and Ballerud and restored original club.
- Real authenticated Chrome showed exact 2.1.2-r3 script, Ha prefix results including Haga/Hauger, then the two separate Haga course choices. Only reading/opening suggestions was used; existing user selection was not changed.
- Browser QA verified H→Ha filtering, Haga course split, click-to-add, single-course direct add, removal, multiple-course search payload, reload persistence, future-dated search, self-first picker and final review showing Haga membership. Complete synthetic booking was tested before the final layout-only revision; final review was rechecked. 320/393/1440 views have no document-wide overflow. Screenshots and starttider-212-qa.json are in the current visualization directory.
- 221 Python tests passed. No live booking window, reservation, cancellation or automatic job used as QA. Physical-device keyboard/safe area and actual GolfBox booking authorization remain separate acceptance checks; membership existence does not itself prove every playing right.
- Deployment email confirmed by mailer return True and matching success log. Synthetic server stopped (exact process exit verified) and viewport overrides reset. No new iOS binary or TestFlight upload.
- All release work complete. README.md documents architecture, cache, permissions, old/new job resource boundaries and test commands. Read current Git/runtime state before a future change; temporary staging paths may disappear.

Shared /Volumes/Shared/AGENTS.md is unchanged. Project AGENTS.md documents authoritative SSH Git checks when SMB reports an index error and the correct switchClub/fresh-identity/resource handling.

Resume command if quota interrupts: Fortsett Shanklife Sportsmodus fra siste kontrollpunkt.

---

# Historical: Starttider 2.1.1 delivery

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
