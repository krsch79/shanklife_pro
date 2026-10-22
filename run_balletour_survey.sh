#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
VENV_PATH="${VENV_PATH:-/opt/shanklife/venvs/sl-pro}"
if [[ ! -x "$VENV_PATH/bin/python" ]]; then
    echo "Pre-provisioned production runtime is missing" >&2
    exit 1
fi
exec "$VENV_PATH/bin/python" -m gunicorn --workers 2 --threads 2 --timeout 120 --bind 127.0.0.1:5060 balletour_survey.app:app
