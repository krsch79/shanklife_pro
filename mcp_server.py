from mcp.server.fastmcp import FastMCP

from app import app as flask_app
from services.balletour_mcp import (
    get_balletour_overview,
    get_balletour_player_summary,
    list_balletour_players,
    list_balletour_rounds,
)
from services.golfbox import find_golfbox_availability
from services.golfbox import process_golfbox_prompt

mcp = FastMCP("Shanklife Pro BalleTour", json_response=True)


def _with_app_context(callback, *args, **kwargs):
    with flask_app.app_context():
        return callback(*args, **kwargs)


@mcp.tool()
def balletour_overview(tee: str = "gul") -> dict:
    """Hent BalleTour-oppsummering, rundetall og leaderboard for valgt tee."""
    return _with_app_context(get_balletour_overview, tee=tee)


@mcp.tool()
def balletour_players() -> dict:
    """List BalleTour-spillere med handicap og basisdata."""
    return _with_app_context(list_balletour_players)


@mcp.tool()
def balletour_rounds(status: str = "finished", player_name: str | None = None, limit: int = 10, tee: str = "gul") -> dict:
    """List BalleTour-runder, eventuelt filtrert på status, spiller og tee."""
    return _with_app_context(
        list_balletour_rounds,
        status=status,
        player_name=player_name,
        limit=limit,
        tee=tee,
    )


@mcp.tool()
def balletour_player_summary(player_name: str, tee: str = "gul") -> dict:
    """Hent BalleTour-sammendrag for en spiller."""
    return _with_app_context(get_balletour_player_summary, player_name=player_name, tee=tee)


@mcp.tool()
def golfbox_find_tee_times(
    course: str = "Ballerud",
    players: int = 2,
    play_date: str | None = None,
    time_from: str = "15:00",
    time_to: str = "17:00",
) -> dict:
    """Sjekk GolfBox-ledighet for en bane, antall spillere, dato og tidsvindu."""
    return _with_app_context(
        find_golfbox_availability,
        course=course,
        players=players,
        play_date=play_date,
        time_from=time_from,
        time_to=time_to,
    )


@mcp.tool()
def golfbox_prompt(prompt: str) -> dict:
    """Tolke en vanlig GolfBox-prompt og utfør støttet handling."""
    return _with_app_context(process_golfbox_prompt, prompt=prompt)


if __name__ == "__main__":
    mcp.run()
