#!/usr/bin/env python3
"""
Mindscape Headless Runner — OS-level daemon for task execution.

Polls backend for pending tasks, executes them via Gemini CLI (headless),
and submits results back. Runs as a persistent process (launchd/systemd).

Architecture:
    loop:
      GET /api/v1/mcp/agent/pending → reserve task
      POST /api/v1/mcp/agent/ack → confirm pickup
      threading: POST /api/v1/mcp/agent/progress → heartbeat every 25s
      subprocess: gemini -p "<task>" -o text --yolo → blocking execution
      POST /api/v1/mcp/agent/result → submit result
"""

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from concurrent.futures import ThreadPoolExecutor

# ---- Configuration ----

BACKEND_URL = os.environ.get("MINDSCAPE_BASE_URL", "http://localhost:8200")
WORKSPACE_ID = os.environ.get("MINDSCAPE_WORKSPACE_ID", "")
CLIENT_ID = os.environ.get("MINDSCAPE_CLIENT_ID", "gemini-headless-runner")
GEMINI_CLI = os.environ.get("GEMINI_CLI_PATH", "gemini")
POLL_WAIT = int(os.environ.get("MINDSCAPE_POLL_WAIT", "5"))
HEARTBEAT_INTERVAL = int(os.environ.get("MINDSCAPE_HEARTBEAT_INTERVAL", "25"))
TASK_TIMEOUT = int(os.environ.get("MINDSCAPE_TASK_TIMEOUT", "600"))
MAX_CONCURRENT = int(os.environ.get("MINDSCAPE_MAX_CONCURRENT", "3"))
MAX_OUTPUT = 500  # chars for summary
WORKSPACE_ROOT = os.environ.get(
    "MINDSCAPE_WORKSPACE_ROOT", "/Users/shock/Projects_local/workspace"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("mindscape-runner")

# ---- Graceful shutdown ----

_shutdown = threading.Event()


def _handle_signal(sig, _frame):
    log.info(f"Received {signal.Signals(sig).name}, shutting down...")
    _shutdown.set()


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---- HTTP helpers ----


def api_get(path: str, params: dict = None) -> dict:
    """GET request to backend API."""
    url = f"{BACKEND_URL}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_post(path: str, body: dict) -> dict:
    """POST request to backend API."""
    url = f"{BACKEND_URL}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---- Heartbeat ----


def heartbeat_loop(execution_id: str, lease_id: str, stop: threading.Event):
    """Send progress heartbeat every HEARTBEAT_INTERVAL seconds."""
    while not stop.is_set():
        try:
            api_post(
                "/api/v1/mcp/agent/progress",
                {
                    "execution_id": execution_id,
                    "lease_id": lease_id,
                    "progress": {"message": "heartbeat", "percent": -1},
                },
            )
        except Exception as e:
            log.warning(f"Heartbeat failed: {e}")
        stop.wait(HEARTBEAT_INTERVAL)


# ---- Executor ----


def execute_with_gemini(task: str, execution_id: str) -> tuple:
    """
    Execute task via Gemini CLI in headless mode.
    Returns (success: bool, output: str, error: str).
    """
    prompt = (
        f"{task}\n\n"
        f"[Context] workspace={WORKSPACE_ID}, execution_id={execution_id}\n"
        f"[Instruction] Answer the user's question. Be concise and factual."
    )

    cmd = [
        GEMINI_CLI,
        "-p",
        prompt,
        "-o",
        "text",
        "--yolo",
    ]

    log.info(f"Executing: gemini -p '...{task[:60]}' (timeout={TASK_TIMEOUT}s)")

    # Server-side tool filtering: pass task hint to MCP gateway
    task_hint = task[:500]

    try:
        sub_env = {
            **os.environ,
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
            "GOOGLE_CLOUD_PROJECT": os.environ.get(
                "GOOGLE_CLOUD_PROJECT", "anafter-workspace-project"
            ),
            "GOOGLE_CLOUD_LOCATION": os.environ.get(
                "GOOGLE_CLOUD_LOCATION", "us-central1"
            ),
            "MINDSCAPE_TASK_HINT": task_hint,
        }

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TASK_TIMEOUT,
            cwd=WORKSPACE_ROOT,
            env=sub_env,
        )

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        # Log stderr for debugging
        if stderr:
            log.info(f"Gemini stderr: {stderr[:300]}")

        # Filter out gemini CLI noise
        lines = [
            l
            for l in stdout.split("\n")
            if not l.startswith("Project hooks disabled")
            and not l.startswith("Hook registry")
            and not l.startswith("YOLO mode")
            and not l.startswith("Approval mode overridden")
            and "is not trusted" not in l
        ]
        output = "\n".join(lines).strip()

        if result.returncode == 0 and output:
            return True, output, ""
        elif result.returncode == 0:
            return True, "Task completed (no output)", ""
        else:
            # Use output if available, otherwise include stderr excerpt
            error_detail = f"Exit code {result.returncode}: {stderr[:500]}"
            log.error(f"Gemini CLI failed: {error_detail}")
            return False, output, error_detail

    except subprocess.TimeoutExpired:
        return False, "", f"Timed out after {TASK_TIMEOUT}s"
    except FileNotFoundError:
        return False, "", f"Gemini CLI not found at {GEMINI_CLI}"
    except Exception as e:
        return False, "", str(e)


# ---- Task execution (thread-safe) ----

