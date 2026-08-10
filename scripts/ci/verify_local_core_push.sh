#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BASE_SHA="${LOCAL_CORE_PUSH_BASE_SHA:-origin/master}"
HEAD_SHA="${LOCAL_CORE_PUSH_HEAD_SHA:-HEAD}"
CONTRACT_ROOT="${MINDSCAPE_CONTRACT_ROOT:-}"
BACKEND_TEST_IMAGE="${LOCAL_CORE_BACKEND_TEST_IMAGE:-mindscape-ai-local-core-backend}"
FORCE=0
EXPLAIN=0

usage() {
  cat <<'EOF'
Usage: scripts/ci/verify_local_core_push.sh [options]

Canonical Local Core push verification. Successful results are cached under
the Git common directory and reused only for the same base, head, verifier,
contract source, and toolchain fingerprints.

Options:
  --base-sha SHA       Remote/base commit (default: origin/master)
  --head-sha SHA       Commit being pushed (default: HEAD)
  --contract-root PATH Canonical mindscape-ai-cloud checkout
  --force              Ignore a matching verification receipt
  --explain            Print gate fingerprints and receipt paths without running gates
  LOCAL_CORE_PUSH_SKIP_WORKTREE_CHECK=1
                       Skip only resolved worktree-count verification
  -h, --help           Show this help
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --base-sha)
      BASE_SHA="$2"
      shift 2
      ;;
    --head-sha)
      HEAD_SHA="$2"
      shift 2
      ;;
    --contract-root)
      CONTRACT_ROOT="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --explain)
      EXPLAIN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'ERROR: unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$REPO_ROOT"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'ERROR: required command is unavailable: %s\n' "$1" >&2
    printf 'HINT: install %s and ensure it is on PATH.\n' "$1" >&2
    exit 1
  fi
}

fail_with_hint() {
  local msg="$1"
  local hint="$2"
  local details="${3:-}"

  printf '\nERROR: %s\n' "$msg" >&2
  if [ -n "$details" ]; then
    printf '%s\n' "$details" >&2
  fi
  printf 'HINT: %s\n' "$hint" >&2
  exit 1
}

path_fingerprint() {
  local path
  for path in "$@"; do
    if ! git rev-parse "$HEAD_FULL:$path" 2>/dev/null; then
      printf 'missing:%s\n' "$path"
    fi
  done | git hash-object --stdin
}

run_cached_gate() {
  local gate_id="$1"
  local label="$2"
  local fingerprint="$3"
  local check_receipt="$CHECK_RECEIPT_DIR/$gate_id-$fingerprint.receipt"
  local -a gate_cmd
  shift 3
  gate_cmd=( "$@" )
  if [ "$FORCE" -eq 0 ] && [ -f "$check_receipt" ] \
      && grep -Fxq 'status=passed' "$check_receipt"; then
    printf '\n==> %s\n' "$label"
    printf 'OK: reusable gate checkpoint found: %s\n' "$check_receipt"
    return
  fi
  printf '\n==> %s\n' "$label"
  if ! "${gate_cmd[@]}"; then
    printf '\nERROR: gate failed: %s\n' "$label" >&2
    printf 'HINT: rerun this gate command directly for detailed traceback:\n  %s\n' "${gate_cmd[*]}" >&2
    exit 1
  fi
  mkdir -p "$CHECK_RECEIPT_DIR"
  umask 077
  {
    printf 'schema=mindscape.local-core-push-gate.v1\n'
    printf 'status=passed\n'
    printf 'gate=%s\n' "$gate_id"
    printf 'fingerprint=%s\n' "$fingerprint"
  } > "$check_receipt"
}

resolve_contract_root() {
  if [ -n "$CONTRACT_ROOT" ]; then
    if contract_root_is_complete "$CONTRACT_ROOT"; then
      return
    fi
    fail_with_hint \
      "configured mindscape-ai-cloud contract source is incomplete" \
      "Set CONTRACT_ROOT to a complete checkout containing scripts/product_semantic_traceability.py, then rerun with --contract-root." \
      "Configured: $CONTRACT_ROOT"
  fi
  if contract_root_is_complete "$REPO_ROOT/.contract-sources/mindscape-ai-cloud"; then
    CONTRACT_ROOT="$REPO_ROOT/.contract-sources/mindscape-ai-cloud"
    return
  fi
  if contract_root_is_complete "$REPO_ROOT/../mindscape-ai-cloud"; then
    CONTRACT_ROOT="$REPO_ROOT/../mindscape-ai-cloud"
    return
  fi
  fail_with_hint \
    "Canonical mindscape-ai-cloud contract source is unavailable" \
    "Initialize a local contract source at one of: .contract-sources/mindscape-ai-cloud or ../mindscape-ai-cloud."
}

