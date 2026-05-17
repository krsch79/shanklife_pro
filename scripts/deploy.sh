#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/kristian/shanklife_pro}"
BRANCH="${BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-/tmp/shanklife_pro_venv/bin/python}"
PIP_BIN="${PIP_BIN:-/tmp/shanklife_pro_venv/bin/pip}"
LOG_FILE="${LOG_FILE:-/tmp/shanklife_pro.log}"
MAINTENANCE_FILE="${SHANKLIFE_MAINTENANCE_FILE:-$APP_DIR/instance/maintenance.lock}"

cd "$APP_DIR"

if [ ! -d .git ]; then
    echo "Deploy stoppet: $APP_DIR er ikke et git-repo."
    echo "Klon repoet eller initier remote før dette scriptet brukes."
    exit 1
fi

disable_maintenance() {
    rm -f "$MAINTENANCE_FILE"
}

echo "Setter Shanklife Pro i vedlikeholdsmodus..."
mkdir -p "$(dirname "$MAINTENANCE_FILE")"
printf 'Deploy startet %s\n' "$(date -Is)" > "$MAINTENANCE_FILE"
trap disable_maintenance EXIT

echo "Tar databasebackup før deploy..."
"$PYTHON_BIN" scripts/daily_backup.py --force --name "Backup før deploy"

echo "Henter siste kode fra GitHub..."
git fetch origin "$BRANCH"
git checkout "$BRANCH"
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

echo "Sender eventuelle versjonsvarsler..."
"$PYTHON_BIN" scripts/send_version_update_notifications.py

echo "Tar Shanklife Pro ut av vedlikeholdsmodus..."
disable_maintenance

echo "Deploy ferdig."
