import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var session: SessionStore
    @State private var username = ""
    @State private var password = ""

    var body: some View {
        NavigationStack {
            Form {
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

                    SecureField("Passord", text: $password)

                    Button {
                        Task {
                            await session.login(username: username, password: password)
                        }
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
        }
    }
}

#Preview {
    LoginView()
        .environmentObject(SessionStore())
}
