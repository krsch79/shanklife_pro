import SwiftUI

struct ShanklifeScoringLoaderView: View {
    @EnvironmentObject private var session: SessionStore
    let roundID: Int

    @State private var detail: ShanklifeRoundDetail?
    @State private var setup: ShanklifeSetupResponse?
    @State private var errorMessage: String?
    @State private var isLoading = false

    var body: some View {
        Group {
            if let detail {
                ShanklifeScoringView(initialDetail: detail, setup: setup)
                    .environmentObject(session)
            } else if isLoading {
                ProgressView("Laster runde")
            } else if let errorMessage {
                ContentUnavailableView("Kunne ikke laste runden", systemImage: "exclamationmark.triangle", description: Text(errorMessage))
            }
        }
        .task { await load() }
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
            async let detailResponse = client.shanklifeRoundDetail(roundID: roundID)
            async let setupResponse = client.shanklifeSetup()
            detail = try await detailResponse
            setup = try await setupResponse
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct ShanklifeScoringView: View {
    @EnvironmentObject private var session: SessionStore
    let initialDetail: ShanklifeRoundDetail
    let setup: ShanklifeSetupResponse?

    @State private var detail: ShanklifeRoundDetail
    @State private var activeSetup: ShanklifeSetupResponse?
    @State private var currentHoleNumber: Int
    @State private var inputs: [Int: BalleTourHolePlayerInput] = [:]
    @State private var isSaving = false
    @State private var busyMessage = "Lagrer..."
    @State private var errorMessage: String?
    @State private var validationMessage: String?
    @State private var finishMessage: String?

    init(initialDetail: ShanklifeRoundDetail, setup: ShanklifeSetupResponse?) {
        self.initialDetail = initialDetail
        self.setup = setup
        _detail = State(initialValue: initialDetail)
        _activeSetup = State(initialValue: setup)
        let firstOpen = initialDetail.players.flatMap(\.scores).first(where: { $0.strokes == nil })?.holeNumber
        _currentHoleNumber = State(initialValue: firstOpen ?? 1)
    }

    var body: some View {
        List {
            headerSection
            scorecardSection

            if let hole = currentHole {
                Section {
                    Picker("Hull", selection: $currentHoleNumber) {
                        ForEach(holes) { hole in
                            Text("\(hole.holeNumber)").tag(hole.holeNumber)
                        }
                    }
                    .pickerStyle(.segmented)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Hull \(hole.holeNumber)")
                            .font(.title3.bold())
                        Text("Par \(hole.par) · Index \(hole.strokeIndex)")
                            .foregroundStyle(.secondary)
                    }
                }

                ForEach(detail.players) { player in
                    playerSection(player, hole: hole)
                }

                Section {
                    HStack {
                        Button {
                            Task { await saveHole(move: -1) }
                        } label: {
                            Label("Forrige", systemImage: "chevron.left")
                        }
                        .disabled(isSaving)

                        Spacer()

                        Button {
                            Task { await saveHole(move: 1) }
                        } label: {
                            Label("Neste", systemImage: "chevron.right")
                        }
                        .disabled(isSaving)
                    }

                    Button {
                        Task { await finishRound() }
                    } label: {
                        if isSaving {
                            ProgressView()
                        } else {
                            Label("Avslutt runde", systemImage: "checkmark.seal")
                        }
                    }
                    .disabled(isSaving || detail.status == "finished")
                }
            }

            if let errorMessage {
                Section {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                }
            }

            if let finishMessage {
                Section {
                    Text(finishMessage)
                        .foregroundStyle(.green)
                }
            }
        }
        .navigationTitle(detail.course.name)
        .onAppear {
            loadInputsForCurrentHole()
        }
        .onChange(of: currentHoleNumber) { _, _ in
            loadInputsForCurrentHole()
        }
        .task {
            if activeSetup == nil {
                await loadSetup()
            }
        }
        .blockingProgress(isSaving, message: busyMessage)
        .alert("Mangler informasjon", isPresented: Binding(
            get: { validationMessage != nil },
            set: { if !$0 { validationMessage = nil } }
        )) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(validationMessage ?? "")
        }
    }

