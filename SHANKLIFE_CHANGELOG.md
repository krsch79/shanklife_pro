# Shanklife Pro Changelog

Merkbare endringer som gjelder Shanklife Pro loggføres her separat fra BalleTour.

## [1.8.86] - 2026-06-19
- Endrer hullføringen til naturlig slagrekkefølge: utslagskølle, lengde, green/fairway, putter, siste putt og score til slutt.
- Lar statistikk fylles ut og lagres før score, samtidig som score og komplette obligatoriske data fortsatt kreves ved fullføring.
- Uthever score som det tydelige siste feltet for hver spiller.

## [1.8.85] - 2026-06-18
- Tydeliggjør tidligere utslagsresultater som Fairwaytreff, Miss fairway høyre eller Miss fairway venstre.

## [1.8.84] - 2026-06-18
- Viser tidligere resultater på samme hull som kompakte og lettleste rundekort på mobil, uten behov for sideveis scrolling.

## [1.8.83] - 2026-06-18
- Beregner snittrunde som gjennomsnittlig score mot par, slik at runder på baner med ulikt par kan sammenlignes riktig.
- Deler beste slagsum i egne nøkkeltall for 18-hulls- og 9-hullsrunder.

## [1.8.82] - 2026-06-18
- Viser registrert lengde- og sideretning for par 3-treff i historikken for samme bane og hull, for eksempel kort høyre, lang venstre og pin high venstre.

## [1.8.81] - 2026-06-18
- Flytter fullføring av en pågående runde til en kompakt knapp ved siden av Scorekort, slik at den ikke lenger ligger som en stor knapp i hullnavigasjonen.

## [1.8.80] - 2026-06-18
- Legger til obligatorisk utslagskølle på par 3-hull for spillere som fører statistikk.
- Endrer utslagslengde til en valgfri nedtrekksliste som foreslår 125 meter på par 3 og 200 meter på par 4 og 5 når feltet åpnes.

## [1.8.79] - 2026-06-18
- Lar spillere hoppe over hull uten å føre score, med sirkulær hullnavigasjon som støtter shotgun-start.
- Kontrollerer hele scorekortet og alle obligatoriske statistikkfelt før en runde kan fullføres.
- Legger til et eget Shanklife-ikon i nettleserfanen.

## [1.8.77] - 2026-06-18
- Velger automatisk den innloggede spilleren som spiller 1 når en ny Shanklife-runde startes.
- Slår på statistikkføring som standard og velger automatisk den lengste teen som har slopeverdier for spilleren.

## [1.8.76] - 2026-06-17
- Lar spillere føre valgfri utslagslengde på alle hull når de spiller Shanklife-runder med statistikk.
- Viser tidligere score, køllevalg og statistikk for samme spiller, bane og hull under scoreføringen.

## [1.8.73] - 2026-06-15
- Lar brukeren velge 9 eller 18 hull ved rundestart når en 18-hullsbane består av to identiske 9-hullssløyfer.
- Beregner og fordeler mottatte slag som en 9-hullsrunde når bare første sløyfe spilles, også når banen har 18-hulls slope og course rating.
- Tilpasser scoreføring, scorekort, live leaderboard, statistikk og GolfBox-grunnlag til valgt rundelengde.

## [1.8.72] - 2026-06-12
- Bytter OpenAI-modellen i løsningen til GPT-5.2.
- Gjør par-feltet bredere på mobil ved opprettelse av bane og viser beregnet par og lengde for front 9, back 9 og totalt.
- Oppdaterer score mot par umiddelbart når en hullscore velges under runden.

## [1.8.71] - 2026-06-08
- Legger til en egen AI-statistikkchat for Shanklife-runder på andre baner enn Ballerud/BalleTour.
- Lar brukeren spørre om spillere, baner, teer, hull, score, putting, GIR, fairwaytreff, missretning og køllevalg.

## [1.8.70] - 2026-06-05
- Komprimerer datagrunnlaget som sendes til OpenAI i BalleTour sin AI-statistikkchat, slik at tee-baserte spørsmål ikke treffer token-grensen.
- Viser en ryddigere feilmelding hvis OpenAI likevel avviser et for stort statistikkgrunnlag.

## [1.8.69] - 2026-06-05
- Lar BalleTour sin AI-statistikkchat scrolle automatisk ned til siste spørsmål eller svar når siden lastes etter en ny melding.

## [1.8.68] - 2026-06-05
- Forbedrer BalleTour sin AI-statistikkchat slik at datagrunnlaget deles per tee og tar hensyn til ulike hull-lengder fra rød og gul tee.

