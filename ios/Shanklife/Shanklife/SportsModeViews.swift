import SwiftUI
import WebKit

// Shared visual language. Dynamic surfaces keep native dark mode and Dynamic Type usable.
enum SportsPalette {
  static let ink = Color(red: 0.094, green: 0.165, blue: 0.255)
  static let lime = Color(red: 0.804, green: 0.965, blue: 0.325)
  static let background = Color(uiColor: .systemGroupedBackground)
  static let surface = Color(uiColor: .secondarySystemGroupedBackground)
  static let action = Color(
    uiColor: UIColor {
      $0.userInterfaceStyle == .dark
        ? UIColor(red: 0.804, green: 0.965, blue: 0.325, alpha: 1)
        : UIColor(red: 0.094, green: 0.165, blue: 0.255, alpha: 1)
    })
}

struct SportsPanel<Content: View>: View {
  @ViewBuilder var content: () -> Content
  var body: some View {
    VStack(alignment: .leading, spacing: 16, content: content).padding(20).frame(
      maxWidth: .infinity, alignment: .leading
    ).background(SportsPalette.surface, in: RoundedRectangle(cornerRadius: 8))
  }
}

struct SportsHomeView: View {
  @EnvironmentObject private var session: SessionStore
  @State private var overview: SportsOverview?
  @State private var errorMessage: String?
  @State private var loading = false
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 22) {
        if let errorMessage { SportsError(message: errorMessage) { Task { await load() } } }
        if let o = overview {
          Text("DITT SPILL · DIN TOUR").font(.caption2.weight(.semibold)).tracking(2)
            .foregroundStyle(.secondary)
          Text("Hei, \(o.name).").font(.largeTitle.weight(.heavy))
          VStack(alignment: .leading, spacing: 20) {
            Text(
              o.activeRounds.isEmpty ? "FØRSTE TEE.\nFULL KONTROLL." : "RUNDEN DIN.\nRETT VIDERE."
            ).font(.system(.largeTitle, design: .default).weight(.heavy)).tracking(-1)
            Text("Score, statistikk og fellesskapet ditt. Samlet.").font(.subheadline)
              .foregroundStyle(.white.opacity(0.8))
            if let active = o.activeRounds.first {
              NavigationLink {
                SportsRoundDestination(row: active)
              } label: {
                heroAction("Fortsett \(active.course)")
              }.accessibilityIdentifier("sports-resume-round")
            } else {
              NavigationLink {
                SportsNewRoundView()
              } label: {
                heroAction("Start en runde")
              }
            }
            if let last = o.recentRounds.first {
              Divider().overlay(.white.opacity(0.25))
              Text("SISTE RUNDE").font(.caption2.weight(.semibold)).tracking(2)
              ViewThatFits(in: .horizontal) {
                HStack(alignment: .center, spacing: 18) {
                  heroScore(last)
                  heroDetail(last)
                }
                VStack(alignment: .leading) {
                  heroScore(last)
                  heroDetail(last)
                }
              }
            }
          }.padding(25).frame(maxWidth: .infinity, alignment: .leading).foregroundStyle(.white)
            .background(SportsPalette.ink)
          HStack(alignment: .top, spacing: 18) {
            metric(
              "Handicap", o.hcp.map { $0.formatted(.number.precision(.fractionLength(1))) } ?? "—")
            metric("Mine runder", String(o.roundCount))
            metric(
              o.tour == nil ? "Pågår" : "Tour · gul",
              o.tour.map { "\($0.rounds)/\($0.required)" } ?? String(o.activeRounds.count))
          }
          SportsPanel {
            HStack {
              Text("Siste runder").font(.headline)
              Spacer()
              NavigationLink("Alle") { SportsRoundsView() }.font(.subheadline)
            }
            if o.recentRounds.isEmpty { Text("Ingen runder ennå.").foregroundStyle(.secondary) }
            ForEach(o.recentRounds.prefix(3)) { row in
              NavigationLink {
                SportsRoundDestination(row: row)
              } label: {
                SportsRoundRow(row: row)
              }.buttonStyle(.plain)
            }
          }
          SportsPanel {
            Text("BALLETOUR").font(.caption.weight(.semibold)).tracking(2)
            if let tour = o.tour {
              Text(tour.course).font(.title2.weight(.bold))
              Text(tour.totalVsPar).font(.largeTitle.weight(.heavy))
              Text("Summert mot par · \(tour.rounds) runder · \(tour.tee) tee").font(.subheadline)
                .foregroundStyle(.secondary)
              Text(
                tour.qualified
                  ? "Kvalifisert"
                  : "Under kvalifisering · \(max(0,tour.required-tour.rounds)) runder igjen"
              ).font(.subheadline.weight(.semibold))
              NavigationLink("Åpne touren →") { BalleTourView() }.buttonStyle(.bordered)
            } else {
              Text("Touren har egne medlemmer og konkurranseregler.").foregroundStyle(.secondary)
            }
          }
        } else if loading {
          ProgressView("Laster ditt spill").frame(maxWidth: .infinity)
        }
      }.padding(20)
    }.background(SportsPalette.background).navigationTitle("SHANKLIFE /")
      .navigationBarTitleDisplayMode(.inline)
      .task { await load() }.refreshable { await load() }
  }
  private func heroAction(_ text: String) -> some View {
    HStack {
      Text(text)
      Spacer()
      Image(systemName: "arrow.right")
    }.font(.subheadline.weight(.bold)).padding(15).foregroundStyle(SportsPalette.ink).background(
      SportsPalette.lime, in: RoundedRectangle(cornerRadius: 5))
  }
  private func heroScore(_ row: SportsRoundItem) -> some View {
    Text(row.score).font(.system(size: 58, weight: .heavy)).foregroundStyle(SportsPalette.lime)
      .fixedSize(horizontal: false, vertical: true)
  }
  private func heroDetail(_ row: SportsRoundItem) -> some View {
    VStack(alignment: .leading, spacing: 5) {
      Text(row.course).font(.headline)
      Text("\(row.lengthLabel) · \(row.format)").font(.caption)
      if !row.toPar.isEmpty { Text("\(row.toPar) mot par").font(.caption) }
    }
  }
  private func metric(_ title: String, _ value: String) -> some View {
    VStack(alignment: .leading, spacing: 7) {
      Text(title).font(.caption).foregroundStyle(.secondary)
      Text(value).font(.title2.weight(.heavy))
    }.frame(maxWidth: .infinity, alignment: .leading)
  }
  private func load() async {
    guard let client = session.client, !loading else { return }
    loading = true
    defer { loading = false }
    do {
      overview = try await client.sportsOverview()
      errorMessage = nil
    } catch { errorMessage = error.localizedDescription }
  }
}

