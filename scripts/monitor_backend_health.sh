#!/usr/bin/env bash
set -euo pipefail

HEALTH_URL="${HEALTH_URL:-http://localhost:8200/health}"
DUMP_URL="${DUMP_URL:-http://localhost:8200/debug/dump-stacks}"
INTERVAL="${INTERVAL:-2}"
TIMEOUT="${TIMEOUT:-2}"
MAX_FAILS="${MAX_FAILS:-1}"
COOLDOWN="${COOLDOWN:-10}"
EXIT_AFTER_DUMP="${EXIT_AFTER_DUMP:-1}"

fail_count=0

echo "[monitor] health: $HEALTH_URL"
echo "[monitor] dump:   $DUMP_URL"
echo "[monitor] interval=${INTERVAL}s timeout=${TIMEOUT}s max_fails=${MAX_FAILS} cooldown=${COOLDOWN}s exit_after_dump=${EXIT_AFTER_DUMP}"

while true; do
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  if curl -fsS -m "$TIMEOUT" "$HEALTH_URL" >/dev/null; then
    fail_count=0
    echo "[$ts] health ok"
  else
    fail_count=$((fail_count + 1))
    echo "[$ts] health FAIL ($fail_count/$MAX_FAILS)"
    if [ "$fail_count" -ge "$MAX_FAILS" ]; then
      echo "[$ts] triggering dump..."
      if ! curl -sS -m 5 -X POST "$DUMP_URL" >/dev/null; then
        echo "[$ts] dump request failed"
      fi
      if [ "$EXIT_AFTER_DUMP" = "1" ]; then
        echo "[$ts] exit after dump"
        exit 1
      fi
      echo "[$ts] cooldown ${COOLDOWN}s"
      sleep "$COOLDOWN"
      fail_count=0
    fi
  fi
  sleep "$INTERVAL"
done
