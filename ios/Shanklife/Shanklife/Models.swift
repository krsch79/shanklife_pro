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

struct ShanklifeSetupResponse: Decodable {
    let courses: [ShanklifeCourse]
    let players: [BalleTourPlayer]
    let clubs: [BalleTourClub]
    let maxPlayers: Int
    let driveDistanceOptions: [Int]
    let puttOptions: [Int]
    let lastPuttDistanceOptions: [Double]

    enum CodingKeys: String, CodingKey {
        case courses
        case players
        case clubs
        case maxPlayers = "max_players"
        case driveDistanceOptions = "drive_distance_options"
        case puttOptions = "putt_options"
        case lastPuttDistanceOptions = "last_putt_distance_options"
    }
}

struct ShanklifeCoursesResponse: Decodable {
    let courses: [ShanklifeCourse]
}

struct ShanklifeCourse: Decodable, Identifiable {
    let id: Int
    let name: String
    let holeCount: Int
    let par: Int
    let supportsNineHoleRound: Bool
    let tees: [BalleTourSetupTee]
    let holes: [BalleTourSetupHole]

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case holeCount = "hole_count"
        case par
        case supportsNineHoleRound = "supports_nine_hole_round"
        case tees
        case holes
    }
}

struct ShanklifeCourseCreateRequest: Encodable {
    let name: String
    let holeCount: Int
    let holes: [ShanklifeCourseHoleInput]
    let tees: [ShanklifeCourseTeeInput]

    enum CodingKeys: String, CodingKey {
        case name
        case holeCount = "hole_count"
        case holes
        case tees
    }
}

struct ShanklifeCourseHoleInput: Codable, Identifiable {
    let holeNumber: Int
    var par: Int
    var strokeIndex: Int
    var physicalCourseGroup: String? = nil
    var physicalLoop: String? = nil
    var physicalHoleNumber: Int? = nil

    var id: Int { holeNumber }

    enum CodingKeys: String, CodingKey {
        case holeNumber = "hole_number"
        case par
        case strokeIndex = "stroke_index"
        case physicalCourseGroup = "physical_course_group"
        case physicalLoop = "physical_loop"
        case physicalHoleNumber = "physical_hole_number"
    }
}

struct ShanklifeCourseTeeInput: Encodable, Identifiable {
    var id = UUID()
    var name: String
    var lengths: [String: Int]
    var ratings: ShanklifeCourseTeeRatings? = nil

    enum CodingKeys: String, CodingKey {
        case name
        case lengths
        case ratings
    }
}

struct ShanklifeCourseImportResponse: Decodable {
    let courseName: String
    let holeCount: Int
    let holes: [ShanklifeCourseHoleInput]
    let tees: [ShanklifeImportedTee]
    let slopeImported: Bool

    enum CodingKeys: String, CodingKey {
        case courseName = "course_name"
        case holeCount = "hole_count"
        case holes
        case tees
        case slopeImported = "slope_imported"
    }
}

struct ShanklifeImportedTee: Decodable {
    let name: String
    let lengths: [String: Int]
    let ratings: ShanklifeCourseTeeRatings?
}

struct ShanklifeCourseTeeRatings: Codable {
    var male: ShanklifeCourseTeeRating? = nil
    var female: ShanklifeCourseTeeRating? = nil
}

struct ShanklifeCourseTeeRating: Codable {
    var slope: Int? = nil
    var courseRating: Double? = nil

    enum CodingKeys: String, CodingKey {
        case slope
        case courseRating = "course_rating"
    }
}

struct ShanklifeRoundsResponse: Decodable {
    let status: String
    let rounds: [ShanklifeRoundListItem]
}

struct ShanklifeRoundListItem: Decodable, Identifiable {
    let id: Int
    let status: String
    let course: String
    let startedAt: String?
    let startedAtDisplay: String?
    let finishedAt: String?
    let players: [ShanklifeRoundPlayerSummary]

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

struct ShanklifeRoundPlayerSummary: Decodable, Identifiable {
    let id: Int
    let roundPlayerID: Int
    let name: String
    let hcp: Double
    let tee: String?
    let tracksStats: Bool
    let totalStrokes: Int?

    enum CodingKeys: String, CodingKey {
        case id
        case roundPlayerID = "round_player_id"
        case name
        case hcp
        case tee
        case tracksStats = "tracks_stats"
        case totalStrokes = "total_strokes"
    }
}

struct ShanklifeCreateRoundRequest: Encodable {
    let courseID: Int
    let playedHoleCount: Int
    let players: [ShanklifeCreateRoundPlayer]

