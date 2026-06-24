import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var session: SessionStore

    var body: some View {
        TabView {
            NavigationStack {
                ShanklifeView()
            }
            .tabItem {
                Label("Shanklife", systemImage: "figure.golf")
            }

            NavigationStack {
                BalleTourView()
            }
            .tabItem {
                Label("BalleTour", systemImage: "trophy")
            }

            NavigationStack {
                profileView
            }
            .tabItem {
                Label("Profil", systemImage: "person.crop.circle")
            }
        }
    }

    private var profileView: some View {
        Form {
            if let user = session.user {
                Section("Bruker") {
                    LabeledContent("Navn", value: user.player?.name ?? user.username)
                    LabeledContent("Brukernavn", value: user.username)
                    if let email = user.email, !email.isEmpty {
                        LabeledContent("E-post", value: email)
                    }
                    LabeledContent("Shanklife", value: user.products.shanklife ? "Tilgang" : "Ingen tilgang")
                    LabeledContent("BalleTour", value: user.products.balletour ? "Tilgang" : "Ingen tilgang")
                }
            }

            Section("Tilkobling") {
                LabeledContent("Server", value: session.baseURLText)
                if let version = session.bootstrap?.version {
                    LabeledContent("Serverversjon", value: version)
                }
                if let lastConnectionMessage = session.lastConnectionMessage {
                    Text(lastConnectionMessage)
                        .foregroundStyle(.secondary)
                }
            }

            Section {
                Button(role: .destructive) {
                    Task {
                        await session.logout()
                    }
                } label: {
                    Label("Logg ut", systemImage: "rectangle.portrait.and.arrow.right")
                }
            }
        }
        .navigationTitle("Profil")
    }
}

#Preview {
    DashboardView()
        .environmentObject(SessionStore())
}
