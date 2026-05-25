# BalleTour Changelog

Merkbare endringer som gjelder BalleTour loggføres her separat fra Shanklife Pro.

## [1.8.51] - 2026-05-25
- Lar GolfBox AI booke flere baner enn Ballerud når GolfBox ikke krever betaling ved booking.
- Bytter til riktig GolfBox-medlemsklubb ved booking når brukeren har flere klubbmedlemskap, og matcher medspillere mot samme klubb.
- Legger til faste ukentlige GolfBox-bookinger fra AI-chatten.
- Tillater GolfBox-brukernavn som ikke er e-postadresse.

## [1.8.50] - 2026-05-25
- Bytter lagring av GolfBox-passord fra intern tilsløring til Fernet-kryptering, og migrerer eksisterende GolfBox-passord automatisk ved oppstart.
- Beholder vanlige BalleTour-passord som irreversible passord-hasher, slik at de fortsatt ikke kan dekrypteres.
- Laster lokal `.env` ved appstart, slik at krypteringsnøkler og andre hemmelige innstillinger kan ligge utenfor repoet.

## [1.8.49] - 2026-05-25
- Retter GolfBox-innsending slik at hullscorer sendes som aktivert hullscorekort, med justert bruttoscore og poeng beregnet sammen med scorekortet.
- Lar en BalleTour-score sendes på nytt til GolfBox etter kontroll, med tydelig varsel om mulig duplikat.

## [1.8.48] - 2026-05-25
- Legger til GolfBox-innsending for innlogget BalleTour-spillers fullførte runder, med markørsøk, bekreftelse og lagret sendestatus.
- Holder innsendingen i BalleTour-visning når den startes fra en BalleTour-runde.

## [1.8.46] - 2026-05-24
- Skjuler BalleTour-spillere uten registrerte runder fra leaderboard, beste-score-tabellen, statistikkvalg, samlet statistikk og spillerlisten.

## [1.8.45] - 2026-05-24
- Legger til valgfrie e-postvarsler når BalleTour-runder startes.
- Fargelegger scorekortscore med grønt for birdie eller bedre og rødt for bogey eller verre.

## [1.8.40] - 2026-05-24
- Viser BalleTour-changeloggen på en egen BalleTour-side og lar versjonslenken på BalleTour-forsiden bli i BalleTour.

## [1.8.39] - 2026-05-24
- Begrenser nye BalleTour-runder til maks 4 spillere.

## [1.8.38] - 2026-05-24
- Holder BalleTour-endringer i en egen changelog-fil ved siden av Shanklife Pro-changeloggen.

## [1.8.35] - 2026-05-24
- Viser hvordan spillerne ligger an mot par før hullet som skal føres i scoreføringen.

## [1.8.33] - 2026-05-23
- Skiller BalleTour-changelog fra Shanklife Pro-changelog, slik at fremtidige BalleTour-endringer kan føres separat.

## [1.8.31] - 2026-05-20
- Viser kommende planlagte GolfBox-bookinger på BalleTour AI-siden med spillere, bane, spilledato, spilletid og gjennomføringstidspunkt.

## [1.8.27] - 2026-05-20
- Viser hvilken GolfBox-klubb og hvilket medlemsnummer BalleTour AI er koblet til.

## [1.8.24] - 2026-05-20
- Gjør BalleTour AI-siden om til et enkelt GolfBox-promptfelt for vanlige BalleTour-brukere.
- Flytter den tekniske MCP-verktøyoversikten fra BalleTour-menyen til Admin.

## [1.8.23] - 2026-05-20
- Legger til en read-only MCP-MVP for BalleTour, slik at AI-klienter kan hente leaderboard, spillere, runder og spilleroppsummeringer uten a endre score eller tilgang.
- Legger til en AI-side i BalleTour-menyen med oversikt over tilgjengelige MCP-verktøy og lokal kjørekommando for Raspberry Pi.

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
- Setter avsender for appens e-poster til noreply@balletour.shanklife.no.