struct SportsError: View {
  let message: String
  var retry: () -> Void
  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Label(message, systemImage: "exclamationmark.triangle").foregroundStyle(.red)
      Button("Prøv igjen", action: retry).buttonStyle(.bordered)
    }.padding().frame(maxWidth: .infinity, alignment: .leading).background(
      SportsPalette.surface, in: RoundedRectangle(cornerRadius: 8))
  }
}

struct SportsRoundRow: View {
  let row: SportsRoundItem
  var body: some View {
    HStack(alignment: .top, spacing: 12) {
      VStack(alignment: .leading, spacing: 5) {
        Text(row.course).font(.subheadline.weight(.semibold)).foregroundStyle(.primary)
        Text("\(row.dateDisplay) · \(row.lengthLabel)").font(.caption).foregroundStyle(.secondary)
        Text(
          row.isPrivate
            ? "Privat · \(row.environment == "simulator" ? "Simulator" : row.environment == "outdoor" ? "Utendørs" : "Ukjent miljø")"
            : row.isTour ? "BalleTour · \(row.tee) tee" : row.format
        ).font(.caption2).foregroundStyle(.secondary)
        if row.status == "ongoing" {
          Text(row.isPrivate ? "Delvis spilt" : "Pågående").font(.caption2.weight(.semibold))
        }
      }
      Spacer(minLength: 4)
      VStack(alignment: .trailing, spacing: 4) {
        Text(row.score).font(.title2.weight(.heavy)).foregroundStyle(.primary)
        if !row.toPar.isEmpty { Text(row.toPar).font(.caption).foregroundStyle(.secondary) }
      }
    }.padding(.vertical, 12)
  }
}

