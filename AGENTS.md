# Repository Instructions

- Read and follow `/Volumes/Shared/AGENTS.md` before making changes in this project.
- When a mistake or recurring failure is discovered, document the corrected approach in `/Volumes/Shared/AGENTS.md` if it applies across shared projects, or in this file if it is specific to Shanklife Pro/BalleTour.

- Update the product-specific changelog for every code change: `SHANKLIFE_CHANGELOG.md` for Shanklife Pro changes and `BALLETOUR_CHANGELOG.md` for BalleTour changes.
- Bump `APP_VERSION` in `services/version.py` whenever a product changelog gets a new release entry.
- Keep changelog entries user-facing and specific enough to explain what changed in Shanklife Pro or BalleTour.
- For server code changes and deploys, enable maintenance mode before touching the running server and disable it only after deploy and verification are done. Use the app's maintenance flag file/deploy script flow.
- When deployment or updates require the app process to stop or restart, the static maintenance HTML page must be shown for the whole downtime/restart window.
- Production runs on a Raspberry Pi at `192.168.50.116`.
- `/Volumes/Shared/shanklife_pro` is the SMB-mounted production source directory, not an isolated development worktree. Do not edit application code there before maintenance mode. Make code changes in a clean clone under `/tmp`, test and commit there, then let `scripts/deploy.sh` update the production directory while maintenance mode is active.
- SSH user for the Raspberry Pi is `kristian`; do not store SSH passwords or other secrets in this repository.
- Default delivery expectation: code changes should be committed, pushed to GitHub, and deployed to the Raspberry Pi unless the user explicitly asks not to deploy.
- If the Pi worktree has an unborn local `main` while `refs/remotes/origin/main` exists, do not run the deploy script immediately. First compare every `origin/main` blob with the corresponding worktree file using `git hash-object`, require zero missing/mismatched files and zero index-only extras, then repair only the Git metadata with `git reset --mixed origin/main`; never use `reset --hard` for this recovery.
- Shanklife Pro is managed by `shanklife-pro.service`, installed from `deploy/shanklife-pro.service` by `scripts/deploy.sh`. After deploy, verify that the unit is enabled and active, the actual `/tmp/shanklife_pro_venv/bin/python app.py` process is running, port `5055` listens, `/api/v1/health` succeeds, and `instance/maintenance.lock` is removed.
- While `instance/maintenance.lock` exists, the local `/api/v1/health` endpoint intentionally returns HTTP 503. During deploy, first require an active unit, the expected process, and any HTTP response from the local port; then remove the maintenance lock and require HTTP 200 from health. If that final health check fails, recreate the maintenance lock before exiting.
- GitHub push may use the existing macOS Keychain credential for `github.com`; never print, commit, or otherwise store the token value. If Git cannot use the credential helper directly, read it only into a transient environment variable for the single `git push` process and remove any temporary askpass file immediately.
- Local iOS simulator builds may auto-login as `kristian/kristian` for faster manual testing, but this must be guarded by `DEBUG` and `targetEnvironment(simulator)` so it is never compiled into Release, TestFlight, or App Store builds. Before any Apple upload, verify the archive/build does not include the local auto-login shortcut.
- Do not delete or clean `ios/Shanklife/Shanklife.xcodeproj/project.xcworkspace` or Xcode `xcuserdata` files while the user may have Xcode open. Leave those local generated files untracked instead, so Xcode does not show workspace disappearance prompts.
- Garmin Connect's golf-shot endpoint currently rejects the `garminconnect` package's comma-separated default for `hole-numbers` with HTTP 400. Fetch Garmin shot data one hole at a time with a single hole number per request.
- For local macOS Python validation, do not assume `/tmp/shanklife_pro_venv` contains the app dependencies, and do not reuse `/tmp/shanklife-test-deps` if a native module such as `pydantic_core` is missing. Create a fresh temporary venv with `python3 -m venv /tmp/<name> && /tmp/<name>/bin/pip install -r requirements.txt`, then run tests with that venv's Python.
- When a Flask test client request uses a production-like host, set the same `base_url` on `client.session_transaction(base_url=...)` and on the request. Otherwise the session cookie is scoped to the default test host and the protected request is redirected to login.
- API tests that create a temporary SQLite database must also seed `app_registry` and `user_app_access` for the test user before calling authenticated `/api/v1` endpoints; `db.create_all()` cannot create these shared admin-owned tables.
- Verify Shanklife Pro publicly through `https://pro.shanklife.no/api/v1/health` and the native app host through `https://app.shanklife.no/api/v1/health`; do not use the bare `https://shanklife.no` root, which is not configured with the app's TLS certificate.
- When adding responsive CSS to `static/style.css`, do not use a generic closing-brace patch context that can match near the top of the file. Anchor the patch to the final media block or verify with both `sed -n '1,100p'` and `tail` that responsive overrides appear after their base rules before browser testing.

- Before read-only database probes, resolve the configured SQLite filename from app.py/environment; the default is instance/shanklife_pro.db, not instance/shanklife.db. Open with mode=ro and require the expected schema before querying.
- Use explicit type="text" for text inputs in new forms: static/style.css styles input[type="text"], so omitted types render as unstyled browser defaults. Verify the rendered form before deployment.

