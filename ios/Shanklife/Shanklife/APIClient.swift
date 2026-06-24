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

    private func request<Response: Decodable>(
        path: String,
        method: String = "GET",
        body: [String: String]? = nil
    ) async throws -> Response {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw APIClientError.invalidBaseURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(body)
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