    enum CodingKeys: String, CodingKey {
        case courseID = "course_id"
        case playedHoleCount = "played_hole_count"
        case players
    }
}

struct ShanklifeCreateRoundPlayer: Encodable, Identifiable {
    var playerID: Int?
    var newPlayerName: String?
    var hcp: Double
    var teeID: Int
    var tracksStats: Bool

    var id: String {
        if let playerID { return "player-\(playerID)" }
        return "new-\(newPlayerName ?? UUID().uuidString)"
    }

    enum CodingKeys: String, CodingKey {
        case playerID = "player_id"
        case newPlayerName = "new_player_name"
        case hcp
        case teeID = "tee_id"
        case tracksStats = "tracks_stats"
    }
}

struct ShanklifeRoundDetail: Decodable, Identifiable {
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

struct ShanklifeSaveHoleRequest: Encodable {
    let players: [BalleTourHolePlayerInput]
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

struct BalleTourRoundSetup: Decodable {
    let course: BalleTourCourse
    let holes: [BalleTourSetupHole]
    let tees: [BalleTourSetupTee]
    let players: [BalleTourPlayer]
    let clubs: [BalleTourClub]
    let maxPlayers: Int
    let driveDistanceOptions: [Int]
    let puttOptions: [Int]
    let lastPuttDistanceOptions: [Double]
    let weatherSummary: String?

    enum CodingKeys: String, CodingKey {
        case course
        case holes
        case tees
        case players
        case clubs
        case maxPlayers = "max_players"
        case driveDistanceOptions = "drive_distance_options"
        case puttOptions = "putt_options"
        case lastPuttDistanceOptions = "last_putt_distance_options"
        case weatherSummary = "weather_summary"
    }
}

struct BalleTourSetupHole: Decodable, Identifiable {
    let holeNumber: Int
    let par: Int
    let strokeIndex: Int
    let lengths: [String: Int]
    let scoreOptions: [Int]

    var id: Int { holeNumber }

    enum CodingKeys: String, CodingKey {
        case holeNumber = "hole_number"
        case par
        case strokeIndex = "stroke_index"
        case lengths
        case scoreOptions = "score_options"
    }
}

struct BalleTourSetupTee: Decodable, Identifiable, Hashable {
    let id: Int
    let name: String
    let displayOrder: Int
    let totalLengthMeters: Int

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case displayOrder = "display_order"
        case totalLengthMeters = "total_length_meters"
    }
}

struct BalleTourClub: Decodable, Identifiable, Hashable {
    let id: Int
    let name: String
    let sortOrder: Int

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case sortOrder = "sort_order"
    }
}

struct BalleTourCreateRoundRequest: Encodable {
    let players: [BalleTourCreateRoundPlayer]
}

struct BalleTourCreateRoundPlayer: Encodable, Identifiable {
    var playerID: Int
    var hcp: Double
    var teeID: Int

    var id: Int { playerID }

    enum CodingKeys: String, CodingKey {
        case playerID = "player_id"
        case hcp
        case teeID = "tee_id"
    }
}

struct BalleTourSaveHoleRequest: Encodable {
    let players: [BalleTourHolePlayerInput]
}

struct BalleTourHolePlayerInput: Encodable, Identifiable {
    let roundPlayerID: Int
    var strokes: Int?
    var teeClubID: Int?
    var driveDistanceM: Int?
    var green: BalleTourGreenInput?
    var fairwayResult: String?
    var putts: Int?
    var lastPuttDistanceM: Double?

    var id: Int { roundPlayerID }

    enum CodingKeys: String, CodingKey {
        case roundPlayerID = "round_player_id"
        case strokes
        case teeClubID = "tee_club_id"
        case driveDistanceM = "drive_distance_m"
        case green
        case fairwayResult = "fairway_result"
        case putts
        case lastPuttDistanceM = "last_putt_distance_m"
    }
}

struct BalleTourGreenInput: Encodable, Hashable {
    var status: String
    var directions: [String]
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
    let teeClubID: Int?
    let defaultTeeClubID: Int?
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
        case teeClubID = "tee_club_id"
        case defaultTeeClubID = "default_tee_club_id"
        case teeClub = "tee_club"
        case driveDistanceM = "drive_distance_m"
        case greenResult = "green_result"
        case putts
        case lastPuttDistanceM = "last_putt_distance_m"
    }
}

struct BalleTourStatsResponse: Decodable {
    let tee: String
    let players: [BalleTourPlayerProfile]
    let stats: BalleTourDetailedStats
}

