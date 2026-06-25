# Repository Instructions

- Update the product-specific changelog for every code change: `SHANKLIFE_CHANGELOG.md` for Shanklife Pro changes and `BALLETOUR_CHANGELOG.md` for BalleTour changes.
- Bump `APP_VERSION` in `services/version.py` whenever a product changelog gets a new release entry.
- Keep changelog entries user-facing and specific enough to explain what changed in Shanklife Pro or BalleTour.
- For server code changes and deploys, enable maintenance mode before touching the running server and disable it only after deploy and verification are done. Use the app's maintenance flag file/deploy script flow.
- When deployment or updates require the app process to stop or restart, the static maintenance HTML page must be shown for the whole downtime/restart window.
- Production runs on a Raspberry Pi at `192.168.50.116`.
- SSH user for the Raspberry Pi is `kristian`; do not store SSH passwords or other secrets in this repository.
- Default delivery expectation: code changes should be committed, pushed to GitHub, and deployed to the Raspberry Pi unless the user explicitly asks not to deploy.
- Local iOS simulator builds may auto-login as `kristian/kristian` for faster manual testing, but this must be guarded by `DEBUG` and `targetEnvironment(simulator)` so it is never compiled into Release, TestFlight, or App Store builds. Before any Apple upload, verify the archive/build does not include the local auto-login shortcut.
