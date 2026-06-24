import SwiftUI

struct BalleTourStatsView: View {
    @EnvironmentObject private var session: SessionStore
    let tee: String

    @State private var stats: BalleTourStatsResponse?
    @State private var allStats: BalleTourAllStatsResponse?
    @State private var selectedPlayerID: Int?
    @State private var selectedHole: Int?
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        List {
            if isLoading && stats == nil {
                ProgressView("Laster statistikk")
            }

            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                }
            }

            if let stats {
                playerPicker(stats)
                playerStatsSection(stats.stats)
                strokesGainedSection(stats.stats.strokesGained)
                greenMapSection(stats.stats)
                clubSection(stats.stats.clubRows ?? [])
            }

            if let allStats {
                allStatsSection(allStats.rows)
            }
        }
        .navigationTitle("BalleTour-statistikk")
        .task {
            await load()
        }
        .refreshable {
            await load()
        }
    }

    private func playerPicker(_ response: BalleTourStatsResponse) -> some View {
        Section {
            Picker("Spiller", selection: Binding(
                get: { selectedPlayerID ?? response.stats.selectedPlayer?.id ?? response.players.first?.id },
                set: { newValue in
                    selectedPlayerID = newValue
                    Task { await load() }
                }
            )) {
                ForEach(response.players) { player in
                    Text(player.displayName).tag(Int?.some(player.id))
                }
            }

            Picker("Hull", selection: Binding(
                get: { selectedHole },
                set: { newValue in
                    selectedHole = newValue
                    Task { await load() }
                }
            )) {
                Text("Alle hull").tag(Int?.none)
                ForEach(1...9, id: \.self) { hole in
                    Text("Hull \(hole)").tag(Int?.some(hole))
                }
            }
        }
    }

    private func playerStatsSection(_ stats: BalleTourDetailedStats) -> some View {
        Section(stats.selectedPlayer?.displayName ?? "Spiller") {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                statTile("Runder", "\(stats.completedRoundCount ?? 0)", "flag.checkered")
                statTile("Snitt", optionalNumber(stats.avgRound, digits: 1), "chart.line.uptrend.xyaxis")
                statTile("Beste", stats.bestRound.map(String.init) ?? "-", "star")
                statTile("Beste par", parText(stats.bestRoundVsPar), "plus.forwardslash.minus")
                statTile("Birdie+", "\(stats.birdiesOrBetter ?? 0)", "circle")
                statTile("Bogey+", "\(stats.bogeysOrWorse ?? 0)", "exclamationmark.circle")
                statTile("Greentreff", optionalPercent(stats.greenHitPercent), "scope")
                statTile("Putts", optionalNumber(stats.avgPutts, digits: 2), "circle.grid.cross")
            }
            .padding(.vertical, 4)
        }
    }

    private func strokesGainedSection(_ sg: BalleTourStrokesGained?) -> some View {
        Section("Strokes gained") {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                statTile("Total", signed(sg?.total), "sum")
                statTile("Før putting", signed(sg?.teeToGreen), "figure.golf")
                statTile("Putting", signed(sg?.putting), "smallcircle.filled.circle")
                statTile("Green", signed(sg?.greenResult), "scope")
            }
            Text(sg?.unitLabel ?? "per runde")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private func greenMapSection(_ stats: BalleTourDetailedStats) -> some View {
        Section("Greenmønster") {
            ZStack {
                RoundedRectangle(cornerRadius: 140)
                    .fill(
                        RadialGradient(
                            colors: [Color.green.opacity(0.28), Color.green.opacity(0.14)],
                            center: .center,
                            startRadius: 10,
                            endRadius: 160
                        )
                    )
                    .frame(height: 240)
                Circle()
                    .stroke(Color.primary.opacity(0.2), lineWidth: 1)
                    .frame(width: 24, height: 24)
                ForEach(stats.greenPoints ?? []) { point in
                    Circle()
                        .fill(pointColor(point.status))
                        .frame(width: 9, height: 9)
                        .position(x: CGFloat(point.x / 100) * 300, y: CGFloat(point.y / 100) * 220 + 10)
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 250)

            ForEach(stats.greenDistribution ?? []) { row in
                LabeledContent(row.label, value: "\(row.count) · \(optionalPercent(row.percent))")
            }
        }
    }

    private func clubSection(_ clubs: [BalleTourClubStats]) -> some View {
        Section("Køllebruk") {
            if clubs.isEmpty {
                Text("Ingen kølledata.")
                    .foregroundStyle(.secondary)
            }
            ForEach(clubs) { club in
                LabeledContent(club.name, value: "\(club.count) slag · snitt \(number(club.avg, digits: 2))")
            }
        }
    }

    private func allStatsSection(_ rows: [BalleTourAllStatsRow]) -> some View {
        Section("Samlet statistikk") {
            ForEach(rows) { row in
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(row.player.displayName)
                            .font(.headline)
                        Spacer()
                        Text(optionalNumber(row.avgRound, digits: 1))
                            .font(.headline.monospacedDigit())
                    }
                    HStack(spacing: 10) {
                        mini("R", "\(row.completedRoundCount ?? 0)")
                        mini("GIR", optionalPercent(row.greenHitPercent))
                        mini("P", optionalNumber(row.avgPutts, digits: 2))
                        mini("SG", signed(row.strokesGained?.total))
                    }
                }
                .padding(.vertical, 4)
            }
        }
    }

    private func statTile(_ title: String, _ value: String, _ systemImage: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Label(title, systemImage: systemImage)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.headline.monospacedDigit())
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func mini(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.monospacedDigit())
        }
        .frame(maxWidth: .infinity, alignment: .leading)
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
            async let statsResponse = client.balletourStats(tee: tee, playerID: selectedPlayerID, hole: selectedHole)
            async let allStatsResponse = client.balletourAllStats(tee: tee)
            stats = try await statsResponse
            allStats = try await allStatsResponse
            if selectedPlayerID == nil {
                selectedPlayerID = stats?.stats.selectedPlayer?.id
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private func pointColor(_ status: String) -> Color {
    switch status {
    case "hit": .green
    case "bunker": .orange
    default: .red
    }
}

private func signed(_ value: Double?) -> String {
    guard let value else { return "-" }
    if value > 0 { return "+\(number(value, digits: 2))" }
    return number(value, digits: 2)
}

private func parText(_ value: Int?) -> String {
    guard let value else { return "-" }
    if value == 0 { return "E" }
    if value > 0 { return "+\(value)" }
    return "\(value)"
}

private func number(_ value: Double, digits: Int) -> String {
    value.formatted(.number.precision(.fractionLength(digits)))
}

private func optionalNumber(_ value: Double?, digits: Int) -> String {
    value.map { number($0, digits: digits) } ?? "-"
}

private func optionalPercent(_ value: Double?) -> String {
    value.map { "\(number($0, digits: 1))%" } ?? "-"
}