struct BalleTourAllStatsResponse: Decodable {
    let tee: String
    let rows: [BalleTourAllStatsRow]
}

struct BalleTourDetailedStats: Decodable {
    let selectedPlayer: BalleTourPlayerProfile?
    let selectedHoleNumber: Int?
    let roundCount: Int?
    let completedRoundCount: Int?
    let avgRound: Double?
    let bestRound: Int?
    let bestRoundVsPar: Int?
    let scoredHoles: Int?
    let birdiesOrBetter: Int?
    let pars: Int?
    let bogeysOrWorse: Int?
    let greenAttempts: Int?
    let greenHitPercent: Double?
    let bunkerPercent: Double?
    let sandSaveAttempts: Int?
    let sandSaves: Int?
    let sandSavePercent: Double?
    let avgPutts: Double?
    let avgLastPuttDistance: Double?
    let avgPuttMetersPerRound: Double?
    let strokesGained: BalleTourStrokesGained?
    let greenPoints: [BalleTourGreenPoint]?
    let greenDistribution: [BalleTourGreenDistribution]?
    let bestByHole: [String: Int?]?
    let clubRows: [BalleTourClubStats]?

    enum CodingKeys: String, CodingKey {
        case selectedPlayer = "selected_player"
        case selectedHoleNumber = "selected_hole_number"
        case roundCount = "round_count"
        case completedRoundCount = "completed_round_count"
        case avgRound = "avg_round"
        case bestRound = "best_round"
        case bestRoundVsPar = "best_round_vs_par"
        case scoredHoles = "scored_holes"
        case birdiesOrBetter = "birdies_or_better"
        case pars
        case bogeysOrWorse = "bogeys_or_worse"
        case greenAttempts = "green_attempts"
        case greenHitPercent = "green_hit_percent"
        case bunkerPercent = "bunker_percent"
        case sandSaveAttempts = "sand_save_attempts"
        case sandSaves = "sand_saves"
        case sandSavePercent = "sand_save_percent"
        case avgPutts = "avg_putts"
        case avgLastPuttDistance = "avg_last_putt_distance"
        case avgPuttMetersPerRound = "avg_putt_meters_per_round"
        case strokesGained = "strokes_gained"
        case greenPoints = "green_points"
        case greenDistribution = "green_distribution"
        case bestByHole = "best_by_hole"
        case clubRows = "club_rows"
    }
}

struct BalleTourStrokesGained: Decodable {
    let unitLabel: String?
    let total: Double?
    let teeToGreen: Double?
    let putting: Double?
    let greenResult: Double?

    enum CodingKeys: String, CodingKey {
        case unitLabel = "unit_label"
        case total
        case teeToGreen = "tee_to_green"
        case putting
        case greenResult = "green_result"
    }
}

struct BalleTourGreenPoint: Decodable, Identifiable {
    let status: String
    let x: Double
    let y: Double

    var id: String { "\(status)-\(x)-\(y)" }
}

struct BalleTourGreenDistribution: Decodable, Identifiable {
    let key: String
    let label: String
    let count: Int
    let percent: Double?

    var id: String { key }
}

struct BalleTourClubStats: Decodable, Identifiable {
    let name: String
    let count: Int
    let avg: Double

    var id: String { name }
}

struct BalleTourAllStatsRow: Decodable, Identifiable {
    let player: BalleTourPlayerProfile
    let completedRoundCount: Int?
    let avgRound: Double?
    let bestRound: Int?
    let greenHitPercent: Double?
    let bunkerPercent: Double?
    let sandSavePercent: Double?
    let avgPutts: Double?
    let avgLastPuttDistance: Double?
    let avgPuttMetersPerRound: Double?
    let birdiesOrBetter: Int?
    let pars: Int?
    let bogeysOrWorse: Int?
    let strokesGained: BalleTourStrokesGained?

    var id: Int { player.id }

    enum CodingKeys: String, CodingKey {
        case player
        case completedRoundCount = "completed_round_count"
        case avgRound = "avg_round"
        case bestRound = "best_round"
        case greenHitPercent = "green_hit_percent"
        case bunkerPercent = "bunker_percent"
        case sandSavePercent = "sand_save_percent"
        case avgPutts = "avg_putts"
        case avgLastPuttDistance = "avg_last_putt_distance"
        case avgPuttMetersPerRound = "avg_putt_meters_per_round"
        case birdiesOrBetter = "birdies_or_better"
        case pars
        case bogeysOrWorse = "bogeys_or_worse"
        case strokesGained = "strokes_gained"
    }
}
