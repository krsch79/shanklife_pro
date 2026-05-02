import os
import shutil
import subprocess
import smtplib
from email.message import EmailMessage
from pathlib import Path


DEFAULT_RECIPIENT = "kristian.schiander@gmail.com"
LOG_PATH = Path(os.environ.get("SHANKLIFE_MAIL_LOG", "/tmp/shanklife_pro_mail.log"))


def _load_env_file():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _log(message):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{message}\n")


def _mail_config():
    _load_env_file()
    host = os.environ.get("SMTP_HOST", "").strip()
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    sender = os.environ.get("SMTP_FROM", "").strip() or username
    recipient = os.environ.get("TASK_NOTIFY_EMAIL", "").strip() or DEFAULT_RECIPIENT
    port = int(os.environ.get("SMTP_PORT", "587"))
    use_tls = os.environ.get("SMTP_USE_TLS", "1").strip().lower() not in ("0", "false", "no")
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "sender": sender,
        "recipient": recipient,
        "use_tls": use_tls,
    }


def send_mail(subject, body, *, recipient=None):
    config = _mail_config()
    target = recipient or config["recipient"]
    if not config["host"] and shutil.which("sendmail"):
        return _send_with_sendmail(subject, body, config["sender"] or "shanklife@localhost", target)

    missing = [key for key in ("host", "sender") if not config[key]]
    if not target:
        missing.append("recipient")
    if missing:
        _log(f"Mail ikke sendt, mangler {', '.join(missing)}. Subject: {subject}")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["sender"]
    message["To"] = target
    message.set_content(body)

    try:
        with smtplib.SMTP(config["host"], config["port"], timeout=20) as smtp:
            if config["use_tls"]:
                smtp.starttls()
            if config["username"] or config["password"]:
                smtp.login(config["username"], config["password"])
            smtp.send_message(message)
    except Exception as exc:
        _log(f"Mail feilet: {exc}. Subject: {subject}")
        return False

    _log(f"Mail sendt til {target}. Subject: {subject}")
    return True


def _send_with_sendmail(subject, body, sender, target):
    if not target:
        _log(f"Mail ikke sendt, mangler recipient. Subject: {subject}")
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = target
    message.set_content(body)
    try:
        subprocess.run(
            ["sendmail", "-t", "-oi"],
            input=message.as_string(),
            text=True,
            check=True,
            timeout=20,
        )
    except Exception as exc:
        _log(f"Sendmail feilet: {exc}. Subject: {subject}")
        return False
    _log(f"Mail sendt via sendmail til {target}. Subject: {subject}")
    return True


def send_task_complete(summary):
    return send_mail(
        "Codex-oppgave ferdig",
        f"Codex er ferdig med oppgaven.\n\n{summary}".strip(),
    )