struct SportsRoundsView: View {
  @EnvironmentObject private var session: SessionStore
  @State private var rows: [SportsRoundItem] = []
  @State private var source = "all"
  @State private var environment = "all"
  @State private var errorMessage: String?
  @State private var loading = false
  @State private var requestID = UUID()
  var body: some View {
    List {
      Section {
        Picker("Rundetype", selection: $source) {
          Text("Alle").tag("all")
          if session.user?.products.shanklife == true {
            Text("Vanlige runder").tag("shanklife")
            Text("TrackMan").tag("trackman")
          }
          if session.user?.products.balletour == true { Text("BalleTour").tag("balletour") }
        }
        Picker("Miljø", selection: $environment) {
          Text("Inne og ute").tag("all")
          Text("Utendørs").tag("outdoor")
          Text("Simulator").tag("simulator")
        }
      }
      if let errorMessage {
        Section { SportsError(message: errorMessage) { Task { await load() } } }
      }
      if loading && rows.isEmpty { ProgressView("Laster runder") }
      Section("\(rows.count) runder") {
        ForEach(rows) { row in
          NavigationLink {
            SportsRoundDestination(row: row)
          } label: {
            SportsRoundRow(row: row)
          }
        }
        if rows.isEmpty && !loading && errorMessage == nil {
          Text("Ingen runder i dette utvalget.").foregroundStyle(.secondary)
        }
      }
    }.navigationTitle("Rundene dine").toolbar {
      NavigationLink {
        SportsNewRoundView()
      } label: {
        Image(systemName: "plus")
      }.accessibilityLabel("Ny runde")
    }
    .task { await load() }.refreshable { await load() }.onChange(of: source) { _, _ in
      Task { await load() }
    }.onChange(of: environment) { _, _ in Task { await load() } }
  }
  private func load() async {
    guard let client = session.client else { return }
    let token = UUID()
    requestID = token
    loading = true
    defer { if requestID == token { loading = false } }
    do {
      let result = try await client.sportsRounds(source: source, environment: environment)
      guard requestID == token else { return }
      rows = result.rounds
      errorMessage = nil
    } catch { if requestID == token { errorMessage = error.localizedDescription } }
  }
}

struct SportsRoundDestination: View {
  let row: SportsRoundItem
  var body: some View {
    if row.source == "trackman" {
      SportsWebScreen(path: row.url, title: row.course)
    } else if row.isTour && row.status == "ongoing" {
      BalleTourScoringLoaderView(roundID: row.roundID)
    } else if row.isTour {
      BalleTourRoundDetailView(roundID: row.roundID)
    } else if row.status == "ongoing" {
      ShanklifeScoringLoaderView(roundID: row.roundID)
    } else {
      SportsWebScreen(path: row.url, title: row.course)
    }
  }
}

