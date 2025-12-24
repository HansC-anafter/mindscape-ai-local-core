#!/usr/bin/env python3
"""
Architecture A verification script.

Verifies core functionality using a real workspace.
"""
import asyncio
import httpx
import os
import sys
from typing import Dict, Any, List, Optional


WORKSPACE_ID = "37bce3ff-16b1-49fe-973e-fe0ca43fc962"
BASE_URL = os.getenv("LOCAL_CORE_URL", "http://localhost:8000")
TIMEOUT = 30


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class VerificationResult:
    """Verification result container."""
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.message = ""
        self.details: Dict[str, Any] = {}


async def verify_workspace_exists(client: httpx.AsyncClient) -> VerificationResult:
    """Verify workspace exists."""
    result = VerificationResult("Workspace Exists")
    try:
        response = await client.get(f"/api/v1/workspaces/{WORKSPACE_ID}")
        if response.status_code == 200:
            data = response.json()
            result.passed = True
            result.message = f"Workspace found: {data.get('title', 'N/A')}"
            result.details = {"workspace_id": WORKSPACE_ID, "title": data.get("title")}
        else:
            result.message = f"Workspace not found: {response.status_code}"
    except Exception as e:
        result.message = f"Error: {str(e)}"
    return result


async def verify_lens_api(client: httpx.AsyncClient) -> VerificationResult:
    """Verify Lens API is accessible."""
    result = VerificationResult("Lens API")
    try:
        response = await client.get("/api/v1/lenses")
        if response.status_code == 501:
            result.message = "Lens API returns 501 Not Implemented"
        elif response.status_code in [200, 404]:
            result.passed = True
            data = response.json() if response.status_code == 200 else []
            result.message = f"Lens API accessible ({len(data) if isinstance(data, list) else 0} lenses)"
            result.details = {"status_code": response.status_code, "count": len(data) if isinstance(data, list) else 0}
        else:
            result.message = f"Lens API error: {response.status_code}"
    except Exception as e:
        result.message = f"Error: {str(e)}"
    return result


async def verify_composition_api(client: httpx.AsyncClient) -> VerificationResult:
    """Verify Composition API is accessible."""
    result = VerificationResult("Composition API")
    try:
        response = await client.get(f"/api/v1/compositions?workspace_id={WORKSPACE_ID}")
        if response.status_code == 200:
            data = response.json()
            result.passed = True
            result.message = f"Composition API accessible ({len(data)} compositions)"
            result.details = {"count": len(data)}
        else:
            result.message = f"Composition API error: {response.status_code}"
    except Exception as e:
        result.message = f"Error: {str(e)}"
    return result


async def verify_surface_registration(client: httpx.AsyncClient) -> VerificationResult:
    """Verify Surface registration."""
    result = VerificationResult("Surface Registration")
    try:
        response = await client.get("/api/v1/surfaces")
        if response.status_code == 200:
            data = response.json()
            surface_ids = [s["surface_id"] for s in data]

            if "mindscape_ui" in surface_ids and "line" in surface_ids:
                ui_surface = next(s for s in data if s["surface_id"] == "mindscape_ui")
                line_surface = next(s for s in data if s["surface_id"] == "line")

                if ui_surface["surface_type"] == "control" and line_surface["surface_type"] == "delivery":
                    result.passed = True
                    result.message = f"Surface registration correct ({len(data)} surfaces)"
                    result.details = {
                        "total": len(data),
                        "ui_type": ui_surface["surface_type"],
                        "line_type": line_surface["surface_type"]
                    }
                else:
                    result.message = f"Surface type incorrect: UI={ui_surface['surface_type']}, LINE={line_surface['surface_type']}"
            else:
                result.message = f"Required surfaces not found. Found: {surface_ids}"
        else:
            result.message = f"Surface API error: {response.status_code}"
    except Exception as e:
        result.message = f"Error: {str(e)}"
    return result


async def verify_command_bus(client: httpx.AsyncClient) -> VerificationResult:
    """Verify Command Bus API."""
    result = VerificationResult("Command Bus")
    try:
        response = await client.get(f"/api/v1/commands?workspace_id={WORKSPACE_ID}&limit=10")
        if response.status_code == 200:
            data = response.json()
            result.passed = True
            result.message = f"Command Bus API accessible ({len(data)} commands)"
            result.details = {"count": len(data)}
        else:
            result.message = f"Command Bus API error: {response.status_code}"
    except Exception as e:
        result.message = f"Error: {str(e)}"
    return result


async def verify_event_stream(client: httpx.AsyncClient) -> VerificationResult:
    """Verify Event Stream API."""
    result = VerificationResult("Event Stream")
    try:
        response = await client.get(f"/api/v1/events?workspace_id={WORKSPACE_ID}&limit=10")
        if response.status_code == 200:
            data = response.json()
            result.passed = True
            result.message = f"Event Stream API accessible ({len(data)} events)"
            result.details = {"count": len(data)}
        else:
            result.message = f"Event Stream API error: {response.status_code}"
    except Exception as e:
        result.message = f"Error: {str(e)}"
    return result


