import Foundation
import Security

struct SavedLogin {
    let username: String
    let password: String
}

enum KeychainStore {
    private static let service = "no.shanklife.app.login"
    private static let account = "default"

    static func save(username: String, password: String) {
        let payload = "\(username)\n\(password)"
        guard let data = payload.data(using: .utf8) else { return }
        delete()

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]
        SecItemAdd(query as CFDictionary, nil)
    }

    static func load() -> SavedLogin? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let payload = String(data: data, encoding: .utf8)
        else {
            return nil
        }

        let parts = payload.split(separator: "\n", maxSplits: 1).map(String.init)
        guard parts.count == 2 else { return nil }
        return SavedLogin(username: parts[0], password: parts[1])
    }

    static func delete() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }
}
