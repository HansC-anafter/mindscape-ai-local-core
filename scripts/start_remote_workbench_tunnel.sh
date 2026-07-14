#!/usr/bin/env bash
set -euo pipefail

umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE_DIR="${REMOTE_WORKBENCH_BRIDGE_STATE_DIR:-$HOME/.mindscape/remote-workbench-bridge}"
MAINTENANCE_FILE="$STATE_DIR/maintenance.json"
STATUS_FILE="$STATE_DIR/status.json"
INGRESS_LOCK_PATH="$STATE_DIR/remote-ingress-lock.json"
CONTAINER_NAME="${REMOTE_WORKBENCH_TUNNEL_CONTAINER:-ig-workbench-cloudflared}"
NETWORK_NAME="mindscape-network"
INTERNAL_TARGET="http://mindscape-ai-local-core-frontend:3001"
PUBLIC_HOSTNAME="remote-workbench.mindscapeai.app"
TOKEN_PATH="${REMOTE_WORKBENCH_CLOUDFLARED_TOKEN_FILE:-$PROJECT_ROOT/data/cloudflared/tunnel-token}"
CLOUDFLARED_IMAGE="cloudflare/cloudflared@sha256:ba461b8aa9c042156dbd39c38657fe7431bafa063220eab8d5330a523863da9f"
METRICS_HOST_PORT="2000"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
INGRESS_LOCK_HELPER="$PROJECT_ROOT/scripts/remote_workbench_remote_ingress_lock.py"
BRIDGE_INSTALLER="$PROJECT_ROOT/scripts/install-remote-workbench-bridge-macos.sh"
STATUS_STALE_SECONDS="60"

if [[ -z "${DOCKER_HOST:-}" && -S "$HOME/.docker/run/docker.sock" ]]; then
  export DOCKER_HOST="unix://$HOME/.docker/run/docker.sock"
fi

log() {
  printf '[remote-workbench-tunnel] %s\n' "$*" >&2
}

fail() {
  log "ERROR: $*"
  exit 1
}

ensure_state_dir() {
  [[ ! -L "$STATE_DIR" ]] || fail "Bridge state directory must not be a symbolic link"
  mkdir -p "$STATE_DIR"
  [[ -d "$STATE_DIR" ]] || fail "Bridge state path is not a directory"
  chmod 700 "$STATE_DIR"
}

file_mode() {
  local mode
  mode="$(stat -f '%Lp' "$1" 2>/dev/null || true)"
  if [[ "$mode" =~ ^[0-7]{3,4}$ ]]; then
    printf '%s\n' "$mode"
    return
  fi
  stat -c '%a' "$1" 2>/dev/null
}

file_mtime() {
  local value
  value="$(stat -f '%m' "$1" 2>/dev/null || true)"
  if [[ "$value" =~ ^[0-9]+$ ]]; then
    printf '%s\n' "$value"
    return
  fi
  stat -c '%Y' "$1" 2>/dev/null
}

token_file_valid() {
  [[ -f "$TOKEN_PATH" && ! -L "$TOKEN_PATH" ]] || return 1
  local mode
  mode="$(file_mode "$TOKEN_PATH")" || return 1
  [[ "$mode" == "600" ]]
}

