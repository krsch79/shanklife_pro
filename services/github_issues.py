import os
from pathlib import Path

import httpx


class GitHubIssueError(RuntimeError):
    pass


LABELS = ("from-shanklife-admin", "ai-request", "needs-triage")


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


def _github_config():
    _load_env_file()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO", "").strip()
    if not token:
        raise GitHubIssueError("GITHUB_TOKEN mangler.")
    if not repo:
        raise GitHubIssueError("GITHUB_REPO mangler.")
    if "/" not in repo:
        raise GitHubIssueError("GITHUB_REPO må være på formatet owner/repo.")
    return token, repo


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _ensure_label(client, repo, label):
    response = client.post(
        f"https://api.github.com/repos/{repo}/labels",
        json={"name": label, "color": "0f766e"},
    )
    if response.status_code in (201, 422):
        return
    raise GitHubIssueError(f"Kunne ikke opprette label {label}: {response.status_code}")


def create_issue_for_ai_request(fix_request):
    token, repo = _github_config()
    creator = fix_request.created_by_user.username if fix_request.created_by_user else "ukjent"
    body = (
        "Opprettet fra Shanklife Pro admin.\n\n"
        f"Intern forespørsel: #{fix_request.id}\n"
        f"Opprettet av: {creator}\n\n"
        "Prompt:\n"
        f"{fix_request.prompt}\n"
    )

    with httpx.Client(headers=_headers(token), timeout=15) as client:
        for label in LABELS:
            _ensure_label(client, repo, label)
        response = client.post(
            f"https://api.github.com/repos/{repo}/issues",
            json={
                "title": f"AI request #{fix_request.id}",
                "body": body,
                "labels": list(LABELS),
            },
        )

    if response.status_code != 201:
        message = response.text[:300]
        raise GitHubIssueError(f"GitHub issue kunne ikke opprettes: {response.status_code} {message}")

    data = response.json()
    return {
        "number": data["number"],
        "url": data["html_url"],
    }
