import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var session: SessionStore
    @State private var username = ""
    @State private var password = ""
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
}

#Preview {
    LoginView()
        .environmentObject(SessionStore())
}