struct SportsNewRoundView: View {
  @EnvironmentObject private var session: SessionStore
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("KLAR FOR FØRSTE TEE?").font(.title.weight(.heavy))
        Text(
          "Tourtilknytningen følger valget ditt. En vanlig runde på Ballerud teller ikke automatisk i BalleTour."
        ).font(.subheadline).foregroundStyle(.secondary)
        if session.user?.products.shanklife == true {
          NavigationLink {
            ShanklifeNewRoundView()
          } label: {
            SportsPanel {
              Label("En vanlig runde", systemImage: "figure.golf").font(.title3.weight(.bold))
              Text("Valgfri bane, spilleform og statistikk.").font(.subheadline)
            }
          }.buttonStyle(.plain)
        }
        if session.user?.products.balletour == true {
          NavigationLink {
            BalleTourNewRoundView()
          } label: {
            SportsPanel {
              Label("En BalleTour-runde", systemImage: "trophy").font(.title3.weight(.bold))
              Text("Tourens bane, medlemmer og statistikkkrav.").font(.subheadline)
            }
          }.buttonStyle(.plain)
        }
      }.padding(20)
    }.background(SportsPalette.background).navigationTitle("Ny runde")
  }
}

struct SportsInsightView: View {
  @EnvironmentObject private var session: SessionStore
  @State private var stats: SportsStats?
  @State private var environment = "all"
  @State private var errorMessage: String?
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 22) {
        Text("TREN PÅ DET\nSOM TELLER.").font(.largeTitle.weight(.heavy)).tracking(-1)
        if session.user?.products.shanklife == true {
          Picker("Miljø", selection: $environment) {
            Text("Inne og ute").tag("all")
            Text("Utendørs").tag("outdoor")
            Text("Simulator").tag("simulator")
          }.pickerStyle(.segmented)
          if let stats {
            SportsPanel {
              Text("\(stats.completedRounds) fullførte runder · \(stats.scoredHoles) hull").font(
                .caption
              ).foregroundStyle(.secondary)
              stat("Snitt mot par", stats.averageVsPar, suffix: "")
              stat("GIR", stats.gir, suffix: " %", sample: stats.girAttempts)
              stat("Fairwaytreff", stats.fairway, suffix: " %", sample: stats.fairwayAttempts)
              stat("Putter inkl. gimmies", stats.putts, suffix: "", sample: stats.puttingHoles)
              Text(
                "Automatisk putting utelates fra målt putting. BalleTour analyseres i sitt eget tourgrunnlag."
              ).font(.caption).foregroundStyle(.secondary)
              NavigationLink("Hele statistikken →") {
                SportsWebScreen(path: "/stats/?environment=\(environment)", title: "Statistikk")
              }
              NavigationLink("Spør om dette grunnlaget") {
                SportsWebScreen(
                  path: "/stats/ai?environment=\(environment)", title: "AI-statistikk")
              }
            }
          }
        }
        if let errorMessage { SportsError(message: errorMessage) { Task { await load() } } }
        if session.user?.products.balletour == true {
          SportsPanel {
            Text("BALLETOUR").font(.caption.weight(.semibold)).tracking(2)
            Text("Hull, putting og køllevalg.").font(.title2.weight(.bold))
            Text("Intern strokes gained sammenligner mot BalleTour-feltet.").font(.subheadline)
              .foregroundStyle(.secondary)
            NavigationLink("Tourstatistikk →") { BalleTourStatsView(tee: "gul") }
            NavigationLink("Spør om touren") {
              SportsWebScreen(path: "/balletour/stats/ai", title: "Tourinnsikt")
            }
          }
        }
      }.padding(20)
    }.background(SportsPalette.background).navigationTitle("Innsikt").task { await load() }
      .onChange(of: environment) { _, _ in Task { await load() } }
  }
  private func stat(_ title: String, _ value: Double?, suffix: String, sample: Int? = nil)
    -> some View
  {
    HStack {
      VStack(alignment: .leading) {
        Text(title).font(.subheadline)
        if let sample {
          Text("\(sample) registrerte hull").font(.caption2).foregroundStyle(.secondary)
        }
      }
      Spacer()
      Text(value.map { $0.formatted(.number.precision(.fractionLength(1))) + suffix } ?? "—").font(
        .title2.weight(.heavy))
    }
  }
  private func load() async {
    guard session.user?.products.shanklife == true, let client = session.client else { return }
    do {
      stats = try await client.sportsStats(environment: environment).stats
      errorMessage = nil
    } catch { errorMessage = error.localizedDescription }
  }
}