async def verify_cross_channel_events(client: httpx.AsyncClient) -> VerificationResult:
    """Verify cross-channel event collection."""
    result = VerificationResult("Cross-Channel Events")
    try:
        surfaces = ["mindscape_ui", "line", "ig"]
        event_ids = []

        for surface in surfaces:
            event_data = {
                "workspace_id": WORKSPACE_ID,
                "source_surface": surface,
                "event_type": "test.cross_channel",
                "payload": {"surface": surface, "test": "verification"},
                "actor_id": f"test_user_{surface}"
            }

            response = await client.post("/api/v1/events", json=event_data)
            if response.status_code in [200, 201]:
                event = response.json()
                event_ids.append(event.get("event_id"))

        if len(event_ids) >= 2:
            response = await client.get(f"/api/v1/events?workspace_id={WORKSPACE_ID}&limit=20")
            if response.status_code == 200:
                events = response.json()
                surfaces_found = {e["source_surface"] for e in events if e.get("event_type") == "test.cross_channel"}

                if len(surfaces_found) >= 2:
                    result.passed = True
                    result.message = f"Cross-channel events working ({len(surfaces_found)} surfaces)"
                    result.details = {"surfaces": list(surfaces_found), "events_created": len(event_ids)}
                else:
                    result.message = f"Expected events from multiple surfaces, got: {surfaces_found}"
            else:
                result.message = f"Failed to query events: {response.status_code}"
        else:
            result.message = f"Failed to create events from all surfaces. Created: {len(event_ids)}"
    except Exception as e:
        result.message = f"Error: {str(e)}"
    return result


async def verify_fusion_api(client: httpx.AsyncClient) -> VerificationResult:
    """Verify Fusion API is accessible."""
    result = VerificationResult("Fusion API")
    try:
        import time
        unique_id = f"test_fusion_{int(time.time())}"
        composition_data = {
            "composition_id": unique_id,
            "workspace_id": WORKSPACE_ID,
            "name": "Test Fusion Composition",
            "description": "Test composition for fusion verification",
            "lens_stack": [
                {
                    "lens_instance_id": "test_lens_1",
                    "role": "writer",
                    "modality": "text",
                    "weight": 1.0,
                    "priority": 1
                }
            ],
            "fusion_strategy": "weighted_merge"
        }

        create_response = await client.post("/api/v1/compositions", json=composition_data)
        if create_response.status_code in [200, 201]:
            composition = create_response.json()
            composition_id = composition["composition_id"]

            fuse_data = {
                "composition_id": composition_id,
                "lens_instances": {
                    "test_lens_1": {
                        "mind_lens_id": "test_lens_1",
                        "instance_id": "test_lens_1",
                        "schema_id": "test_schema",
                        "owner_user_id": "test_user",
                        "role": "writer",
                        "values": {"tone": "formal"}
                    }
                }
            }

            fuse_response = await client.post(
                f"/api/v1/compositions/{composition_id}/fuse",
                json=fuse_data
            )

            if fuse_response.status_code == 200:
                fused = fuse_response.json()
                result.passed = True
                result.message = "Fusion API working"
                result.details = {"composition_id": composition_id}
            else:
                result.message = f"Fusion API error: {fuse_response.status_code} - {fuse_response.text}"
        else:
            result.message = f"Failed to create composition: {create_response.status_code}"
    except Exception as e:
        result.message = f"Error: {str(e)}"
    return result


async def main():
    """Run all verification tests."""
    print(f"{Colors.BOLD}{Colors.BLUE}Architecture A Verification{Colors.RESET}")
    print(f"Workspace: {WORKSPACE_ID}")
    print(f"Base URL: {BASE_URL}")
    print("-" * 60)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        verifications = [
            verify_workspace_exists(client),
            verify_lens_api(client),
            verify_composition_api(client),
            verify_surface_registration(client),
            verify_command_bus(client),
            verify_event_stream(client),
            verify_cross_channel_events(client),
            verify_fusion_api(client),
        ]

        results = await asyncio.gather(*verifications)

        passed = 0
        failed = 0

        for result in results:
            if result.passed:
                print(f"{Colors.GREEN}[PASS] {result.name}: {result.message}{Colors.RESET}")
                passed += 1
            else:
                print(f"{Colors.RED}[FAIL] {result.name}: {result.message}{Colors.RESET}")
                failed += 1

        print("-" * 60)
        print(f"{Colors.BOLD}Summary: {Colors.GREEN}{passed} passed{Colors.RESET}, {Colors.RED}{failed} failed{Colors.RESET} out of {len(results)} tests")

        if failed == 0:
            print(f"{Colors.GREEN}{Colors.BOLD}[SUCCESS] All verifications passed! Architecture A is working correctly.{Colors.RESET}")
            return 0
        else:
            print(f"{Colors.YELLOW}{Colors.BOLD}[WARNING] Some verifications failed. Please check the errors above.{Colors.RESET}")
            return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

