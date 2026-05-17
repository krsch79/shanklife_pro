# Changelog

Alle merkbare endringer i Shanklife Pro loggfores her.

## [1.8.22] - 2026-05-17
- Bygger logoene og golfillustrasjonen direkte inn i vedlikeholdssiden, slik at de vises også når appens statiske filserver ikke er tilgjengelig under deploy.

## [1.8.21] - 2026-05-17
- Viser fullførte og pågående BalleTour-runder på forsiden, sammen med totalantall birdies, par, bogeys og dobbelbogeys eller verre for valgt tee.
- Fjerner BalleTour-spillere-statistikken og Status-kolonnen fra BalleTour-forsiden.
- Flytter adminvalget for minimum tellende BalleTour-runder fra forsiden til admin-siden.
- Setter både e-postheader og faktisk SMTP/sendmail-avsender til noreply@balletour.shanklife.no.
- Gjør BalleTour-scorekortkolonner faste, slik at sirkel- og firkantmarkeringer ikke endrer kolonnebredde på mobil.

## [1.8.20] - 2026-05-17
- Flytter knappen for BalleTour default-køller fra Køllestatistikk til Min side.
- Fjerner Start ny BalleTour-runde fra Min side, slik at siden fokuserer på spillerens egne innstillinger og runder.
- Rydder BalleTour-forsiden ved å fjerne kortknappene for Spillere, Statistikk og Samlet statistikk.
- Skjuler Tellende grense som forsidestatistikk og lar administratorer endre minimum tellende runder direkte fra BalleTour-forsiden.

## [1.8.19] - 2026-05-17
- Gjør Min side BalleTour-spesifikk for BalleTour-brukere og legger lenken i BalleTour-toppmenyen.
- Lar brukere velge om rundevarsler skal gjelde alle BalleTour-spillere eller bare valgte spillere.
- Setter alle e-postvarseltyper på som standard, slik at brukere aktivt kan velge bort varsler de ikke vil ha.
- Setter avsender for appens e-poster til noreply@balletour.shanklife.no.
- Lar deploy-scriptet vise den statiske vedlikeholdssiden mens app-prosessen er stoppet under restart.

## [1.8.18] - 2026-05-17
- Lar BalleTour-brukere lagre e-postadresse og velge hvilke e-postvarsler de vil motta.
- Viser BalleTour-brukere uten registrert e-post en påminnelse med lenke til varselinnstillingene etter innlogging.
- Sender fullført BalleTour-runde til brukere som har valgt rundevarsler, med starttid, sluttid, væroppsummering, totalscore og fullt scorekort.
- Legger til valgfri e-post ved versjonsoppdateringer og sender versjonsvarsel én gang per deployet versjon.

## [1.8.17] - 2026-05-15
- Viser Admin i toppmenyen også på BalleTour-sider for innloggede administratorer.
- Gjør admin-rollen dynamisk slik at administratorer kan gi og fjerne admin-tilgang for registrerte brukere, uten at Kristian tvinges til admin ved hver oppstart.
- Legger til egen Live leaderboard-side under BalleTour som bruker BalleTour-meny/header og bare viser BalleTour-runder.

## [1.8.16] - 2026-05-14
- Fjerner datofiltrene fra BalleTour-galleriet.
- Viser tag- og hullfiltre fast øverst i galleriet som synlige checkbox-grupper, og oppdaterer galleriet hver gang et filter velges eller velges bort.

## [1.8.15] - 2026-05-14
- Lar tag- og hullvalgene i BalleTour-galleriet bli stående åpne mens flere checkbokser velges, og oppdaterer først når dropdownen lukkes.

## [1.8.14] - 2026-05-14
- Lar BalleTour-galleriet filtrere pa flere tags og flere hull samtidig med checkbox-valg.
- Rydder bildeteksten i galleriet til dato/tid, hull og tags, og fjerner fast banenavn og teksten Lastet opp.
- Gjør galleribildene klikkbare slik at originalbildet åpnes i ny fane.

## [1.8.13] - 2026-05-14
- Legger til vedlikeholdsmodus for deploy, med statisk Shanklife Pro/BalleTour-side, logoer og golfillustrasjon mens serveren oppdateres.
- Oppdaterer deploy-scriptet slik at vedlikeholdsmodus skrus pa for deploy og fjernes automatisk nar deployen er ferdig eller feiler.
- Gjør filterne i BalleTour-galleriet og Avsluttede runder automatiske, slik at visningen oppdateres nar filtervalg endres.