contract_root_is_complete() {
  local root="$1"
  [ -f "$root/scripts/product_semantic_traceability.py" ]
}

require_clean_git_scope() {
  local status_output stash_output worktree_count
  status_output="$(git status --porcelain --untracked-files=all)"
  if [ -n "$status_output" ]; then
    fail_with_hint \
      "Push verification requires a clean worktree" \
      "Commit/stash or discard local changes, then rerun verify/push." \
      "$status_output"
  fi
  stash_output="$(git stash list)"
  if [ -n "$stash_output" ]; then
    fail_with_hint \
      "Push verification requires every stash to be resolved or classified" \
      "Review `git stash list`, apply/drop unresolved stashes, then rerun." \
      "$stash_output"
  fi
  if [ "${LOCAL_CORE_PUSH_SKIP_WORKTREE_CHECK:-0}" = "1" ]; then
    printf 'WARNING: skipping resolved worktree-count verification due LOCAL_CORE_PUSH_SKIP_WORKTREE_CHECK=1\n' >&2
    return
  fi
  worktree_count="$(git worktree list --porcelain | grep -c '^worktree ')"
  if [ "$worktree_count" -ne 1 ]; then
    fail_with_hint \
      "Push verification requires one resolved Local Core worktree" \
      "Please keep a single worktree for push verification; for temporary bypass use LOCAL_CORE_PUSH_SKIP_WORKTREE_CHECK=1." \
      "Found worktree_count=${worktree_count}"
  fi
}

reject_secret_literals() {
  local high_confidence_pattern
  high_confidence_pattern='sk-[a-zA-Z0-9]{20,}|AIza[0-9A-Za-z_-]{35}|gh[po]_[a-zA-Z0-9]{36}|xox[bp]-[0-9]|PRIVATE KEY'
  high_confidence_pattern="${high_confidence_pattern}-----"
  if git diff -U0 "$BASE_FULL..$HEAD_FULL" | grep -iE "$high_confidence_pattern" >/dev/null; then
    fail_with_hint \
      "High-confidence credential literal detected in push range" \
      "Remove secrets and rebase/push; use environment variables or secure vault instead."
  fi
  if git diff --name-only "$BASE_FULL..$HEAD_FULL" | grep -Eq '(^|/)\.env$'; then
    fail_with_hint \
      "'.env' file detected in push range" \
      "Do not include .env in commits; add it to excludes and rework commit history if needed."
  fi
}

run_backend_tests() {
  docker run --rm \
    --entrypoint python \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$REPO_ROOT:/workspace:ro" \
    -w /workspace \
    "$BACKEND_TEST_IMAGE" \
    -m pytest \
    backend/tests/database/runtime_secret_values_spec.py \
    backend/tests/runtime_secret_bootstrap_contract_spec.py \
    backend/tests/runtime_secret_compose_contract_spec.py \
    backend/tests/postgres_vector_runtime_reconcile_spec.py \
    backend/tests/database/connection_semantics_spec.py \
    backend/tests/postgres_runtime_readiness_config_spec.py \
    backend/tests/compose_topology_matrix_spec.py \
    backend/tests/test_system_control_restart_api.py \
    -p no:cacheprovider -q
}

run_architecture_tests() {
  docker run --rm \
    --entrypoint python \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$REPO_ROOT:/workspace:ro" \
    -w /workspace/backend \
    "$BACKEND_TEST_IMAGE" \
    -m pytest \
    tests/ci/validate_modular_entrypoints_guard_spec.py \
    tests/ci/product_semantic_helper_parity_spec.py \
    tests/ci/validate_product_semantics_guard_spec.py \
    tests/ci/product_semantic_contract_source_spec.py \
    tests/ci/pr_template_modular_entry_section_spec.py \
    tests/ci/local_core_push_verification_contract_spec.py \
    -p no:cacheprovider -q
}

