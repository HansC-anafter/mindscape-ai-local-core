#!/bin/bash

mindscape_list_conflicting_containers() {
    docker ps -a --filter "name=mindscape-ai-local-core" --format "{{.Names}}" 2>/dev/null
}

mindscape_remove_residual_containers() {
    local residual_containers
    local current_containers
    local failed_containers=()

    if ! residual_containers="$(mindscape_list_conflicting_containers)"; then
        echo "ERROR: Unable to list existing Mindscape containers." >&2
        return 1
    fi

    while IFS= read -r container; do
        if [ -z "$container" ]; then
            continue
        fi
        if docker rm -f "$container" >/dev/null 2>&1; then
            continue
        fi
        if ! current_containers="$(mindscape_list_conflicting_containers)"; then
            failed_containers+=("$container")
            continue
        fi
        if printf '%s\n' "$current_containers" | grep -Fxq "$container"; then
            failed_containers+=("$container")
        fi
    done <<< "$residual_containers"

    if [ "${#failed_containers[@]}" -gt 0 ]; then
        echo "ERROR: Unable to remove conflicting containers: ${failed_containers[*]}." >&2
        return 1
    fi
}
