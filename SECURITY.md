# Security maintenance - 2026-10-22

Release 2.1.5.

Sikkerhetsoppdatering: strengere tilgangskontroll, beskyttelse av endringer og isolert serverdrift. Webtjenestene forblir i vedlikehold til de er særskilt gjenåpnet.

Development and tests use a separate staging clone. Never test against production user databases. Flask security uses per-app SQLite state (`SECURITY_STATE_DB`) for revocable logins and one-use challenges. Browser POST/PUT/PATCH/DELETE requests need `_shanklife_csrf` or `X-Shanklife-CSRF`; forms and same-origin fetch/XHR obtain it from the server. Native Shanklife JSON requests without Origin retain their existing API flow; cross-origin browser requests are denied.

Runtime identities, resource limits, a restricted Unix-socket control broker and the persistent maintenance marker are managed by the Status project deploy/security helpers. The marker is `/etc/shanklife/webapps-maintenance`; this release does not remove it or reopen public endpoints. Secrets stay in root-managed environment files and private app runtime paths, never in Git.

Follow-up verification: test authentication, rejected cross-user requests and expired/revoked sessions, then the documented app functionality on iPhone and desktop where applicable. A passing source test does not establish that a currently stopped app is healthy in production. Restore source and system configuration only from the verified private rollback set if needed.

For the 2026-10-22 maintenance release, the operator keeps production listeners stopped. Run Python regressions with `python -m pytest` so the browser-equivalent CSRF/session fixture plugin is loaded. Negative security tests use the default Flask client. Dependency environments live under `/opt/shanklife/venvs/<project>-20261022`; systemd overrides select them explicitly. Keep the previous environments only as inactive rollback material. Read the Status remediation report for verification and any remaining scope limits.