## [1.8.18] - 2026-05-17
- Lar BalleTour-brukere lagre e-postadresse og velge hvilke e-postvarsler de vil motta.
- Viser BalleTour-brukere uten registrert e-post en påminnelse med lenke til varselinnstillingene etter innlogging.
- Sender fullført BalleTour-runde til brukere som har valgt rundevarsler, med starttid, sluttid, væroppsummering, totalscore og fullt scorekort.

## [1.8.17] - 2026-05-15
- Viser Admin i toppmenyen også på BalleTour-sider for innloggede administratorer.
- Legger til egen Live leaderboard-side under BalleTour som bruker BalleTour-meny/header og bare viser BalleTour-runder.

## [1.8.16] - 2026-05-14
- Fjerner datofiltrene fra BalleTour-galleriet.

## [1.8.15] - 2026-05-14
- Lar tag- og hullvalgene i BalleTour-galleriet bli stående åpne mens flere checkbokser velges, og oppdaterer først når dropdownen lukkes.

## [1.8.14] - 2026-05-14
- Lar BalleTour-galleriet filtrere pa flere tags og flere hull samtidig med checkbox-valg.

## [1.8.13] - 2026-05-14
- Legger til vedlikeholdsmodus for deploy, med statisk Shanklife Pro/BalleTour-side, logoer og golfillustrasjon mens serveren oppdateres.
- Gjør filterne i BalleTour-galleriet og Avsluttede runder automatiske, slik at visningen oppdateres nar filtervalg endres.

## [1.8.12] - 2026-05-14
- Utvider bildeopplasting med fleksible tags: BalleTour-bilder kan tagges med alle BalleTour-spillere og med nye fritekst-tags som lagres til senere bruk.

## [1.8.10] - 2026-05-14
- Etterregistrerer BalleTour-endringene som manglet fra changelog: beholdt scrollposisjon ved hullbytte i statistikk, rettet scorestat-validering og justerte pin-offsets i greenmønsteret.

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
- Stopper BalleTour-scorevalidering i nettleseren før siden sendes inn, slik at utfylte valg ikke nullstilles nar noe mangler.

## [1.8.4] - 2026-05-05 19:59
- Setter Pa flagget og Pin high som standardvalg for BalleTour-greenvalg, mens score, putter og siste putt starter tomt.
- Stopper navigering til neste hull nar obligatoriske BalleTour-valg mangler og viser hvilke felt som mangler per spiller.

## [1.8.2] - 2026-05-05 19:42
- Forbedrer mobil-layouten for BalleTour-greenvalg med tydelige grupper og tekst over radioknappene.

## [1.8.1] - 2026-05-05 17:25
- Rydder greenvalg i BalleTour-score: fjerner Rett, flytter Pa flagget inn i sidevalget og endrer Riktig til Pin high.

## [1.8.0] - 2026-05-05 16:43
- Lar BalleTour-leaderboardet lenke til filtrert oversikt over avsluttede runder per spiller.
- Legger til spillerfilter, vaeroppsummering og fjerner egen Scorekort-knapp fra avsluttede BalleTour-runder.
- Henter og lagrer vaer for Bekkestua nar en BalleTour-runde startes, og viser vaeret ved opprettelse og pa rundeoversikten.
- Lar BalleTour-runder med flere spillere fore full statistikk for alle spillere.

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

## [1.5.11] - 2026-05-02 19:29
- Viser meter siste putter per runde pa BalleTour-statistikk for hver spiller.
- Legger til samlet BalleTour-statistikkside som sammenligner alle spillerne i tabellformat.

## [1.5.10] - 2026-05-02 11:55
- Sender e-post nar en BalleTour-runde fullfores, med bane, runde-id og score per spiller.

## [1.5.5] - 2026-05-01 21:21
- La til Live leaderboard i BalleTour-menyen.

## [1.1.1] - 2026-05-01 14:57
- Oppdaterte visningen av mottatte slag ved opprettelse av ordinare runder, statistikkrunder og BalleTour-runder.

## [1.1.0] - 2026-05-01 14:37
- Viser versjonsnummer pa Shanklife Pro-forsiden og BalleTour-forsiden.

## [1.0.0] - 2026-05-01 11:42
- Inneholder runder, spillere, baner, statistikk, BalleTour, adminverktoy og automatisk databasebackup.
