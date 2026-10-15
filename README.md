# Shanklife Sportsmodus

Shanklife samler personlig golf og BalleTour i én Sportsmodus-opplevelse. Den dekker scoreføring og statistikk for Shanklife-runder, BalleTour, delte brukere, GolfBox-integrasjon, Garmin-synkronisering, varsler og enkelte administrative arbeidsflyter.

## Arkitektur

- `app.py` oppretter Flask-applikasjonen, registrerer blueprints og kjører nødvendige skjema- og datakorreksjoner ved oppstart.
- `routes/` inneholder HTTP-flytene for scoreføring, runder, statistikk, profiler, BalleTour, GolfBox og API.
- `models.py` og `extensions.py` definerer SQLAlchemy-modellen og databasekoblingen.
- `services/` inneholder domene- og integrasjonslogikk, blant annet GolfBox, Garmin, statistikk, e-post, hemmelighetslagring og varsler.
- Rundelengde styres av `Round.played_hole_count` og `Round.starting_hole_number`. `services/round_length.py` er felles kilde for hvilke hull en runde omfatter; en 18-hullsbane kan spilles som 18 hull, «Første 9» (1–9) eller «Siste 9» (10–18).
- Administratorredigering av en fullført Shanklife-runde kan oppdatere både score/statistikk på det viste hullet og `RoundPlayer.selected_tee_id` per spiller. Tee-valget valideres mot rundens bane, gjelder hele runden og lagres ved hullbytte eller «Lagre og lukk», uten å åpne runden eller endre `finished_at`.
- GET-visningen etter fullføring oppretter ikke en GolfBox-kladd. Kladden opprettes og committes separat først ved markørsøk eller innsending, slik at Safari-retry og treg GolfBox-respons ikke holder en SQLite-skrivelås eller konkurrerer om den unike kladden.
- `templates/` og `static/` inneholder det server-renderte grensesnittet. GPS-måling av slag ligger i `templates/round_hole.html` og aktiveres bare etter en eksplisitt brukerhandling.
- `scripts/` inneholder deploy, backup, vedlikeholdsserver, planlagte jobber og driftsverktøy.
- `balletour_survey/` er en separat sideapp med egen README og runtime.

## Sportsmodus 2.0

Fem hovedområder er felles for web og iOS: Hjem, Runder, Innsikt, Tour og Profil. `routes/main.py` leverer den personlige oversikten; `/api/v1/sports/overview` og `/api/v1/sports/rounds` bruker samme eieravgrensede lesemodell i `services/sportsmode.py`. Eksisterende runde-, integrasjons-, administrasjons- og touradresser beholdes. Nye installasjoner bruker ett Shanklife-manifest; det gamle BalleTour-manifestet beholder sin installasjons-ID, men utvider virkeområdet til den samlede appen.

`Round.series_id` og `Round.tour_context_set` skiller en ny vanlig runde fra en BalleTour-runde, også på samme bane. Ved første oppstart etter oppgradering legges de to kolonnene og en indeks til. `migrate_legacy_tour_context()` fester tidligere baneklassifiserte BalleTour-runder til touren og markerer de øvrige som vanlige runder. Senere oppstarter kan ikke gjøre en allerede merket vanlig runde om til tourrunde. Andre eldre klubbserier beholder sitt eksisterende banebaserte beregningsgrunnlag. Score, resultat, rundelengde og private TrackMan-arkiver skrives ikke om av denne migreringen. Backup før oppgradering er nødvendig for tilbakeføring av denne førstegangsklassifiseringen.

Den personlige historikken viser egne `RoundPlayer`-rader og bare brukerens egne TrackMan-projeksjoner. Shanklife-tilgang følger `shanklife-pro` på web og `shanklife-app` på appverten; tourtilgang krever `balletour` og tourmedlemskap. Felles sider og autentisering godtar minst én av disse tilgangene; rundevisning og scoreføring krever riktig produkttilgang for selve runden. Tourberegningen, tee-filtrene og kvalifiseringskravet beholdes. Kvalifisering er en egen status og endrer ikke sorteringsrekkefølgen.

`static/sports.css`, `sports.js` og `sports-icons.svg` utgjør den nye visuelle rammen. Score lagres ved Lagre, hullbytte og åpning av scorekort. Par velges aldri automatisk. Scoreføring krever nett; det finnes ingen vedvarende lokal scorekø. Service worker lagrer bare offentlig statisk innhold, aldri private sider eller API-svar. GPS, bilder, GolfBox, Garmin, TrackMan, AI-statistikk og starttidsfunksjoner bruker eksisterende tjenester.

## Lokal utvikling

Ikke utvikle direkte i `/Volumes/Shared/shanklife_pro`; denne SMB-mappen er produksjonskilden på Raspberry Pi-en. Bruk en ren klone under `/tmp` eller en annen lokal arbeidsmappe.

```bash
python3.11 -m venv /tmp/shanklife-pro-dev
/tmp/shanklife-pro-dev/bin/pip install -r requirements.txt
cp .env.example .env
DATABASE_URL=sqlite:////tmp/shanklife-pro-dev.db /tmp/shanklife-pro-dev/bin/python app.py
```

