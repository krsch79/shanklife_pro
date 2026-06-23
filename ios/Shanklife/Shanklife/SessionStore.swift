import Foundation

@MainActor
final class SessionStore: ObservableObject {
    @Published var user: AppUser?
    @Published var bootstrap: BootstrapResponse?
    @Published var isLoading = false
    @Published var errorMessage: String?

    @Published var baseURLText: String {
        didSet {
            UserDefaults.standard.set(baseURLText, forKey: "baseURLText")
        }
    }

    init() {
        baseURLText = UserDefaults.standard.string(forKey: "baseURLText") ?? "http://127.0.0.1:5055"
    }

    var isLoggedIn: Bool {
        user != nil
    }

    var client: APIClient? {
        guard let url = URL(string: baseURLText) else {
            return nil
        }
        return APIClient(baseURL: url)
    }

    func restore() async {
        guard let client else {
            return
        }

        isLoading = true
        defer { isLoading = false }

        do {
            user = try await client.me()
            bootstrap = try await client.bootstrap()
        } catch {
            user = nil
            bootstrap = nil
        }
    }

    func login(username: String, password: String) async {
        guard let client else {
            errorMessage = "Skriv inn en gyldig serveradresse."
            return
        }

        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            user = try await client.login(username: username, password: password)
            bootstrap = try await client.bootstrap()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func logout() async {
        guard let client else {
            user = nil
            bootstrap = nil
            return
        }

        do {
            try await client.logout()
        } catch {
            errorMessage = error.localizedDescription
        }

        user = nil
        bootstrap = nil
    }
}
