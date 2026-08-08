#!/usr/bin/env bash

# File-backed runtime secret storage for Unix-like hosts.

mindscape_secret_fail() {
    printf 'ERROR: %s\n' "$1" >&2
    return 1
}

mindscape_secret_validate_value() {
    local value="$1"
    if [ -z "$value" ]; then
        mindscape_secret_fail "Runtime secret is empty"
        return 1
    fi
    if [ "${#value}" -gt 4096 ]; then
        mindscape_secret_fail "Runtime secret exceeds the 4096-byte limit"
        return 1
    fi
    if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
        mindscape_secret_fail "Runtime secret must be a single line"
        return 1
    fi
}

mindscape_secret_mode() {
    local path="$1"
    if stat -f '%Lp' "$path" >/dev/null 2>&1; then
        stat -f '%Lp' "$path"
    else
        stat -c '%a' "$path"
    fi
}

mindscape_secret_owner_uid() {
    local path="$1"
    if stat -f '%u' "$path" >/dev/null 2>&1; then
        stat -f '%u' "$path"
    else
        stat -c '%u' "$path"
    fi
}

mindscape_secret_assert_private_path() {
    local path="$1"
    local expected_mode="$2"
    local actual_mode
    local actual_uid

    if [ -L "$path" ]; then
        mindscape_secret_fail "Runtime secret path must not be a symlink: $path"
        return 1
    fi
    actual_mode="$(mindscape_secret_mode "$path")"
    actual_uid="$(mindscape_secret_owner_uid "$path")"
    if [ "$actual_mode" != "$expected_mode" ]; then
        mindscape_secret_fail "Runtime secret path has mode $actual_mode; expected $expected_mode: $path"
        return 1
    fi
    if [ "$actual_uid" != "$(id -u)" ]; then
        mindscape_secret_fail "Runtime secret path is not owned by the current user: $path"
        return 1
    fi
}

mindscape_secret_read_file() {
    local path="$1"
    local value
    local file_bytes
    local value_bytes
    local final_byte

    [ -f "$path" ] || {
        mindscape_secret_fail "Runtime secret file is missing: $path"
        return 1
    }
    mindscape_secret_assert_private_path "$path" 600 || return 1
    value=""
    IFS= read -r value < "$path" || true
    file_bytes="$(LC_ALL=C command wc -c < "$path")"
    value_bytes="$(LC_ALL=C printf '%s' "$value" | command wc -c)"
    final_byte="$(LC_ALL=C command tail -c 1 "$path" | command od -An -tu1 | command tr -d ' ')"
    if [ "$file_bytes" -eq "$value_bytes" ]; then
        :
    elif [ "$file_bytes" -eq $((value_bytes + 1)) ] && [ "$final_byte" = "10" ]; then
        value="${value%$'\r'}"
    else
        mindscape_secret_fail "Runtime secret file must contain exactly one line"
        return 1
    fi
    mindscape_secret_validate_value "$value" || return 1
    printf '%s' "$value"
}

mindscape_secret_read_legacy_env() {
    local env_file="$1"
    local line
    local value=""

    [ -f "$env_file" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%$'\r'}"
        case "$line" in
            POSTGRES_VECTOR_RUNTIME_PASSWORD=*)
                value="${line#POSTGRES_VECTOR_RUNTIME_PASSWORD=}"
                ;;
        esac
    done < "$env_file"

    if [ "${#value}" -ge 2 ]; then
        if [[ "$value" == \"*\" && "$value" == *\" ]]; then
            value="${value:1:${#value}-2}"
        elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
            value="${value:1:${#value}-2}"
        fi
    fi
    if [ -n "$value" ]; then
        mindscape_secret_validate_value "$value" || return 1
        printf '%s' "$value"
    fi
}

mindscape_secret_generate() {
    local value
    value="$(LC_ALL=C od -An -N32 -tx1 /dev/urandom | command tr -d ' \n')"
    mindscape_secret_validate_value "$value" || return 1
    printf '%s' "$value"
}

mindscape_secret_write_file() {
    local directory="$1"
    local path="$2"
    local value="$3"
    local temp_path

    mindscape_secret_validate_value "$value" || return 1
    if [ -L "$directory" ] || [ -L "$path" ]; then
        mindscape_secret_fail "Runtime secret storage must not contain symlinks"
        return 1
    fi
    umask 077
    mkdir -p "$directory"
    chmod 700 "$directory"
    mindscape_secret_assert_private_path "$directory" 700 || return 1
    temp_path="$(mktemp "$directory/.runtime-secret.XXXXXX")"
    if ! printf '%s' "$value" > "$temp_path"; then
        rm -f "$temp_path"
        return 1
    fi
    chmod 600 "$temp_path"
    mv -f "$temp_path" "$path"
    mindscape_secret_assert_private_path "$path" 600
}
