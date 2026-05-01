#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/kristian/shanklife_pro}"
BRANCH="${BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-/tmp/shanklife_pro_venv/bin/python}"
PIP_BIN="${PIP_BIN:-/tmp/shanklife_pro_venv/bin/pip}"
LOG_FILE="${LOG_FILE:-/tmp/shanklife_pro.log}"

cd "$APP_DIR"

if [ ! -d .git ]; then
    echo "Deploy stoppet: $APP_DIR er ikke et git-repo."
    echo "Klon repoet eller initier remote før dette scriptet brukes."
    exit 1
fi

echo "Tar databasebackup før deploy..."
"$PYTHON_BIN" scripts/daily_backup.py

echo "Henter siste kode fra GitHub..."
git fetch origin "$BRANCH"
git merge --ff-only "origin/$BRANCH"

echo "Installerer avhengigheter..."
"$PIP_BIN" install -r requirements.txt

echo "Kjører syntakssjekk..."
"$PYTHON_BIN" -m py_compile $(git ls-files '*.py')

echo "Restarter Shanklife Pro..."
pids="$(ps -ef | awk '/\/tmp\/shanklife_pro_venv\/bin\/python app.py/ && !/awk/ {print $2}')"
if [ -n "$pids" ]; then
    kill $pids
    sleep 2
fi
nohup ./run.sh > "$LOG_FILE" 2>&1 < /dev/null &
sleep 3
ps -ef | grep "/tmp/shanklife_pro_venv/bin/python app.py" | grep -v grep

echo "Deploy ferdig."