## [1.8.67] - 2026-06-05
- Legger til en BalleTour-spesifikk AI-statistikkchat med lokalt beregnet datagrunnlag for score, hull, putting, køller, greenmønster og trender.

## [1.8.66] - 2026-06-05
- Viser en liten jobb-popup med sprettende golfball når brukeren starter tidkrevende handlinger, slik at samme skjema ikke sendes flere ganger.

## [1.8.65] - 2026-06-02
- Viser både navn og GolfBox-medlemsnummer for spillere i listen over planlagte AI-bookinger.

## [1.8.64] - 2026-06-02
- Retter faste GolfBox AI-bookinger slik at “neste” eller “påfølgende” spilledag ikke bookes som samme dag som kjøringen.
- Viser kommende spilledato og tid/tidsrom tydeligere i listen over planlagte AI-bookinger.

## [1.8.63] - 2026-05-29
- Viser fullførte Shanklife-runder som kompakte scorekort, på samme måte som fullførte BalleTour-runder.

## [1.8.62] - 2026-05-29
- Retter scorevisningen i live leaderboard-scorekortet slik at score mot par beregnes mot fullførte hull, ikke hele banen.

## [1.8.61] - 2026-05-28
- Viser i GolfBox AI-chatten om siste melding ble tolket med OpenAI og lokale regler, eller kun lokale regler.

## [1.8.60] - 2026-05-28
- Gir GolfBox AI mer kontekst om innlogget bruker og medlemskap når brukerens bookingforespørsel tolkes.
- Kobler navn i parentes etter medlemsnummer til riktig medspiller i GolfBox AI, for eksempel `65-2560 (Øyvind)`.
- Gjør feilmeldinger om manglende spillere tydeligere ved booking og automatisk ledighetssøk.

## [1.8.56] - 2026-05-28
- Skiller Shanklife-statistikk, Min side og generelle rundelister fra BalleTour ved å skjule runder på BalleTour-banen i Shanklife-visningene.

## [1.8.51] - 2026-05-25
- Tillater GolfBox-brukernavn som ikke er e-postadresse på Shanklife Min side.

## [1.8.50] - 2026-05-25
- Bytter lagring av GolfBox-passord fra intern tilsløring til Fernet-kryptering, og migrerer eksisterende GolfBox-passord automatisk ved oppstart.
- Beholder vanlige Shanklife-passord som irreversible passord-hasher, slik at de fortsatt ikke kan dekrypteres.
- Laster lokal `.env` ved appstart, slik at krypteringsnøkler og andre hemmelige innstillinger kan ligge utenfor repoet.

## [1.8.49] - 2026-05-25
- Retter GolfBox-innsending slik at hullscorer sendes som aktivert hullscorekort, med justert bruttoscore og poeng beregnet sammen med scorekortet.
- Lar en Shanklife-score sendes på nytt til GolfBox etter kontroll, med tydelig varsel om mulig duplikat.

## [1.8.48] - 2026-05-25
- Legger til GolfBox-innsending for fullførte Shanklife-runder for innlogget spiller, med markørsøk, bekreftelse og lagret sendestatus.
- Viser spørsmål om GolfBox-innsending når en Shanklife-runde fullføres, og legger til knappen Send til GolfBox på tidligere runder.

## [1.8.47] - 2026-05-24
- Lar nye Shanklife-baner lagres med 9 hull uten at tomme felt for hull 10-18 stopper lagringen.
- Gjør slope og course rating valgfrie ved manuell opprettelse, redigering og import av baner.

## [1.8.45] - 2026-05-24
- Legger til valgfrie e-postvarsler når Shanklife-runder startes og fullføres.
- Fargelegger scorekortscore med grønt for birdie eller bedre og rødt for bogey eller verre.

## [1.8.44] - 2026-05-24
- Retter Haga Blå+Gul hull 17 fra par 4 til par 5.
- Utvider Shanklife-statistikken med GIR, scorefordeling og per-runde-statistikk for fairway, putter og scoretyper.

## [1.8.43] - 2026-05-24
- Viser alle tees som standard på Shanklife live leaderboard, slik at pågående runder med tee-navn uten gul/rød ikke skjules.

## [1.8.42] - 2026-05-24
- Retter Shanklife live leaderboard slik at den gamle `/live-leaderboard`-adressen også fungerer uten innlogging.

## [1.8.41] - 2026-05-24
- Legger Driver, 3-wood, 5-wood og 2 hybrid til i køllevalgene for Shanklife Pro-statistikk.

## [1.8.38] - 2026-05-24
- Flytter Shanklife Pro-endringer til en egen changelog-fil ved siden av BalleTour-changeloggen.

