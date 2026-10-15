# Shanklife iOS Sportsmodus

SwiftUI-klienten samler Shanklife og BalleTour i Hjem, Runder, Innsikt, Tour og Profil. Standardserver er `https://app.shanklife.no`. Web/backend-deploy oppdaterer ikke en allerede installert native app; native 2.0.0 (21) må distribueres som egen signert iOS-utgivelse.

## Struktur og grenser

- `DashboardView.swift` gir femområdenavigasjon. `SportsModeViews.swift` viser personlige serverdata og de felles funksjonene.
- `APIClient.swift` og `Models.swift` bruker de eieravgrensede Sportsmodus-endepunktene og eksisterende score-/statistikk-API. Rundetype og medlemskap kommer fra serveren.
- `SessionStore.swift` håndterer innlogging, cookie-sesjon og eksisterende Keychain-lagring. Konto, originaldata, ferdige vanlige scorekort, starttider og administrasjon åpnes i en autentisert WKWebView med samme servercookie og ikke-vedvarende webdatastore. Passord sendes aldri i JavaScript eller URL.
- Vanlige runder og tourrunder føres native. Store scorevalg viser birdie/par/bogey og hele listen ved trykk på scoren. Lagre og hullbytte sender til serveren; ved feil beholdes gjeldende hull og input. Det finnes ingen offline scorekø.
- Ferdige tourrunder, tourstatistikk og baneoppretting bruker eksisterende native visninger. Eksterne tjenester trenger tilgjengelig server og nett.
- Lokal automatisk testinnlogging er beskyttet med både `DEBUG` og `targetEnvironment(simulator)`. `SPORTS_UI_QA=1` aktiverer kun syntetisk localhost-fixture på 5057 og lagrer ikke testpassord i Keychain. Release inneholder ikke denne grenen.

## Bygg og test

Åpne `Shanklife.xcodeproj`, bruk delt scheme `Shanklife` og en tilgjengelig iOS-runtime. Lokal testserveradresse kan velges under Tilkoblingsdetaljer på innloggingssiden. Ikke rydd brukerens åpne Xcode-workspace eller xcuserdata.

```bash
xcodebuild -project ios/Shanklife/Shanklife.xcodeproj -scheme Shanklife -configuration Release -destination 'generic/platform=iOS' -derivedDataPath /tmp/shanklife-release CODE_SIGNING_ALLOWED=NO
```

`ShanklifeUITests/SportsModeUITests.swift` prøver ekte navigasjon, felles innlogging og scorelagring gjennom hullbytte mot den disponible demo-serveren beskrevet i `IMPLEMENTATION_STATUS.md`. Start serveren og kontroller health før testen; ikke nullstill fixture eller opprett browser-runder mens XCTest kjører. Skjermbilder lagres som xcresult-vedlegg. Signering og Apple-opplasting krever egne kontroller av arkiv, team og provisioning. Et usignert Release-bygg er kompilasjonsbevis, ikke en publisert iPhone-utgivelse.

## Starttider på iPhone

I native2.0.0(21) finnes **Profil → Starttider** for brukere med BalleTour-tilgang. Den autentiserte webvisningen åpner /balletour/ai, som serveren videresender til /starttider. Den bruker dermed gjeldende webflyt med banesøk/sløyfer, AI, antall ledige plasser og valgfritt færre bookingdeltakere uten ny iOS-binær. Tilgangsgrensen er den samme som på web.

`testStarttiderFromProfileCanReviewFewerPlayers` er bestått på iPhone18Pro-simulator med iOS27: Profil→Starttider, innlogget webside, ingen dobbel tabbar, tidsvalg fra topersonsøk, spiller1 alene og korrekt bookingoppsummering. Den oppretter ingen live booking. Før denne testen skal den disponible serveren på5057 ha et fremtidsdatert søk med2plasser og tilgjengelige syntetiske tider lagret i demoens arbeidsflate. Ikke endre fixture mens XCTest kjører. Faktisk installert versjon på brukerens fysiske iPhone er ikke lest.
