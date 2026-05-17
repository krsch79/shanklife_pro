from pathlib import Path
import json

from services.balletour import get_balletour_memberships
from services.mailer import send_mail
from services.version import APP_VERSION, get_changelog_entries


def _balletour_users():
    users = []
    seen_user_ids = set()
    for membership in get_balletour_memberships():
        for user in membership.player.user_accounts:
            if user.id in seen_user_ids:
                continue
            seen_user_ids.add(user.id)
            users.append(user)
    return users


def _selected_player_ids(user):
    raw_value = (user.balletour_round_notification_player_ids or "").strip()
    if not raw_value:
        return set()
    try:
        values = json.loads(raw_value)
    except json.JSONDecodeError:
        return set()
    return {int(value) for value in values if str(value).isdigit()}


def _wants_round_notification_for(user, round_obj):
    selected_player_ids = _selected_player_ids(user)
    if not selected_player_ids:
        return True

    round_player_ids = {
        round_player.player_id
        for round_player in round_obj.round_players
        if round_player.player_id
    }
    return bool(selected_player_ids & round_player_ids)


def balletour_round_finished_recipients(round_obj):
    return [
        user
        for user in _balletour_users()
        if (user.email or "").strip()
        and user.email_notifications_enabled
        and user.notify_balletour_round_finished
        and _wants_round_notification_for(user, round_obj)
    ]


def version_update_recipients():
    return [
        user
        for user in _balletour_users()
        if (user.email or "").strip()
        and user.email_notifications_enabled
        and user.notify_version_updates
    ]


def send_balletour_round_finished_notifications(round_obj, subject, body):
    sent = 0
    for user in balletour_round_finished_recipients(round_obj):
        if send_mail(subject, body, recipient=user.email):
            sent += 1
    return sent


def send_version_update_notifications(instance_path):
    entries = get_changelog_entries()
    if not entries:
        return 0

    latest = entries[0]
    if latest["version"] != APP_VERSION:
        return 0

    marker_dir = Path(instance_path) / "notification_markers"
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker_path = marker_dir / f"version-{APP_VERSION}.sent"
    if marker_path.exists():
        return 0

    changes = "\n".join(f"- {change}" for change in latest["changes"])
    body = (
        f"Shanklife Pro er oppdatert til versjon {APP_VERSION}.\n\n"
        f"Endringer:\n{changes}"
    ).strip()

    sent = 0
    for user in version_update_recipients():
        if send_mail(f"Shanklife Pro v{APP_VERSION}", body, recipient=user.email):
            sent += 1

    marker_path.write_text(f"Sent to {sent} recipient(s).\n", encoding="utf-8")
    return sent
