#!/bin/sh
set -eu

secret_file="${POSTGRES_VECTOR_RUNTIME_PASSWORD_FILE:-/run/secrets/postgres_vector_runtime_password}"
auth_file="/tmp/pgbouncer-userlist.txt"
if [ ! -r "$secret_file" ]; then
  echo "[runtime-secret] PgBouncer vector runtime secret file is unavailable" >&2
  exit 1
fi

runtime_secret=""
IFS= read -r runtime_secret < "$secret_file" || true
secret_file_bytes="$(LC_ALL=C wc -c < "$secret_file")"
secret_value_bytes="$(LC_ALL=C printf '%s' "$runtime_secret" | wc -c)"
secret_final_byte="$(LC_ALL=C tail -c 1 "$secret_file" | od -An -tu1 | tr -d ' ')"
if [ "$secret_file_bytes" -eq "$secret_value_bytes" ]; then
  :
elif [ "$secret_file_bytes" -eq $((secret_value_bytes + 1)) ] && [ "$secret_final_byte" = "10" ]; then
  runtime_secret="${runtime_secret%$(printf '\r')}"
else
  echo "[runtime-secret] PgBouncer vector runtime secret must contain exactly one line" >&2
  exit 1
fi
case "$runtime_secret" in
  *"$(printf '\r')"*)
    echo "[runtime-secret] PgBouncer vector runtime secret is invalid" >&2
    exit 1
    ;;
esac
if [ -z "$runtime_secret" ] || [ "${#runtime_secret}" -gt 4096 ]; then
  echo "[runtime-secret] PgBouncer vector runtime secret is invalid" >&2
  exit 1
fi

escape_auth_field() {
  printf '%s' "$1" | sed 's/"/""/g'
}

core_user="$(escape_auth_field "${POSTGRES_CORE_USER:-mindscape}")"
core_password="$(escape_auth_field "${POSTGRES_CORE_PASSWORD:-mindscape_password}")"
runtime_user="$(escape_auth_field "${POSTGRES_VECTOR_RUNTIME_USER:-mindscape_vector_runtime}")"
runtime_password="$(escape_auth_field "$runtime_secret")"

umask 077
printf '"%s" "%s"\n' "$core_user" "$core_password" > "$auth_file"
printf '"%s" "%s"\n' "$runtime_user" "$runtime_password" >> "$auth_file"
chmod 600 "$auth_file"
exec /usr/sbin/pgbouncer /etc/pgbouncer/pgbouncer.ini
