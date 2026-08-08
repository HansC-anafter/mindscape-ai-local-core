#!/usr/bin/env bash

# Public Unix-like facade for Local Core runtime secrets.

MINDSCAPE_RUNTIME_SECRETS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=file_store.sh
source "$MINDSCAPE_RUNTIME_SECRETS_DIR/file_store.sh"

mindscape_initialize_runtime_secrets() {
    local project_root="${1:-$(cd "$MINDSCAPE_RUNTIME_SECRETS_DIR/../.." && pwd)}"
    local secret_root="${MINDSCAPE_RUNTIME_SECRET_ROOT:-$project_root/data/secrets}"
    local env_file="${MINDSCAPE_RUNTIME_ENV_FILE:-$project_root/.env}"
    local secret_file="$secret_root/postgres_vector_runtime_password"
    local secret_value
    local state

    if [ -e "$secret_file" ] || [ -L "$secret_file" ]; then
        secret_value="$(mindscape_secret_read_file "$secret_file")" || return 1
        state="existing"
    else
        secret_value="$(mindscape_secret_read_legacy_env "$env_file")" || return 1
        if [ -n "$secret_value" ]; then
            state="imported"
        else
            secret_value="$(mindscape_secret_generate)" || return 1
            state="created"
        fi
        mindscape_secret_write_file "$secret_root" "$secret_file" "$secret_value" || return 1
        secret_value="$(mindscape_secret_read_file "$secret_file")" || return 1
    fi

    export POSTGRES_VECTOR_RUNTIME_PASSWORD="$secret_value"
    export MINDSCAPE_RUNTIME_SECRET_STATE="$state"
    export MINDSCAPE_RUNTIME_SECRET_BACKEND="file"
}
