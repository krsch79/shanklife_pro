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
                ForEach(overview?.recentRounds ?? []) { round in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(round.course?.name ?? "Ukjent bane")
                            .font(.headline)
                        Text(round.players.map(\.name).joined(separator: ", "))
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
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
                ForEach(overview?.players ?? []) { player in
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
