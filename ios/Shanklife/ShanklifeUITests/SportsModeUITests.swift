import XCTest

// Run against the disposable local demo server described in IMPLEMENTATION_STATUS.md.
final class SportsModeUITests: XCTestCase {
  override func setUp() {
    super.setUp()
    continueAfterFailure = false
  }
  // The disposable fixture has a future-dated two-place search ready before launch.
  func testStarttiderFromProfileCanReviewFewerPlayers() throws {
    let app = XCUIApplication()
    app.launchEnvironment["SPORTS_UI_QA"] = "1"
    app.launch()
    XCTAssertTrue(app.tabBars.buttons["Profil"].waitForExistence(timeout: 30), app.debugDescription)
    app.tabBars.buttons["Profil"].tap()
    XCTAssertTrue(app.buttons["Starttider"].waitForExistence(timeout: 10), app.debugDescription)
    app.buttons["Starttider"].tap()
    let web = app.webViews.firstMatch
    XCTAssertTrue(web.waitForExistence(timeout: 20), app.debugDescription)
    XCTAssertTrue(web.staticTexts["Starttider."].waitForExistence(timeout: 20), app.debugDescription)
    XCTAssertFalse(app.tabBars.firstMatch.exists)
    XCTAssertTrue(web.buttons["Finn tid"].exists)
    XCTAssertTrue(web.buttons["Mine tider 1"].exists || web.buttons["Mine tider 0"].exists)
    let choose = web.buttons["Velg tid"].firstMatch
    if !choose.isHittable { web.swipeUp() }
    XCTAssertTrue(choose.waitForExistence(timeout: 15), app.debugDescription)
    choose.tap()
    XCTAssertTrue(web.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Søkt etter plass til 2")).firstMatch.waitForExistence(timeout: 15), app.debugDescription)
    attach(app, "Starttider på iPhone med valgfri medspiller")
    let review = web.buttons["Kontroller booking →"]
    if !review.isHittable { web.swipeUp() }
    XCTAssertTrue(review.isEnabled)
    review.tap()
    XCTAssertTrue(web.buttons["Bekreft booking"].waitForExistence(timeout: 15), app.debugDescription)
    XCTAssertTrue(web.staticTexts["Kristian"].exists, app.debugDescription)
    attach(app, "Bookingoppsummering med bare spiller 1")
    // Review only: never submit a real booking from this native navigation test.
  }
  func testPersonalNavigationAndAuthenticatedWebsite() throws {
    let app = XCUIApplication()
    app.launchEnvironment["SPORTS_UI_QA"] = "1"
    app.launch()
    XCTAssertTrue(app.tabBars.buttons["Hjem"].waitForExistence(timeout: 30), app.debugDescription)
    attach(app, "Hjem")
    for tab in ["Runder", "Innsikt", "Tour", "Profil"] {
      app.tabBars.buttons[tab].tap()
      XCTAssertTrue(app.navigationBars.firstMatch.waitForExistence(timeout: 10))
      attach(app, tab)
    }
    app.buttons["Konto og integrasjoner"].tap()
    XCTAssertTrue(app.webViews.firstMatch.waitForExistence(timeout: 15))
    XCTAssertTrue(
      app.webViews.staticTexts["Min side"].waitForExistence(timeout: 20), app.debugDescription)
    XCTAssertFalse(app.webViews.secureTextFields["Passord"].exists)
    XCTAssertFalse(app.tabBars.firstMatch.exists)
    attach(app, "Felles profil med serverinnlogging")
  }
  func testOnlineScoreSurvivesPreviousAndNextHole() throws {
    let app = XCUIApplication()
    app.launchEnvironment["SPORTS_UI_QA"] = "1"
    app.launch()
    let resume = app.buttons["sports-resume-round"]
    XCTAssertTrue(resume.waitForExistence(timeout: 30), app.debugDescription)
    resume.tap()
    let bogey = app.buttons["sports-score-5"]
    XCTAssertTrue(bogey.waitForExistence(timeout: 20), app.debugDescription)
    bogey.tap()
    app.buttons["Lagre"].tap()
    XCTAssertTrue(app.buttons["Neste"].waitForExistence(timeout: 15))
    app.buttons["Neste"].tap()
    XCTAssertTrue(app.staticTexts["Hull 2"].waitForExistence(timeout: 15), app.debugDescription)
    app.buttons["Forrige"].tap()
    XCTAssertTrue(app.staticTexts["Hull 1"].waitForExistence(timeout: 15), app.debugDescription)
    XCTAssertEqual(app.buttons["sports-score-value"].label, "Score, 5", app.debugDescription)
    attach(app, "Lagret score ved hullbytte")
    app.buttons["Avslutt runde"].tap()
    XCTAssertTrue(
      app.buttons["Se resultat og scorekort"].waitForExistence(timeout: 15), app.debugDescription)
    XCTAssertFalse(app.buttons["sports-score-5"].exists)
    attach(app, "Fullført runde")
  }
  private func attach(_ app: XCUIApplication, _ name: String) {
    let artifact = XCTAttachment(screenshot: app.screenshot())
    artifact.name = name
    artifact.lifetime = .keepAlways
    add(artifact)
  }
}
