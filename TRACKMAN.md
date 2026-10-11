# TrackMan integration

Shanklife Pro archives its user's TrackMan golf history separately from existing
outdoor `Round` records. The private archive preserves the original returned
JSON before creating a conservative statistics projection. Legacy rounds remain
outdoor; TrackMan `SIMULATOR_BAY` CoursePlay scorecards are simulator rounds.
Unknown bay kinds, practice and closest-to-pin remain in the archive. Team rounds are shown in history but excluded from individual averages.

## Connection and credentials

`/me/trackman/` starts TrackMan's device authorization. The user logs in only at
`https://login.trackmangolf.com/device`. OAuth device/access/refresh credentials
are encrypted with `services.secret_store`; they never enter browser cookies,
exports, process arguments or operational logs. Session-bound CSRF tokens protect
all connection/sync/disconnection actions. A previously bound player ID cannot
be replaced by a different account. Disconnection removes credentials and keeps
the historical archive. Account locks serialize polling, refresh and archive jobs
across Flask workers/cron. Disconnect while a sync holds the lock is rejected.

The client currently uses the public TrackMan Golf native client ID documented
by [apiman](https://github.com/l3wi/apiman), with device and refresh grants from
TrackMan's OpenID discovery. `TRACKMAN_CLIENT_ID` can override it. This is an
unofficial integration, not an officially registered Shanklife OAuth application.
There is no TrackMan client secret and no stored TrackMan password. The upstream
may change the client or API; the connection page reports failure without wiping
history. Protect the application's `SECRET_KEY`/`SHANKLIFE_CREDENTIAL_KEY` and
back up the database together with the server's private key configuration.

## Archive and coverage

Tables registered in `services/trackman_models.py` are created by normal
`db.create_all()`; no existing golf tables or scores are rewritten.

- `trackman_accounts`: encrypted OAuth state and bound TrackMan player ID.
- `trackman_archives`: unique user/category/remote ID, type and fetch time.
  Complete reads retain original JSON. On partial GraphQL errors the canonical
  record preserves previously known values; exact partial originals are stored
  separately in `partial_responses` with source/identity/error paths and exported.
  No missing/null field or truncated list from an errored read erases known data.
  The current GraphQL schema is also archived.
- `trackman_sync_runs`: source counts, API-reported totals, gaps, errors,
  schema checksum and completion status. Failed runs preserve prior records.
- `trackman_rounds`: own-user projection, environment, completion and hole data.

`services/trackman_api.py` discovers the current GraphQL schema, reads only `me`
and nodes discovered from those private sources, includes hidden activities,
follows offset pages and checks counts/repeated pages. Scalar fields, actual and
normalized measurements, trajectories, scorecard holes/shots/statistics, game
settings, equipment and handicap history are included. It avoids other players'
scorecards/global discovery and treats facilities, courses and tournament graphs
as context references. The native schema can expose fields that this account
cannot read; partial GraphQL responses are retained and every reported field
error is included in coverage. Some `data` objects expose **keys only**; their
values are inaccessible through this schema. Fields with required arguments,
reference/depth boundaries, inaccessible data and unresolved nested pagination
are listed, never described as a complete import. Query size is capped before
HTTP; contextual graphs must not be expanded into unbounded queries.

Media/report URLs and metadata are preserved. Binary video/PDF payloads are not
mirrored and signed links can expire. A JSON export contains raw golf records,
schema and coverage, but no OAuth credentials. Every browser/detail/export/query
is scoped to the current user's ID. Other-player scorecard references are also
stripped before storage/administrative import and before preserving older partial
snapshots; those fields are excluded from upstream selections. This applies when selecting another player's
public outdoor statistics.

## Statistics rules

The source selector applies to `/stats/`, `/stats/ai`, `/me/rounds` and the native
API `/api/v1/shanklife/stats?environment=all|simulator|outdoor`.
Sample counts/numerators are pooled; rounded percentages are never averaged.
Full round records require 9/18 expected, played and scored holes and matching
gross total. Partial rounds supply only played holes and are excluded from best
round/average round summaries. Zero/unplayed holes stay in the raw archive.
Automatically assigned putting and holes with a gimme are excluded from putting
averages; their original values and settings remain available. Unsupported green
miss, bunker, fairway-per-club and putt-distance comparisons retain outdoor samples
only, rather than inventing simulator measurements. Detailed fairway outcomes
and per-club fairway percentages explicitly use outdoor samples. Club and distance
averages pool available first-tee-shot data, preferring ScorecardShot.total (played
simulator distance) over launch measurement.total; unknown clubs are retained.
Completed rounds without known par retain gross records but no to-par value.
AI player/course/hole totals pool eligible own simulator rows and exclude team/match.
Practice strokes never count
as completed rounds. There is no GolfBox submission/edit route for imported data.
An outdoor round uploaded from another service is not automatically merged with
an existing manual record: identity is independent of environment/source.

## Runtime and development

`python scripts/sync_trackman.py [--user-id N]` runs a full history reconciliation
for connected users. `scripts/deploy.sh` installs the cron block at 00:17, 06:17,
12:17 and 18:17. It defers while maintenance is active. Logs show counts/status
only. UI sync jobs run in a daemon thread, so a process restart interrupts them;
the next full sync safely upserts the same remote IDs. Each index/record/projection
write is committed before the next network request, so full-history retrieval
does not hold a SQLite writer lock while waiting for TrackMan. No archive records are
silently removed when TrackMan hides/deletes a source or a request fails.

Use a fresh temporary virtualenv with `requirements.txt`, a private temporary
SQLite database and `python -m unittest discover -s tests -p 'test_*.py'`.
Never run development against `/Volumes/Shared` or the production database.
Read-only live verification uses SQLite URI `mode=ro`/`PRAGMA query_only=ON`.
The independently requested tester must check data isolation, source filters,
missing/zero/partial/putting rules, pagination, retries, refresh, export and mobile
layout. Desktop/iPhone browser emulation is not a physical iPhone test.

Production deployment enables maintenance before modifying production source,
backs up data and uses the exact committed version. The nginx maintenance setup
makes the static page available through app restarts; nginx configs are backed
up before edits and validated before reload. `SHANKLIFE_GIT_SOURCE` may point to a
Git bundle created from named `main` for Pi fetch when HTTPS auth is unavailable.

For an already approved local archive, administrators may use
`python scripts/import_trackman_archive.py --username <exact-user>` with private
JSON on standard input. It verifies the token's player ID against the archive
and the existing binding, encrypts credentials with the target server's key and
upserts records for that user only. Never commit or log the transfer payload.
