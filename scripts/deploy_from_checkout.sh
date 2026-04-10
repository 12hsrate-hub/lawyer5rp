#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

APP_ROOT="${APP_ROOT:-/srv/lawyer5rp.ru}"
RUN_AS_USER="${RUN_AS_USER:-www-data}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-8000}"
PYTHON_BIN="${PYTHON_BIN:-${APP_ROOT}/web/.venv/bin/python}"
HEALTH_URL="${HEALTH_URL:-http://${WEB_HOST}:${WEB_PORT}/health}"
SERVER_CMD="${PYTHON_BIN} ${APP_ROOT}/web/server.py --host ${WEB_HOST} --port ${WEB_PORT}"

if [[ ! -d "${REPO_ROOT}/shared" || ! -d "${REPO_ROOT}/web" || ! -d "${REPO_ROOT}/scripts" ]]; then
  echo "Repository root is incomplete: ${REPO_ROOT}" >&2
  exit 1
fi

if [[ ! -d "${APP_ROOT}/web" ]]; then
  echo "Application root is missing: ${APP_ROOT}" >&2
  exit 1
fi

mkdir -p "${APP_ROOT}/backups"

timestamp="$(date +%Y%m%d_%H%M%S)"
backup_root="${APP_ROOT}/backups/deploy_${timestamp}"
mkdir -p "${backup_root}"

if [[ -d "${APP_ROOT}/shared" ]]; then
  cp -a "${APP_ROOT}/shared" "${backup_root}/"
fi
if [[ -d "${APP_ROOT}/web" ]]; then
  cp -a "${APP_ROOT}/web" "${backup_root}/"
fi
if [[ -d "${APP_ROOT}/scripts" ]]; then
  cp -a "${APP_ROOT}/scripts" "${backup_root}/"
fi

rsync -a --delete "${REPO_ROOT}/shared/" "${APP_ROOT}/shared/"
rsync -a --delete \
  --exclude ".env" \
  --exclude "data/" \
  --exclude ".venv/" \
  "${REPO_ROOT}/web/" "${APP_ROOT}/web/"
rsync -a --delete "${REPO_ROOT}/scripts/" "${APP_ROOT}/scripts/"

chown -R "${RUN_AS_USER}:${RUN_AS_USER}" "${APP_ROOT}/shared" "${APP_ROOT}/web"

"${PYTHON_BIN}" "${APP_ROOT}/scripts/run_db_migrations.py" --backend postgres

pkill -f "${APP_ROOT}/web/server.py --host ${WEB_HOST} --port ${WEB_PORT}" || true
sleep 2

su -s /bin/bash -c "nohup ${SERVER_CMD} >${APP_ROOT}/web/data/logs/server.out 2>&1 </dev/null &" "${RUN_AS_USER}"

sleep 5

echo "Deployed commit: $(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
echo "Health:"
curl -fsS "${HEALTH_URL}"
echo
