import SwiftUI

struct ProductOverviewView: View {
    @EnvironmentObject private var session: SessionStore
    let productID: String
    let title: String

    @State private var overview: OverviewResponse?
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        List {
            if isLoading {
                ProgressView()
            }

            if let errorMessage {
                Text(errorMessage)
                    .foregroundStyle(.red)
            }

            if productID == "shanklife" {
                shanklifeContent
            } else {
                balletourContent
            }
        }
        .navigationTitle(title)
        .task {
            await load()
        }
        .refreshable {
            await load()
        }
    }

    private var shanklifeContent: some View {
        Group {
            Section("Oversikt") {
                LabeledContent("Baner", value: "\(overview?.courseCount ?? 0)")
                LabeledContent("Siste runder", value: "\(overview?.recentRounds?.count ?? 0)")
            }

            Section("Runder") {
                let rounds = overview?.recentRounds ?? []
                if rounds.isEmpty && !isLoading {
                    Text("Ingen runder funnet.")
                        .foregroundStyle(.secondary)
                }

                ForEach(rounds) { round in
                    let playerNames = round.players.map(\.name).joined(separator: ", ")
                    VStack(alignment: .leading, spacing: 4) {
                        Text(round.course?.name ?? "Ukjent bane")
                            .font(.headline)
                        Text(playerNames.isEmpty ? round.status : playerNames)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        if let startedAt = round.startedAt {
                            Text(startedAt)
                                .font(.caption)
                                .foregroundStyle(.tertiary)
                        }
                    }
                }
            }
        }
    }

    private var balletourContent: some View {
        Group {
            if overview?.enabled == false {
                Section {
                    Text("Denne brukeren har ikke BalleTour-tilgang.")
                        .foregroundStyle(.secondary)
                }
            }

            Section("Spillere") {
                let players = overview?.players ?? []
                if players.isEmpty && !isLoading {
                    Text("Ingen spillere funnet.")
                        .foregroundStyle(.secondary)
                }

                ForEach(players) { player in
                    Text(player.name)
                }
            }
        }
    }

    private func load() async {
        guard let client = session.client else {
            errorMessage = "Ugyldig serveradresse."
            return
        }

        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            if productID == "shanklife" {
                overview = try await client.shanklifeOverview()
            } else {
                overview = try await client.balletourOverview()
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

#Preview {
    ProductOverviewView(productID: "shanklife", title: "Shanklife Pro")
        .environmentObject(SessionStore())
}