struct SportsTourView: View {
  @EnvironmentObject private var session: SessionStore
  var body: some View {
    if session.user?.products.balletour == true {
      BalleTourView()
    } else {
      ContentUnavailableView(
        "BalleTour", systemImage: "trophy",
        description: Text(
          "Touren har egne medlemmer og konkurranseregler. Du har ikke medlemstilgang."))
    }
  }
}

// Shared website functions use the same server session, never credentials in JavaScript or URLs.
struct SportsWebScreen: View {
  @EnvironmentObject private var session: SessionStore
  let path: String
  let title: String
  var body: some View {
    Group {
      if let base = URL(string: session.baseURLText), let url = URL(string: path, relativeTo: base)
      {
        SportsAuthenticatedWebView(url: url.absoluteURL)
      } else {
        Text("Ugyldig adresse.")
      }
    }.navigationTitle(title).navigationBarTitleDisplayMode(.inline)
      .toolbar(.hidden, for: .tabBar)
  }
}
struct SportsAuthenticatedWebView: UIViewRepresentable {
  let url: URL
  func makeUIView(context: Context) -> WKWebView {
    let config = WKWebViewConfiguration()
    config.websiteDataStore = .nonPersistent()
    let web = WKWebView(frame: .zero, configuration: config)
    Task { @MainActor in
      let cookies = HTTPCookieStorage.shared.cookies(for: url) ?? []
      for cookie in cookies {
        await web.configuration.websiteDataStore.httpCookieStore.setCookie(cookie)
      }
      web.load(URLRequest(url: url))
    }
    return web
  }
  func updateUIView(_ uiView: WKWebView, context: Context) {}
}

// No implicit par and no offline queue. A network failure leaves the current input intact.
struct SportsScoreControl: View {
  @Binding var score: Int?
  let par: Int
  let options: [Int]
  var body: some View {
    VStack(spacing: 12) {
      HStack {
        Button {
          step(-1)
        } label: {
          Image(systemName: "minus").frame(width: 48, height: 48)
        }.accessibilityLabel("Ett slag mindre")
        Spacer()
        Menu {
          Button("Ikke registrert") { score = nil }
          ForEach(options, id: \.self) { value in Button("\(value) slag") { score = value } }
        } label: {
          Text(score.map(String.init) ?? "—").font(
            .system(size: 42, weight: .heavy, design: .rounded)
          ).monospacedDigit().frame(minWidth: 64, minHeight: 52)
        }
        .accessibilityLabel("Score, \(score.map(String.init) ?? "ikke registrert")")
        .accessibilityIdentifier("sports-score-value")
        Spacer()
        Button {
          step(1)
        } label: {
          Image(systemName: "plus").frame(width: 48, height: 48)
        }.accessibilityLabel("Ett slag mer")
      }.buttonStyle(.borderless)
      HStack(spacing: 8) {
        choice("Birdie", par - 1)
        choice("Par", par)
        choice("Bogey", par + 1)
      }
    }
  }
  private func choice(_ title: String, _ value: Int) -> some View {
    Button {
      score = value
    } label: {
      VStack {
        Text(title).font(.caption.weight(.semibold))
        Text("\(value)").font(.headline)
      }.frame(maxWidth: .infinity, minHeight: 48).background(
        score == value ? SportsPalette.lime : Color.secondary.opacity(0.1),
        in: RoundedRectangle(cornerRadius: 8)
      ).foregroundStyle(score == value ? SportsPalette.ink : Color.primary)
    }.buttonStyle(.borderless).disabled(!options.contains(value)).accessibilityAddTraits(
      score == value ? .isSelected : []
    ).accessibilityIdentifier("sports-score-\(value)")
  }
  private func step(_ amount: Int) {
    let target = (score ?? par) + amount
    if options.contains(target) { score = target }
  }
}
