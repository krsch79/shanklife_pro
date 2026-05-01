# Changelog

Alle merkbare endringer i Shanklife Pro loggfores her.

## [1.4.2] - 2026-05-01 17:51
- Rettet retry av AI-fiks ved a oppdatere eksisterende issue-branch fra main.
- Fjerner failed-label automatisk nar en AI-fiks startes pa nytt.
- Ryddet Git-indeks pa Raspberryen etter at worktree feilaktig ble vist som skittent.

## [1.4.1] - 2026-05-01 17:35
- Installerte og konfigurerte Codex CLI pa Raspberryen for AI-fiksing.
- Oppdaterte AI worker til a bruke Codex-stien pa Raspberryen og markere failed ved feil.
- Gjorde deploy-scriptet tryggere ved a sjekke ut main for pull/deploy.

## [1.4.0] - 2026-05-01 15:49
- La til knappene Generer fiks og Deploy fiks pa hvert AI-issue i admin.
- Deploy fiks er deaktivert frem til GitHub-issuet er markert ready-to-deploy.
- Deploy fiks merger tilhorende PR, markerer issuet som deployed og starter deploy fra GitHub.

## [1.3.0] - 2026-05-01 15:16
- La til AI worker-script som kan hente GitHub issues, lage branch, markere status og valgfritt kjore Codex CLI.
- La til admin-knapp for a starte deploy fra GitHub i bakgrunnen.
- Endret changelog-formatet slik at hver versjon viser klokkeslett i tillegg til dato.

## [1.2.0] - 2026-05-01 15:10
- Utvidet AI-feilretting i admin med GitHub issue-state, labels og manuell status-synk.
- Standardiserte GitHub issue-formatet og labels for videre AI-arbeidsflyt.
- La til deploy-script som tar databasebackup, henter kode fra GitHub, sjekker syntaks og restarter appen.

## [1.1.1] - 2026-05-01 14:57
- Rettet beregning av mottatte slag pa 9-hullsbaner, slik at spillehandicap halveres og halve slag rundes opp.
- Oppdaterte visningen av mottatte slag ved opprettelse av ordinare runder, statistikkrunder og BalleTour-runder.

## [1.1.0] - 2026-05-01 14:37
- Viser versjonsnummer pa Shanklife Pro-forsiden og BalleTour-forsiden.
- La til changelog-side som apnes fra versjonsnummeret.
- Flyttet OpenAI API-nokkel ut av kildekoden og over til miljovariabel for GitHub-push.

## [1.0.0] - 2026-05-01 11:42
- Forste versjon av Shanklife Pro lagt i GitHub.
- Inneholder runder, spillere, baner, statistikk, BalleTour, adminverktoy og automatisk databasebackup.
