# AOL Host Bridge Runtime Evidence - 2026-05-04

## Verdict

`codex_cli` host bridge persistence is now verified for workspace `bac7ce63-e768-454d-96f3-3a00e8e1df69`.

What was wrong before this correction:

- LaunchAgent `ai.mindscape.cli-bridge` was loaded, but the target workspace was being served by a `host_ws_client.py` process whose parent was Codex app-server, not the launchd-managed `codex_cli` watcher.
- Historical `logs/cli-bridge.log` lines showed the watcher had previously stopped target workspace bridge processes after the workspace list reported the workspace as removed.
- The watcher lacked workspace-list missing debounce, so transient backend/workspace-list instability could make it kill a bridge that should have survived a restart window.

What was changed:

- `scripts/start_cli_bridge.sh` now supports `MINDSCAPE_BRIDGE_WORKSPACE_REMOVAL_GRACE_POLLS` with default `12` polls before stopping a missing workspace bridge.
- `scripts/start_cli_bridge.sh` now supports `MINDSCAPE_BRIDGE_PINNED_WORKSPACE_IDS` / `MINDSCAPE_WORKSPACE_ID` pinning.
- `find_ws_index()` and `find_missing_index()` now return a single `-1` sentinel without triggering duplicated fallback output that caused `bad array subscript`.

## Runtime Process Evidence

LaunchAgent after kickstart:

```bash
launchctl list ai.mindscape.cli-bridge
```

Observed key fields:

```text
"PID" = 17624
"ProgramArguments" = (
  "/opt/homebrew/bin/bash";
  "/Users/shock/Projects_local/workspace/mindscape-ai-local-core/scripts/start_cli_bridge_supervisor.sh";
  "--all";
)
"LastExitStatus" = 0
```

Target `codex_cli` bridge after stabilization:

```bash
ps -Ao pid=,ppid=,command= | awk '$2 == 17641 || /host_ws_client.py/ && /bac7ce63-e768-454d-96f3-3a00e8e1df69/ && /codex_cli/ {print}'
```

Observed:

```text
18082 17641 /opt/miniconda3/bin/python3 /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/external_agents/bridge/host_ws_client.py --workspace-id bac7ce63-e768-454d-96f3-3a00e8e1df69 --host localhost:8200 --surface codex_cli --workspace-root /Users/shock/Projects_local/workspace/mindscape-ai-local-core
```

This proves the target `codex_cli` bridge was under the launchd-managed surface watcher, not only under Codex app-server.

## Controlled Respawn Test

Command:

```bash
kill 18082
sleep 20
ps -Ao pid=,ppid=,command= | awk '/host_ws_client.py/ && /bac7ce63-e768-454d-96f3-3a00e8e1df69/ && /codex_cli/ && $0 !~ /awk/ {print}'
```

Observed process:

```text
21617 17641 /opt/miniconda3/bin/python3 /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/external_agents/bridge/host_ws_client.py --workspace-id bac7ce63-e768-454d-96f3-3a00e8e1df69 --host localhost:8200 --surface codex_cli --workspace-root /Users/shock/Projects_local/workspace/mindscape-ai-local-core
```

Observed watcher log:

```text
[WARN]  Bridge PID 18082 for bac7ce63-e768-454d-96f3-3a00e8e1df69 died, will respawn
[INFO]    Spawning bridge for workspace: bac7ce63-e768-454d-96f3-3a00e8e1df69
[INFO]    Bridge PID 21617 started for bac7ce63-e768-454d-96f3-3a00e8e1df69
```

Observed client connection log:

```text
2026-05-04 03:41:16,381 [INFO] Starting host bridge WS client (workspace=bac7ce63-e768-454d-96f3-3a00e8e1df69 surface=codex_cli pid=21617 ppid=17641 pgid=17624 xpc_service=ai.mindscape.cli-bridge)
2026-05-04 03:41:16,690 [INFO] Connected!
2026-05-04 03:41:17,900 [INFO] Host-session runtime registered for workspace=bac7ce63-e768-454d-96f3-3a00e8e1df69 surface=codex_cli runtime_id=runtime-codex_cli-d15b49a23df6 count=36
```

## Residual Notes

- The controlled `kill` test produces expected shutdown noise from asyncio cancellation (`Task was destroyed but it is pending!`). That is not a respawn failure; the replacement process connected and registered.
- This evidence proves process-level auto-revival for the target workspace after the correction. It does not by itself prove any MeetingEngine E2E content deliverable.
