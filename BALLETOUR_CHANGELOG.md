# BalleTour Changelog

Merkbare endringer som gjelder BalleTour loggføres her separat fra Shanklife Pro.

## [1.9.14] - 2026-06-26
- Gjør pågående BalleTour-runder tydelige i iPhone-appen, med rask fortsettelse av runder som allerede er startet.
- Hindrer at lokal Kristian-auto-login fra simulator følger med som lagret innlogging i TestFlight.

## [1.9.13] - 2026-06-25
- Sikrer at handlingsknappene i native scoreføring bare utløser valgt handling, slik at utfylte felter ikke kan lastes på nytt ved valideringsstopp.

## [1.9.12] - 2026-06-25
- Retter iPhone-scoreføringen slik at manglende påkrevde felt stopper før lagring, viser hva som mangler og beholder utfylte valg på skjermen.
- Gjør putter og siste putt valgfrie ved fullføring av runder, samtidig som ugyldige puttervalg fortsatt stoppes.

## [1.9.11] - 2026-06-25
- Viser iPhone-appens versjonsnummer på profilsiden, og lar scoreføringen gå videre uten putter og siste putt når resten av de påkrevde feltene er fylt ut.

## [1.9.10] - 2026-06-25
- Beholder utfylte scoreføringsfelt i iPhone-appen når spilleren prøver å gå videre uten alle nødvendige valg, og viser en tydelig melding om hva som mangler.

## [1.9.9] - 2026-06-25
- Forbedrer native iPhone-scoreføring med tydelige valgmenyer for kølle, utslagslengde, putter og siste putt, samt ventemelding ved lagring, navigering og fullføring av runder.

## [1.9.8] - 2026-06-25
- Hindrer at lokale iOS-simulatortester sender BalleTour-varsel om at en runde er startet, samtidig som TestFlight- og App Store-builds beholder vanlige varsler.

## [1.9.2] - 2026-06-24
- Legger til native iPhone-flyt for å starte BalleTour-runder, føre score og statistikk hull for hull og fullføre runden.
- Viser BalleTour-scorekort mer visuelt i iPhone-appen med tydeligere markering av score mot par.
- Legger til native BalleTour-statistikk med spillerstatistikk, samlet oversikt, strokes gained, greenmønster og køllebruk.

## [1.9.1] - 2026-06-24
- Legger til native BalleTour-visninger i iPhone-appen for oversikt, tee-filter, leaderboard, spillere, runder, personlig statistikk og scorekortdetaljer.
- Utvider BalleTour-API-et med strukturerte endepunkter som appen kan bruke uten webvisning.

## [1.9.0] - 2026-06-23
- Gjør iPhone-prototypen mer TestFlight-klar med appikon, oppdatert buildversjon og bedre innloggings- og profilvisning.
- Viser BalleTour-tilgang og enkel spilleroversikt i den native prototypen.

## [1.8.99] - 2026-06-23
- Setter iPhone-prototypen til å bruke `https://app.shanklife.no` som standard serveradresse for TestFlight-testing.

## [1.8.98] - 2026-06-23
- Legger grunnmuren for en native iPhone-app med JSON-API for innlogging, brukerprofil, app-oppsett og BalleTour-oversikt.
- Legger til et første SwiftUI-prosjekt som kan vise BalleTour som egen appdel for spillere med tilgang.

## [1.8.95] - 2026-06-20
- Slår opp oppgitte medlemsnumre direkte i GolfBox før en fremtidig eller overvåket AI-booking lagres.
- Viser og lagrer korrekt navn, medlemsnummer og klubb for hver oppgitt medspiller i planlagte bookinger.
- Stopper planleggingen dersom et medlemsnummer ikke kan bekreftes i GolfBox, slik at en uklar spiller ikke bookes inn senere.

