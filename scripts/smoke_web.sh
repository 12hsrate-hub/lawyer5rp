#!/usr/bin/env bash
set -euo pipefail

WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-8000}"
BASE_URL="${BASE_URL:-http://${WEB_HOST}:${WEB_PORT}}"

echo "Smoke checks against ${BASE_URL}"

health_json="$(curl -fsS "${BASE_URL}/health")"
echo "health: ${health_json}"
echo "${health_json}" | grep -q '"status":"ok"'

login_status="$(curl -sS -o /dev/null -w '%{http_code}' "${BASE_URL}/login")"
if [[ "${login_status}" != "200" ]]; then
  echo "Unexpected /login status: ${login_status}" >&2
  exit 1
fi
echo "login page: ${login_status}"

me_status="$(curl -sS -o /dev/null -w '%{http_code}' "${BASE_URL}/api/auth/me")"
if [[ "${me_status}" != "401" ]]; then
  echo "Unexpected /api/auth/me status without session: ${me_status}" >&2
  exit 1
fi
echo "auth probe (unauthorized expected): ${me_status}"

echo "Smoke checks passed."
