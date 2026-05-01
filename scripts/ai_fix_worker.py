#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.github_issues import _github_config, _headers  # noqa: E402


WORKFLOW_LABELS = {
    "triage": "needs-triage",
    "progress": "in-progress",
    "ready": "ready-to-deploy",
    "failed": "failed",
}

DEFAULT_CODEX_BIN = "/home/kristian/.npm-global/bin/codex"


def run(command, *, cwd=ROOT, check=True, env=None, shell=False):
    print(f"$ {command if isinstance(command, str) else ' '.join(command)}")
    return subprocess.run(command, cwd=cwd, check=check, env=env, shell=shell)


def load_env_file():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def github_client():
    token, repo = _github_config()
    return token, repo, httpx.Client(headers=_headers(token), timeout=30)


def get_issue(client, repo, number):
    response = client.get(f"https://api.github.com/repos/{repo}/issues/{number}")
    response.raise_for_status()
    return response.json()


def find_next_issue(client, repo):
    response = client.get(
        f"https://api.github.com/repos/{repo}/issues",
        params={
            "state": "open",
            "labels": "from-shanklife-admin,ai-request,needs-triage",
            "sort": "created",
            "direction": "asc",
        },
    )
    response.raise_for_status()
    issues = [issue for issue in response.json() if "pull_request" not in issue]
    return issues[0] if issues else None


def add_labels(client, repo, number, labels):
    if not labels:
        return
    response = client.post(
        f"https://api.github.com/repos/{repo}/issues/{number}/labels",
        json={"labels": list(labels)},
    )
    response.raise_for_status()


def remove_label(client, repo, number, label):
    response = client.delete(f"https://api.github.com/repos/{repo}/issues/{number}/labels/{label}")
    if response.status_code not in (200, 404):
        response.raise_for_status()


def add_comment(client, repo, number, body):
    response = client.post(
        f"https://api.github.com/repos/{repo}/issues/{number}/comments",
        json={"body": body},
    )
    response.raise_for_status()


def create_pull_request(client, repo, issue, branch):
    response = client.post(
        f"https://api.github.com/repos/{repo}/pulls",
        json={
            "title": f"AI request #{issue['number']}",
            "head": branch,
            "base": "main",
            "body": f"Løser #{issue['number']}.\n\nOpprettet av Shanklife AI worker.",
        },
    )
    if response.status_code == 422:
        return None
    response.raise_for_status()
    return response.json()


def ensure_clean_worktree():
    run(["git", "reset", "--mixed", "HEAD"])
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    if status:
        raise RuntimeError(
            "Arbeidstreet er ikke rent. Commit/stash endringer før AI worker kjøres.\n\n"
            f"{status}"
        )


def make_askpass(token):
    handle = tempfile.NamedTemporaryFile("w", delete=False)
    handle.write("#!/bin/sh\n")
    handle.write("case \"$1\" in\n")
    handle.write("  *Username*) echo \"x-access-token\" ;;\n")
    handle.write(f"  *Password*) echo \"{token}\" ;;\n")
    handle.write("esac\n")
    handle.close()
    os.chmod(handle.name, 0o700)
    return handle.name


def git_push_with_token(token, branch):
    askpass = make_askpass(token)
    env = os.environ.copy()
    env["GIT_ASKPASS"] = askpass
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        run(["git", "push", "-u", "origin", branch], env=env)
    finally:
        Path(askpass).unlink(missing_ok=True)


def prepare_branch(issue):
    branch = f"ai/issue-{issue['number']}"
    run(["git", "checkout", "main"])
    run(["git", "pull", "--ff-only", "origin", "main"])
    existing_branches = subprocess.check_output(["git", "branch", "--list", branch], cwd=ROOT, text=True).strip()
    if existing_branches:
        run(["git", "branch", "-D", branch])
    run(["git", "checkout", "-b", branch])

    job_dir = ROOT / "instance" / "ai_jobs"
    job_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = job_dir / f"issue-{issue['number']}.md"
    prompt_path.write_text(
        f"# GitHub issue #{issue['number']}\n\n"
        f"{issue.get('html_url', '')}\n\n"
        f"## Tittel\n{issue.get('title', '')}\n\n"
        f"## Beskrivelse\n{issue.get('body', '')}\n",
        encoding="utf-8",
    )
    return branch, prompt_path


