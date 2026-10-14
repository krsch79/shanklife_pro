import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var session: SessionStore
    var body: some View {
        TabView {
            NavigationStack { SportsHomeView() }.tabItem { Label("Hjem", systemImage: "house") }
            NavigationStack { SportsRoundsView() }.tabItem { Label("Runder", systemImage: "flag") }
            NavigationStack { SportsInsightView() }.tabItem { Label("Innsikt", systemImage: "chart.xyaxis.line") }
            NavigationStack { SportsTourView() }.tabItem { Label("Tour", systemImage: "trophy") }
            NavigationStack { profileView }.tabItem { Label("Profil", systemImage: "person.crop.circle") }
        }.tint(SportsPalette.action)
    }
    private var profileView: some View {
        List {
            if let user = session.user { Section {
                VStack(alignment: .leading,spacing: 10) {
                    Text("DIN KONTO").font(.caption.weight(.semibold)).tracking(2).foregroundStyle(.secondary)
                    Text(user.player?.name ?? user.username).font(.title.weight(.heavy))
                    if let player = user.player { Text("Handicap \(player.defaultHcp.formatted(.number.precision(.fractionLength(1))))").foregroundStyle(.secondary) }
                }.padding(.vertical, 12)
            } }
            Section("Golfen din") {
                NavigationLink { SportsWebScreen(path: "/me", title: "Konto og integrasjoner") } label: { Label("Konto og integrasjoner", systemImage: "link") }
                NavigationLink { SportsWebScreen(path: "/me/notifications", title: "Varsler") } label: { Label("Varsler", systemImage: "bell") }
                if session.user?.products.shanklife == true { NavigationLink { ShanklifeCoursesView() } label: { Label("Baner", systemImage: "flag.2.crossed") } }
                if session.user?.products.balletour == true { NavigationLink { SportsWebScreen(path: "/balletour/ai", title: "Starttider") } label: { Label("Starttider", systemImage: "calendar") } }
                if session.user?.isAdmin == true { NavigationLink { SportsWebScreen(path: "/admin", title: "Administrasjon") } label: { Label("Administrasjon", systemImage: "slider.horizontal.3") } }
            }
            Section("Om Shanklife") {
                LabeledContent("Appversjon", value: appVersionDisplay)
                if let version = session.bootstrap?.version { LabeledContent("Serverversjon", value: version) }
                DisclosureGroup("Tilkoblingsdetaljer") { Text(session.baseURLText).font(.caption); if let message = session.lastConnectionMessage { Text(message).font(.caption).foregroundStyle(.secondary) } }
            }
            Section { Button(role: .destructive) { Task { await session.logout() } } label: { Label("Logg ut", systemImage: "rectangle.portrait.and.arrow.right") } }
        }.navigationTitle("Profil")
    }
    private var appVersionDisplay: String { let info=Bundle.main.infoDictionary;return "\(info?["CFBundleShortVersionString"] as? String ?? "—") (\(info?["CFBundleVersion"] as? String ?? "—"))" }
}
