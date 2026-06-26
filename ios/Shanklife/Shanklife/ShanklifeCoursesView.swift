import PhotosUI
import SwiftUI

struct ShanklifeCoursesView: View {
    @EnvironmentObject private var session: SessionStore
    @State private var courses: [ShanklifeCourse] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        List {
            if isLoading {
                ProgressView("Laster baner")
            }

            if let errorMessage {
                Text(errorMessage)
                    .foregroundStyle(.red)
            }

            Section {
                NavigationLink {
                    ShanklifeNewCourseView()
                        .environmentObject(session)
                } label: {
                    Label("Ny bane", systemImage: "plus.circle.fill")
                }
            }

            Section("Baner") {
                if courses.isEmpty && !isLoading {
                    Text("Ingen baner registrert.")
                        .foregroundStyle(.secondary)
                }
                ForEach(courses) { course in
                    NavigationLink {
                        ShanklifeCourseDetailView(course: course)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(course.name)
                                .font(.headline)
                            Text("\(course.holeCount) hull · par \(course.par) · \(course.tees.count) tee")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .navigationTitle("Baner")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
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

    private func load() async {
        guard let client = session.client else {
            errorMessage = "Ugyldig serveradresse."
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            courses = try await client.shanklifeCourses().courses
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct ShanklifeCourseDetailView: View {
    let course: ShanklifeCourse

    var body: some View {
        List {
            Section {
                LabeledContent("Hull", value: "\(course.holeCount)")
                LabeledContent("Par", value: "\(course.par)")
            }

            ForEach(course.tees) { tee in
                Section(tee.name) {
                    LabeledContent("Lengde", value: "\(tee.totalLengthMeters)m")
                    ForEach(course.holes) { hole in
                        let length = hole.lengths[String(tee.id)].map { "\($0)m" } ?? "-"
                        LabeledContent("Hull \(hole.holeNumber)", value: "Par \(hole.par) · Index \(hole.strokeIndex) · \(length)")
                    }
                }
            }
        }
        .navigationTitle(course.name)
    }
}

struct ShanklifeNewCourseView: View {
    @EnvironmentObject private var session: SessionStore
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var holeCount = 18
    @State private var holes = ShanklifeNewCourseView.defaultHoles(18)
    @State private var tees = [ShanklifeCourseTeeInput(name: "Gul", lengths: ShanklifeNewCourseView.defaultLengths(18))]
    @State private var scorecardItem: PhotosPickerItem?
    @State private var slopeItem: PhotosPickerItem?
    @State private var scorecardImageData: Data?
    @State private var slopeImageData: Data?
    @State private var isImporting = false
    @State private var isSaving = false
    @State private var errorMessage: String?

    var body: some View {
        Form {
            Section("Bane") {
                TextField("Navn", text: $name)
                Picker("Hull", selection: $holeCount) {
                    Text("18").tag(18)
                    Text("9").tag(9)
                }
                .pickerStyle(.segmented)
                .onChange(of: holeCount) { _, newValue in
                    holes = Self.defaultHoles(newValue)
                    tees = [ShanklifeCourseTeeInput(name: tees.first?.name ?? "Gul", lengths: Self.defaultLengths(newValue))]
                }
            }

            Section("Importer fra bilde") {
                PhotosPicker(selection: $scorecardItem, matching: .images) {
                    Label(scorecardImageData == nil ? "Velg scorekort" : "Scorekort valgt", systemImage: "doc.viewfinder")
                }
                PhotosPicker(selection: $slopeItem, matching: .images) {
                    Label(slopeImageData == nil ? "Velg slopetabell" : "Slopetabell valgt", systemImage: "tablecells")
                }
                Button {
                    Task { await importCourseImages() }
                } label: {
                    if isImporting {
                        ProgressView()
                    } else {
                        Label("Les bane fra bilde", systemImage: "sparkles")
                    }
                }
                .disabled(isImporting || scorecardImageData == nil)
            }

            Section("Hull") {
                ForEach($holes) { $hole in
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Hull \(hole.holeNumber)")
                            .font(.headline)
                        HStack {
                            Stepper("Par \(hole.par)", value: $hole.par, in: 3...6)
                            TextField("Index", value: $hole.strokeIndex, format: .number)
                                .keyboardType(.numberPad)
                                .frame(width: 72)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }

            ForEach($tees) { $tee in
                Section("Tee") {
                    TextField("Navn", text: $tee.name)
                    ForEach(holes) { hole in
                        teeLengthField(tee: $tee, holeNumber: hole.holeNumber)
                    }

                    Text("Slope og course rating")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    ratingFields(title: "Herre", rating: maleRatingBinding(tee: $tee))
                    ratingFields(title: "Dame", rating: femaleRatingBinding(tee: $tee))
                }
            }

            Section {
                Button {
                    addTee()
                } label: {
                    Label("Legg til tee", systemImage: "plus.circle")
                }
                .disabled(tees.count >= 6)
            }

            Section {
                Button {
                    Task { await save() }
                } label: {
                    if isSaving {
                        ProgressView()
                    } else {
                        Label("Lagre bane", systemImage: "checkmark.circle")
                    }
                }
                .disabled(isSaving || name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            if let errorMessage {
                Section {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                }
            }
        }
        .navigationTitle("Ny bane")
        .blockingProgress(isSaving || isImporting, message: isImporting ? "Leser bilder..." : "Lagrer bane...")
        .onChange(of: scorecardItem) { _, item in
            Task { scorecardImageData = await loadImageData(from: item) }
        }
        .onChange(of: slopeItem) { _, item in
            Task { slopeImageData = await loadImageData(from: item) }
        }
    }

    private static func defaultHoles(_ count: Int) -> [ShanklifeCourseHoleInput] {
        (1...count).map { number in
            ShanklifeCourseHoleInput(holeNumber: number, par: number % 3 == 0 ? 3 : number % 5 == 0 ? 5 : 4, strokeIndex: number)
        }
    }

    private static func defaultLengths(_ count: Int) -> [String: Int] {
        var values: [String: Int] = [:]
        for number in 1...count {
            let length: Int
            if number % 3 == 0 {
                length = 145
            } else if number % 5 == 0 {
                length = 450
            } else {
                length = 330
            }
            values[String(number)] = length
        }
        return values
    }

    private func save() async {
        guard let client = session.client else {
            errorMessage = "Ugyldig serveradresse."
            return
        }
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }
        do {
            _ = try await client.createShanklifeCourse(
                ShanklifeCourseCreateRequest(
                    name: name.trimmingCharacters(in: .whitespacesAndNewlines),
                    holeCount: holeCount,
                    holes: holes,
                    tees: tees
                )
            )
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @ViewBuilder
    private func ratingFields(title: String, rating: Binding<ShanklifeCourseTeeRating?>) -> some View {
        HStack {
            Text(title)
                .frame(width: 52, alignment: .leading)
            TextField("Slope", text: optionalIntText(rating, keyPath: \.slope))
                .keyboardType(.numberPad)
            TextField("CR", text: optionalDoubleText(rating, keyPath: \.courseRating))
                .keyboardType(.decimalPad)
        }
    }

    private func teeLengthField(tee: Binding<ShanklifeCourseTeeInput>, holeNumber: Int) -> some View {
        let key = String(holeNumber)
        let lengthBinding = Binding<Int>(
            get: { tee.wrappedValue.lengths[key] ?? 300 },
            set: { tee.wrappedValue.lengths[key] = $0 }
        )
        return TextField("Hull \(holeNumber)", value: lengthBinding, format: .number)
            .keyboardType(.numberPad)
    }

    private func addTee() {
        tees.append(ShanklifeCourseTeeInput(name: "Tee \(tees.count + 1)", lengths: Self.defaultLengths(holeCount)))
    }

    private func importCourseImages() async {
        guard let client = session.client, let scorecardImageData else {
            errorMessage = "Velg et bilde av scorekortet først."
            return
        }
        isImporting = true
        errorMessage = nil
        defer { isImporting = false }
        do {
            let draft = try await client.importShanklifeCourse(
                scorecardImage: scorecardImageData,
                scorecardFilename: "scorecard.jpg",
                slopeImage: slopeImageData,
                slopeFilename: slopeImageData == nil ? nil : "slope.jpg"
            )
            name = draft.courseName
            holeCount = draft.holeCount
            holes = draft.holes.map {
                ShanklifeCourseHoleInput(
                    holeNumber: $0.holeNumber,
                    par: $0.par,
                    strokeIndex: $0.strokeIndex,
                    physicalCourseGroup: $0.physicalCourseGroup,
                    physicalLoop: $0.physicalLoop,
                    physicalHoleNumber: $0.physicalHoleNumber
                )
            }
            tees = draft.tees.map {
                ShanklifeCourseTeeInput(name: $0.name, lengths: $0.lengths, ratings: $0.ratings)
            }
            if tees.isEmpty {
                tees = [ShanklifeCourseTeeInput(name: "Gul", lengths: Self.defaultLengths(draft.holeCount))]
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func loadImageData(from item: PhotosPickerItem?) async -> Data? {
        guard let item else { return nil }
        return try? await item.loadTransferable(type: Data.self)
    }

    private func maleRatingBinding(tee: Binding<ShanklifeCourseTeeInput>) -> Binding<ShanklifeCourseTeeRating?> {
        Binding(
            get: { tee.wrappedValue.ratings?.male },
            set: { newValue in
                var ratings = tee.wrappedValue.ratings ?? ShanklifeCourseTeeRatings()
                ratings.male = newValue
                tee.wrappedValue.ratings = ratings
            }
        )
    }

    private func femaleRatingBinding(tee: Binding<ShanklifeCourseTeeInput>) -> Binding<ShanklifeCourseTeeRating?> {
        Binding(
            get: { tee.wrappedValue.ratings?.female },
            set: { newValue in
                var ratings = tee.wrappedValue.ratings ?? ShanklifeCourseTeeRatings()
                ratings.female = newValue
                tee.wrappedValue.ratings = ratings
            }
        )
    }

    private func optionalIntText(_ rating: Binding<ShanklifeCourseTeeRating?>, keyPath: WritableKeyPath<ShanklifeCourseTeeRating, Int?>) -> Binding<String> {
        Binding(
            get: {
                guard let value = rating.wrappedValue?[keyPath: keyPath] else { return "" }
                return String(value)
            },
            set: { text in
                var value = rating.wrappedValue ?? ShanklifeCourseTeeRating()
                value[keyPath: keyPath] = Int(text.trimmingCharacters(in: .whitespacesAndNewlines))
                rating.wrappedValue = value.isEmpty ? nil : value
            }
        )
    }

    private func optionalDoubleText(_ rating: Binding<ShanklifeCourseTeeRating?>, keyPath: WritableKeyPath<ShanklifeCourseTeeRating, Double?>) -> Binding<String> {
        Binding(
            get: {
                guard let value = rating.wrappedValue?[keyPath: keyPath] else { return "" }
                return formatShanklifeNumber(value)
            },
            set: { text in
                var value = rating.wrappedValue ?? ShanklifeCourseTeeRating()
                value[keyPath: keyPath] = Double(text.replacingOccurrences(of: ",", with: ".").trimmingCharacters(in: .whitespacesAndNewlines))
                rating.wrappedValue = value.isEmpty ? nil : value
            }
        )
    }
}

private func formatShanklifeNumber(_ value: Double) -> String {
    value == floor(value) ? String(Int(value)) : String(format: "%.1f", value)
}

private extension ShanklifeCourseTeeRating {
    var isEmpty: Bool {
        slope == nil && courseRating == nil
    }
}