## [1.8.37] - 2026-05-24
- Endrer teksten over stillingen mot par i hullføringen til Score.

## [1.8.36] - 2026-05-24
- Krever innlogging for Shanklife Pro-sider, med live leaderboard som eneste åpne Shanklife-visning.
- Rydder startside og meny til én knapp for å starte ny runde, siden statistikk velges per spiller i rundeopprettelsen.

## [1.8.35] - 2026-05-24
- Tydeliggjør køllefeltet som utslagskølle på par 4 og 5 når score føres hull for hull.
- Viser hvordan spillerne ligger an mot par før hullet som skal føres.

## [1.8.34] - 2026-05-24
- Lar hver spiller velge score eller full statistikk når en vanlig Shanklife-runde opprettes.
- Krever at statistikkspillere fyller ut alle statistikkfelt før neste hull eller fullføring.
- Legger køllevalg på utslag for statistikkspillere, med fairwaytreff eller venstre/høyre miss på par 4 og 5.

## [1.8.33] - 2026-05-23
- Legger til egen Shanklife Pro-statistikkside for fullførte statistikkrunder med greentreff, putting, scorefordeling og utslag på par 4/5.
- Lar Shanklife Pro-statistikkrunder registrere kølle og fairwaytreff, venstre eller høyre miss på utslag på par 4 og 5 uten å registrere utslagslengde.
- Viser produktspesifikke changelog-lister hver for seg på changelog-siden.

## [1.8.32] - 2026-05-20
- Sender e-post til brukeren når en GolfBox-booking er bekreftet, når en fremtidig booking legges inn, og når en planlagt booking er gjennomført.
- Legger bane, dato, tidspunkt, spillere, gjennomføringstidspunkt og forventet vær inn i GolfBox-bookingmailene.

## [1.8.31] - 2026-05-20
- Legger til planlagte GolfBox-bookinger for Ballerud, slik at en booking kan gjennomføres automatisk på et valgt tidspunkt uten ny bekreftelse.
- Lar brukeren kansellere en planlagt GolfBox-booking frem til ett minutt før gjennomføring.
- Installerer en minuttvis Raspberry Pi-kjører ved deploy som utfører planlagte GolfBox-bookinger når tidspunktet kommer.
- Retter den planlagte GolfBox-kjøreren slik at den kan startes direkte fra cron på Raspberry Pi.

## [1.8.30] - 2026-05-20
- Lar GolfBox AI svare direkte på spørsmål om brukerens lagrede GolfBox-medlemsnummer uten å gjøre et nytt ledighetssøk.
- Tolker “meg”, “jeg” og “mitt” som innlogget bruker i bookingprompter, slik at egen booking bruker lagret medlemsnummer automatisk.

## [1.8.29] - 2026-05-20
- Retter GolfBox AI-booking når brukeren oppgir ett bestemt klokkeslett, slik at tidspunktet tolkes som et kort søkevindu i stedet for et ugyldig nullintervall.
- Korter ned OpenAI-konteksten for GolfBox AI, slik at bare nødvendig prompttolkning sendes til modellen.
- Nullstiller GolfBox AI-chatten hver gang AI-siden åpnes på nytt.
- Skroller GolfBox AI-siden automatisk ned til siste svar etter innsending.

## [1.8.28] - 2026-05-20
- Bytter GolfBox AI til OpenAI-basert tolkning av spørsmål, med strukturert intent, baner, dato, tidsrom, spillere og spillernavn.
- Låser meldingsfeltet nederst på GolfBox AI-siden, slik at nye svar vises rett over feltet mens man skroller.
- Lagrer GolfBox-medlemskap og medlemsnummer per bruker når GolfBox kobles til på Min side.
- Lar GolfBox AI søke etter ledige starttider på flere baner samtidig, inkludert baner i Oslo-området.
- Viser dato på hver ledige starttid og sorterer resultatene stigende etter dato og klokkeslett.
- Klargjør Ballerud-booking for inntil fire spillere når medspillernes lagrede GolfBox-medlemsnummer finnes.

## [1.8.27] - 2026-05-20
- Lar innloggede brukere lagre egne GolfBox-detaljer på Min side og bruker disse i GolfBox AI.
- Legger til ledighetssøk for andre GolfBox-baner, foreløpig uten booking på andre baner enn Ballerud.
- Legger til en bekreftet Ballerud-bookingflyt som stopper før booking hvis GolfBox viser betaling, feil klubb eller feil medlemskap.

## [1.8.26] - 2026-05-20
- Gjør GolfBox AI-siden om til en chatvisning med spørsmål og svar.
- Tilpasser promptfeltet på GolfBox AI-siden etter skjermstørrelse, slik at det fungerer bedre på mobil og desktop.

