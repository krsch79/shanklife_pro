import SwiftUI

struct BalleTourView: View {
    @EnvironmentObject private var session: SessionStore

    @State private var selectedTee = "gul"
    @State private var overview: BalleTourOverviewResponse?
    @State private var players: [BalleTourPlayer] = []
    @State private var finishedRounds: [BalleTourRoundListItem] = []
    @State private var ongoingRounds: [BalleTourRoundListItem] = []
    @State private var mySummary: BalleTourPlayerSummaryResponse?
    @State private var selectedSection = BalleTourSection.leaderboard
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        List {
            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                }
            }

            if isLoading && overview == nil {
                Section {
                    ProgressView("Laster BalleTour")
                }
            }

            if let overview {
                overviewSection(overview)
                teeSection(overview)
                sectionPicker

                switch selectedSection {
                case .leaderboard:
                    leaderboardSection(overview)
                case .rounds:
                    roundsSection
                case .players:
                    playersSection
                case .me:
                    meSection
                }
            }
        }
        .navigationTitle("BalleTour")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task { await load() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(isLoading)
                .accessibilityLabel("Oppdater")
            }
        }
        .task {
            await load()
        }
        .refreshable {
            await load()
        }
    }

    private func overviewSection(_ overview: BalleTourOverviewResponse) -> some View {
        Section {
            VStack(alignment: .leading, spacing: 12) {
                Text(overview.course.name)
                    .font(.headline)

                HStack(spacing: 10) {
                    metric("Spillere", "\(overview.playerCount)", systemImage: "person.3")
                    metric("Ferdige", "\(overview.finishedRoundCount)", systemImage: "checkmark.circle")
                    metric("Pågår", "\(overview.ongoingRoundCount)", systemImage: "dot.radiowaves.left.and.right")
                }

                Text("Kvalifisering: \(overview.minQualifyingRounds) tellende runder")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.vertical, 4)
        }
    }

    private func teeSection(_ overview: BalleTourOverviewResponse) -> some View {
        Section {
            Picker("Tee", selection: $selectedTee) {
                ForEach(overview.teeOptions) { option in
                    Text(option.label).tag(option.key)
                }
            }
            .pickerStyle(.segmented)
            .onChange(of: selectedTee) { _, _ in
                Task { await load() }
            }
        }
    }

    private var sectionPicker: some View {
        Section {
            Picker("Visning", selection: $selectedSection) {
                ForEach(BalleTourSection.allCases) { section in
                    Label(section.title, systemImage: section.systemImage).tag(section)
                }
            }
            .pickerStyle(.segmented)
        }
    }

    private func leaderboardSection(_ overview: BalleTourOverviewResponse) -> some View {
        Section("Leaderboard") {
            if overview.leaderboard.isEmpty {
                emptyRow("Ingen leaderboard-data ennå.")
            }

            ForEach(overview.leaderboard) { row in
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    Text(row.rank.map(String.init) ?? "-")
                        .font(.headline.monospacedDigit())
                        .frame(width: 32, alignment: .leading)

                    VStack(alignment: .leading, spacing: 3) {
                        Text(row.playerName)
                            .font(.headline)
                        Text("\(row.roundsPlayed) runder\(row.qualified ? "" : " - ikke kvalifisert")")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    VStack(alignment: .trailing, spacing: 3) {
                        Text(row.totalVsParDisplay)
                            .font(.headline.monospacedDigit())
                        Text(row.averageRound.map { "Snitt \(number($0, digits: 1))" } ?? "Ingen snitt")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 4)
            }
        }
    }

    private var roundsSection: some View {
        Group {
            Section("Pågående runder") {
                if ongoingRounds.isEmpty {
                    emptyRow("Ingen pågående runder.")
                }
                ForEach(ongoingRounds) { round in
                    NavigationLink {
                        BalleTourRoundDetailView(roundID: round.id)
                            .environmentObject(session)
                    } label: {
                        roundRow(round)
                    }
                }
            }

            Section("Ferdige runder") {
                if finishedRounds.isEmpty {
                    emptyRow("Ingen ferdige runder.")
                }
                ForEach(finishedRounds) { round in
                    NavigationLink {
                        BalleTourRoundDetailView(roundID: round.id)
                            .environmentObject(session)
                    } label: {
                        roundRow(round)
                    }
                }
            }
        }
    }

    private var playersSection: some View {
        Section("Spillere") {
            if players.isEmpty {
                emptyRow("Ingen spillere funnet.")
            }

            ForEach(players) { player in
                NavigationLink {
                    BalleTourPlayerSummaryView(playerID: player.id, playerName: player.displayName ?? player.name, tee: selectedTee)
                        .environmentObject(session)
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(player.displayName ?? player.name)
                                .font(.headline)
                            Text(player.name)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        if let hcp = player.defaultHcp {
                            Text("HCP \(number(hcp, digits: 1))")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
    }

    private var meSection: some View {
        Section("Min BalleTour") {
            if let mySummary {
                summaryGrid(mySummary)
            } else {
                emptyRow("Ingen personlig statistikk funnet.")
            }
        }
    }

    private func roundRow(_ round: BalleTourRoundListItem) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(round.course)
                    .font(.headline)
                Spacer()
                Text("#\(round.id)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            Text(round.startedAtDisplay ?? round.startedAt ?? "Ukjent starttid")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(round.players.map { "\($0.playerName) \($0.toParDisplay)" }.joined(separator: ", "))
                .font(.subheadline)
                .lineLimit(2)
        }
        .padding(.vertical, 4)
    }

    private func summaryGrid(_ summary: BalleTourPlayerSummaryResponse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(summary.player.displayName)
                .font(.headline)
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                metric("Runder", "\(summary.roundsPlayed)", systemImage: "flag.checkered")
                metric("Ferdige", "\(summary.finishedRounds)", systemImage: "checkmark.circle")
                metric("Snitt", optionalNumber(summary.averageRound, digits: 1), systemImage: "chart.line.uptrend.xyaxis")
                metric("Beste", summary.bestRound.map(String.init) ?? "-", systemImage: "star")
                metric("Putts", optionalNumber(summary.averagePutts, digits: 2), systemImage: "circle.grid.cross")
                metric("GIR", optionalPercent(summary.girPercent), systemImage: "scope")
            }
        }
        .padding(.vertical, 4)
    }

    private func metric(_ title: String, _ value: String, systemImage: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(title, systemImage: systemImage)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.headline.monospacedDigit())
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func emptyRow(_ text: String) -> some View {
        Text(text)
            .foregroundStyle(.secondary)
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
            async let overviewResponse = client.balletourOverview(tee: selectedTee)
            async let playersResponse = client.balletourPlayers()
            async let finishedResponse = client.balletourRounds(status: "finished", tee: selectedTee)
            async let ongoingResponse = client.balletourRounds(status: "ongoing", tee: selectedTee)
            async let meResponse = client.balletourMe(tee: selectedTee)

            overview = try await overviewResponse
            players = try await playersResponse.players
            finishedRounds = try await finishedResponse.rounds
            ongoingRounds = try await ongoingResponse.rounds
            mySummary = try await meResponse
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct BalleTourRoundDetailView: View {
    @EnvironmentObject private var session: SessionStore
    let roundID: Int

    @State private var detail: BalleTourRoundDetail?
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        List {
            if isLoading {
                ProgressView("Laster scorekort")
            }

            if let errorMessage {
                Text(errorMessage)
                    .foregroundStyle(.red)
            }

            if let detail {
                Section("Runde") {
                    LabeledContent("Bane", value: detail.course.name)
                    LabeledContent("Start", value: detail.startedAtDisplay ?? "-")
                    LabeledContent("Status", value: detail.status)
                    LabeledContent("Par", value: "\(detail.course.par)")
                }

                ForEach(detail.players) { player in
                    Section(player.name) {
                        LabeledContent("Tee", value: player.tee ?? "-")
                        LabeledContent("HCP", value: number(player.hcp, digits: 1))
                        LabeledContent("Total", value: player.totalStrokes.map(String.init) ?? "-")
                        LabeledContent("Mot par", value: player.toParDisplay)

                        ForEach(player.scores) { score in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text("Hull \(score.holeNumber)")
                                        .font(.headline)
                                    Spacer()
                                    Text(score.strokes.map(String.init) ?? "-")
                                        .font(.headline.monospacedDigit())
                                }
                                Text("Par \(score.par) · SI \(score.strokeIndex)\(score.lengthMeters.map { " · \($0)m" } ?? "")")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                scoreFacts(score)
                            }
                            .padding(.vertical, 3)
                        }
                    }
                }
            }
        }
        .navigationTitle("Runde #\(roundID)")
        .task {
            await load()
        }
        .refreshable {
            await load()
        }
    }

    private func scoreFacts(_ score: BalleTourHoleScore) -> some View {
        let facts = [
            score.teeClub.map { "Kølle: \($0)" },
            score.driveDistanceM.map { "Lengde: \($0)m" },
            score.greenResult.map { "Green: \($0)" },
            score.putts.map { "Putts: \($0)" },
            score.lastPuttDistanceM.map { "Siste putt: \(number($0, digits: 1))m" },
        ].compactMap { $0 }

        return Text(facts.isEmpty ? "Ingen detaljstatistikk" : facts.joined(separator: " · "))
            .font(.caption)
            .foregroundStyle(.secondary)
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
            detail = try await client.balletourRoundDetail(roundID: roundID)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct BalleTourPlayerSummaryView: View {
    @EnvironmentObject private var session: SessionStore
    let playerID: Int
    let playerName: String
    let tee: String

    @State private var summary: BalleTourPlayerSummaryResponse?
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        List {
            if isLoading {
                ProgressView("Laster spiller")
            }

            if let errorMessage {
                Text(errorMessage)
                    .foregroundStyle(.red)
            }

            if let summary {
                Section("Spiller") {
                    LabeledContent("Navn", value: summary.player.displayName)
                    LabeledContent("HCP", value: number(summary.player.defaultHcp, digits: 1))
                }

                Section("Resultater") {
                    LabeledContent("Runder", value: "\(summary.roundsPlayed)")
                    LabeledContent("Ferdige", value: "\(summary.finishedRounds)")
                    LabeledContent("Snitt", value: optionalNumber(summary.averageRound, digits: 1))
                    LabeledContent("Beste", value: summary.bestRound.map(String.init) ?? "-")
                }

                Section("Statistikk") {
                    LabeledContent("Registrerte hull", value: "\(summary.trackedHoles)")
                    LabeledContent("Putts", value: optionalNumber(summary.averagePutts, digits: 2))
                    LabeledContent("Drive", value: summary.averageDriveDistance.map { "\(number($0, digits: 1))m" } ?? "-")
                    LabeledContent("GIR", value: optionalPercent(summary.girPercent))
                    LabeledContent("Par 3", value: optionalNumber(summary.averagePar3, digits: 2))
                    LabeledContent("Par 4", value: optionalNumber(summary.averagePar4, digits: 2))
                    LabeledContent("Par 5", value: optionalNumber(summary.averagePar5, digits: 2))
                }
            }
        }
        .navigationTitle(playerName)
        .task {
            await load()
        }
        .refreshable {
            await load()
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
            summary = try await client.balletourPlayerSummary(playerID: playerID, tee: tee)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

enum BalleTourSection: String, CaseIterable, Identifiable {
    case leaderboard
    case rounds
    case players
    case me

    var id: String { rawValue }

    var title: String {
        switch self {
        case .leaderboard: "Live"
        case .rounds: "Runder"
        case .players: "Spillere"
        case .me: "Meg"
        }
    }

    var systemImage: String {
        switch self {
        case .leaderboard: "trophy"
        case .rounds: "list.bullet.rectangle"
        case .players: "person.3"
        case .me: "person.crop.circle"
        }
    }
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

#Preview {
    NavigationStack {
        BalleTourView()
            .environmentObject(SessionStore())
    }
}
