# Shanklife iOS

Native SwiftUI-klient for Shanklife Pro og BalleTour.

## Lokal oppstart

1. Åpne `Shanklife.xcodeproj` i Xcode.
2. Velg en iPhone-simulator eller fysisk iPhone.
3. Start Flask-serveren lokalt på port `5055`.
4. I appens login-skjerm bruker du base URL `http://127.0.0.1:5055` i simulatoren.

For fysisk iPhone må base URL peke til en HTTPS-adresse eller en lokal nettverksadresse som telefonen når.

## Struktur

- `APIClient.swift` håndterer JSON-kall mot `/api/v1`.
- `SessionStore.swift` eier innlogging, bootstrap og utlogging.
- `ContentView.swift` bytter mellom login og hovedapp.
- `DashboardView.swift` viser de to produktdelene: Shanklife Pro og BalleTour.