## [1.8.25] - 2026-05-20
- Endrer GolfBox-prompten slik at spørsmål uten tidsrom sjekker hele spilldagen, ikke bare standardvinduet 15-17.
- Lar GolfBox-prompten forstå enkle tidsuttrykk som etter, før, fra og rundt klokkeslett.

## [1.8.24] - 2026-05-20
- Kobler GolfBox-ledighetssjekk til innlogget lesing av Ballerud-starttider, slik at promptfeltet kan vise ledige tider når GolfBox-innlogging er konfigurert.
- Leser GolfBox-innlogging trygt fra lokal `.env`, slik at tilgangen kan konfigureres på Raspberry Pi uten a lagres i repoet.

## [1.8.23] - 2026-05-20
- Legger til et GolfBox-verktøy i MCP som kan motta spørsmål om ledige starttider for bane, antall spillere, dato og tidsrom, og som tydelig varsler når GolfBox-credentials mangler på Pi-en.

## [1.8.22] - 2026-05-17
- Bygger logoene og golfillustrasjonen direkte inn i vedlikeholdssiden, slik at de vises også når appens statiske filserver ikke er tilgjengelig under deploy.

## [1.8.19] - 2026-05-17
- Setter alle e-postvarseltyper på som standard, slik at brukere aktivt kan velge bort varsler de ikke vil ha.
- Lar deploy-scriptet vise den statiske vedlikeholdssiden mens app-prosessen er stoppet under restart.

## [1.8.18] - 2026-05-17
- Legger til valgfri e-post ved versjonsoppdateringer og sender versjonsvarsel én gang per deployet versjon.

## [1.8.17] - 2026-05-15
- Gjør admin-rollen dynamisk slik at administratorer kan gi og fjerne admin-tilgang for registrerte brukere, uten at Kristian tvinges til admin ved hver oppstart.

## [1.8.16] - 2026-05-14
- Viser tag- og hullfiltre fast øverst i galleriet som synlige checkbox-grupper, og oppdaterer galleriet hver gang et filter velges eller velges bort.

## [1.8.14] - 2026-05-14
- Rydder bildeteksten i galleriet til dato/tid, hull og tags, og fjerner fast banenavn og teksten Lastet opp.
- Gjør galleribildene klikkbare slik at originalbildet åpnes i ny fane.

## [1.8.13] - 2026-05-14
- Oppdaterer deploy-scriptet slik at vedlikeholdsmodus skrus pa for deploy og fjernes automatisk nar deployen er ferdig eller feiler.

## [1.8.12] - 2026-05-14
- Endrer bildeopplastingsfeltet fra Spiller-tag til Tag og viser alle tags på hullside, spillerprofil og galleri.
- Legger til filter og sortering i galleriet for tag, hull, datointervall og visningsrekkefølge.

## [1.8.11] - 2026-05-14
- Gjør GitHub-kommentarer fra AI worker tydeligere når Codex/OpenAI feiler, med egne meldinger for kvote/billing, autentisering, rate limit, utilgjengelig modell og lokale kode-/kommandofeil.
- Lar isolert AI worker returnere feilkode uten a overskrive den forklarende GitHub-feilmeldingen med en ekstra Python-stacktrace.

## [1.8.10] - 2026-05-14
- Dokumenterer repo-regelen om at changelog og versjon alltid skal oppdateres sammen med kodeendringer.

## [1.8.5] - 2026-05-05 20:13
- Viser opplastingsdato og klokkeslett i galleriet.
- Fjerner automatisk 0,5 m valg ved fokus pa siste putt slik at siste putt ma velges aktivt.

## [1.8.3] - 2026-05-05 19:49
- Endrer Side til Retning og fikser at Pa flagget ikke laser de andre greenvalgene.

## [1.8.0] - 2026-05-05 16:43
- Endrer siste putt til ett valg med 0,1 meters intervall og radiovalg for gjensidig utelukkende greenretninger.

## [1.7.1] - 2026-05-04 21:15
- Sender Fortsett runde til forste hull der minst en spiller mangler score.

## [1.5.12] - 2026-05-02 19:46
- Viser strokes gained pa spillerstatistikk og samlet statistikk basert pa fullforte runder.

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

## [1.1.0] - 2026-05-01 14:37
- La til changelog-side som apnes fra versjonsnummeret.
- Flyttet OpenAI API-nokkel ut av kildekoden og over til miljovariabel for GitHub-push.

## [1.0.0] - 2026-05-01 11:42
- Forste versjon av Shanklife Pro lagt i GitHub.
