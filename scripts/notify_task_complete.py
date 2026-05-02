#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.mailer import send_task_complete  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Send e-post om at en Codex-oppgave er ferdig.")
    parser.add_argument("summary", nargs="*", help="Kort oppsummering av ferdig arbeid.")
    args = parser.parse_args()
    summary = " ".join(args.summary).strip() or sys.stdin.read().strip()
    if not summary:
        summary = "Oppgaven er ferdig."
    return 0 if send_task_complete(summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