# Track inflight execution_ids to prevent duplicate pickup
_inflight: set = set()
_inflight_lock = threading.Lock()


def run_task(task_data: dict) -> None:
    """Execute a single task (runs in a worker thread)."""
    execution_id = task_data.get("execution_id", "")
    task_text = task_data.get("task", "")
    lease_id = task_data.get("lease_id", "")
    agent_id = task_data.get("agent_id")

    log.info(
        f"Task received: exec={execution_id}, agent={agent_id}, "
        f"task={task_text[:80]}..."
    )

    # Fail-fast: reject tasks with missing or wrong agent_id
    if agent_id != "gemini_cli":
        log.error(
            f"Unknown agent_id '{agent_id}' for exec={execution_id}. "
            f"This runner only supports gemini_cli. Failing task."
        )
        try:
            api_post(
                "/api/v1/mcp/agent/result",
                {
                    "execution_id": execution_id,
                    "status": "failed",
                    "output": "",
                    "error": (
                        f"Task routed to wrong runner: agent_id='{agent_id}' "
                        f"but this runner only handles 'gemini_cli'."
                    ),
                    "duration_seconds": 0,
                },
            )
        except Exception as e:
            log.error(f"Failed to submit rejection result: {e}")
        return

    # ACK
    try:
        api_post(
            "/api/v1/mcp/agent/ack",
            {
                "execution_id": execution_id,
                "lease_id": lease_id,
                "client_id": CLIENT_ID,
            },
        )
        log.info(f"Task acknowledged: exec={execution_id}")
    except Exception as e:
        log.error(f"Ack failed: {e}")

    # Start heartbeat
    stop_heartbeat = threading.Event()
    hb_thread = threading.Thread(
        target=heartbeat_loop,
        args=(execution_id, lease_id, stop_heartbeat),
        daemon=True,
    )
    hb_thread.start()

    # Execute
    start = time.monotonic()
    try:
        success, output, error = execute_with_gemini(task_text, execution_id)
    except Exception as e:
        success, output, error = False, "", str(e)
    duration = time.monotonic() - start

    # Stop heartbeat
    stop_heartbeat.set()
    hb_thread.join(timeout=3)

    # Submit result
    status = "completed" if success else "failed"
    summary = output[:MAX_OUTPUT] if output else error[:MAX_OUTPUT]
    log.info(
        f"Task {status}: exec={execution_id}, "
        f"duration={duration:.1f}s, output={len(output)} chars"
    )

    try:
        api_post(
            "/api/v1/mcp/agent/result",
            {
                "execution_id": execution_id,
                "status": status,
                "output": summary,
                "result_json": {"full_output": output} if output else None,
                "duration_seconds": round(duration, 2),
                "error": error if error else None,
                "client_id": CLIENT_ID,
                "lease_id": lease_id,
                "metadata": {
                    "executor_location": "container",
                    "client_id": CLIENT_ID,
                },
            },
        )
        log.info(f"Result submitted: exec={execution_id}")
    except Exception as e:
        log.error(f"Submit result failed: {e}")
    finally:
        with _inflight_lock:
            _inflight.discard(execution_id)


# ---- Main loop ----


def poll_once(pool: ThreadPoolExecutor) -> bool:
    """Poll for one task and submit to thread pool. Returns True if a task was dispatched."""
    # Check capacity before polling
    with _inflight_lock:
        active = len(_inflight)
    if active >= MAX_CONCURRENT:
        return False

    try:
        resp = api_get(
            "/api/v1/mcp/agent/pending",
            {
                "workspace_id": WORKSPACE_ID,
                "client_id": CLIENT_ID,
                "surface": "gemini_cli",
                "limit": "1",
                "wait_seconds": str(POLL_WAIT),
            },
        )
    except Exception as e:
        log.error(f"Poll failed: {e}")
        time.sleep(5)
        return False

    tasks = resp.get("tasks", [])
    if not tasks:
        return False

    task_data = tasks[0]
    execution_id = task_data.get("execution_id", "")

    # Prevent duplicate pickup
    with _inflight_lock:
        if execution_id in _inflight:
            log.warning(f"Duplicate task skipped: exec={execution_id}")
            return False
        _inflight.add(execution_id)

    # Submit to thread pool (non-blocking)
    pool.submit(run_task, task_data)
    return True


def main():
    if not WORKSPACE_ID:
        log.error("MINDSCAPE_WORKSPACE_ID is required")
        sys.exit(1)

    log.info("=" * 50)
    log.info(" Mindscape Headless Runner")
    log.info("=" * 50)
    log.info(f" Backend:      {BACKEND_URL}")
    log.info(f" Workspace:    {WORKSPACE_ID}")
    log.info(f" Client:       {CLIENT_ID}")
    log.info(f" Executor:     {GEMINI_CLI}")
    log.info(f" CWD:          {WORKSPACE_ROOT}")
    log.info(f" Concurrency:  {MAX_CONCURRENT}")
    log.info("=" * 50)

    pool = ThreadPoolExecutor(
        max_workers=MAX_CONCURRENT,
        thread_name_prefix="runner-task",
    )

    try:
        while not _shutdown.is_set():
            dispatched = poll_once(pool)

            if _shutdown.is_set():
                break

            # Brief pause between polls
            if not dispatched:
                _shutdown.wait(1)
    finally:
        log.info("Shutting down thread pool...")
        pool.shutdown(wait=True, cancel_futures=False)
        log.info("Runner stopped.")


if __name__ == "__main__":
    main()
