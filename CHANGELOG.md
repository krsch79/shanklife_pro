# Changelog

Alle merkbare endringer i Shanklife Pro loggfores her.

## [1.6.1] - 2026-05-02 21:46
- Flytter BalleTour-knappen for a bytte mellom prod- og testdatabase fra BalleTour-forsiden til admin-siden.

## [1.6.0] - 2026-05-02 20:09
- Legger til separat BalleTour-testdatabase ved siden av prod-databasen.
- Lar admin opprette, slette og bytte BalleTour-visning mellom prod- og testdatabase uten at ekte runder lagres i test.
- Fyller BalleTour-testdatabasen med 25 fullforte runder per spiller basert pa prod-spillere, baner og serie.

## [1.5.12] - 2026-05-02 19:46
- Legger til intern BalleTour strokes gained for total, for putting, for slag for putting og for greenresultat.
- Viser strokes gained pa spillerstatistikk og samlet statistikk basert pa fullforte runder.

## [1.5.11] - 2026-05-02 19:29
- Viser meter siste putter per runde pa BalleTour-statistikk for hver spiller.
- Legger til samlet BalleTour-statistikkside som sammenligner alle spillerne i tabellformat.

## [1.5.10] - 2026-05-02 11:55
- Sender e-post nar en BalleTour-runde fullfores, med bane, runde-id og score per spiller.

## [1.5.9] - 2026-05-02 10:22
- Legger til SMTP/sendmail-basert e-postvarsling med logging ved feil.
- Sender e-post ved ny GitHub-sak fra admin, AI-fiks klar for deploy og fullfort admin-deploy.
- Legger til script for e-postvarsel nar en Codex-oppgave er ferdig.

## [1.5.8] - 2026-05-02 10:03
- Lar automatisk daglig backup bare lage backup kl. 01:00 serverstid og maks én gang per dato.
- Samler appens klokkeslettbruk rundt serverens lokale tid for lagring, filnavn og visning.
- Beholder deploy-backup som eksplisitt tvungen backup utenfor den daglige tidsplanen.

## [1.5.7] - 2026-05-02 09:06
- Hindrer at AI-fiks deployes ved generering ved a kjore worker i separat Git worktree.
- Skrur av Flask debug/reloader som standard slik at filendringer ikke auto-reloader produksjon.
- Dokumenterer endringer og automatisk risikovurdering i GitHub nar en AI-fiks er klar.
- Fjerner manuell Deploy fra GitHub fra admin.
- Retter mottatte slag for 9-hullsbaner med 18-hulls course rating, blant annet Ballerud.

## [1.5.6] - 2026-05-01 22:05
- Endret AI-feilretting-overskriften i admin til rod.

## [1.5.5] - 2026-05-01 21:21
- La til Live leaderboard i BalleTour-menyen.

## [1.5.4] - 2026-05-01 21:14
- Sender OpenAI-autentisering eksplisitt videre til Codex CLI fra AI worker.
- Setter CODEX_API_KEY fra OPENAI_API_KEY ved Codex-kjoring for headless worker.
- Reoppretter AI issue-branch fra fersk main ved nytt forsok for a unnga fast-forward-feil.

## [1.5.3] - 2026-05-01 20:10
- Gjenopprettet execute-bit pa deploy-scriptet slik at deploy kan startes direkte igjen.

## [1.5.2] - 2026-05-01 20:03
- Laster .env eksplisitt i AI worker for Codex-kjoring.
- Legger inn tydelig preflight-feil dersom OpenAI-autentisering mangler for AI worker.
- Dokumenterer at OPENAI_API_KEY ma settes pa Raspberryen for automatisk AI-fiks.

## [1.5.1] - 2026-05-01 19:46
- Gjorde GitHub til fasit for AI-feilretting slik at dashboardet kun viser saker som faktisk finnes i GitHub med Shanklife-labels.
- Hindrer at nye AI-forespørsler lagres lokalt dersom GitHub issue ikke kan opprettes.
- Rydder bort lokale AI-kopier som peker til slettede eller irrelevante GitHub-saker.

## [1.5.0] - 2026-05-01 19:24
- Gjorde AI worker mer robust ved a reparere Git-indeksen for den sjekker rent worktree.
- Bygget om AI-feilretting til en kompakt GitHub-saksliste med filtre.
- Synker GitHub-saker automatisk ved sidevisning og viser kommentarer fra GitHub i utvidbare paneler.

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