## [1.8.94] - 2026-06-20
- Retter planlagte enkeltbookinger slik at GolfBox bruker klubb- og baneinformasjonen til banen som faktisk skal bookes, i stedet for alltid å bruke Ballerud.
- Viser historiske GolfBox AI-bookinger med status, spillere, bane og spilletid.
- Gir hver historisk booking en egen beskrivende logg med opprinnelig forespørsel, hendelser og resultat eller feilmelding.
- Lagrer hver fremtidige automatisk bookingkjøring separat, slik at resultatet fra tidligere gjentakende bookinger ikke overskrives.
- Sikrer at GolfBox AI også kan åpnes når administrator bruker BalleTour-testdatabasen.

## [1.8.90] - 2026-06-19
- Beregner live score mot par fra alle hull som faktisk er registrert, også ved shotgun-start eller annen spillerekkefølge.

## [1.8.88] - 2026-06-19
- Lagrer et tomt puttervalg som 0 putter, slik at chip-in kan registreres uten å åpne putterlisten.
- Godtar 0 putter uten lengde på siste putt ved navigering og fullføring av runden.

## [1.8.87] - 2026-06-19
- Tydeliggjør fairwayvalgene som Traff fairway, Misset høyre og Misset venstre.
- Tillater tomt putterfelt når man går videre, men krever at score er minst én mer enn antall putter når begge er fylt ut.
- Beholder krav om registrerte putter før runden kan fullføres.

## [1.8.86] - 2026-06-19
- Endrer hullføringen til naturlig slagrekkefølge: utslagskølle, lengde, green/fairway, putter, siste putt og score til slutt.
- Lar statistikk fylles ut før score, samtidig som score og komplette obligatoriske data fortsatt kreves ved fullføring.
- Uthever score som det tydelige siste feltet for hver spiller.

## [1.8.81] - 2026-06-18
- Flytter fullføring av en pågående runde til en kompakt knapp ved siden av Scorekort, slik at den ikke lenger ligger som en stor knapp i hullnavigasjonen.

## [1.8.80] - 2026-06-18
- Endrer utslagslengde til en valgfri nedtrekksliste på alle hull, med forslag på 125 meter på par 3 og 200 meter på par 4 og 5 når feltet åpnes.

## [1.8.79] - 2026-06-18
- Lar spillere hoppe over hull uten å føre score, med sirkulær hullnavigasjon som støtter shotgun-start.
- Kontrollerer hele scorekortet og alle obligatoriske statistikkfelt før en BalleTour-runde kan fullføres.

## [1.8.78] - 2026-06-18
- Sender e-post med resultatet av planlagte GolfBox AI-bookinger også når bookingen mislykkes eller ingen ledig tid blir funnet.
- Varsler på e-post når et overvåket søk etter ledig starttid utløper uten booking.

## [1.8.75] - 2026-06-16
- Viser både navn og medlemsnummer for spillere i planlagte GolfBox AI-bookinger.
- Slår opp medlemsnummer fra GolfBox-favoritter når en booking er opprettet med medlemsnummer i prompten.

## [1.8.74] - 2026-06-16
- Lagrer GolfBox-favoritter per BalleTour-bruker med navn, medlemsnummer og klubb.
- Lar GolfBox AI bruke favorittlisten når brukeren ber om booking med navn i stedet for medlemsnummer.
- Velger riktig favorittmedlemskap når samme person har flere klubber og en av klubbene matcher banen som bookes.

## [1.8.72] - 2026-06-12
- Bytter OpenAI-modellen i løsningen til GPT-5.2.
- Oppdaterer score mot par umiddelbart når en hullscore velges under runden.

## [1.8.70] - 2026-06-05
- Komprimerer datagrunnlaget som sendes til OpenAI i BalleTour sin AI-statistikkchat, slik at tee-baserte spørsmål ikke treffer token-grensen.
- Viser en ryddigere feilmelding hvis OpenAI likevel avviser et for stort statistikkgrunnlag.

## [1.8.69] - 2026-06-05
- Lar BalleTour sin AI-statistikkchat scrolle automatisk ned til siste spørsmål eller svar når siden lastes etter en ny melding.

