import SwiftUI

struct ShanklifeView: View {
    @EnvironmentObject private var session: SessionStore
    @State private var rounds: [ShanklifeRoundListItem] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        List {
            if isLoading {
                ProgressView("Laster Shanklife")
            }

            if let errorMessage {
                Text(errorMessage)
                    .foregroundStyle(.red)
            }

            Section {
                NavigationLink {
                    ShanklifeNewRoundView()
                        .environmentObject(session)
                } label: {
                    Label("Ny runde", systemImage: "plus.circle.fill")
                }

                NavigationLink {
                    ShanklifeCoursesView()
                        .environmentObject(session)
                } label: {
                    Label("Baner", systemImage: "map")
                }
            }

            Section("Pågående") {
                let ongoing = rounds.filter { $0.status == "ongoing" }
                if ongoing.isEmpty && !isLoading {
                    Text("Ingen pågående runder.")
                        .foregroundStyle(.secondary)
                }
                ForEach(ongoing) { round in
                    NavigationLink {
                        ShanklifeScoringLoaderView(roundID: round.id)
                            .environmentObject(session)
                    } label: {
                        shanklifeRoundRow(round)
                    }
                }
            }

            Section("Siste runder") {
                let finished = rounds.filter { $0.status == "finished" }
                if finished.isEmpty && !isLoading {
                    Text("Ingen fullførte runder.")
                        .foregroundStyle(.secondary)
                }
                ForEach(finished) { round in
                    NavigationLink {
                        ShanklifeScoringLoaderView(roundID: round.id)
                            .environmentObject(session)
                    } label: {
                        shanklifeRoundRow(round)
                    }
                }
            }
        }
        .navigationTitle("Shanklife")
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                NavigationLink {
                    ShanklifeNewRoundView()
                        .environmentObject(session)
                } label: {
                    Image(systemName: "plus")
                }
                Button {
                    Task { await load() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
            }
        }
        .task { await load() }
        .refreshable { await load() }
    }

    private func shanklifeRoundRow(_ round: ShanklifeRoundListItem) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(round.course)
                    .font(.headline)
                Spacer()
                Text(round.status == "finished" ? "Ferdig" : "Pågår")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(round.status == "finished" ? Color.secondary : Color.green)
            }
            Text(round.players.map(\.name).joined(separator: ", "))
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text(round.startedAtDisplay ?? round.startedAt ?? "Ukjent start")
                .font(.caption)
                .foregroundStyle(.tertiary)
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
            rounds = try await client.shanklifeRounds(status: "all").rounds
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct ShanklifeNewRoundView: View {
    @EnvironmentObject private var session: SessionStore
    @State private var setup: ShanklifeSetupResponse?
    @State private var selectedCourseID: Int?
    @State private var playedHoleCount = 18
    @State private var selectedPlayers: [ShanklifeCreateRoundPlayer] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var createdRound: ShanklifeRoundNavigation?

    var body: some View {
        Form {
            if let setup {
                Section("Bane") {
                    Picker("Bane", selection: courseSelection) {
                        ForEach(setup.courses) { course in
                            Text(course.name).tag(Optional(course.id))
                        }
                    }

                    if let course = selectedCourse(setup) {
                        Picker("Hull", selection: $playedHoleCount) {
                            Text("\(course.holeCount)").tag(course.holeCount)
                            if course.supportsNineHoleRound {
                                Text("9").tag(9)
                            }
                        }
                    }
                }

                Section("Spillere") {
                    ForEach(selectedPlayers.indices, id: \.self) { index in
                        playerRow(setup: setup, index: index)
                    }
                    .onDelete { selectedPlayers.remove(atOffsets: $0) }

                    Button {
                        addPlayer(setup)
                    } label: {
                        Label("Legg til spiller", systemImage: "person.badge.plus")
                    }
                    .disabled(selectedPlayers.count >= setup.maxPlayers)
                }

                Section {
                    Button {
                        Task { await createRound() }
                    } label: {
                        if isLoading {
                            ProgressView()
                        } else {
                            Label("Start runde", systemImage: "figure.golf")
                        }
                    }
                    .disabled(isLoading || selectedCourseID == nil || selectedPlayers.isEmpty)
                }
            } else if isLoading {
                ProgressView("Laster")
            }

            if let errorMessage {
                Section {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                }
            }
        }
        .navigationTitle("Ny Shanklife-runde")
        .task { await load() }
        .navigationDestination(item: $createdRound) { destination in
            ShanklifeScoringLoaderView(roundID: destination.id)
                .environmentObject(session)
        }
    }

    private var courseSelection: Binding<Int?> {
        Binding(
            get: { selectedCourseID },
            set: { newValue in
                selectedCourseID = newValue
                if let setup, let course = selectedCourse(setup) {
                    playedHoleCount = course.holeCount
                    normalizeTees(for: course)
                }
            }
        )
    }

    private func selectedCourse(_ setup: ShanklifeSetupResponse) -> ShanklifeCourse? {
        setup.courses.first { $0.id == selectedCourseID }
    }

    private func playerRow(setup: ShanklifeSetupResponse, index: Int) -> some View {
        let playerBinding = Binding(
            get: { selectedPlayers[index] },
            set: { selectedPlayers[index] = $0 }
        )

        return VStack(alignment: .leading, spacing: 10) {
            Picker("Spiller", selection: Binding(
                get: { selectedPlayers[index].playerID ?? 0 },
                set: { newValue in
                    if let player = setup.players.first(where: { $0.id == newValue }) {
                        selectedPlayers[index].playerID = player.id
                        selectedPlayers[index].newPlayerName = nil
                        selectedPlayers[index].hcp = player.defaultHcp ?? 0
                    }
                }
            )) {
                ForEach(setup.players) { player in
                    Text(player.displayName ?? player.name).tag(player.id)
                }
            }

            HStack {
                TextField("HCP", value: playerBinding.hcp, format: .number)
                    .keyboardType(.decimalPad)
                if let course = selectedCourse(setup) {
                    Picker("Tee", selection: playerBinding.teeID) {
                        ForEach(course.tees) { tee in
                            Text(tee.name).tag(tee.id)
                        }
                    }
                }
            }

            Toggle("Før statistikk", isOn: playerBinding.tracksStats)
        }
        .padding(.vertical, 3)
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
            let loaded = try await client.shanklifeSetup()
            setup = loaded
            selectedCourseID = loaded.courses.first?.id
            if let course = loaded.courses.first {
                playedHoleCount = course.holeCount
            }
            selectedPlayers = []
            if let currentPlayerID = session.user?.player?.id,
               let player = loaded.players.first(where: { $0.id == currentPlayerID }),
               let tee = loaded.courses.first?.tees.first {
                selectedPlayers = [
                    ShanklifeCreateRoundPlayer(
                        playerID: player.id,
                        hcp: player.defaultHcp ?? 0,
                        teeID: tee.id,
                        tracksStats: true
                    )
                ]
            } else {
                addPlayer(loaded)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func addPlayer(_ setup: ShanklifeSetupResponse) {
        guard let player = setup.players.first(where: { candidate in
            !selectedPlayers.contains(where: { $0.playerID == candidate.id })
        }), let teeID = selectedCourse(setup)?.tees.first?.id else {
            return
        }
        selectedPlayers.append(
            ShanklifeCreateRoundPlayer(
                playerID: player.id,
                hcp: player.defaultHcp ?? 0,
                teeID: teeID,
                tracksStats: selectedPlayers.isEmpty
            )
        )
    }

    private func normalizeTees(for course: ShanklifeCourse) {
        guard let firstTee = course.tees.first else { return }
        let validTeeIDs = Set(course.tees.map(\.id))
        for index in selectedPlayers.indices where !validTeeIDs.contains(selectedPlayers[index].teeID) {
            selectedPlayers[index].teeID = firstTee.id
        }
    }

    private func createRound() async {
        guard let client = session.client, let selectedCourseID else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let round = try await client.createShanklifeRound(
                ShanklifeCreateRoundRequest(
                    courseID: selectedCourseID,
                    playedHoleCount: playedHoleCount,
                    players: selectedPlayers
                )
            )
            createdRound = ShanklifeRoundNavigation(id: round.id)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct ShanklifeRoundNavigation: Hashable, Identifiable {
    let id: Int
}

private extension Binding where Value == ShanklifeCreateRoundPlayer {
    var hcp: Binding<Double> {
        Binding<Double>(
            get: { wrappedValue.hcp },
            set: { wrappedValue.hcp = $0 }
        )
    }

    var teeID: Binding<Int> {
        Binding<Int>(
            get: { wrappedValue.teeID },
            set: { wrappedValue.teeID = $0 }
        )
    }

    var tracksStats: Binding<Bool> {
        Binding<Bool>(
            get: { wrappedValue.tracksStats },
            set: { wrappedValue.tracksStats = $0 }
        )
    }
}
