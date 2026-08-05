# Shanklife Pro

Shanklife Pro er hovedapplikasjonen i Shanklife-økosystemet. Den dekker scoreføring og statistikk for Shanklife-runder, BalleTour, delte brukere, GolfBox-integrasjon, Garmin-synkronisering, varsler og enkelte administrative arbeidsflyter.

## Arkitektur

- `app.py` oppretter Flask-applikasjonen, registrerer blueprints og kjører nødvendige skjema- og datakorreksjoner ved oppstart.
- `routes/` inneholder HTTP-flytene for scoreføring, runder, statistikk, profiler, BalleTour, GolfBox og API.
- `models.py` og `extensions.py` definerer SQLAlchemy-modellen og databasekoblingen.
- `services/` inneholder domene- og integrasjonslogikk, blant annet GolfBox, Garmin, statistikk, e-post, hemmelighetslagring og varsler.
- Rundelengde styres av `Round.played_hole_count` og `Round.starting_hole_number`. `services/round_length.py` er felles kilde for hvilke hull en runde omfatter; en 18-hullsbane kan spilles som 18 hull, «Første 9» (1–9) eller «Siste 9» (10–18).
- Administratorredigering av en fullført Shanklife-runde kan oppdatere både score/statistikk på det viste hullet og `RoundPlayer.selected_tee_id` per spiller. Tee-valget valideres mot rundens bane, gjelder hele runden og lagres ved hullbytte eller «Lagre og lukk», uten å åpne runden eller endre `finished_at`.
- `templates/` og `static/` inneholder det server-renderte grensesnittet. GPS-måling av slag ligger i `templates/round_hole.html` og aktiveres bare etter en eksplisitt brukerhandling.
- `scripts/` inneholder deploy, backup, vedlikeholdsserver, planlagte jobber og driftsverktøy.
- `balletour_survey/` er en separat sideapp med egen README og runtime.

## Lokal utvikling

Ikke utvikle direkte i `/Volumes/Shared/shanklife_pro`; denne SMB-mappen er produksjonskilden på Raspberry Pi-en. Bruk en ren klone under `/tmp` eller en annen lokal arbeidsmappe.

```bash
python3 -m venv /tmp/shanklife-pro-dev
/tmp/shanklife-pro-dev/bin/pip install -r requirements.txt
cp .env.example .env
DATABASE_URL=sqlite:////tmp/shanklife-pro-dev.db /tmp/shanklife-pro-dev/bin/python app.py
```

Appen lytter som standard på port `5055`. `.env` er lokal og skal aldri committes. En tom lokal database opprettes automatisk; produksjonsdata skal ikke kopieres inn uten et konkret testbehov og skal aldri legges i Git.

## Tester

Bruk et ferskt midlertidig virtuelt miljø på macOS, fordi eksisterende miljøer under `/tmp` kan være utdaterte eller mangle native avhengigheter.

```bash
python3 -m venv /tmp/shanklife-pro-test
/tmp/shanklife-pro-test/bin/pip install -r requirements.txt
/tmp/shanklife-pro-test/bin/python -m py_compile $(git ls-files '*.py')
/tmp/shanklife-pro-test/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Bruk nettlesertest i tillegg når endringen gjelder interaksjon eller responsivt grensesnitt. Test GPS-flyter med mockede posisjonshendelser eller uten å gi posisjonstilgang før brukeren trykker på aktiveringskontrollen.

## Produksjon og deploy

Produksjonen kjører på Raspberry Pi via SSH-aliaset `shanklife-pi`. Kilden ligger i `/home/kristian/shanklife_pro`, prosessen er `/tmp/shanklife_pro_venv/bin/python app.py`, og appen lytter på port `5055`. Den er ikke en egen systemd-tjeneste.

Normal flyt er å teste, oppdatere riktig changelog og `services/version.py`, committe og pushe `main`, og deretter kjøre:

```bash
ssh shanklife-pi 'cd /home/kristian/shanklife_pro && ./scripts/deploy.sh'
```

Deployskriptet setter vedlikeholdsmodus, tar databasebackup, fast-forwarder fra GitHub, installerer avhengigheter, syntakssjekker og restarter appen. Etter deploy skal følgende verifiseres:

- prosessen `/tmp/shanklife_pro_venv/bin/python app.py` kjører og port `5055` lytter;
- `instance/maintenance.lock` er fjernet;
- `https://pro.shanklife.no/api/v1/health` og `https://app.shanklife.no/api/v1/health` viser riktig versjon;
- produksjons-HEAD er den samme committen som er pushet til GitHub;
- deploy-e-post er sendt og bekreftet i mail-loggen.

## Data og hemmeligheter

Produksjonsdatabasen og runtime-data ligger under `instance/` og `uploads/` og er ignorert av Git. `.env`, SQLite-filer, logger, backuper, Garmin-tokenfiler, GolfBox-legitimasjon, SMTP-legitimasjon og OpenAI-nøkler skal aldri committes eller skrives ut i logger og svar. `.env.example` dokumenterer bare trygge variabelnavn.

## Begrensninger og oppfølging

- GPS-måling krever eksplisitt nettlesertillatelse og 5 meters nøyaktighet før lengdemåling kan starte.
- GolfBox og Garmin er eksterne integrasjoner; feil der skal ikke hindre lagring eller fullføring av en vanlig Shanklife-runde når flyten er definert som valgfri.
- Produksjonsprosessen styres av `scripts/deploy.sh` og `run.sh`, ikke systemd. Driftskontroller må derfor følge faktisk prosess, port og health-endepunkt.
- Eldre 9-hullsrunder uten `starting_hole_number` tolkes som «Første 9». Nye runder valideres mot både antall hull og tillatt start-hull.
- Produktendringer dokumenteres i `SHANKLIFE_CHANGELOG.md` eller `BALLETOUR_CHANGELOG.md`. Relevante åpne oppgaver spores i GitHub Issues.