## [1.8.68] - 2026-06-05
- Deler AI-statistikkgrunnlaget for BalleTour per tee, slik at svar kan baseres på rød eller gul tee og ta hensyn til ulike hull-lengder.

## [1.8.67] - 2026-06-05
- Legger til AI-statistikkchat for BalleTour, der brukeren kan spørre om score, hull, putting, køller, greenmønster og trender basert på lokalt beregnet datagrunnlag.

## [1.8.66] - 2026-06-05
- Viser en liten jobb-popup med sprettende golfball når brukeren starter tidkrevende handlinger, slik at samme skjema ikke sendes flere ganger.

## [1.8.65] - 2026-06-02
- Viser både navn og GolfBox-medlemsnummer for spillere i listen over planlagte AI-bookinger.

## [1.8.64] - 2026-06-02
- Retter faste GolfBox AI-bookinger slik at “neste” eller “påfølgende” spilledag ikke bookes som samme dag som kjøringen.
- Viser kommende spilledato og tid/tidsrom tydeligere i listen over planlagte AI-bookinger.

## [1.8.62] - 2026-05-29
- Retter scorevisningen i live leaderboard-scorekortet slik at score mot par beregnes mot fullførte hull, ikke hele banen.

## [1.8.61] - 2026-05-28
- Viser i GolfBox AI-chatten om siste melding ble tolket med OpenAI og lokale regler, eller kun lokale regler.

## [1.8.60] - 2026-05-28
- Gir GolfBox AI mer kontekst om innlogget bruker og medlemskap når brukerens bookingforespørsel tolkes.
- Kobler navn i parentes etter medlemsnummer til riktig medspiller i GolfBox AI, for eksempel `65-2560 (Øyvind)`.
- Gjør feilmeldinger om manglende spillere tydeligere ved booking og automatisk ledighetssøk.

## [1.8.59] - 2026-05-28
- Retter GolfBox AI slik at bookingforespørsler med ordet medlemsnummer ikke feiltolkes som spørsmål om egen GolfBox-profil.
- Gjør spillerantall mer robust når GolfBox AI får “meg” sammen med en navngitt medspiller eller et medlemsnummer.

## [1.8.58] - 2026-05-28
- Lar GolfBox AI opprette aktive ledighetssøk som sjekker jevnlig og booker automatisk når en passende starttid blir ledig.
- Støtter medspillere oppgitt som GolfBox-medlemsnummer i AI-bookinger.

## [1.8.57] - 2026-05-28
- Viser kommende GolfBox-bookinger direkte øverst i GolfBox AI.
- Legger til avbestilling av GolfBox-bookinger fra oversikten og via AI-chatten, med bekreftelse før spilleren fjernes fra starttiden.

## [1.8.55] - 2026-05-25
- Retter GolfBox-klubbbytte før booking ved å poste til GolfBox sin faktiske “endre klubb”-adresse etter redirect.
- Oppfrisker lagrede GolfBox-medlemskap før booking når valgt klubb mangler lokalt, og bruker medlemsklubbens GUID ved klubbbytte.
- Stopper booking hvis GolfBox fortsatt står i feil medlemsklubb etter klubbbytte.

## [1.8.54] - 2026-05-25
- Retter Internal Server Error ved GolfBox AI-ledighetssøk på Haga og andre ikke-Ballerud-baner.

## [1.8.53] - 2026-05-25
- Lar GolfBox AI planlegge solobooking for innlogget bruker selv om medlemsnummeret for valgt klubb ikke er lagret lokalt etter klubbbytte i GolfBox.
- Validerer ikke mot hjemmeklubbens medlemsnummer når GolfBox-bookingen gjelder en annen klubb.

## [1.8.52] - 2026-05-25
- Tolker GolfBox AI-prompter som “book meg” og “ikke noen flere enn meg” som booking for én spiller.
- Matcher GolfBox-medlemskap mer robust mot banenavnet når klubbnavn og GolfBox-resource ikke er identiske.
- Gjør feilmeldingen tydeligere når egen medlemsklubb mangler, i stedet for å etterspørre medspillere.

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