    private var holes: [BalleTourSetupHole] {
        if let course = activeSetup?.courses.first(where: { $0.id == detail.course.id }) {
            return course.holes.prefix(detail.course.holeCount).map { $0 }
        }
        return (1...detail.course.holeCount).map {
            BalleTourSetupHole(holeNumber: $0, par: 4, strokeIndex: $0, lengths: [:], scoreOptions: [3, 4, 5, 6, 7, 8, 9])
        }
    }

    private var currentHole: BalleTourSetupHole? {
        holes.first { $0.holeNumber == currentHoleNumber }
    }

    private var headerSection: some View {
        Section {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(detail.status == "finished" ? "Fullført" : "Pågående")
                        .font(.headline)
                    Text(detail.startedAtDisplay ?? detail.startedAt ?? "")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text("Par \(detail.course.par)")
                    .font(.headline.monospacedDigit())
            }
        }
    }

    private var scorecardSection: some View {
        Section("Scorekort") {
            ScrollView(.horizontal, showsIndicators: false) {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 6) {
                        Text("Hull")
                            .font(.caption.weight(.semibold))
                            .frame(width: 64, alignment: .leading)
                        ForEach(holes) { hole in
                            Text("\(hole.holeNumber)")
                                .font(.caption.monospacedDigit())
                                .frame(width: 30)
                        }
                        Text("Tot")
                            .font(.caption.weight(.semibold))
                            .frame(width: 38)
                    }

                    HStack(spacing: 6) {
                        Text("Par")
                            .font(.caption)
                            .frame(width: 64, alignment: .leading)
                        ForEach(holes) { hole in
                            Text("\(hole.par)")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                                .frame(width: 30)
                        }
                        Text("\(detail.course.par)")
                            .font(.caption.monospacedDigit())
                            .frame(width: 38)
                    }

                    ForEach(detail.players) { player in
                        HStack(spacing: 6) {
                            Text(player.name)
                                .font(.caption.weight(.medium))
                                .lineLimit(1)
                                .frame(width: 64, alignment: .leading)
                            ForEach(player.scores) { score in
                                scoreChip(score: score.strokes, par: score.par)
                            }
                            Text(player.totalStrokes.map(String.init) ?? "-")
                                .font(.caption.monospacedDigit().weight(.semibold))
                                .frame(width: 38)
                        }
                    }
                }
                .padding(.vertical, 4)
            }
        }
    }

    private func playerSection(_ player: BalleTourRoundDetailPlayer, hole: BalleTourSetupHole) -> some View {
        let input = binding(for: player.roundPlayerID)
        return Section(player.name) {
            Picker("Score", selection: input.strokes) {
                Text("-").tag(Optional<Int>.none)
                ForEach(hole.scoreOptions, id: \.self) { value in
                    Text("\(value)").tag(Optional(value))
                }
            }
            .pickerStyle(.segmented)

            if player.tracksStats {
                OptionMenuRow(
                    title: "Kølle",
                    options: clubOptions,
                    selection: input.teeClubID
                )

                OptionMenuRow(
                    title: "Utslagslengde",
                    options: driveDistanceOptions,
                    selection: input.driveDistanceM
                )

                if hole.par == 3 {
                    greenControls(input)
                } else {
                    Picker("Fairway", selection: input.fairwayResult) {
                        Text("-").tag(Optional<String>.none)
                        Text("Treff").tag(Optional("hit"))
                        Text("Venstre").tag(Optional("left"))
                        Text("Høyre").tag(Optional("right"))
                    }
                    .pickerStyle(.segmented)
                }

                OptionMenuRow(
                    title: "Putts",
                    options: puttOptions,
                    selection: input.putts
                )

                OptionMenuRow(
                    title: "Siste putt",
                    options: lastPuttOptions,
                    selection: input.lastPuttDistanceM
                )
            }
        }
    }

    private func greenControls(_ input: Binding<BalleTourHolePlayerInput>) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker("Green", selection: greenStatus(input)) {
                Text("Treff").tag("hit")
                Text("Miss").tag("miss")
                Text("Bunker").tag("bunker")
            }
            .pickerStyle(.segmented)

            Picker("Retning", selection: greenHorizontal(input)) {
                Text("Pin").tag("pin")
                Text("Venstre").tag("left")
                Text("Høyre").tag("right")
            }
            .pickerStyle(.segmented)

            Picker("Lengde", selection: greenVertical(input)) {
                Text("Pin high").tag("")
                Text("Kort").tag("short")
                Text("Lang").tag("long")
            }
            .pickerStyle(.segmented)
        }
    }

    private func binding(for roundPlayerID: Int) -> Binding<BalleTourHolePlayerInput> {
        Binding(
            get: { inputs[roundPlayerID] ?? BalleTourHolePlayerInput(roundPlayerID: roundPlayerID) },
            set: { inputs[roundPlayerID] = $0 }
        )
    }

    private func loadInputsForCurrentHole() {
        var nextInputs: [Int: BalleTourHolePlayerInput] = [:]
        for player in detail.players {
            let score = player.scores.first { $0.holeNumber == currentHoleNumber }
            nextInputs[player.roundPlayerID] = BalleTourHolePlayerInput(
                roundPlayerID: player.roundPlayerID,
                strokes: score?.strokes,
                teeClubID: score?.teeClubID,
                driveDistanceM: score?.driveDistanceM,
                green: greenInput(from: score),
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

    private func saveHole(move: Int) async {
        guard let client = session.client else { return }

        if move > 0, let message = currentHoleValidationMessage() {
            validationMessage = message
            errorMessage = nil
            return
        }

        busyMessage = move == 0 ? "Lagrer hull..." : "Lagrer og går videre..."
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }
        do {
            let request = ShanklifeSaveHoleRequest(players: detail.players.map { player in
                inputs[player.roundPlayerID] ?? BalleTourHolePlayerInput(roundPlayerID: player.roundPlayerID)
            })
            detail = try await client.saveShanklifeHole(roundID: detail.id, holeNumber: currentHoleNumber, body: request)
            let target = currentHoleNumber + move
            if holes.contains(where: { $0.holeNumber == target }) {
                currentHoleNumber = target
            }
            loadInputsForCurrentHole()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func loadSetup() async {
        guard let client = session.client else { return }
        do {
            activeSetup = try await client.shanklifeSetup()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func finishRound() async {
        guard let client = session.client else { return }
        if let message = currentHoleValidationMessage() {
            validationMessage = message
            errorMessage = nil
            return
        }

        await saveHole(move: 0)
        if errorMessage != nil { return }
        busyMessage = "Fullfører runde..."
        isSaving = true
        defer { isSaving = false }
        do {
            detail = try await client.finishShanklifeRound(roundID: detail.id)
            finishMessage = "Runden er fullført."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private var clubOptions: [(label: String, value: Int?)] {
        [("-", nil)] + (activeSetup?.clubs ?? []).map { ($0.name, Optional($0.id)) }
    }

    private var driveDistanceOptions: [(label: String, value: Int?)] {
        [("-", nil)] + (activeSetup?.driveDistanceOptions ?? []).map { ("\($0)m", Optional($0)) }
    }

    private var puttOptions: [(label: String, value: Int?)] {
        [("-", nil)] + (activeSetup?.puttOptions ?? []).map { ("\($0)", Optional($0)) }
    }

    private var lastPuttOptions: [(label: String, value: Double?)] {
        [("-", nil)] + (activeSetup?.lastPuttDistanceOptions ?? []).map {
            ("\(shanklifeNumber($0))m", Optional($0))
        }
    }

    private func currentHoleValidationMessage() -> String? {
        guard let hole = currentHole else {
            return nil
        }

        var missingRows: [String] = []

        for player in detail.players {
            let input = inputs[player.roundPlayerID] ?? BalleTourHolePlayerInput(roundPlayerID: player.roundPlayerID)
            var missing: [String] = []

            if input.strokes == nil {
                missing.append("score")
            }

            if player.tracksStats {
                if input.teeClubID == nil {
                    missing.append("kølle")
                }

                if hole.par == 3 {
                    if input.green?.status.isEmpty ?? true {
                        missing.append("green")
                    }
                    let directions = input.green?.directions ?? []
                    if !directions.contains(where: { ["pin", "left", "right"].contains($0) }) {
                        missing.append("retning")
                    }
                } else if input.fairwayResult == nil {
                    missing.append("fairway")
                }

                if let putts = input.putts {
                    if let strokes = input.strokes, putts > 0, putts > strokes - 1 {
                        missing.append("putter kan ikke være høyere enn score minus 1")
                    }
                }
            }

            if !missing.isEmpty {
                missingRows.append("\(player.name): \(missing.joined(separator: ", "))")
            }
        }

        guard !missingRows.isEmpty else {
            return nil
        }
        return "Fyll ut dette før du går videre:\n" + missingRows.joined(separator: "\n")
    }
}

private func scoreChip(score: Int?, par: Int) -> some View {
    let diff = score.map { $0 - par }
    let color: Color = {
        guard let diff else { return .secondary }
        if diff < 0 { return .green }
        if diff == 0 { return .primary }
        if diff == 1 { return .orange }
        return .red
    }()

    return Text(score.map(String.init) ?? "-")
        .font(.caption.monospacedDigit().weight(.semibold))
        .frame(width: 30, height: 30)
        .foregroundStyle(color)
        .background(color.opacity(diff == nil ? 0.06 : 0.14))
        .clipShape(RoundedRectangle(cornerRadius: diff.map { $0 < 0 ? 15 : 6 } ?? 6))
}

private func shanklifeNumber(_ value: Double) -> String {
    value == floor(value) ? String(Int(value)) : String(format: "%.1f", value)
}

private extension Binding where Value == BalleTourHolePlayerInput {
    var strokes: Binding<Int?> {
        Binding<Int?>(
            get: { wrappedValue.strokes },
            set: { wrappedValue.strokes = $0 }
        )
    }

    var teeClubID: Binding<Int?> {
        Binding<Int?>(
            get: { wrappedValue.teeClubID },
            set: { wrappedValue.teeClubID = $0 }
        )
    }

    var driveDistanceM: Binding<Int?> {
        Binding<Int?>(
            get: { wrappedValue.driveDistanceM },
            set: { wrappedValue.driveDistanceM = $0 }
        )
    }

    var fairwayResult: Binding<String?> {
        Binding<String?>(
            get: { wrappedValue.fairwayResult },
            set: { wrappedValue.fairwayResult = $0 }
        )
    }

    var putts: Binding<Int?> {
        Binding<Int?>(
            get: { wrappedValue.putts },
            set: { wrappedValue.putts = $0 }
        )
    }

    var lastPuttDistanceM: Binding<Double?> {
        Binding<Double?>(
            get: { wrappedValue.lastPuttDistanceM },
            set: { wrappedValue.lastPuttDistanceM = $0 }
        )
    }
}

private func greenStatus(_ input: Binding<BalleTourHolePlayerInput>) -> Binding<String> {
    Binding<String>(
        get: { input.wrappedValue.green?.status ?? "hit" },
        set: {
            var value = input.wrappedValue
            var green = value.green ?? BalleTourGreenInput(status: "hit", directions: ["pin"])
            green.status = $0
            value.green = green
            input.wrappedValue = value
        }
    )
}

private func greenHorizontal(_ input: Binding<BalleTourHolePlayerInput>) -> Binding<String> {
    Binding<String>(
        get: {
            let directions = input.wrappedValue.green?.directions ?? ["pin"]
            if directions.contains("left") { return "left" }
            if directions.contains("right") { return "right" }
            return "pin"
        },
        set: {
            var value = input.wrappedValue
            var green = value.green ?? BalleTourGreenInput(status: "hit", directions: [])
            green.directions.removeAll { ["pin", "left", "right"].contains($0) }
            green.directions.append($0)
            value.green = green
            input.wrappedValue = value
        }
    )
}

private func greenVertical(_ input: Binding<BalleTourHolePlayerInput>) -> Binding<String> {
    Binding<String>(
        get: {
            let directions = input.wrappedValue.green?.directions ?? []
            if directions.contains("short") { return "short" }
            if directions.contains("long") { return "long" }
            return ""
        },
        set: {
            var value = input.wrappedValue
            var green = value.green ?? BalleTourGreenInput(status: "hit", directions: ["pin"])
            green.directions.removeAll { ["short", "long"].contains($0) }
            if !$0.isEmpty {
                green.directions.append($0)
            }
            value.green = green
            input.wrappedValue = value
        }
    )
}
