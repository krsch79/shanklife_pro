import Foundation

enum APIClientError: LocalizedError {
    case invalidBaseURL
    case invalidResponse
    case server(String)

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL:
            return "Ugyldig serveradresse."
        case .invalidResponse:
            return "Serveren svarte ikke som forventet."
        case .server(let message):
            return message
        }
    }
}

struct APIClient {
    var baseURL: URL
    var session: URLSession = .shared

    func login(username: String, password: String) async throws -> AppUser {
        let response: LoginResponse = try await request(
            path: "/api/v1/auth/login",
            method: "POST",
            body: ["username": username, "password": password]
        )
        return response.user
    }

    func me() async throws -> AppUser {
        let response: MeResponse = try await request(path: "/api/v1/auth/me")
        return response.user
    }

    func logout() async throws {
        let _: EmptyResponse = try await request(path: "/api/v1/auth/logout", method: "POST")
    }

    func bootstrap() async throws -> BootstrapResponse {
        try await request(path: "/api/v1/bootstrap")
    }

    func shanklifeOverview() async throws -> OverviewResponse {
        try await request(path: "/api/v1/shanklife/overview")
    }

    func shanklifeSetup() async throws -> ShanklifeSetupResponse {
        try await request(path: "/api/v1/shanklife/setup")
    }

    func shanklifeCourses() async throws -> ShanklifeCoursesResponse {
        try await request(path: "/api/v1/shanklife/courses")
    }

    func createShanklifeCourse(_ body: ShanklifeCourseCreateRequest) async throws -> ShanklifeCourse {
        try await request(path: "/api/v1/shanklife/courses", method: "POST", encodableBody: body)
    }

    func shanklifeRounds(status: String = "all") async throws -> ShanklifeRoundsResponse {
        try await request(path: "/api/v1/shanklife/rounds?status=\(status)")
    }

    func shanklifeRoundDetail(roundID: Int) async throws -> ShanklifeRoundDetail {
        try await request(path: "/api/v1/shanklife/rounds/\(roundID)")
    }

    func createShanklifeRound(_ body: ShanklifeCreateRoundRequest) async throws -> ShanklifeRoundDetail {
        try await request(path: "/api/v1/shanklife/rounds", method: "POST", encodableBody: body)
    }

    func saveShanklifeHole(roundID: Int, holeNumber: Int, body: ShanklifeSaveHoleRequest) async throws -> ShanklifeRoundDetail {
        try await request(path: "/api/v1/shanklife/rounds/\(roundID)/holes/\(holeNumber)", method: "PUT", encodableBody: body)
    }

    func finishShanklifeRound(roundID: Int) async throws -> ShanklifeRoundDetail {
        try await request(path: "/api/v1/shanklife/rounds/\(roundID)/finish", method: "POST")
    }

    func balletourOverview() async throws -> OverviewResponse {
        try await request(path: "/api/v1/balletour/overview")
    }

    func balletourOverview(tee: String) async throws -> BalleTourOverviewResponse {
        try await request(path: "/api/v1/balletour/overview?tee=\(tee)")
    }

    func balletourPlayers() async throws -> BalleTourPlayersResponse {
        try await request(path: "/api/v1/balletour/players")
    }

    func balletourRounds(status: String, tee: String, limit: Int = 30) async throws -> BalleTourRoundsResponse {
        try await request(path: "/api/v1/balletour/rounds?status=\(status)&tee=\(tee)&limit=\(limit)")
    }

    func balletourMe(tee: String) async throws -> BalleTourPlayerSummaryResponse {
        try await request(path: "/api/v1/balletour/me?tee=\(tee)")
    }

    func balletourPlayerSummary(playerID: Int, tee: String) async throws -> BalleTourPlayerSummaryResponse {
        try await request(path: "/api/v1/balletour/players/\(playerID)/summary?tee=\(tee)")
    }

    func balletourRoundDetail(roundID: Int) async throws -> BalleTourRoundDetail {
        try await request(path: "/api/v1/balletour/rounds/\(roundID)")
    }

    func balletourRoundSetup() async throws -> BalleTourRoundSetup {
        try await request(path: "/api/v1/balletour/round-setup")
    }

    func createBalleTourRound(_ body: BalleTourCreateRoundRequest) async throws -> BalleTourRoundDetail {
        try await request(path: "/api/v1/balletour/rounds", method: "POST", encodableBody: body)
    }

    func saveBalleTourHole(roundID: Int, holeNumber: Int, body: BalleTourSaveHoleRequest) async throws -> BalleTourRoundDetail {
        try await request(path: "/api/v1/balletour/rounds/\(roundID)/holes/\(holeNumber)", method: "PUT", encodableBody: body)
    }

    func finishBalleTourRound(roundID: Int) async throws -> BalleTourRoundDetail {
        try await request(path: "/api/v1/balletour/rounds/\(roundID)/finish", method: "POST")
    }

    func balletourStats(tee: String, playerID: Int? = nil, hole: Int? = nil) async throws -> BalleTourStatsResponse {
        var path = "/api/v1/balletour/stats?tee=\(tee)"
        if let playerID {
            path += "&player_id=\(playerID)"
        }
        if let hole {
            path += "&hole=\(hole)"
        }
        return try await request(path: path)
    }

    func balletourAllStats(tee: String) async throws -> BalleTourAllStatsResponse {
        try await request(path: "/api/v1/balletour/stats/all?tee=\(tee)")
    }

    private func request<Response: Decodable>(
        path: String,
        method: String = "GET",
        body: [String: String]? = nil
    ) async throws -> Response {
        try await request(path: path, method: method, encodableBody: body)
    }

    private func request<Response: Decodable, Body: Encodable>(
        path: String,
        method: String = "GET",
        encodableBody: Body? = nil
    ) async throws -> Response {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw APIClientError.invalidBaseURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        if let encodableBody {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(encodableBody)
        }

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIClientError.invalidResponse
        }

        if (200..<300).contains(httpResponse.statusCode) {
            if Response.self == EmptyResponse.self {
                return EmptyResponse() as! Response
            }
            return try JSONDecoder().decode(Response.self, from: data)
        }

        if let apiError = try? JSONDecoder().decode(APIErrorEnvelope.self, from: data) {
            throw APIClientError.server(apiError.error.message)
        }

        throw APIClientError.invalidResponse
    }
}

struct EmptyResponse: Decodable {}
