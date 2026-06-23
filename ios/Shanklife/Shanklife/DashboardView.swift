import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var session: SessionStore

    var body: some View {
        TabView {
            NavigationStack {
                ProductOverviewView(productID: "shanklife", title: "Shanklife Pro")
            }
            .tabItem {
                Label("Shanklife", systemImage: "figure.golf")
            }

            NavigationStack {
                ProductOverviewView(productID: "balletour", title: "BalleTour")
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