def run_codex(issue, prompt_path):
    codex_env = codex_environment()
    prompt = (
        f"Du jobber i Shanklife Pro-repoet med GitHub issue #{issue['number']}.\n"
        f"Les arbeidsbeskrivelsen i {prompt_path}.\n"
        "Gjør nødvendige kodeendringer. Hold endringen smal.\n"
        "Hvis du endrer kode, bump versjon etter SemVer og oppdater CHANGELOG.md med dato og klokkeslett.\n"
        "Kjør relevante kontroller før du avslutter.\n"
    )
    codex_bin = os.environ.get("CODEX_BIN") or (DEFAULT_CODEX_BIN if Path(DEFAULT_CODEX_BIN).exists() else "codex")
    if not shutil.which(codex_bin) and not Path(codex_bin).exists():
        raise RuntimeError(f"Fant ikke Codex CLI: {codex_bin}")
    run([codex_bin, "exec", "--sandbox", "workspace-write", "-C", str(ROOT), prompt], env=codex_env)


def codex_environment():
    env = os.environ.copy()
    openai_key = env.get("OPENAI_API_KEY", "").strip()
    codex_key = env.get("CODEX_API_KEY", "").strip()
    if openai_key and not codex_key:
        env["CODEX_API_KEY"] = openai_key
    if codex_key and not openai_key:
        env["OPENAI_API_KEY"] = codex_key
    if env.get("OPENAI_API_KEY") or env.get("CODEX_API_KEY"):
        return env
    raise RuntimeError(
        "OPENAI_API_KEY mangler i miljøet for AI worker. "
        "Legg OPENAI_API_KEY i /home/kristian/shanklife_pro/.env på Raspberryen, "
        "eller konfigurer Codex CLI med en gyldig headless autentisering."
    )


def has_changes():
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    return bool(status)


def commit_changes(issue):
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", f"Fix AI request #{issue['number']}"])


def run_checks():
    run("python3 -m py_compile $(git ls-files '*.py')", shell=True)


def main():
    parser = argparse.ArgumentParser(description="Klargjør og eventuelt kjør AI-fiks fra GitHub issue.")
    parser.add_argument("--issue", type=int, help="GitHub issue-nummer. Hvis utelatt hentes eldste needs-triage.")
    parser.add_argument("--run-codex", action="store_true", help="Kjør Codex CLI etter at branch er klargjort.")
    parser.add_argument("--push", action="store_true", help="Push branch til GitHub etter commit.")
    parser.add_argument("--create-pr", action="store_true", help="Opprett pull request etter push.")
    args = parser.parse_args()

    load_env_file()
    ensure_clean_worktree()
    token, repo, client = github_client()
    with client:
        issue = get_issue(client, repo, args.issue) if args.issue else find_next_issue(client, repo)
        if not issue:
            print("Fant ingen åpne AI-issues med needs-triage.")
            return 0

        if args.run_codex:
            codex_environment()

        branch, prompt_path = prepare_branch(issue)
        remove_label(client, repo, issue["number"], WORKFLOW_LABELS["triage"])
        remove_label(client, repo, issue["number"], WORKFLOW_LABELS["failed"])
        add_labels(client, repo, issue["number"], [WORKFLOW_LABELS["progress"]])
        add_comment(
            client,
            repo,
            issue["number"],
            f"AI worker har klargjort branch `{branch}` og arbeidsfil `{prompt_path}`.",
        )

        if args.run_codex:
            try:
                run_codex(issue, prompt_path)
                run_checks()
                if not has_changes():
                    remove_label(client, repo, issue["number"], WORKFLOW_LABELS["progress"])
                    add_labels(client, repo, issue["number"], [WORKFLOW_LABELS["failed"]])
                    add_comment(client, repo, issue["number"], "Codex-kjøring fullført, men ga ingen kodeendringer.")
                    return 0
                commit_changes(issue)

                if args.push or args.create_pr:
                    git_push_with_token(token, branch)

                if args.create_pr:
                    pull_request = create_pull_request(client, repo, issue, branch)
                    if pull_request:
                        remove_label(client, repo, issue["number"], WORKFLOW_LABELS["progress"])
                        add_labels(client, repo, issue["number"], [WORKFLOW_LABELS["ready"]])
                        add_comment(
                            client,
                            repo,
                            issue["number"],
                            f"Pull request er opprettet: {pull_request['html_url']}",
                        )
                    else:
                        add_comment(client, repo, issue["number"], "Pull request finnes trolig allerede for denne branchen.")
            except Exception as exc:
                remove_label(client, repo, issue["number"], WORKFLOW_LABELS["progress"])
                add_labels(client, repo, issue["number"], [WORKFLOW_LABELS["failed"]])
                add_comment(client, repo, issue["number"], f"AI worker feilet:\n\n```text\n{exc}\n```")
                raise

        print(f"Klar: issue #{issue['number']} på branch {branch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