Appen lytter som standard på port `5055`. `.env` er lokal og skal aldri committes. En tom lokal database opprettes automatisk; produksjonsdata skal ikke kopieres inn uten et konkret testbehov og skal aldri legges i Git.

## Tester

Bruk et ferskt midlertidig virtuelt miljø på macOS, fordi eksisterende miljøer under `/tmp` kan være utdaterte eller mangle native avhengigheter.

```bash
python3.11 -m venv /tmp/shanklife-pro-test
/tmp/shanklife-pro-test/bin/pip install -r requirements.txt
/tmp/shanklife-pro-test/bin/python -m py_compile $(git ls-files '*.py')
/tmp/shanklife-pro-test/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Bruk nettlesertest i tillegg når endringen gjelder interaksjon eller responsivt grensesnitt. Test GPS-flyter med mockede posisjonshendelser eller uten å gi posisjonstilgang før brukeren trykker på aktiveringskontrollen.

## Produksjon og deploy

Produksjonen kjører på Raspberry Pi via SSH-aliaset `shanklife-pi`. Kilden ligger i `/home/kristian/shanklife_pro`, prosessen er `/tmp/shanklife_pro_venv/bin/python app.py`, og appen lytter på port `5055`. Systemd-tjenesten `shanklife-pro.service` starter og overvåker prosessen, slik at Shanklife Pro, Shanklife App, BalleTour og Score kommer tilbake automatisk etter en serveromstart.

Normal flyt er å teste, oppdatere riktig changelog og `services/version.py`, committe og pushe `main`, og deretter kjøre:

```bash
ssh shanklife-pi 'cd /home/kristian/shanklife_pro && ./scripts/deploy.sh'
```

Deployskriptet setter vedlikeholdsmodus, tar databasebackup, fast-forwarder fra GitHub, installerer avhengigheter, syntakssjekker, installerer/aktiverer systemd-tjenesten og restarter appen. Etter deploy skal følgende verifiseres:

Ved datamigrering kan `SHANKLIFE_PRE_UNLOCK_CHECK=/absolutt/sti/til/kontroll.py` kreve en ekstra kontroll før vedlikeholdsflagget fjernes. En feil skal beholde vedlikehold og utløse den forberedte tilbakeføringen. Den særskilte Sportsmodus-utrullingen tar konsistent SQLite-backup og SHA-256 mens hovedappen er stanset, pauser bare prosjektets cronjobber og bruker en uavhengig systemd-timer for tilbakeføring av koden. GPS Survey bruker også databasen og skal ikke miste sine skriveresultater: automatisk koderollback beholder den additive databasestrukturen. En full databaserestaurering fra backup krever kontroll av alle delte skrivere.

- `shanklife-pro.service` er aktiv og aktivert for automatisk oppstart;
- prosessen `/tmp/shanklife_pro_venv/bin/python app.py` kjører og port `5055` lytter;
- `instance/maintenance.lock` er fjernet;
- `https://pro.shanklife.no/api/v1/health` og `https://app.shanklife.no/api/v1/health` viser riktig versjon;
- produksjons-HEAD er den samme committen som er pushet til GitHub;
- deploy-e-post er sendt og bekreftet i mail-loggen.

## Data og hemmeligheter

Produksjonsdatabasen og runtime-data ligger under `instance/` og `uploads/` og er ignorert av Git. `.env`, SQLite-filer, logger, backuper, Garmin-tokenfiler, GolfBox-legitimasjon, SMTP-legitimasjon og OpenAI-nøkler skal aldri committes eller skrives ut i logger og svar. `.env.example` dokumenterer bare trygge variabelnavn.

## Invitasjoner og rundefiltre

- Admin-siden sender Shanklife-invitasjoner gjennom `services/shanklife_invitations.py` og eksisterende SMTP-oppsett. `shanklife_invitations` opprettes av `db.create_all()` ved oppstart; bare SHA-256 av token lagres. Lenken varer i sju dager, kan brukes én gang, og en ny utsending erstatter den gamle lenken. Ved e-postfeil rulles endringen tilbake.
- Aksept oppretter vanlig bruker og spiller og gir `user_app_access` til både `shanklife-pro` og `shanklife-app`, uten adminrettigheter eller BalleTour-medlemskap. Begge appene må allerede finnes i den sentrale `app_registry`. Eksisterende e-post eller spillernavn avvises for å unngå duplikater.
- `/rounds/finished` støtter kombinerbare GET-filtre `course`, `holes`, `year` og `player`. Baner, år og spillere hentes fra de fullførte Shanklife-rundene. Rundelengde bruker `round_hole_count`, også for eldre runder uten eksplisitt lengde.
- `services/fairway.py` definerer par-4/par-5-resultatene. `green` betyr at utslaget traff green og telles separat fra fairwaytreff; alle sju registrerte resultater inngår i nevneren for fairwayprosent. GIR beregnes som før fra score og putter. De nye valgene er tilgjengelige i nettgrensesnittet; native iOS får dem først ved en egen apputgivelse.
- Regresjonstester ligger i `tests/test_shanklife_improvements.py`; SMTP mockes slik at testene ikke sender invitasjoner.

