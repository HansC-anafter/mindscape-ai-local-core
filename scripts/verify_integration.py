import sys
import time
import subprocess
import requests
import os

# Set PYTHONPATH to include current directory
env = os.environ.copy()
env["PYTHONPATH"] = os.getcwd()

print("Starting verification script...")

# 1. Start Client
client_cmd = [
    sys.executable,
    "-u",
    "backend/app/services/external_agents/agents/antigravity/ide_ws_client.py",
    "--workspace-id",
    "bac7ce63-e768-454d-96f3-3a00e8e1df69",
    "--host",
    "localhost:8200",
    "--client-id",
    "mock-ide-002",
]
print(f"Executing: {' '.join(client_cmd)}")
client = subprocess.Popen(
    client_cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    env=env,
    bufsize=0,  # Unbuffered
)

# 2. Wait for connection
print("Waiting for client to connect...")
max_retries = 10
connected = False
for i in range(max_retries):
    try:
        r = requests.get("http://localhost:8200/api/v1/mcp/agent/status")
        status = r.json()
        print(f"Status check {i+1}: {status}")

        # Check if our workspace has clients
        workspaces = status.get("workspaces", {})
        ws_info = workspaces.get("bac7ce63-e768-454d-96f3-3a00e8e1df69", {})
        clients = ws_info.get("clients", [])

        if clients:
            print(f"Client connected: {clients}")
            connected = True
            break
    except Exception as e:
        print(f"Status check failed: {e}")

    time.sleep(1)

if not connected:
    print("ERROR: Client failed to connect within timeout.")
    client.terminate()
    sys.exit(1)

# 3. Dispatch
try:
    print("Sending dispatch request...")
    url = "http://localhost:8200/ws/agent/test/dispatch/bac7ce63-e768-454d-96f3-3a00e8e1df69"
    # Set timeout to avoid hanging indefinitely if backend blocks
    r = requests.post(url, json={"task": "Direct verification task"}, timeout=10)
    print(f"Dispatch Response: {r.status_code}")
    print(f"Dispatch Body: {r.text}")
except Exception as e:
    print(f"Dispatch failed: {e}")

# 4. Cleanup & Logs
print("Terminating client...")
client.terminate()
try:
    outs, _ = client.communicate(timeout=2)
    print("\n=== Client Logs ===")
    print(outs)
    print("===================")
except subprocess.TimeoutExpired:
    client.kill()
    outs, _ = client.communicate()
    print("\n=== Client Logs (Killed) ===")
    print(outs)
    print("============================")
