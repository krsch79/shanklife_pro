# Starttider delivery checkpoint

Approved 2026-10-15: implement the Søk først proposal in the chat artifact starttider-vurdering.md. Preserve existing BalleTour access; access expansion is not included. Web page is also used by native iOS; no native distribution requested.

Baseline production f3ba8a75b7a066081251afb6f99b18747a7edc14, version 2.0.0. Work clone /tmp/shanklife-starttider.o6EiSi/repo, branch codex/starttider. Verified Python 3.11 dependencies /tmp/shanklife-sportsmodus.nqnY0T/venv311. Production database about 4.1 GB and survey service is another writer. Never edit SMB app source directly.

Implemented; final validation passed; deployment pending: server-owned search drafts, explicit single-use booking/job review, lazy external data; responsive four-area page and searchable player picker; context-aware AI patches; legacy URL; tests and browser QA; documented release, commit/push, consistent backup and maintenance deployment, health/ownership verification and deployment email.

Do not exercise real reservations, cancellations or job activation as QA. Use fixtures/mocks. A physical iPhone is not yet tested. Tests must verify access, CSRF, stale revisions, repeated confirmation, external uncertainty, player capacity/identity, AI context and all three job types. Read AGENTS.md before continuing.

If quota interrupts, finish with: Fortsett Shanklife Sportsmodus fra siste kontrollpunkt.

Validation 2026-10-15: 195 Python tests passed (30 new Starttider cases). Local browser verified search, player selection, reviewed booking, own-place cancellation with verification, watch activation, stop and history, controlled HTTP 503 with retained input and successful retry. Last edits only tighten mobile spacing and response error wording; resources use 2.1.0-r4 and the final QA server must be restarted before screenshots. No real GolfBox actions were sent.

Final browser QA: 393 px primary search button at y=588, no horizontal overflow at 320/393/852 landscape/1440. Versioned starttider CSS/JS 2.1.0-r4 match shell cache. Tested AI after-17 update preserves course/date/people and end time, and invalidates old results. Screenshots and starttider-implementering-qa.json are in the chat artifact directory. 195 unit/route tests passed; no real GolfBox mutations used in QA. Deployment controller /tmp/shanklife-starttider.o6EiSi/release_guard.py prepared for baseline f3ba8a7 -> 2.1.0, with 25-minute independent rollback, consistent database backup, row-digest gates including all existing GolfBox jobs/favorites/history, new-table checks, both HTTPS vhosts and verified email.
