#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/kristian/shanklife_pro}"
BRANCH="${BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-/tmp/shanklife_pro_venv/bin/python}"
PIP_BIN="${PIP_BIN:-/tmp/shanklife_pro_venv/bin/pip}"
MAINTENANCE_FILE="${SHANKLIFE_MAINTENANCE_FILE:-$APP_DIR/instance/maintenance.lock}"
APP_PORT="${APP_PORT:-5055}"
MAINTENANCE_LOG_FILE="${MAINTENANCE_LOG_FILE:-/tmp/shanklife_pro_maintenance.log}"
SERVICE_NAME="${SHANKLIFE_SERVICE_NAME:-shanklife-pro.service}"
SERVICE_FILE="${SHANKLIFE_SERVICE_FILE:-$APP_DIR/deploy/shanklife-pro.service}"
HEALTH_URL="${SHANKLIFE_HEALTH_URL:-http://127.0.0.1:$APP_PORT/api/v1/health}"
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
        sudo systemctl stop "$SERVICE_NAME" >/dev/null 2>&1 || true
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

install_golfbox_scheduler() {
    scheduler_line="* * * * * cd $APP_DIR && $PYTHON_BIN scripts/run_scheduled_golfbox_bookings.py >> /tmp/shanklife_pro_golfbox_scheduler.log 2>&1"
    tmp_cron="$(mktemp)"
    crontab -l 2>/dev/null | awk '
        /# shanklife-golfbox-scheduler-start/ {skip=1; next}
        /# shanklife-golfbox-scheduler-end/ {skip=0; next}
        !skip {print}
    ' > "$tmp_cron"
    {
        echo "# shanklife-golfbox-scheduler-start"
        echo "$scheduler_line"
        echo "# shanklife-golfbox-scheduler-end"
    } >> "$tmp_cron"
    crontab "$tmp_cron"
    rm -f "$tmp_cron"
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

echo "Installerer planlagt GolfBox-booking-kjører..."
install_golfbox_scheduler

echo "Installerer og aktiverer systemd-tjenesten..."
sudo install -m 0644 "$SERVICE_FILE" "/etc/systemd/system/$SERVICE_NAME"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

echo "Restarter Shanklife Pro..."
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    sudo systemctl stop "$SERVICE_NAME"
else
    pids="$(app_pids)"
    if [ -n "$pids" ]; then
        kill $pids
    fi
fi

for wait_number in $(seq 1 20); do
    if [ -z "$(app_pids)" ]; then
        break
    fi
    sleep 0.5
done

if [ -n "$(app_pids)" ]; then
    echo "Kunne ikke stoppe eksisterende Shanklife Pro-prosess kontrollert."
    exit 1
fi

start_maintenance_server
stop_maintenance_server
sudo systemctl restart "$SERVICE_NAME"

app_ready=0
for wait_number in $(seq 1 30); do
    if sudo systemctl is-active --quiet "$SERVICE_NAME" \
        && [ -n "$(app_pids)" ] \
        && curl -sS -o /dev/null --max-time 3 "$HEALTH_URL"; then
        app_ready=1
        break
    fi
    sleep 1
done

if [ "$app_ready" -ne 1 ]; then
    echo "Shanklife Pro-prosessen ble ikke klar etter restart."
    sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
    exit 1
fi

sudo systemctl is-active --quiet "$SERVICE_NAME"
ps -ef | grep "/tmp/shanklife_pro_venv/bin/python app.py" | grep -v grep

echo "Tar Shanklife Pro ut av vedlikeholdsmodus..."
disable_maintenance

health_ok=0
for wait_number in $(seq 1 30); do
    if curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null; then
        health_ok=1
        break
    fi
    sleep 1
done

if [ "$health_ok" -ne 1 ]; then
    mkdir -p "$(dirname "$MAINTENANCE_FILE")"
    printf 'Health-sjekk feilet %s\n' "$(date -Is)" > "$MAINTENANCE_FILE"
    echo "Shanklife Pro svarte ikke på health-sjekken etter restart."
    sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
    exit 1
fi

if [ "${SHANKLIFE_SEND_VERSION_NOTIFICATIONS:-0}" = "1" ]; then
    echo "Sender eventuelle versjonsvarsler..."
    "$PYTHON_BIN" scripts/send_version_update_notifications.py
else
    echo "Hopper over versjonsvarsler. Sett SHANKLIFE_SEND_VERSION_NOTIFICATIONS=1 for å sende dem."
fi

echo "Deploy ferdig."