## [1.8.12] - 2026-05-14
- Utvider bildeopplasting med fleksible tags: BalleTour-bilder kan tagges med alle BalleTour-spillere og med nye fritekst-tags som lagres til senere bruk.
- Endrer bildeopplastingsfeltet fra Spiller-tag til Tag og viser alle tags på hullside, spillerprofil og galleri.
- Legger til filter og sortering i galleriet for tag, hull, datointervall og visningsrekkefølge.

## [1.8.11] - 2026-05-14
- Gjør GitHub-kommentarer fra AI worker tydeligere når Codex/OpenAI feiler, med egne meldinger for kvote/billing, autentisering, rate limit, utilgjengelig modell og lokale kode-/kommandofeil.
- Lar isolert AI worker returnere feilkode uten a overskrive den forklarende GitHub-feilmeldingen med en ekstra Python-stacktrace.

## [1.8.10] - 2026-05-14
- Etterregistrerer BalleTour-endringene som manglet fra changelog: beholdt scrollposisjon ved hullbytte i statistikk, rettet scorestat-validering og justerte pin-offsets i greenmønsteret.
- Dokumenterer repo-regelen om at changelog og versjon alltid skal oppdateres sammen med kodeendringer.

## [1.8.9] - 2026-05-14
- Lar BalleTour-runder velge dynamisk blant alle BalleTour-spillere, ikke bare fire faste spillerplasser.
- Legger til admin-invitasjoner for nye BalleTour-spillere med e-postlenke for a sette passord og bli lagt til i touren.

## [1.8.8] - 2026-05-06
- Splitter leaderboard, BalleTour-statistikk, series-statistikk og Min side pa gul og rod tee, med gul som standardvisning.

## [1.8.7] - 2026-05-05 20:29
- Høyrestiller versjonsnummeret pa BalleTour-forsiden og legger BalleTour-menyen pa samme rad som logoen.

## [1.8.6] - 2026-05-05 20:22
- Lar BalleTour-retningen Pa flagget brukes sammen med miss og bunker, ikke bare greentreff.

## [1.8.5] - 2026-05-05 20:13
- Gjør BalleTour-headeren mer kompakt, fjerner Logg ut fra BalleTour-menyen og flytter versjonsnummeret ved BalleTour-overskriften.
- Viser opplastingsdato og klokkeslett i galleriet.
- Stopper BalleTour-scorevalidering i nettleseren før siden sendes inn, slik at utfylte valg ikke nullstilles nar noe mangler.
- Fjerner automatisk 0,5 m valg ved fokus pa siste putt slik at siste putt ma velges aktivt.

## [1.8.4] - 2026-05-05 19:59
- Setter Pa flagget og Pin high som standardvalg for BalleTour-greenvalg, mens score, putter og siste putt starter tomt.
- Stopper navigering til neste hull nar obligatoriske BalleTour-valg mangler og viser hvilke felt som mangler per spiller.

## [1.8.3] - 2026-05-05 19:49
- Endrer Side til Retning og fikser at Pa flagget ikke laser de andre greenvalgene.

## [1.8.2] - 2026-05-05 19:42
- Forbedrer mobil-layouten for BalleTour-greenvalg med tydelige grupper og tekst over radioknappene.

## [1.8.1] - 2026-05-05 17:25
- Rydder greenvalg i BalleTour-score: fjerner Rett, flytter Pa flagget inn i sidevalget og endrer Riktig til Pin high.

## [1.8.0] - 2026-05-05 16:43
- Lar BalleTour-leaderboardet lenke til filtrert oversikt over avsluttede runder per spiller.
- Legger til spillerfilter, vaeroppsummering og fjerner egen Scorekort-knapp fra avsluttede BalleTour-runder.
- Henter og lagrer vaer for Bekkestua nar en BalleTour-runde startes, og viser vaeret ved opprettelse og pa rundeoversikten.
- Lar BalleTour-runder med flere spillere fore full statistikk for alle spillere.
- Endrer siste putt til ett valg med 0,1 meters intervall og radiovalg for gjensidig utelukkende greenretninger.

## [1.7.1] - 2026-05-04 21:15
- Sender Fortsett runde til forste hull der minst en spiller mangler score.

## [1.7.0] - 2026-05-03 18:15
- Bytter registrering av siste putt i detaljert BalleTour-score fra faste valg til separate meter- og desimetervalg.

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