## Begrensninger og oppfølging

- GPS-måling krever eksplisitt nettlesertillatelse og 5 meters nøyaktighet før lengdemåling kan starte.
- GolfBox og Garmin er eksterne integrasjoner; feil der skal ikke hindre lagring eller fullføring av en vanlig Shanklife-runde når flyten er definert som valgfri.
- Produksjonsprosessen startes og overvåkes av `shanklife-pro.service`; `scripts/deploy.sh` installerer tjenesten og bruker fortsatt `run.sh` som felles runtime-startpunkt. Driftskontroller skal verifisere både systemd, faktisk prosess, port og health-endepunkt.
- Eldre 9-hullsrunder uten `starting_hole_number` tolkes som «Første 9». Nye runder valideres mot både antall hull og tillatt start-hull.
- Produktendringer dokumenteres i `SHANKLIFE_CHANGELOG.md` eller `BALLETOUR_CHANGELOG.md`. Relevante åpne oppgaver spores i GitHub Issues.

TrackMan simulator rounds, raw archives, OAuth setup, source filters, completeness
checks and scheduled synchronization are documented in [TRACKMAN.md](TRACKMAN.md).

## Starttider (2.1.1)

`/starttider` er den felles responsive bookingflaten; `/balletour/ai` videresender gamle GET-lenker. POST fra en gammel innlastet side utfører ingen gammel handling og ber brukeren kontrollere søket i den nye flyten. Native iOS bruker sin eksisterende autentiserte webvisning og trenger ingen ny binær for denne endringen. Dagens BalleTour-medlemskap og sentrale tilgang er fortsatt påkrevd.

- `routes/starttider.py`, `services/starttider.py`, `templates/starttider.html` og `static/starttider.{css,js}` gir Finn tid, Mine tider, Automatikk og paginert historikk. Skallet gjør ingen eksterne oppslag. Klienten henter kommende bookinger separat, med 90 sekunders eierbundet cache og synlig hentetid. Favoritter oppdateres bare ved eksplisitt handling, og eksisterende medlemsnumre brukes som stabile valg selv om synk erstatter databaserader.
- Søk bruker bare antall spillere; identiteter velges etter valgt tid. Innlogget bruker normaliseres til spiller 1 både ved validering og før bekreftelse. Nye oppdrag går gjennom samme spillervalg. `POST /starttider/players` gjør kun et autentisert CSRF-beskyttet katalogoppslag med private no-store-svar; det endrer verken favoritter, utkast eller revisjon. Navnesøk gjenbruker GolfBox sitt markørsøk og henter medlemsnummer fra resultatetiketten. Medlemsnummer kontrolleres igjen i GolfBox før oppsummering; navn fra nettleseren godtas aldri som bookingidentitet. Flere medlemskap er separate valg med klubb og nummer. Ingen nye tabeller eller datamigreringer i 2.1.1.
- `golfbox_workspaces` er en ny, additiv tabell med brukerbundet utkast, avgrenset samtale, søkeresultater, cache og revisjon. Utkast utløper etter 24 timer. `golfbox_actions` lagrer frosne oppsummeringer som utløper etter ti minutter. Ingen eksisterende GolfBox-oppdrag eller historikk migreres eller opprettes ved utrulling.
- Alle nye mutasjoner krever sesjonsbundet CSRF-token og gjeldende revisjon. Revidert SQL-oppdatering hindrer konkurrerende endringer. Handlings-ID kreves og konsumeres før ekstern innsending. Ved uavklart resultat tilbys ingen automatisk gjentakelse; brukeren skal kontrollere Mine tider/oppdragslogg. SQLite-skrivetransaksjoner avsluttes før nettverkskall. Eksisterende bokmotor verifiserer reservasjonen i GolfBox; ny flyt kontrollerer også ledig kapasitet før innsending og kontrollerer avbestilling mot Mine tider etterpå.
- AI returnerer bare et validert forslag til søkeendringer. AI kan ikke aktivere oppdrag eller booke. Vanlig søk fungerer uten AI-nøkkel; kort oppfølging som «heller etter 17» støttes også med lokale regler. Alle tre eksisterende automatikktype krever eksplisitt bekreftelse. Tidspunkter følger serverens Europe/Oslo-tidssone. BalleTour-testvisning blokkerer mutasjoner i den nye bookingflaten.
- Private responser har `Cache-Control: no-store`. Verken service worker eller nettleserlagring brukes til private bookinger, søkeutkast eller legitimasjon. Nye versjonerte ressurser er oppført i shell-cachen. Det finnes ingen offline bookingkø.
- Kjør `python -m unittest tests.test_starttider -q` og hele `python -m unittest discover -s tests -q` i et verifisert Python 3.11-miljø. Bruk syntetisk database og mock alle eksterne bookinger, kanselleringer og e-poster. Starttider-skjermene skal i tillegg kontrolleres i nettleser ved 320/393 px og desktop. Fysisk iPhone/tastatur og reelle reservasjoner er separate akseptansetester, ikke noe mocktestene beviser.