frontend_supports_current_toolchain() {
  docker compose run --rm --no-deps frontend \
    node -e 'const {styleText}=require("node:util");process.exit(typeof styleText === "function" ? 0 : 1)' \
    >/dev/null 2>&1
}

ensure_frontend_toolchain() {
  local verification_secret
  verification_secret='local-core-verification-synthetic-value'
  printf -v POSTGRES_VECTOR_RUNTIME_PASSWORD '%s' "$verification_secret"
  export POSTGRES_VECTOR_RUNTIME_PASSWORD
  if frontend_supports_current_toolchain; then
    return
  fi
  printf 'Frontend verification image is stale; rebuilding from the pinned Dockerfile toolchain.\n'
  docker compose build frontend
  if ! frontend_supports_current_toolchain; then
    printf 'ERROR: frontend verification image does not provide the required Node toolchain\n' >&2
    exit 1
  fi
}

run_frontend_tests() {
  ensure_frontend_toolchain
  docker compose run --rm --no-deps frontend \
    ./node_modules/.bin/vitest run \
    src/lib/i18n/locales/en/settings.seams.spec.ts \
    src/lib/i18n/locales/ja/settings.seams.spec.ts \
    src/lib/i18n/locales/zh-TW/settings.seams.spec.ts \
    --no-cache
}

write_receipt() {
  mkdir -p "$RECEIPT_DIR"
  umask 077
  {
    printf 'schema=mindscape.local-core-push-verification.v1\n'
    printf 'status=passed\n'
    printf 'base_sha=%s\n' "$BASE_FULL"
    printf 'head_sha=%s\n' "$HEAD_FULL"
    printf 'verifier_hash=%s\n' "$VERIFIER_HASH"
    printf 'contract_hash=%s\n' "$CONTRACT_HASH"
    printf 'backend_image_id=%s\n' "$BACKEND_IMAGE_ID"
    printf 'frontend_image_id=%s\n' "$FRONTEND_IMAGE_ID"
  } > "$RECEIPT_PATH"
}

require_command git
require_command docker
resolve_contract_root

PYTHON_BIN="${LOCAL_CORE_VERIFICATION_PYTHON:-$REPO_ROOT/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  fail_with_hint \
    "Verification Python is unavailable" \
    "Install requirements or set LOCAL_CORE_VERIFICATION_PYTHON to a valid executable." \
    "Current setting: $PYTHON_BIN"
fi

BASE_FULL="$(git rev-parse "$BASE_SHA^{commit}")"
HEAD_FULL="$(git rev-parse "$HEAD_SHA^{commit}")"
if ! git merge-base --is-ancestor "$BASE_FULL" "$HEAD_FULL"; then
  fail_with_hint \
    "Base commit is not ancestor of head" \
    "Check base/head SHA arguments; example: --base-sha origin/master --head-sha HEAD." \
    "Current base=$BASE_FULL head=$HEAD_FULL"
fi

require_clean_git_scope
docker compose version >/dev/null
docker image inspect "$BACKEND_TEST_IMAGE" >/dev/null

