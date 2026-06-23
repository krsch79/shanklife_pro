import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var session: SessionStore

    var body: some View {
        Group {
            if session.isLoggedIn {
                DashboardView()
            } else {
                LoginView()
            }
        }
        .task {
            await session.restore()
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(SessionStore())
}
