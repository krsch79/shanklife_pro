from datetime import datetime


def server_now():
    return datetime.now()


def to_server_time(value):
    if not value:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


def format_server_datetime(value):
    if not value:
        return "-"
    return to_server_time(value).strftime("%d.%m.%Y %H:%M")
