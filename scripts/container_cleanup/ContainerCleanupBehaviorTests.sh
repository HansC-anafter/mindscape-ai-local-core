#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/container_cleanup.sh"

TEST_TMP_DIR="$(mktemp -d)"
CALL_LOG="$TEST_TMP_DIR/docker-calls.log"
SCENARIO=""
trap 'rm -rf "$TEST_TMP_DIR"' EXIT

docker() {
    local call_index
    call_index="$(wc -l < "$CALL_LOG" | tr -d ' ')"
    printf '%s\n' "$*" >> "$CALL_LOG"

    case "$SCENARIO:$call_index" in
        empty:0)
            return 0
            ;;
        disappears:0|persistent:0|persistent:2)
            printf '%s\n' "mindscape-ai-local-core-backend"
            return 0
            ;;
        disappears:1|persistent:1)
            return 1
            ;;
        disappears:2)
            return 0
            ;;
        *)
            echo "Unexpected docker invocation for $SCENARIO: $*" >&2
            return 99
            ;;
    esac
}

assert_call_count() {
    local expected="$1"
    local message="$2"
    local actual
    actual="$(wc -l < "$CALL_LOG" | tr -d ' ')"
    if [ "$actual" -ne "$expected" ]; then
        echo "$message Expected '$expected', got '$actual'." >&2
        exit 1
    fi
}

: > "$CALL_LOG"
SCENARIO="empty"
mindscape_remove_residual_containers
assert_call_count 1 "An empty post-compose query must not invoke docker rm."

: > "$CALL_LOG"
SCENARIO="disappears"
mindscape_remove_residual_containers
assert_call_count 3 "A container that disappears during removal must be accepted."

: > "$CALL_LOG"
SCENARIO="persistent"
if mindscape_remove_residual_containers 2> "$TEST_TMP_DIR/persistent-error.log"; then
    echo "A container that remains after removal must fail cleanup." >&2
    exit 1
fi
assert_call_count 3 "Persistent-container verification must re-query Docker."
grep -Fq "mindscape-ai-local-core-backend" "$TEST_TMP_DIR/persistent-error.log"

echo "Shell container cleanup behavior tests passed."