remote_ingress_lock_valid() {
  [[ "$PYTHON_BIN" == /* && -x "$PYTHON_BIN" ]] || return 1
  [[ -f "$INGRESS_LOCK_HELPER" && ! -L "$INGRESS_LOCK_HELPER" ]] || return 1
  "$PYTHON_BIN" "$INGRESS_LOCK_HELPER" validate-lock \
    --lock-path "$INGRESS_LOCK_PATH" --token-path "$TOKEN_PATH" >/dev/null 2>&1
}

remote_ingress_live_json() {
  [[ "$PYTHON_BIN" == /* && -x "$PYTHON_BIN" ]] || return 1
  [[ -f "$INGRESS_LOCK_HELPER" && ! -L "$INGRESS_LOCK_HELPER" ]] || return 1
  "$PYTHON_BIN" "$INGRESS_LOCK_HELPER" verify-live \
    --lock-path "$INGRESS_LOCK_PATH" --token-path "$TOKEN_PATH" --json
}

wait_remote_ingress_live() {
  local attempt
  for attempt in $(seq 1 10); do
    if remote_ingress_live_json >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

container_exists() {
  docker inspect "$CONTAINER_NAME" >/dev/null 2>&1
}

container_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || true)" == "true" ]]
}

container_contract_valid() {
  container_exists || return 1
  local token_source token_rw token_type bindings expected_bindings image_id
  local container_environment image_environment container_user image_user
  local expected_command expected_entrypoint
  [[ "$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$CONTAINER_NAME")" == "unless-stopped" ]] || return 1
  [[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$CONTAINER_NAME")" == "$NETWORK_NAME" ]] || return 1
  [[ "$(docker inspect -f '{{len .Mounts}}' "$CONTAINER_NAME")" == "1" ]] || return 1
  token_source="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/cloudflared/tunnel-token"}}{{.Source}}{{end}}{{end}}' "$CONTAINER_NAME")"
  token_rw="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/cloudflared/tunnel-token"}}{{.RW}}{{end}}{{end}}' "$CONTAINER_NAME")"
  token_type="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/cloudflared/tunnel-token"}}{{.Type}}{{end}}{{end}}' "$CONTAINER_NAME")"
  [[ "$token_source" == "$TOKEN_PATH" ]] || return 1
  [[ "$token_rw" == "false" && "$token_type" == "bind" ]] || return 1
  bindings="$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$CONTAINER_NAME")"
  expected_bindings="{\"2000/tcp\":[{\"HostIp\":\"127.0.0.1\",\"HostPort\":\"$METRICS_HOST_PORT\"}]}"
  [[ "$bindings" == "$expected_bindings" ]] || return 1
  [[ "$(docker inspect -f '{{.Config.Image}}' "$CONTAINER_NAME")" == "$CLOUDFLARED_IMAGE" ]] || return 1
  image_id="$(docker image inspect -f '{{.Id}}' "$CLOUDFLARED_IMAGE" 2>/dev/null)" || return 1
  [[ "$(docker inspect -f '{{.Image}}' "$CONTAINER_NAME")" == "$image_id" ]] || return 1
  container_environment="$(docker inspect -f '{{json .Config.Env}}' "$CONTAINER_NAME")"
  image_environment="$(docker image inspect -f '{{json .Config.Env}}' "$CLOUDFLARED_IMAGE")"
  [[ "$container_environment" == "$image_environment" ]] || return 1
  container_user="$(docker inspect -f '{{.Config.User}}' "$CONTAINER_NAME")"
  image_user="$(docker image inspect -f '{{.Config.User}}' "$CLOUDFLARED_IMAGE")"
  [[ -n "$image_user" && "$container_user" == "$image_user" ]] || return 1
  [[ "$(docker inspect -f '{{.HostConfig.Privileged}}' "$CONTAINER_NAME")" == "false" ]] || return 1
  expected_entrypoint='["cloudflared","--no-autoupdate"]'
  [[ "$(docker inspect -f '{{json .Config.Entrypoint}}' "$CONTAINER_NAME")" == "$expected_entrypoint" ]] || return 1
  expected_command='["tunnel","--no-autoupdate","--metrics","0.0.0.0:2000","run","--token-file","/etc/cloudflared/tunnel-token"]'
  [[ "$(docker inspect -f '{{json .Config.Cmd}}' "$CONTAINER_NAME")" == "$expected_command" ]] || return 1
  token_file_valid || return 1
}

create_container() {
  token_file_valid || fail "Cloudflared token file must be regular and operator-only"
  docker network inspect "$NETWORK_NAME" >/dev/null 2>&1 || fail "Docker network $NETWORK_NAME is unavailable"
  docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    --network "$NETWORK_NAME" \
    -p "127.0.0.1:${METRICS_HOST_PORT}:2000" \
    -v "$TOKEN_PATH:/etc/cloudflared/tunnel-token:ro" \
    "$CLOUDFLARED_IMAGE" \
    tunnel --no-autoupdate --metrics 0.0.0.0:2000 run \
    --token-file /etc/cloudflared/tunnel-token >/dev/null
  log "Pinned remotely-managed tunnel container created"
}

ensure_tunnel() {
  token_file_valid || fail "Cloudflared token file must be regular and operator-only"
  ensure_state_dir
  if ! remote_ingress_lock_valid; then
    stop_tunnel
    fail "Exact Cloudflare remote-ingress lock is unavailable or malformed"
  fi
  if container_exists && ! container_contract_valid; then
    log "Replacing tunnel container because its immutable local contract does not match"
    docker rm -f "$CONTAINER_NAME" >/dev/null
  fi
  if ! container_exists; then
    create_container
  elif ! container_running; then
    docker start "$CONTAINER_NAME" >/dev/null
    log "Tunnel container started"
  fi
  if ! wait_remote_ingress_live; then
    stop_tunnel
    fail "Live connector tunnel/config version does not match the Cloudflare readback lock"
  fi
}

stop_tunnel() {
  if container_running; then
    docker stop "$CONTAINER_NAME" >/dev/null
    log "Tunnel container stopped"
  fi
}

restart_tunnel() {
  token_file_valid || fail "Cloudflared token file must be regular and operator-only"
  ensure_state_dir
  if ! remote_ingress_lock_valid; then
    stop_tunnel
    fail "Exact Cloudflare remote-ingress lock is unavailable or malformed"
  fi
  if container_exists && ! container_contract_valid; then
    docker rm -f "$CONTAINER_NAME" >/dev/null
  fi
  if container_exists; then
    docker restart "$CONTAINER_NAME" >/dev/null
    log "Tunnel container restarted"
  else
    create_container
  fi
  if ! wait_remote_ingress_live; then
    stop_tunnel
    fail "Restarted connector did not activate the locked Cloudflare config version"
  fi
}

recreate_tunnel() {
  token_file_valid || fail "Cloudflared token file must be regular and operator-only"
  ensure_state_dir
  if ! remote_ingress_lock_valid; then
    stop_tunnel
    fail "Exact Cloudflare remote-ingress lock is unavailable or malformed"
  fi
  if container_exists; then
    docker rm -f "$CONTAINER_NAME" >/dev/null
  fi
  create_container
  if ! wait_remote_ingress_live; then
    stop_tunnel
    fail "Recreated connector did not activate the locked Cloudflare config version"
  fi
}

supervisor_activation_json() {
  [[ -x "$BRIDGE_INSTALLER" && ! -L "$BRIDGE_INSTALLER" ]] || return 1
  "$BRIDGE_INSTALLER" verify --json
}

supervisor_loaded() {
  /bin/launchctl print "gui/$(id -u)/ai.mindscape.remote-workbench-bridge" >/dev/null 2>&1
}

docker_available() {
  docker info >/dev/null 2>&1
}

tunnel_closed() {
  ! container_running
}

maintenance_enter() {
  local reason="${1:-operator_cutover}"
  local temporary
  [[ "$reason" =~ ^[A-Za-z0-9._:-]+$ ]] || fail "Maintenance reason contains unsupported characters"
  if [[ "$reason" == "supervisor_activation" ]]; then
    [[ "$(uname -s)" == "Darwin" ]] || fail "Supervisor activation is supported only on macOS"
    if supervisor_loaded; then
      fail "Supervisor activation maintenance requires the previous launchd service to be unloaded"
    fi
  else
    supervisor_activation_json >/dev/null || fail "Current launchd supervisor build/argv/state is not verified"
  fi
  ensure_state_dir
  temporary="$(mktemp "$STATE_DIR/.maintenance.XXXXXX")"
  printf '{"enabled":true,"reason":"%s","updated_at":"%s"}\n' \
    "$reason" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$temporary"
  chmod 600 "$temporary"
  mv -f "$temporary" "$MAINTENANCE_FILE"
  chmod 600 "$MAINTENANCE_FILE"
  if [[ "$reason" == "supervisor_activation" ]]; then
    docker_available || fail "Docker must be reachable before supervisor activation"
    stop_tunnel || fail "Tunnel stop failed during supervisor activation"
    tunnel_closed || fail "Tunnel remained running during supervisor activation"
    log "Activation maintenance recorded and tunnel closure proved"
    return
  fi
  local activation attempt
  for attempt in $(seq 1 30); do
    activation="$(supervisor_activation_json 2>/dev/null || true)"
    if [[ "$activation" == *'"maintenance":true'* && "$activation" == *'"state":"maintenance"'* ]]; then
      log "Maintenance enabled; current supervisor confirmed no-repair state"
      return
    fi
    sleep 1
  done
  fail "Current supervisor did not confirm maintenance state"
}

maintenance_exit() {
  local activation
  activation="$(supervisor_activation_json 2>/dev/null || true)"
  [[ "$activation" == *'"maintenance":true'* && "$activation" == *'"state":"maintenance"'* ]] || fail "Maintenance exit requires the verified current supervisor"
  rm -f "$MAINTENANCE_FILE"
  log "Maintenance disabled"
}

status_json() {
  local running=false
  local container_contract=false
  local remote_ingress=false
  local contract=false
  local maintenance=false
  local token=false
  local supervisor_fresh=false
  local supervisor_ready=false
  local supervisor_state=unavailable
  local ready=false
  container_running && running=true
  container_contract_valid && container_contract=true
  if [[ "$running" == true ]] && remote_ingress_live_json >/dev/null 2>&1; then
    remote_ingress=true
  fi
  if [[ "$container_contract" == true && "$remote_ingress" == true ]]; then
    contract=true
  fi
  if [[ -L "$MAINTENANCE_FILE" || -f "$MAINTENANCE_FILE" ]]; then
    maintenance=true
  fi
  token_file_valid && token=true
  if [[ -f "$STATUS_FILE" && ! -L "$STATUS_FILE" && "$(file_mode "$STATUS_FILE")" == "600" ]]; then
    local checked age
    checked="$(file_mtime "$STATUS_FILE" || true)"
    if [[ "$checked" =~ ^[0-9]+$ ]]; then
      age=$(( $(date +%s) - checked ))
      if (( age >= 0 && age <= STATUS_STALE_SECONDS )); then
        supervisor_fresh=true
        grep -Fq '"ready":true' "$STATUS_FILE" && supervisor_ready=true
        supervisor_state="$(sed -n 's/.*"state":"\([A-Za-z0-9_]*\)".*/\1/p' "$STATUS_FILE")"
        [[ -n "$supervisor_state" ]] || supervisor_state=malformed
      else
        supervisor_state=stale
      fi
    else
      supervisor_state=malformed
    fi
  fi
  if [[ "$maintenance" == true ]]; then
    supervisor_state=maintenance
    supervisor_ready=false
  fi
  if [[ "$running" == true && "$contract" == true && "$supervisor_fresh" == true && "$supervisor_ready" == true && "$maintenance" == false ]]; then
    ready=true
  fi
  printf '{"container":"%s","running":%s,"container_contract_conformant":%s,"remote_ingress_verified":%s,"contract_conformant":%s,"maintenance":%s,"token_file_valid":%s,"image":"%s","network":"%s","remote_config_source":"cloudflare","hostname":"%s","internal_target":"%s","supervisor_fresh":%s,"supervisor_state":"%s","ready":%s,"authorization_conformant":false}\n' \
    "$CONTAINER_NAME" "$running" "$container_contract" "$remote_ingress" "$contract" "$maintenance" "$token" "$CLOUDFLARED_IMAGE" "$NETWORK_NAME" "$PUBLIC_HOSTNAME" "$INTERNAL_TARGET" "$supervisor_fresh" "$supervisor_state" "$ready"
  return 0
}

status_human() {
  status_json
}

usage() {
  printf 'Usage: %s [ensure|restart|recreate|stop|status [--json]|supervisor verify --json|maintenance enter [reason]|maintenance exit|--restart|--recreate]\n' "$0" >&2
}

main() {
  if [[ $# -eq 0 ]]; then
    set -- ensure
  elif [[ $# -eq 1 && "$1" == "--restart" ]]; then
    set -- restart
  elif [[ $# -eq 1 && "$1" == "--recreate" ]]; then
    set -- recreate
  elif [[ $# -eq 1 && ( "$1" == "--help" || "$1" == "-h" ) ]]; then
    usage
    return 0
  fi
  local action="$1"
  [[ "$STATE_DIR" == /* ]] || fail "Bridge state directory must be absolute"
  [[ "$TOKEN_PATH" == /* ]] || fail "Cloudflared token path must be absolute"
  [[ "$CONTAINER_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]] || fail "Tunnel container name is malformed"
  case "$action" in
    ensure)
      [[ $# -eq 1 ]] || fail "ensure accepts no additional arguments"
      ensure_tunnel
      ;;
    restart)
      [[ $# -eq 1 ]] || fail "restart accepts no additional arguments"
      restart_tunnel
      ;;
    recreate)
      [[ $# -eq 1 ]] || fail "recreate accepts no additional arguments"
      recreate_tunnel
      ;;
    stop)
      [[ $# -eq 1 ]] || fail "stop accepts no additional arguments"
      stop_tunnel
      ;;
    status)
      [[ $# -le 2 ]] || fail "status accepts only --json"
      [[ $# -eq 1 || "${2:-}" == "--json" ]] || fail "status accepts only --json"
      if [[ "${2:-}" == "--json" ]]; then
        status_json
      else
        status_human
      fi
      ;;
    supervisor)
      [[ $# -eq 3 && "${2:-}" == "verify" && "${3:-}" == "--json" ]] || fail "supervisor accepts only verify --json"
      supervisor_activation_json
      ;;
    maintenance)
      case "${2:-}" in
        enter)
          [[ $# -le 3 ]] || fail "maintenance enter accepts one reason"
          maintenance_enter "${3:-operator_cutover}"
          ;;
        exit)
          [[ $# -eq 2 ]] || fail "maintenance exit accepts no additional arguments"
          maintenance_exit
          ;;
        *)
          usage
          return 2
          ;;
      esac
      ;;
    *)
      usage
      return 2
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
