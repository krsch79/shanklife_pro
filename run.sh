#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x /tmp/shanklife_pro_venv/bin/python ]; then
    if command -v python3.11 >/dev/null 2>&1; then
        PYTHON_BIN="python3.11"
    else
        PYTHON_BIN="python3"
    fi
    "$PYTHON_BIN" -m venv /tmp/shanklife_pro_venv
    /tmp/shanklife_pro_venv/bin/pip install -r requirements.txt
fi

/tmp/shanklife_pro_venv/bin/python app.py