VERIFIER_HASH="$(git hash-object "$SCRIPT_DIR/verify_local_core_push.sh")"
CONTRACT_HASH="$(git hash-object "$CONTRACT_ROOT/scripts/product_semantic_traceability.py")"
BACKEND_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$BACKEND_TEST_IMAGE")"
ensure_frontend_toolchain
FRONTEND_IMAGE_ID="$(docker image inspect --format '{{.Id}}' mindscape-ai-local-core-frontend)"
GIT_COMMON_DIR_RAW="$(git rev-parse --git-common-dir)"
case "$GIT_COMMON_DIR_RAW" in
  /*) GIT_COMMON_DIR="$GIT_COMMON_DIR_RAW" ;;
  *) GIT_COMMON_DIR="$REPO_ROOT/$GIT_COMMON_DIR_RAW" ;;
esac
RECEIPT_DIR="$GIT_COMMON_DIR/mindscape-verification/local-core-push"
CHECK_RECEIPT_DIR="$RECEIPT_DIR/checks"
RECEIPT_KEY="$(printf '%s\n' \
  "$BASE_FULL" "$HEAD_FULL" "$VERIFIER_HASH" "$CONTRACT_HASH" \
  "$BACKEND_IMAGE_ID" "$FRONTEND_IMAGE_ID" | git hash-object --stdin)"
RECEIPT_PATH="$RECEIPT_DIR/$RECEIPT_KEY.receipt"

RANGE_FINGERPRINT="$(printf '%s\n' "$BASE_FULL" "$HEAD_FULL" "$VERIFIER_HASH" | git hash-object --stdin)"
SEMANTIC_FINGERPRINT="$(printf '%s\n' "$BASE_FULL" "$HEAD_FULL" "$CONTRACT_HASH" | git hash-object --stdin)"
SHELL_FINGERPRINT="$(path_fingerprint \
  install.sh scripts/start.sh scripts/compose.sh scripts/runtime_secrets \
  scripts/container_cleanup \
  docker/pgbouncer/start.sh docker/postgres/init-dual-dbs.sh \
  docker/postgres/reconcile-vector-runtime-role.sh \
  scripts/ci/runtime_secret_disposable_integration.sh)"
BACKEND_FINGERPRINT="$(printf '%s\n' "$BACKEND_IMAGE_ID" "$(path_fingerprint \
  backend/app/database backend/app/runtime_secret_command_facade.py \
  backend/app/routes/core/admin_reload.py \
  backend/app/routes/core/system_settings/system_control.py \
  backend/app/app_bootstrap/lifecycle_startup.py \
  backend/app/app_bootstrap/routes.py docker-compose.yml \
  docker/postgres docker/pgbouncer scripts/runtime_secrets \
  scripts/container_cleanup \
  install.sh install.ps1 scripts/start.sh scripts/start.ps1 \
  scripts/compose.sh scripts/compose.ps1 \
  backend/tests/database/runtime_secret_values_spec.py \
  backend/tests/runtime_secret_bootstrap_contract_spec.py \
  backend/tests/runtime_secret_compose_contract_spec.py \
  backend/tests/scripts/windows_container_cleanup_contract_spec.py \
  backend/tests/postgres_vector_runtime_reconcile_spec.py \
  backend/tests/database/connection_semantics_spec.py \
  backend/tests/postgres_runtime_readiness_config_spec.py \
  backend/tests/compose_topology_matrix_spec.py \
  backend/tests/test_system_control_restart_api.py)" \
  | git hash-object --stdin)"
ARCHITECTURE_FINGERPRINT="$(printf '%s\n' "$BACKEND_IMAGE_ID" "$(path_fingerprint \
  .github/workflows/architecture-guardrails.yml ci scripts/ci \
  scripts/git-hooks/pre-push.template backend/tests/ci)" | git hash-object --stdin)"
FRONTEND_FINGERPRINT="$(printf '%s\n' "$FRONTEND_IMAGE_ID" "$(path_fingerprint \
  Dockerfile.frontend package.json pnpm-lock.yaml pnpm-workspace.yaml \
  web-console/package.json web-console/src/lib/i18n/locales)" | git hash-object --stdin)"
DISPOSABLE_FINGERPRINT="$(path_fingerprint \
  scripts/ci/runtime_secret_disposable_integration.sh \
  docker/postgres docker/pgbouncer)"

if [ "$EXPLAIN" -eq 1 ]; then
  printf 'receipt_dir=%s\n' "$RECEIPT_DIR"
  printf 'git-scope=%s\n' "$RANGE_FINGERPRINT"
  printf 'credential-scan=%s\n' "$RANGE_FINGERPRINT"
  printf 'shell-syntax=%s\n' "$SHELL_FINGERPRINT"
  printf 'helper-parity=%s\n' "$CONTRACT_HASH"
  printf 'compose-topology=%s\n' "$ARCHITECTURE_FINGERPRINT"
  printf 'modular-entrypoints=%s\n' "$SEMANTIC_FINGERPRINT"
  printf 'product-semantics=%s\n' "$SEMANTIC_FINGERPRINT"
  printf 'backend-contracts=%s\n' "$BACKEND_FINGERPRINT"
  printf 'architecture-contracts=%s\n' "$ARCHITECTURE_FINGERPRINT"
  printf 'frontend-locale=%s\n' "$FRONTEND_FINGERPRINT"
  printf 'disposable-integration=%s\n' "$DISPOSABLE_FINGERPRINT"
  exit 0
fi

if [ "$FORCE" -eq 0 ] && [ -f "$RECEIPT_PATH" ] \
    && grep -Fxq 'status=passed' "$RECEIPT_PATH"; then
  printf 'OK: reusable Local Core push verification receipt found\n'
  printf '  base=%s\n  head=%s\n  receipt=%s\n' "$BASE_FULL" "$HEAD_FULL" "$RECEIPT_PATH"
  exit 0
fi

run_cached_gate git-scope "Git scope and whitespace" "$RANGE_FINGERPRINT" \
  git diff --check "$BASE_FULL..$HEAD_FULL"
run_cached_gate credential-scan "Credential and .env scan" "$RANGE_FINGERPRINT" \
  reject_secret_literals
run_cached_gate shell-syntax "Shell syntax" "$SHELL_FINGERPRINT" bash -n \
  install.sh \
  scripts/start.sh \
  scripts/compose.sh \
  scripts/runtime_secrets/file_store.sh \
  scripts/runtime_secrets/runtime_secrets.sh \
  docker/pgbouncer/start.sh \
  docker/postgres/init-dual-dbs.sh \
  docker/postgres/reconcile-vector-runtime-role.sh \
  scripts/ci/runtime_secret_disposable_integration.sh
run_cached_gate helper-parity "Product semantic helper parity" "$CONTRACT_HASH" "$PYTHON_BIN" \
  scripts/ci/validate_product_semantic_helper_parity.py \
  --canonical-helper "$CONTRACT_ROOT/scripts/product_semantic_traceability.py"
run_cached_gate compose-topology "Compose topology" "$ARCHITECTURE_FINGERPRINT" \
  "$PYTHON_BIN" scripts/ci/validate_compose_topology.py --repo-root .
run_cached_gate modular-entrypoints "Modular entrypoints" "$SEMANTIC_FINGERPRINT" \
  "$PYTHON_BIN" scripts/ci/validate_modular_entrypoints.py \
  --event-name push --base-sha "$BASE_FULL" --head-sha "$HEAD_FULL" \
  --policy ci/modular_entry_guardrails.yaml
run_cached_gate product-semantics "Product semantics" "$SEMANTIC_FINGERPRINT" \
  "$PYTHON_BIN" scripts/ci/validate_product_semantics.py \
  --event-name push --base-sha "$BASE_FULL" --head-sha "$HEAD_FULL" \
  --registry ci/product_semantic_surfaces.yaml --contract-root "$CONTRACT_ROOT"
run_cached_gate backend-contracts "Focused backend contracts" "$BACKEND_FINGERPRINT" run_backend_tests
run_cached_gate architecture-contracts "Architecture guardrail contracts" \
  "$ARCHITECTURE_FINGERPRINT" run_architecture_tests
run_cached_gate frontend-locale "Frontend locale contracts" "$FRONTEND_FINGERPRINT" run_frontend_tests
run_cached_gate disposable-integration "Disposable PostgreSQL and PgBouncer integration" \
  "$DISPOSABLE_FINGERPRINT" scripts/ci/runtime_secret_disposable_integration.sh

FRONTEND_IMAGE_ID="$(docker image inspect --format '{{.Id}}' mindscape-ai-local-core-frontend)"
RECEIPT_KEY="$(printf '%s\n' \
  "$BASE_FULL" "$HEAD_FULL" "$VERIFIER_HASH" "$CONTRACT_HASH" \
  "$BACKEND_IMAGE_ID" "$FRONTEND_IMAGE_ID" | git hash-object --stdin)"
RECEIPT_PATH="$RECEIPT_DIR/$RECEIPT_KEY.receipt"
write_receipt
printf '\nOK: Local Core push verification passed\n'
printf '  base=%s\n  head=%s\n  receipt=%s\n' "$BASE_FULL" "$HEAD_FULL" "$RECEIPT_PATH"