- TrackMan schema-driven reads must bound query size before any HTTP request. Recursive expansion of facility/course/tournament graphs can create gigabyte queries; treat those as context references, expand only golf measurement paths deeply, and reject queries above 250 KB before sending. Retain excluded/required fields in the coverage manifest.
- For partial TrackMan GraphQL reads, retain exact errored observations separately and never erase previously known fields/list items. Expand nested pagination for paged root items as well as node details, and test nullable par, team exclusion and played ScorecardShot.total versus launch measurement.total in statistics.
- Commit each TrackMan index/archive/projection write before the next upstream HTTP request. Holding a SQLite writer transaction across a whole 50-record network page blocks normal app requests and can fail with database locked.
- Validate all nginx maintenance vhosts and back them all up before writing any one of them; keep every write inside the rollback boundary so a later preflight/write failure cannot leave earlier configs modified.

- TrackMan hole.putts already includes the final conceded stroke when gimmeWasGiven is true. Keep the preceding putts in the statistics, subtract one only for the separate count without gimmies, and never add the gimme twice. Expose sample denominators, keep automatic putting separate, and derive historical updates from existing projections without rewriting the private archive.
- Before nginx maintenance preflight, enumerate the actual files under /etc/nginx/sites-enabled and select those proxying to port 5055. The current vhosts are pro and app-shanklife; do not assume a file named shanklife-pro exists.

- For Sportsmodus validation on macOS, use the explicit Python 3.11 executable to create the fresh test venv; PATH may select Python 3.14 in a new task. Keep the development/test Python minor compatible with the Pi.
- Explicit nullable tour IDs must have a two-valued SQL predicate (guard `series_id IS NOT NULL` before equality). Negating a nullable equality otherwise silently excludes private rounds. Test both private and legacy tour rows.

- Native UI QA must start only after the disposable fixture server has restarted and its health check passes. Keep fixture resets and browser round creation outside a running XCTest session; both clients share that fixture and can otherwise change the round the test resumes.
- A SwiftUI loader must render a real initial placeholder before its `.task` runs. A `Group` whose initial branches all produce `EmptyView` can leave navigation blank without issuing the request; verify opening and saving a round in simulator QA, not only the tab bar.

- Obtain the `xcodebuild` process exit code before launching another test against the same simulator or DerivedData directory. Printed XCTest results can precede a delayed Xcode driver exit; if stuck, identify the driver by its exact result-bundle argument, stop only that process, and verify its exit first.

- A non-debug Flask QA server caches Jinja templates. Restart it after final template edits before browser assertions, and verify the rendered asset URL rather than assuming source-file edits are live. Use a new service-worker asset/cache revision when testing changed cached JavaScript or CSS.

- On score forms, controls named `action` shadow `HTMLFormElement.action`. Fetch the destination from `form.getAttribute("action") || location.href`, and verify a successful save and retry in the browser; a simulated server error alone does not prove the destination is correct.

- Starttider player references must use owner-scoped GolfBox member numbers, never `GolfBoxFavorite.id`: the existing sync replaces favorite rows, so SQLite IDs can be reassigned to another person. Test selection across reordered syncs. Keep review/action payloads server-owned and consume action IDs before external mutations; network uncertainty must never offer blind replay.
- A QA fixture may already have handled its first Flask request. Register hooks before creating/using its test client; for later synthetic failure injection, wrap that fixture's WSGI app rather than registering new Flask routes/hooks after the first request.

- The verified macOS Python 3.11 test environment uses stdlib unittest, not necessarily pytest. Run `python -m unittest tests.test_starttider -q` or `python -m unittest discover -s tests -q`; check the runner exists before assuming pytest is installed.
- Responsive viewport override belongs to the browser capability (`browser.capabilities.get("viewport")`), not the tab. Use `browser.capabilities.list()` when checking availability, and reset the override after QA.
- The static maintenance page is `static/maintenance.html` (not `deploy/maintenance.html`). Locate deployment assets with `rg --files` before assuming their path; verify both pro and app hosts return the static maintenance content during downtime.
- If macOS Git reports `bad signature` or `index file corrupt` on the SMB mount, verify `git status` and HEAD directly through `ssh shanklife-pi` before considering recovery. A clean Pi index is authoritative; use a new `/tmp` clone and do not rebuild/reset the production index from macOS.
- GolfBox switchClub POST may acknowledge the command without rendering the updated identity. Fetch `/site/my_golfbox/myFrontPage.asp` and verify club plus membership before caching/booking. Restore the original club in a finally block during membership discovery; never replace a known membership list after partial failure.
- Keep concrete GolfBox resources in new Starttider search/job names and frozen review GUIDs. Never replace a removed explicit resource with the first course. Legacy club-only jobs retain their old resolution; new club-only searches expand resources and new jobs require a specific course.

- GolfBox redirects single-course clubs from chooseclub.asp straight to grid.asp. Read the grid's `ddlRessource_GUID` as well as chooseclub's `ddlRessoruce`, discard placeholder values such as `x`, and share this parser between the catalog and resolver. Regression fixtures must include the actual redirected single-course markup, not only a synthetic one-option chooseclub selector.

- When streaming maintenance checks, consume the complete curl response before printing selected markers/status (for example through Python). Piping the HTML to head can close stdout early and make curl exit 56 before reporting the HTTP code.
