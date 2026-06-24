import SwiftUI

struct BalleTourScoringLoaderView: View {
    @EnvironmentObject private var session: SessionStore
    let roundID: Int

    @State private var detail: BalleTourRoundDetail?
    @State private var setup: BalleTourRoundSetup?
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        Group {
            if let detail {
                BalleTourScoringView(initialDetail: detail, setup: setup)
                    .environmentObject(session)
            } else {
                List {
                    if isLoading {
                        ProgressView("Laster runde")
                    }
                    if let errorMessage {
                        Label(errorMessage, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                    }
                }
                .navigationTitle("Runde #\(roundID)")
            }
        }
        .task {
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
            async let detailResponse = client.balletourRoundDetail(roundID: roundID)
            async let setupResponse = client.balletourRoundSetup()
            detail = try await detailResponse
            setup = try await setupResponse
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct BalleTourNewRoundView: View {
    @EnvironmentObject private var session: SessionStore
    @Environment(\.dismiss) private var dismiss

    @State private var setup: BalleTourRoundSetup?
    @State private var selectedPlayers: [BalleTourCreateRoundPlayer] = []
    @State private var createdRoundID: Int?
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        List {
            if isLoading && setup == nil {
                ProgressView("Laster rundeoppsett")
            }

            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                }
            }

            if let setup {
                Section("Bane") {
                    LabeledContent("Bane", value: setup.course.name)
                    LabeledContent("Hull", value: "\(setup.course.holeCount)")
                    LabeledContent("Par", value: "\(setup.course.par)")
                    if let weather = setup.weatherSummary, !weather.isEmpty {
                        LabeledContent("Vær", value: weather)
                    }
                }

                Section("Spillere") {
                    ForEach($selectedPlayers) { $selection in
                        playerPicker(setup: setup, selection: $selection)
                    }

                    if selectedPlayers.count < setup.maxPlayers {
                        Button {
                            addPlayer(from: setup)
                        } label: {
                            Label("Legg til spiller", systemImage: "plus.circle")
                        }
                    }
                }

                Section {
                    Button {
                        Task { await createRound() }
                    } label: {
                        Label("Start runde", systemImage: "flag.checkered")
                    }
                    .disabled(isLoading || selectedPlayers.isEmpty)
                }
            }
        }
        .navigationTitle("Ny BalleTour-runde")
        .task {
            await load()
        }
        .navigationDestination(item: $createdRoundID) { roundID in
            BalleTourScoringLoaderView(roundID: roundID)
                .environmentObject(session)
        }
    }

    private func playerPicker(setup: BalleTourRoundSetup, selection: Binding<BalleTourCreateRoundPlayer>) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Picker("Spiller", selection: selection.playerID) {
                ForEach(setup.players) { player in
                    Text(player.displayName ?? player.name).tag(player.id)
                }
            }

            HStack {
                Text("HCP")
                    .foregroundStyle(.secondary)
                TextField("HCP", value: selection.hcp, format: .number.precision(.fractionLength(1)))
                    .keyboardType(.decimalPad)
                    .multilineTextAlignment(.trailing)
            }

