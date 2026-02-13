import asyncio
import uuid
import json
import httpx
import time
from backend.app.services.external_agents.agents.antigravity.ide_ws_client import (
    AntigravityWSClient,
)

# Configuration
API_BASE = "http://localhost:8200"
WS_URL = "ws://localhost:8200/ws/agent/test-workspace"
AGENT_ID = "antigravity"
TOKEN = "test-token"


async def run_verification():
    print(f"🚀 Starting Antigravity Integration Verification...")

    # 1. Start Mock IDE Client
    client = AntigravityWSClient(
        workspace_id="test-workspace",
        host="localhost:8200",
        auth_secret=TOKEN,
        surface=AGENT_ID,
    )
    print(f"🔌 Connecting IDE Client to {WS_URL}...")

    # Start client in background
    client_task = asyncio.create_task(client.run())

    # Wait for connection
    await asyncio.sleep(2)
    if not client._ws:
        print("❌ Failed to connect IDE Client (Timeout)")
        return

    print("✅ IDE Client Connected!")

    # 2. Trigger Playbook Execution (using the installed antigravity playbook)
    print("📢 Triggering Playbook: antigravity_single_task...")
    async with httpx.AsyncClient() as api:
        # Correct Endpoint: POST /api/v1/playbooks/execute/start
        response = await api.post(
            f"{API_BASE}/api/v1/playbooks/execute/start",
            params={
                "playbook_code": "antigravity_single_task",
                "workspace_id": "test-workspace",
            },
            json={
                "inputs": {
                    "task_description": "Verify Antigravity Integration from Verification Script"
                }
            },
            timeout=10.0,
        )

        if response.status_code != 200:
            print(f"❌ Failed to trigger playbook: {response.text}")
            await client.stop()
            return

        execution_data = response.json()
        execution_id = execution_data.get("execution_id")
        print(f"✅ Playbook triggered! Execution ID: {execution_id}")

    # 3. Wait for result (IDE Client automatically handles dispatch and sends result)
    print("⏳ Waiting for execution result...")

    # Wait for the cycle to complete (Dispatch -> Ack -> Progress -> Result)
    # The default handler sends progress updates, so we wait enough time for them
    await asyncio.sleep(5)

    print(
        "✅ Verification Check Completed (Check logs above for 'Task completed' or 'Result received')"
    )

    # Cleanup
    await client.stop()
    await client_task


if __name__ == "__main__":
    asyncio.run(run_verification())
