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
    @State private var teeName = "Gul"
    @State private var holes = ShanklifeNewCourseView.defaultHoles(18)
    @State private var lengths = ShanklifeNewCourseView.defaultLengths(18)
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
                    lengths = Self.defaultLengths(newValue)
                }
                TextField("Tee", text: $teeName)
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
                        TextField("Lengde", value: Binding(
                            get: { lengths[String(hole.holeNumber)] ?? 300 },
                            set: { lengths[String(hole.holeNumber)] = $0 }
                        ), format: .number)
                        .keyboardType(.numberPad)
                    }
                    .padding(.vertical, 4)
                }
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
        .blockingProgress(isSaving, message: "Lagrer bane...")
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
                    tees: [ShanklifeCourseTeeInput(name: teeName.trimmingCharacters(in: .whitespacesAndNewlines), lengths: lengths)]
                )
            )
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
