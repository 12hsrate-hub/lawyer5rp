#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[codex-checks] root: $ROOT_DIR"

run_step() {
  label="$1"
  shift
  echo "[codex-checks] $label"
  "$@"
}

run_optional() {
  label="$1"
  shift
  if "$@"; then
    return 0
  fi
  echo "[codex-checks] skip: $label"
  return 0
}

if command -v python >/dev/null 2>&1; then
  run_step "python syntax checks" python -m py_compile tests/test_point3_contract.py tests/test_mode_router.py tests/test_validator_retry.py tests/test_point3_article_policy.py
  run_step "pytest point3" python -m pytest -q tests/test_point3_contract.py tests/test_mode_router.py tests/test_validator_retry.py tests/test_point3_article_policy.py
else
  echo "[codex-checks] error: python is required"
  exit 1
fi

if command -v git >/dev/null 2>&1; then
  run_step "git diff check" git diff --check
else
  echo "[codex-checks] skip: git is not available"
fi

run_optional "shellcheck not installed" sh -c 'command -v shellcheck >/dev/null 2>&1 && shellcheck scripts/codex_run_checks.sh'

echo "[codex-checks] ok"
