# Repository Instructions

- Update `CHANGELOG.md` for every code change, including bug fixes, UI changes, behavior changes, deploy-flow changes, and schema changes.
- Bump `APP_VERSION` in `services/version.py` whenever `CHANGELOG.md` gets a new release entry.
- Keep changelog entries user-facing and specific enough to explain what changed in Shanklife Pro or BalleTour.
- For server code changes and deploys, enable maintenance mode before touching the running server and disable it only after deploy and verification are done. Use the app's maintenance flag file/deploy script flow.
- Production runs on a Raspberry Pi at `192.168.50.116`.
- SSH user for the Raspberry Pi is `kristian`; do not store SSH passwords or other secrets in this repository.