            Picker("Tee", selection: selection.teeID) {
                ForEach(setup.tees) { tee in
                    Text(tee.name).tag(tee.id)
                }
            }
        }
        .padding(.vertical, 4)
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
            let setup = try await client.balletourRoundSetup()
            self.setup = setup
            if selectedPlayers.isEmpty {
                if let currentPlayerID = session.user?.player?.id,
                   let player = setup.players.first(where: { $0.id == currentPlayerID }),
                   let tee = setup.tees.first(where: { $0.name.localizedCaseInsensitiveContains("gul") }) ?? setup.tees.first {
                    selectedPlayers = [
                        BalleTourCreateRoundPlayer(playerID: player.id, hcp: player.defaultHcp ?? 0, teeID: tee.id)
                    ]
                } else {
                    addPlayer(from: setup)
                }
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func addPlayer(from setup: BalleTourRoundSetup) {
        guard let tee = setup.tees.first(where: { $0.name.localizedCaseInsensitiveContains("gul") }) ?? setup.tees.first else {
            return
        }
        let usedIDs = Set(selectedPlayers.map(\.playerID))
        guard let player = setup.players.first(where: { !usedIDs.contains($0.id) }) else {
            return
        }
        selectedPlayers.append(BalleTourCreateRoundPlayer(playerID: player.id, hcp: player.defaultHcp ?? 0, teeID: tee.id))
    }

    private func createRound() async {
        guard let client = session.client else {
            errorMessage = "Ugyldig serveradresse."
            return
        }

        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let round = try await client.createBalleTourRound(BalleTourCreateRoundRequest(players: selectedPlayers))
            createdRoundID = round.id
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct BalleTourScoringView: View {
    @EnvironmentObject private var session: SessionStore

    let initialDetail: BalleTourRoundDetail
    let setup: BalleTourRoundSetup?

    @State private var detail: BalleTourRoundDetail
    @State private var activeSetup: BalleTourRoundSetup?
    @State private var currentHoleNumber = 1
    @State private var inputs: [Int: BalleTourHolePlayerInput] = [:]
    @State private var isSaving = false
    @State private var errorMessage: String?
    @State private var finishMessage: String?

    init(initialDetail: BalleTourRoundDetail, setup: BalleTourRoundSetup?) {
        self.initialDetail = initialDetail
        self.setup = setup
        _detail = State(initialValue: initialDetail)
        _activeSetup = State(initialValue: setup)
    }

    var body: some View {
        List {
            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                }
            }

            if let finishMessage {
                Section {
                    Label(finishMessage, systemImage: "checkmark.circle")
                        .foregroundStyle(.green)
                }
            }

            holeHeader
            playerInputs
            actionButtons
            scorecardSection
        }
        .navigationTitle("Runde #\(detail.id)")
        .onAppear {
            currentHoleNumber = nextPlayableHole()
            loadInputsForCurrentHole()
            Task { await loadSetupIfNeeded() }
        }
        .onChange(of: currentHoleNumber) { _, _ in
            loadInputsForCurrentHole()
        }
    }

    private var currentHole: BalleTourSetupHole? {
        activeSetup?.holes.first(where: { $0.holeNumber == currentHoleNumber })
    }

    private var holeHeader: some View {
        Section {
            HStack(spacing: 14) {
                metric("Hull", "\(currentHoleNumber)", systemImage: "flag")
                metric("Par", "\(currentHole?.par ?? currentScoreFallback?.par ?? 0)", systemImage: "target")
                metric("Index", "\(currentHole?.strokeIndex ?? currentScoreFallback?.strokeIndex ?? 0)", systemImage: "number")
            }
            if detail.status == "finished" {
                Text("Runden er fullført.")
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var currentScoreFallback: BalleTourHoleScore? {
        detail.players.first?.scores.first(where: { $0.holeNumber == currentHoleNumber })
    }

    private var playerInputs: some View {
        Section("Score og statistikk") {
            ForEach(detail.players) { player in
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        VStack(alignment: .leading) {
                            Text(player.name)
                                .font(.headline)
                            Text("\(player.tee ?? "-") · HCP \(number(player.hcp, digits: 1))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        scoreChip(player.scores.first(where: { $0.holeNumber == currentHoleNumber })?.strokes, par: currentHole?.par ?? currentScoreFallback?.par)
                    }

                    Picker("Score", selection: binding(for: player.roundPlayerID).strokes) {
                        Text("-").tag(Int?.none)
                        ForEach(currentHole?.scoreOptions ?? scoreOptions(par: currentScoreFallback?.par ?? 3), id: \.self) { score in
                            Text("\(score)").tag(Int?.some(score))
                        }
                    }
                    .pickerStyle(.segmented)

                    Picker("Kølle", selection: binding(for: player.roundPlayerID).teeClubID) {
                        Text("-").tag(Int?.none)
                        ForEach(activeSetup?.clubs ?? []) { club in
                            Text(club.name).tag(Int?.some(club.id))
                        }
                    }

                    Picker("Utslagslengde", selection: binding(for: player.roundPlayerID).driveDistanceM) {
                        Text("-").tag(Int?.none)
                        ForEach(activeSetup?.driveDistanceOptions ?? defaultDriveOptions, id: \.self) { distance in
                            Text("\(distance)m").tag(Int?.some(distance))
                        }
                    }

                    if (currentHole?.par ?? currentScoreFallback?.par ?? 3) == 3 {
                        greenControls(for: player)
                    } else {
                        Picker("Fairway", selection: binding(for: player.roundPlayerID).fairwayResult) {
                            Text("-").tag(String?.none)
                            Text("Traff").tag(String?.some("hit"))
                            Text("Høyre").tag(String?.some("right"))
                            Text("Venstre").tag(String?.some("left"))
                        }
                        .pickerStyle(.segmented)
                    }

                    HStack {
                        Picker("Putts", selection: binding(for: player.roundPlayerID).putts) {
                            Text("-").tag(Int?.none)
                            ForEach(activeSetup?.puttOptions ?? [0, 1, 2, 3, 4, 5], id: \.self) { putts in
                                Text("\(putts)").tag(Int?.some(putts))
                            }
                        }
                        Picker("Siste putt", selection: binding(for: player.roundPlayerID).lastPuttDistanceM) {
                            Text("-").tag(Double?.none)
                            ForEach(activeSetup?.lastPuttDistanceOptions ?? defaultLastPuttOptions, id: \.self) { distance in
                                Text("\(number(distance, digits: 1))m").tag(Double?.some(distance))
                            }
                        }
                    }
                }
                .padding(.vertical, 6)
                .disabled(detail.status == "finished" || isSaving)
            }
        }
    }

    private func greenControls(for player: BalleTourRoundDetailPlayer) -> some View {
        let input = binding(for: player.roundPlayerID)
        return VStack(alignment: .leading, spacing: 8) {
            Picker("Green", selection: greenStatusBinding(input)) {
                Text("Treff").tag("hit")
                Text("Miss").tag("miss")
                Text("Bunker").tag("bunker")
            }
            .pickerStyle(.segmented)

            Picker("Retning", selection: greenHorizontalBinding(input)) {
                Text("Flagg").tag("pin")
                Text("Venstre").tag("left")
                Text("Høyre").tag("right")
            }
            .pickerStyle(.segmented)

            Picker("Lengde", selection: greenVerticalBinding(input)) {
                Text("Pin high").tag("")
                Text("Kort").tag("short")
                Text("Lang").tag("long")
            }
            .pickerStyle(.segmented)
        }
    }

    private var actionButtons: some View {
        Section {
            HStack {
                Button {
                    moveHole(-1)
                } label: {
                    Label("Forrige", systemImage: "chevron.left")
                }
                .disabled(currentHoleNumber == 1 || isSaving)

                Spacer()

                Button {
                    Task { await saveHole(move: 1) }
                } label: {
                    Label(currentHoleNumber == detail.course.holeCount ? "Lagre" : "Neste", systemImage: "chevron.right")
                }
                .disabled(detail.status == "finished" || isSaving)
            }

            Button(role: .destructive) {
                Task { await finishRound() }
            } label: {
                Label("Fullfør runde", systemImage: "checkmark.seal")
            }
            .disabled(detail.status == "finished" || isSaving)
        }
    }

    private var scorecardSection: some View {
        Section("Scorekort") {
            ForEach(detail.players) { player in
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(player.name)
                            .font(.headline)
                        Spacer()
                        Text("\(player.totalStrokes.map(String.init) ?? "-") · \(player.toParDisplay)")
                            .font(.headline.monospacedDigit())
                    }

                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 3), spacing: 6) {
                        ForEach(player.scores) { score in
                            Button {
                                currentHoleNumber = score.holeNumber
                            } label: {
                                VStack(spacing: 3) {
                                    Text("\(score.holeNumber)")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                    scoreChip(score.strokes, par: score.par)
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 6)
                                .background(score.holeNumber == currentHoleNumber ? Color.accentColor.opacity(0.12) : Color.secondary.opacity(0.08))
                                .clipShape(RoundedRectangle(cornerRadius: 6))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .padding(.vertical, 6)
            }
        }
    }

    private func binding(for roundPlayerID: Int) -> Binding<BalleTourHolePlayerInput> {
        Binding(
            get: {
                inputs[roundPlayerID] ?? BalleTourHolePlayerInput(roundPlayerID: roundPlayerID)
            },
            set: { newValue in
                inputs[roundPlayerID] = newValue
            }
        )
    }

    private func loadInputsForCurrentHole() {
        var nextInputs: [Int: BalleTourHolePlayerInput] = [:]
        for player in detail.players {
            let score = player.scores.first(where: { $0.holeNumber == currentHoleNumber })
            let green = greenInput(from: score)
            nextInputs[player.roundPlayerID] = BalleTourHolePlayerInput(
                roundPlayerID: player.roundPlayerID,
                strokes: score?.strokes,
                teeClubID: score?.teeClubID,
                driveDistanceM: score?.driveDistanceM,
                green: green,
                fairwayResult: score?.greenResult,
                putts: score?.putts,
                lastPuttDistanceM: score?.lastPuttDistanceM
            )
        }
        inputs = nextInputs
    }

    private func greenInput(from score: BalleTourHoleScore?) -> BalleTourGreenInput? {
        guard let raw = score?.greenResult else {
            return BalleTourGreenInput(status: "hit", directions: ["pin"])
        }
        let parts = raw.split(separator: ":", maxSplits: 1).map(String.init)
        if parts.count == 2 {
            return BalleTourGreenInput(status: parts[0], directions: parts[1].split(separator: ",").map(String.init))
        }
        return BalleTourGreenInput(status: raw, directions: raw == "hit" ? ["pin"] : [])
    }

    private func saveHole(move: Int = 0) async {
        guard let client = session.client else {
            errorMessage = "Ugyldig serveradresse."
            return
        }

        isSaving = true
        errorMessage = nil
        defer { isSaving = false }

        do {
            let request = BalleTourSaveHoleRequest(players: detail.players.map { player in
                inputs[player.roundPlayerID] ?? BalleTourHolePlayerInput(roundPlayerID: player.roundPlayerID)
            })
            detail = try await client.saveBalleTourHole(roundID: detail.id, holeNumber: currentHoleNumber, body: request)
            if move != 0 {
                moveHole(move)
            } else {
                loadInputsForCurrentHole()
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func loadSetupIfNeeded() async {
        guard activeSetup == nil, let client = session.client else {
            return
        }
        do {
            activeSetup = try await client.balletourRoundSetup()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func finishRound() async {
        await saveHole()
        guard errorMessage == nil, let client = session.client else {
            return
        }

        isSaving = true
        defer { isSaving = false }

        do {
            detail = try await client.finishBalleTourRound(roundID: detail.id)
            finishMessage = "Runden er fullført."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func moveHole(_ delta: Int) {
        currentHoleNumber = min(max(currentHoleNumber + delta, 1), detail.course.holeCount)
    }

    private func nextPlayableHole() -> Int {
        for score in detail.players.first?.scores ?? [] where score.strokes == nil {
            return score.holeNumber
        }
        return 1
    }

    private func metric(_ title: String, _ value: String, systemImage: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Label(title, systemImage: systemImage)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.headline.monospacedDigit())
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private func scoreOptions(par: Int) -> [Int] {
    switch par {
    case 3: Array(1...9)
    case 4: Array(2...9)
    case 5: Array(3...10)
    default: Array(1...12)
    }
}

private let defaultDriveOptions = Array(stride(from: 25, through: 400, by: 5))
private let defaultLastPuttOptions = (1...150).map { Double($0) / 10.0 }

private func scoreChip(_ score: Int?, par: Int?) -> some View {
    let diff = score.flatMap { value in par.map { value - $0 } }
    let text = score.map(String.init) ?? "-"
    let color: Color = {
        guard let diff else { return .secondary }
        if diff < 0 { return .green }
        if diff == 0 { return .primary }
        if diff == 1 { return .orange }
        return .red
    }()

    return Text(text)
        .font(.headline.monospacedDigit())
        .frame(width: 34, height: 34)
        .foregroundStyle(color)
        .background(color.opacity(diff == 0 ? 0.08 : 0.14))
        .clipShape(RoundedRectangle(cornerRadius: diff.map { $0 < 0 ? 17 : 6 } ?? 6))
}

private func greenStatusBinding(_ input: Binding<BalleTourHolePlayerInput>) -> Binding<String> {
    Binding(
        get: { input.wrappedValue.green?.status ?? "hit" },
        set: { newValue in
            var value = input.wrappedValue
            var green = value.green ?? BalleTourGreenInput(status: "hit", directions: ["pin"])
            green.status = newValue
            value.green = green
            input.wrappedValue = value
        }
    )
}

private func greenHorizontalBinding(_ input: Binding<BalleTourHolePlayerInput>) -> Binding<String> {
    Binding(
        get: {
            let directions = input.wrappedValue.green?.directions ?? ["pin"]
            if directions.contains("left") { return "left" }
            if directions.contains("right") { return "right" }
            return "pin"
        },
        set: { newValue in
            var value = input.wrappedValue
            var green = value.green ?? BalleTourGreenInput(status: "hit", directions: [])
            green.directions.removeAll(where: { ["pin", "left", "right"].contains($0) })
            green.directions.append(newValue)
            value.green = green
            input.wrappedValue = value
        }
    )
}

private func greenVerticalBinding(_ input: Binding<BalleTourHolePlayerInput>) -> Binding<String> {
    Binding(
        get: {
            let directions = input.wrappedValue.green?.directions ?? []
            if directions.contains("short") { return "short" }
            if directions.contains("long") { return "long" }
            return ""
        },
        set: { newValue in
            var value = input.wrappedValue
            var green = value.green ?? BalleTourGreenInput(status: "hit", directions: ["pin"])
            green.directions.removeAll(where: { ["short", "long"].contains($0) })
            if !newValue.isEmpty {
                green.directions.append(newValue)
            }
            value.green = green
            input.wrappedValue = value
        }
    )
}

private func number(_ value: Double, digits: Int) -> String {
    value.formatted(.number.precision(.fractionLength(digits)))
}
