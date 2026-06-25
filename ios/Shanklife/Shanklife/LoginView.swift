import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var session: SessionStore
    @State private var username = ""
    @State private var password = ""
    #if DEBUG && targetEnvironment(simulator)
    @State private var didStartLocalAutoLogin = false
    #endif
    @FocusState private var focusedField: Field?

    private enum Field {
        case username
        case password
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Image(systemName: "figure.golf")
                            .font(.system(size: 42))
                            .foregroundStyle(.green)
                        Text("Shanklife")
                            .font(.title.bold())
                        Text("Native prototype")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        Text(appVersionDisplay)
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                    .padding(.vertical, 8)
                }

                Section("Server") {
                    TextField("Base URL", text: $session.baseURLText)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                }

                Section("Innlogging") {
                    TextField("Brukernavn", text: $username)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.emailAddress)
                        .autocorrectionDisabled()
                        .focused($focusedField, equals: .username)
                        .submitLabel(.next)
                        .onSubmit {
                            focusedField = .password
                        }

                    SecureField("Passord", text: $password)
                        .focused($focusedField, equals: .password)
                        .submitLabel(.go)
                        .onSubmit {
                            login()
                        }

                    Button {
                        login()
                    } label: {
                        if session.isLoading {
                            ProgressView()
                        } else {
                            Label("Logg inn", systemImage: "person.crop.circle.badge.checkmark")
                        }
                    }
                    .disabled(username.isEmpty || password.isEmpty || session.isLoading)
                }

                if let errorMessage = session.errorMessage {
                    Section {
                        Text(errorMessage)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Shanklife")
            .onAppear {
                if username.isEmpty, let savedUsername = session.savedUsername {
                    username = savedUsername
                }
                #if DEBUG && targetEnvironment(simulator)
                startLocalAutoLoginIfAvailable()
                #endif
            }
        }
    }

    private func login() {
        guard !username.isEmpty, !password.isEmpty, !session.isLoading else {
            return
        }

        Task {
            await session.login(username: username, password: password)
        }
    }

    #if DEBUG && targetEnvironment(simulator)
    private func startLocalAutoLoginIfAvailable() {
        guard !didStartLocalAutoLogin, !session.isLoggedIn else {
            return
        }
        didStartLocalAutoLogin = true
        username = "kristian"
        password = "kristian"
        login()
    }
    #endif

    private var appVersionDisplay: String {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "-"
        let build = info?["CFBundleVersion"] as? String ?? "-"
        return "Versjon \(version) (\(build))"
    }
}

#Preview {
    LoginView()
        .environmentObject(SessionStore())
}
