import XCTest

// Run against the disposable local demo server described in IMPLEMENTATION_STATUS.md.
final class SportsModeUITests: XCTestCase {
  override func setUp() {
    super.setUp()
    continueAfterFailure = false
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
