import os
from datetime import datetime
from pathlib import Path

import httpx


class GitHubIssueError(RuntimeError):
    pass


LABELS = {
    "from-shanklife-admin": {
        "color": "0f766e",
        "description": "Opprettet fra Shanklife Pro admin.",
    },
    "ai-request": {
        "color": "2563eb",
        "description": "Forespørsel som skal behandles av AI/Codex.",
    },
    "needs-triage": {
        "color": "f59e0b",
        "description": "Må vurderes før arbeid starter.",
    },
    "in-progress": {
        "color": "7c3aed",
        "description": "Arbeid er startet.",
    },
    "ready-to-deploy": {
        "color": "16a34a",
        "description": "Endringen er klar for deploy.",
    },
    "deployed": {
        "color": "0f766e",
        "description": "Endringen er deployet.",
    },
    "failed": {
        "color": "dc2626",
        "description": "Automatisk AI-jobb feilet.",
    },
}
DEFAULT_LABELS = ("from-shanklife-admin", "ai-request", "needs-triage")


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


def _parse_github_datetime(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _issue_snapshot(data):
    labels = [label["name"] for label in data.get("labels", [])]
    return {
        "number": data["number"],
        "url": data["html_url"],
        "state": data.get("state"),
        "labels": labels,
        "updated_at": _parse_github_datetime(data.get("updated_at")),
    }


def apply_issue_snapshot(fix_request, issue):
    fix_request.github_issue_number = issue["number"]
    fix_request.github_issue_url = issue["url"]
    fix_request.github_issue_state = issue.get("state")
    fix_request.github_issue_labels = ", ".join(issue.get("labels", [])) or None
    fix_request.github_issue_updated_at = issue.get("updated_at")
    fix_request.github_sync_error = None


def _ensure_label(client, repo, label):
    config = LABELS[label]
    response = client.post(
        f"https://api.github.com/repos/{repo}/labels",
        json={"name": label, "color": config["color"], "description": config["description"]},
    )
    if response.status_code in (201, 422):
        return
    raise GitHubIssueError(f"Kunne ikke opprette label {label}: {response.status_code}")


def create_issue_for_ai_request(fix_request):
    token, repo = _github_config()
    creator = fix_request.created_by_user.username if fix_request.created_by_user else "ukjent"
    body = (
        "## Kilde\n"
        "Opprettet fra Shanklife Pro admin.\n\n"
        f"- Intern forespørsel: #{fix_request.id}\n"
        f"- Opprettet av: {creator}\n\n"
        "## Prompt\n"
        f"{fix_request.prompt}\n\n"
        "## Arbeidsflyt\n"
        "- Vurder feilen/endringen.\n"
        "- Lag branch/commit med kort, sporbar beskrivelse.\n"
        "- Oppdater versjon og changelog ved kodeendring.\n"
        "- Deploy først etter verifisering.\n"
    )

    with httpx.Client(headers=_headers(token), timeout=15) as client:
        for label in LABELS:
            _ensure_label(client, repo, label)
        response = client.post(
            f"https://api.github.com/repos/{repo}/issues",
            json={
                "title": f"AI request #{fix_request.id}",
                "body": body,
                "labels": list(DEFAULT_LABELS),
            },
        )

    if response.status_code != 201:
        message = response.text[:300]
        raise GitHubIssueError(f"GitHub issue kunne ikke opprettes: {response.status_code} {message}")

    return _issue_snapshot(response.json())


def fetch_issue_for_ai_request(fix_request):
    if not fix_request.github_issue_number:
        raise GitHubIssueError("Forespørselen har ikke GitHub issue ennå.")

    token, repo = _github_config()
    with httpx.Client(headers=_headers(token), timeout=15) as client:
        response = client.get(
            f"https://api.github.com/repos/{repo}/issues/{fix_request.github_issue_number}"
        )

    if response.status_code != 200:
        message = response.text[:300]
        raise GitHubIssueError(f"Kunne ikke hente GitHub issue: {response.status_code} {message}")

    return _issue_snapshot(response.json())


def _remove_issue_label(client, repo, issue_number, label):
    response = client.delete(f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels/{label}")
    if response.status_code not in (200, 404):
        response.raise_for_status()


def _add_issue_labels(client, repo, issue_number, labels):
    response = client.post(
        f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels",
        json={"labels": list(labels)},
    )
    response.raise_for_status()


def _add_issue_comment(client, repo, issue_number, body):
    response = client.post(
        f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments",
        json={"body": body},
    )
    response.raise_for_status()


def merge_ready_pull_request_for_ai_request(fix_request):
    if not fix_request.github_issue_number:
        raise GitHubIssueError("Forespørselen har ikke GitHub issue ennå.")

    token, repo = _github_config()
    owner = repo.split("/", 1)[0]
    branch = f"ai/issue-{fix_request.github_issue_number}"

    with httpx.Client(headers=_headers(token), timeout=30) as client:
        response = client.get(
            f"https://api.github.com/repos/{repo}/pulls",
            params={"state": "open", "head": f"{owner}:{branch}", "base": "main"},
        )
        if response.status_code != 200:
            message = response.text[:300]
            raise GitHubIssueError(f"Kunne ikke hente pull request: {response.status_code} {message}")

        pull_requests = response.json()
        if not pull_requests:
            raise GitHubIssueError("Fant ingen åpen pull request for denne fiksen.")

        pull_request = pull_requests[0]
        merge_response = client.put(
            f"https://api.github.com/repos/{repo}/pulls/{pull_request['number']}/merge",
            json={
                "merge_method": "squash",
                "commit_title": f"Deploy AI request #{fix_request.github_issue_number}",
            },
        )
        if merge_response.status_code != 200:
            message = merge_response.text[:300]
            raise GitHubIssueError(f"Kunne ikke merge pull request: {merge_response.status_code} {message}")

        _remove_issue_label(client, repo, fix_request.github_issue_number, "ready-to-deploy")
        _add_issue_labels(client, repo, fix_request.github_issue_number, ["deployed"])
        _add_issue_comment(
            client,
            repo,
            fix_request.github_issue_number,
            f"Deploy er startet fra Shanklife Pro admin etter merge av PR #{pull_request['number']}.",
        )
        return {
            "pull_request_number": pull_request["number"],
            "pull_request_url": pull_request["html_url"],
        }
