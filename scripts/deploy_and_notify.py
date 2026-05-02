#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.github_issues import _github_config, _headers  # noqa: E402
from services.mailer import send_mail  # noqa: E402


def _update_issue_after_deploy(issue_number, success, details):
    if not issue_number:
        return
    token, repo = _github_config()
    with httpx.Client(headers=_headers(token), timeout=30) as client:
        for label in ("ready-to-deploy", "in-progress", "failed"):
            response = client.delete(f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels/{label}")
            if response.status_code not in (200, 404):
                response.raise_for_status()

        labels = ["deployed"] if success else ["failed"]
        response = client.post(
            f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels",
            json={"labels": labels},
        )
        response.raise_for_status()

        body = "Deploy fra Shanklife admin er fullført." if success else "Deploy fra Shanklife admin feilet."
        if details:
            body += f"\n\n```text\n{details[-1800:]}\n```"
        response = client.post(
            f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments",
            json={"body": body},
        )
        response.raise_for_status()

        if success:
            response = client.patch(
                f"https://api.github.com/repos/{repo}/issues/{issue_number}",
                json={"state": "closed", "state_reason": "completed"},
            )
            response.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description="Kjør deploy og send e-post når den er ferdig.")
    parser.add_argument("--issue", type=int, help="GitHub issue-nummer som deployen gjelder.")
    args = parser.parse_args()

    result = subprocess.run(
        ["./scripts/deploy.sh"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = result.stdout or ""
    success = result.returncode == 0
    _update_issue_after_deploy(args.issue, success, output)

    version = "ukjent"
    version_file = ROOT / "services" / "version.py"
    if version_file.exists():
        for line in version_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("APP_VERSION"):
                version = line.split("=", 1)[1].strip().strip('"')
                break

    subject = "Deploy fullført" if success else "Deploy feilet"
    if args.issue:
        subject += f" for issue #{args.issue}"
    body = (
        f"Deploy gjennom Shanklife admin er {'fullført' if success else 'feilet'}.\n\n"
        f"Issue: #{args.issue if args.issue else '-'}\n"
        f"Versjon: {version}\n"
        f"Status: {'OK' if success else 'FEILET'}\n\n"
        f"Siste logglinjer:\n{output[-1200:]}"
    )
    send_mail(subject, body)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
