#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/kristian/shanklife_pro}"
BRANCH="${BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-/tmp/shanklife_pro_venv/bin/python}"
PIP_BIN="${PIP_BIN:-/tmp/shanklife_pro_venv/bin/pip}"
LOG_FILE="${LOG_FILE:-/tmp/shanklife_pro.log}"
MAINTENANCE_FILE="${SHANKLIFE_MAINTENANCE_FILE:-$APP_DIR/instance/maintenance.lock}"
APP_PORT="${APP_PORT:-5055}"
MAINTENANCE_LOG_FILE="${MAINTENANCE_LOG_FILE:-/tmp/shanklife_pro_maintenance.log}"
MAINTENANCE_SERVER_PID=""

cd "$APP_DIR"

if [ ! -d .git ]; then
    echo "Deploy stoppet: $APP_DIR er ikke et git-repo."
    echo "Klon repoet eller initier remote før dette scriptet brukes."
    exit 1
fi

disable_maintenance() {
    stop_maintenance_server
    rm -f "$MAINTENANCE_FILE"
}

app_pids() {
    ps -ef | awk '/\/tmp\/shanklife_pro_venv\/bin\/python app.py/ && !/awk/ {print $2}'
}

finish_deploy() {
    exit_code="$1"
    if [ "$exit_code" -eq 0 ]; then
        disable_maintenance
        return
    fi

    if [ -z "$(app_pids)" ]; then
        start_maintenance_server || true
        echo "Deploy feilet mens appen var nede. Statisk vedlikeholdsside blir stående på port $APP_PORT."
    fi
}

start_maintenance_server() {
    if [ -n "$MAINTENANCE_SERVER_PID" ] && kill -0 "$MAINTENANCE_SERVER_PID" >/dev/null 2>&1; then
        return
    fi
    nohup "$PYTHON_BIN" scripts/maintenance_server.py --root "$APP_DIR" --port "$APP_PORT" > "$MAINTENANCE_LOG_FILE" 2>&1 < /dev/null &
    MAINTENANCE_SERVER_PID="$!"
    sleep 1
    if ! kill -0 "$MAINTENANCE_SERVER_PID" >/dev/null 2>&1; then
        echo "Kunne ikke starte statisk vedlikeholdsserver."
        exit 1
    fi
}

stop_maintenance_server() {
    if [ -n "$MAINTENANCE_SERVER_PID" ] && kill -0 "$MAINTENANCE_SERVER_PID" >/dev/null 2>&1; then
        kill "$MAINTENANCE_SERVER_PID"
        wait "$MAINTENANCE_SERVER_PID" 2>/dev/null || true
    fi
    MAINTENANCE_SERVER_PID=""
}

echo "Setter Shanklife Pro i vedlikeholdsmodus..."
mkdir -p "$(dirname "$MAINTENANCE_FILE")"
printf 'Deploy startet %s\n' "$(date -Is)" > "$MAINTENANCE_FILE"
trap 'finish_deploy $?' EXIT

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
pids="$(app_pids)"
if [ -n "$pids" ]; then
    kill $pids
    start_maintenance_server
    sleep 2
fi
stop_maintenance_server
nohup ./run.sh > "$LOG_FILE" 2>&1 < /dev/null &
sleep 3
ps -ef | grep "/tmp/shanklife_pro_venv/bin/python app.py" | grep -v grep

echo "Sender eventuelle versjonsvarsler..."
"$PYTHON_BIN" scripts/send_version_update_notifications.py

echo "Tar Shanklife Pro ut av vedlikeholdsmodus..."
disable_maintenance

echo "Deploy ferdig."
