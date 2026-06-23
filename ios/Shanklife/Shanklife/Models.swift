import Foundation

struct APIErrorEnvelope: Decodable {
    let error: APIErrorMessage
}

struct APIErrorMessage: Decodable {
    let code: String
    let message: String
}

struct LoginResponse: Decodable {
    let user: AppUser
}

struct MeResponse: Decodable {
    let user: AppUser
}

struct BootstrapResponse: Decodable {
    let version: String
    let user: AppUser
    let products: [ProductSection]
}

struct OverviewResponse: Decodable {
    let courseCount: Int?
    let recentRounds: [RoundSummary]?
    let enabled: Bool?
    let players: [BalleTourPlayer]?

    enum CodingKeys: String, CodingKey {
        case courseCount = "course_count"
        case recentRounds = "recent_rounds"
        case enabled
        case players
    }
}

struct AppUser: Decodable, Identifiable {
    let id: Int
    let username: String
    let email: String?
    let isAdmin: Bool
    let player: PlayerSummary?
    let products: ProductAccess

    enum CodingKeys: String, CodingKey {
        case id
        case username
        case email
        case isAdmin = "is_admin"
        case player
        case products
    }
}

struct PlayerSummary: Decodable, Identifiable {
    let id: Int
    let name: String
    let gender: String
    let defaultHcp: Double
    let profileImageURL: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case gender
        case defaultHcp = "default_hcp"
        case profileImageURL = "profile_image_url"
    }
}

struct ProductAccess: Decodable {
    let shanklife: Bool
    let balletour: Bool
}

struct ProductSection: Decodable, Identifiable {
    let id: String
    let name: String
    let enabled: Bool
    let navigation: [NavigationItem]
}

struct NavigationItem: Decodable, Identifiable {
    let id: String
    let title: String
}

struct RoundSummary: Decodable, Identifiable {
    let id: Int
    let status: String
    let startedAt: String?
    let finishedAt: String?
    let playedHoleCount: Int?
    let course: CourseSummary?
    let players: [RoundPlayerSummary]

    enum CodingKeys: String, CodingKey {
        case id
        case status
        case startedAt = "started_at"
        case finishedAt = "finished_at"
        case playedHoleCount = "played_hole_count"
        case course
        case players
    }
}

struct CourseSummary: Decodable, Identifiable {
    let id: Int
    let name: String
    let holeCount: Int

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case holeCount = "hole_count"
    }
}

struct RoundPlayerSummary: Decodable, Identifiable {
    let id: Int
    let name: String
    let hcp: Double
    let tracksStats: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case hcp
        case tracksStats = "tracks_stats"
    }
}

struct BalleTourPlayer: Decodable, Identifiable {
    let id: Int
    let name: String
    let displayOrder: Int

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case displayOrder = "display_order"
    }
}
