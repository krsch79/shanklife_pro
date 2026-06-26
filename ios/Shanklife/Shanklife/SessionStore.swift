import Foundation

@MainActor
final class SessionStore: ObservableObject {
    @Published var user: AppUser?
    @Published var bootstrap: BootstrapResponse?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var lastConnectionMessage: String?
    @Published var savedUsername: String?

    @Published var baseURLText: String {
        didSet {
            UserDefaults.standard.set(baseURLText, forKey: "baseURLText")
        }
    }

    init() {
        baseURLText = UserDefaults.standard.string(forKey: "baseURLText") ?? "https://app.shanklife.no"
        savedUsername = KeychainStore.load()?.username
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
            let restoredUser = try await client.me()
            #if !(DEBUG && targetEnvironment(simulator))
            if restoredUser.username.lowercased() == "kristian" {
                try? await client.logout()
                KeychainStore.delete()
                savedUsername = nil
                user = nil
                bootstrap = nil
                lastConnectionMessage = nil
                return
            }
            #endif
            user = restoredUser
            bootstrap = try await client.bootstrap()
            lastConnectionMessage = "Tilkoblet \(baseURLText)"
        } catch {
            if let savedLogin = KeychainStore.load() {
                #if !(DEBUG && targetEnvironment(simulator))
                if savedLogin.username.lowercased() == "kristian" {
                    KeychainStore.delete()
                    savedUsername = nil
                    user = nil
                    bootstrap = nil
                    lastConnectionMessage = nil
                    return
                }
                #endif
                do {
                    user = try await client.login(username: savedLogin.username, password: savedLogin.password)
                    bootstrap = try await client.bootstrap()
                    savedUsername = savedLogin.username
                    lastConnectionMessage = "Tilkoblet \(baseURLText)"
                    return
                } catch {
                    KeychainStore.delete()
                    savedUsername = nil
                }
            }
            user = nil
            bootstrap = nil
            lastConnectionMessage = nil
        }
    }

    func login(username: String, password: String, rememberCredentials: Bool = true) async {
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
            if rememberCredentials {
                KeychainStore.save(username: username, password: password)
                savedUsername = username
            }
            lastConnectionMessage = "Tilkoblet \(baseURLText)"
        } catch {
            errorMessage = error.localizedDescription
            lastConnectionMessage = nil
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
        KeychainStore.delete()
        savedUsername = nil
        lastConnectionMessage = nil
    }
}
