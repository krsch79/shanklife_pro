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
    let displayName: String?
    let defaultHcp: Double?
    let gender: String?
    let displayOrder: Int

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case displayName = "display_name"
        case defaultHcp = "default_hcp"
        case gender
        case displayOrder = "display_order"
    }
}

struct BalleTourOverviewResponse: Decodable {
    let enabled: Bool?
    let series: String
    let course: BalleTourCourse
    let tee: String
    let teeOptions: [BalleTourTeeOption]
    let playerCount: Int
    let finishedRoundCount: Int
    let ongoingRoundCount: Int
    let minQualifyingRounds: Int
    let leaderboard: [BalleTourLeaderboardRow]

    enum CodingKeys: String, CodingKey {
        case enabled
        case series
        case course
        case tee
        case teeOptions = "tee_options"
        case playerCount = "player_count"
        case finishedRoundCount = "finished_round_count"
        case ongoingRoundCount = "ongoing_round_count"
        case minQualifyingRounds = "min_qualifying_rounds"
        case leaderboard
    }
}

struct BalleTourCourse: Decodable, Identifiable {
    let id: Int
    let name: String
    let holeCount: Int
    let par: Int

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case holeCount = "hole_count"
        case par
    }
}

struct BalleTourTeeOption: Decodable, Identifiable, Hashable {
    let key: String
    let label: String

    var id: String { key }
}

struct BalleTourLeaderboardRow: Decodable, Identifiable {
    let playerID: Int
    let playerName: String
    let rank: Int?
    let roundsPlayed: Int
    let totalStrokes: Int?
    let totalVsPar: Int?
    let totalVsParDisplay: String
    let averageRound: Double?
    let bestRound: Int?
    let qualified: Bool

    var id: Int { playerID }

    enum CodingKeys: String, CodingKey {
        case playerID = "player_id"
        case playerName = "player_name"
        case rank
        case roundsPlayed = "rounds_played"
        case totalStrokes = "total_strokes"
        case totalVsPar = "total_vs_par"
        case totalVsParDisplay = "total_vs_par_display"
        case averageRound = "average_round"
        case bestRound = "best_round"
        case qualified
    }
}

struct BalleTourPlayersResponse: Decodable {
    let players: [BalleTourPlayer]
}

struct BalleTourRoundsResponse: Decodable {
    let status: String
    let tee: String
    let playerName: String?
    let rounds: [BalleTourRoundListItem]

    enum CodingKeys: String, CodingKey {
        case status
        case tee
        case playerName = "player_name"
        case rounds
    }
}

struct BalleTourRoundListItem: Decodable, Identifiable {
    let id: Int
    let status: String
    let course: String
    let startedAt: String?
    let startedAtDisplay: String?
    let finishedAt: String?
    let players: [BalleTourRoundPlayerSummary]

    enum CodingKeys: String, CodingKey {
        case id
        case status
        case course
        case startedAt = "started_at"
        case startedAtDisplay = "started_at_display"
        case finishedAt = "finished_at"
        case players
    }
}

struct BalleTourRoundPlayerSummary: Decodable, Identifiable {
    let playerID: Int
    let playerName: String
    let tee: String?
    let hcp: Double
    let completedHoles: Int
    let totalStrokes: Int?
    let toPar: Int?
    let toParDisplay: String

    var id: Int { playerID }

    enum CodingKeys: String, CodingKey {
        case playerID = "player_id"
        case playerName = "player_name"
        case tee
        case hcp
        case completedHoles = "completed_holes"
        case totalStrokes = "total_strokes"
        case toPar = "to_par"
        case toParDisplay = "to_par_display"
    }
}

struct BalleTourPlayerSummaryResponse: Decodable {
    let player: BalleTourPlayerProfile
    let tee: String
    let roundsPlayed: Int
    let finishedRounds: Int
    let averageRound: Double?
    let bestRound: Int?
    let trackedHoles: Int
    let averagePutts: Double?
    let averageDriveDistance: Double?
    let girPercent: Double?
    let averagePar3: Double?
    let averagePar4: Double?
    let averagePar5: Double?

    enum CodingKeys: String, CodingKey {
        case player
        case tee
        case roundsPlayed = "rounds_played"
        case finishedRounds = "finished_rounds"
        case averageRound = "average_round"
        case bestRound = "best_round"
        case trackedHoles = "tracked_holes"
        case averagePutts = "average_putts"
        case averageDriveDistance = "average_drive_distance"
        case girPercent = "gir_percent"
        case averagePar3 = "average_par_3"
        case averagePar4 = "average_par_4"
        case averagePar5 = "average_par_5"
    }
}

struct BalleTourPlayerProfile: Decodable, Identifiable {
    let id: Int
    let name: String
    let displayName: String
    let defaultHcp: Double

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case displayName = "display_name"
        case defaultHcp = "default_hcp"
    }
}

struct BalleTourRoundDetail: Decodable, Identifiable {
    let id: Int
    let status: String
    let course: BalleTourCourse
    let startedAt: String?
    let startedAtDisplay: String?
    let finishedAt: String?
    let finishedAtDisplay: String?
    let players: [BalleTourRoundDetailPlayer]

    enum CodingKeys: String, CodingKey {
        case id
        case status
        case course
        case startedAt = "started_at"
        case startedAtDisplay = "started_at_display"
        case finishedAt = "finished_at"
        case finishedAtDisplay = "finished_at_display"
        case players
    }
}

struct BalleTourRoundDetailPlayer: Decodable, Identifiable {
    let id: Int
    let roundPlayerID: Int
    let name: String
    let hcp: Double
    let tee: String?
    let tracksStats: Bool
    let completedHoles: Int
    let totalStrokes: Int?
    let toPar: Int?
    let toParDisplay: String
    let scores: [BalleTourHoleScore]

    enum CodingKeys: String, CodingKey {
        case id
        case roundPlayerID = "round_player_id"
        case name
        case hcp
        case tee
        case tracksStats = "tracks_stats"
        case completedHoles = "completed_holes"
        case totalStrokes = "total_strokes"
        case toPar = "to_par"
        case toParDisplay = "to_par_display"
        case scores
    }
}

struct BalleTourHoleScore: Decodable, Identifiable {
    let holeNumber: Int
    let par: Int
    let strokeIndex: Int
    let lengthMeters: Int?
    let strokes: Int?
    let toPar: Int?
    let teeClub: String?
    let driveDistanceM: Int?
    let greenResult: String?
    let putts: Int?
    let lastPuttDistanceM: Double?

    var id: Int { holeNumber }

    enum CodingKeys: String, CodingKey {
        case holeNumber = "hole_number"
        case par
        case strokeIndex = "stroke_index"
        case lengthMeters = "length_meters"
        case strokes
        case toPar = "to_par"
        case teeClub = "tee_club"
        case driveDistanceM = "drive_distance_m"
        case greenResult = "green_result"
        case putts
        case lastPuttDistanceM = "last_putt_distance_m"
    }
}
