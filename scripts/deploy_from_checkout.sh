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
SERVICE_NAME="${SERVICE_NAME:-lawyer5rp.service}"

is_port_busy() {
  ss -ltn "( sport = :${WEB_PORT} )" | grep -q LISTEN
}

wait_for_port_release() {
  local attempts="${1:-30}"
  local delay="${2:-1}"
  local attempt=1

  while (( attempt <= attempts )); do
    if ! is_port_busy; then
      return 0
    fi
    sleep "${delay}"
    attempt=$((attempt + 1))
  done

  return 1
}

wait_for_health() {
  local attempts="${1:-30}"
  local delay="${2:-1}"
  local attempt=1

  while (( attempt <= attempts )); do
    if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${delay}"
    attempt=$((attempt + 1))
  done

  return 1
}

if [[ ! -d "${REPO_ROOT}/config" || ! -d "${REPO_ROOT}/shared" || ! -d "${REPO_ROOT}/web" || ! -d "${REPO_ROOT}/scripts" ]]; then
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
if [[ -d "${APP_ROOT}/config" ]]; then
  cp -a "${APP_ROOT}/config" "${backup_root}/"
fi
if [[ -d "${APP_ROOT}/scripts" ]]; then
  cp -a "${APP_ROOT}/scripts" "${backup_root}/"
fi
if [[ -d "${APP_ROOT}/web" ]]; then
  mkdir -p "${backup_root}/web"
  rsync -a \
    --exclude ".env" \
    --exclude "data/" \
    --exclude ".venv/" \
    "${APP_ROOT}/web/" "${backup_root}/web/"
fi

mkdir -p "${APP_ROOT}/config"
rsync -a --delete "${REPO_ROOT}/shared/" "${APP_ROOT}/shared/"
rsync -a --delete "${REPO_ROOT}/config/" "${APP_ROOT}/config/"
rsync -a --delete \
  --exclude ".env" \
  --exclude "data/" \
  --exclude ".venv/" \
  "${REPO_ROOT}/web/" "${APP_ROOT}/web/"
rsync -a --delete "${REPO_ROOT}/scripts/" "${APP_ROOT}/scripts/"

chown -R "${RUN_AS_USER}:${RUN_AS_USER}" "${APP_ROOT}/config" "${APP_ROOT}/shared" "${APP_ROOT}/web"

"${PYTHON_BIN}" "${APP_ROOT}/scripts/run_db_migrations.py" --backend postgres

if [[ -f "${APP_ROOT}/scripts/sync_law_sources_manifest.py" ]]; then
  echo "Syncing blackberry law sources manifest and rebuilding DB law index..."
  "${PYTHON_BIN}" "${APP_ROOT}/scripts/sync_law_sources_manifest.py" --server blackberry --safe-rerun --rebuild
elif [[ -f "${APP_ROOT}/scripts/import_law_snapshot.py" ]]; then
  echo "Ensuring active DB law snapshot for blackberry..."
  "${PYTHON_BIN}" "${APP_ROOT}/scripts/import_law_snapshot.py" --server blackberry --skip-if-current
fi

if [[ -f "${APP_ROOT}/scripts/seed_admin_catalog_workflow.py" ]]; then
  echo "Seeding admin catalog workflow..."
  "${PYTHON_BIN}" "${APP_ROOT}/scripts/seed_admin_catalog_workflow.py"
fi

systemctl stop "${SERVICE_NAME}" || true
pkill -f "${APP_ROOT}/web/server.py" || true

if ! wait_for_port_release 10 1; then
  pids="$(pgrep -f "${APP_ROOT}/web/server.py" || true)"
  if [[ -n "${pids}" ]]; then
    kill -9 ${pids} || true
  fi
  if ! wait_for_port_release 10 1; then
    echo "Port ${WEB_PORT} is still busy after stopping ${APP_ROOT}/web/server.py" >&2
    ss -ltnp "( sport = :${WEB_PORT} )" || true
    exit 1
  fi
fi

systemctl start "${SERVICE_NAME}"

if ! wait_for_health 30 1; then
  echo "Application did not become healthy at ${HEALTH_URL}" >&2
  systemctl status "${SERVICE_NAME}" --no-pager || true
  tail -n 50 "${APP_ROOT}/web/data/logs/server.out" || true
  exit 1
fi

echo "Deployed commit: $(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
echo "Health:"
curl -fsS "${HEALTH_URL}"
echo

if [[ -x "${APP_ROOT}/scripts/smoke_web.sh" ]]; then
  "${APP_ROOT}/scripts/smoke_web.sh"
fi

if [[ -f "${APP_ROOT}/scripts/run_synthetic_suite.py" ]]; then
  echo "Running synthetic smoke suite..."
  "${PYTHON_BIN}" "${APP_ROOT}/scripts/run_synthetic_suite.py" --suite smoke --trigger post_deploy || {
    echo "Synthetic smoke suite failed" >&2
    exit 1
  }
fi
