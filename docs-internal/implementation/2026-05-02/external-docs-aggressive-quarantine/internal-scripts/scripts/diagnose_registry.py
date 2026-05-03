#!/usr/bin/env python3
"""
Diagnostic script to check capability registry loading status
Run this script to verify that capabilities are loaded correctly
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir.parent))

from backend.app.capabilities.registry import load_capabilities, get_registry

def main():
    """Diagnose capability registry loading"""
    print("=" * 60)
    print("Capability Registry Diagnostic")
    print("=" * 60)

    # Get capabilities directory
    app_dir = Path(__file__).parent.parent / "backend" / "app"
    capabilities_dir = (app_dir / "capabilities").resolve()

    print(f"\n1. Checking capabilities directory...")
    print(f"   Path: {capabilities_dir}")
    print(f"   Exists: {capabilities_dir.exists()}")

    if not capabilities_dir.exists():
        print("   ❌ ERROR: Capabilities directory does not exist!")
        return 1

    # List capability directories
    capability_dirs = [d for d in capabilities_dir.iterdir() if d.is_dir() and not d.name.startswith('_')]
    print(f"   Found {len(capability_dirs)} capability directories:")
    for cap_dir in capability_dirs:
        manifest_path = cap_dir / "manifest.yaml"
        has_manifest = manifest_path.exists()
        print(f"     - {cap_dir.name}: manifest.yaml {'✓' if has_manifest else '✗'}")

    print(f"\n2. Loading capabilities...")
    try:
        load_capabilities(capabilities_dir)
        print("   ✓ Load completed")
    except Exception as e:
        print(f"   ❌ ERROR: Failed to load capabilities: {e}")
        import traceback
        print(f"   Traceback:\n{traceback.format_exc()}")
        return 1

    print(f"\n3. Checking registry status...")
    registry = get_registry()

    capabilities = registry.list_capabilities()
    tools = registry.list_tools()

    print(f"   Loaded capabilities: {len(capabilities)}")
    for cap in capabilities:
        cap_info = registry.get_capability(cap)
        tool_count = len([t for t in tools if t.startswith(f"{cap}.")])
        print(f"     - {cap}: {tool_count} tools")

    print(f"\n   Total tools: {len(tools)}")
    if len(tools) > 0:
        print(f"   Sample tools (first 10):")
        for tool in tools[:10]:
            tool_info = registry.get_tool(tool)
            backend = tool_info.get('backend', 'N/A') if tool_info else 'N/A'
            print(f"     - {tool}: {backend}")

    # Check for core_llm.structured_extract
    print(f"\n4. Checking critical tools...")
    critical_tools = [
        "core_llm.structured_extract",
        "core_llm.generate",
        "content_vault.write_posts"
    ]

    for tool_name in critical_tools:
        tool_info = registry.get_tool(tool_name)
        if tool_info:
            print(f"   ✓ {tool_name}: {tool_info.get('backend', 'N/A')}")
        else:
            print(f"   ✗ {tool_name}: NOT FOUND")

    print(f"\n5. Summary...")
    if len(capabilities) == 0:
        print("   ❌ WARNING: No capabilities loaded!")
        print("   This indicates a serious problem. Check:")
        print("     - Service needs to be restarted")
        print("     - Check startup logs for errors")
        print("     - Verify capabilities directory permissions")
        return 1
    elif len(tools) == 0:
        print("   ❌ WARNING: No tools loaded!")
        print("   Capabilities exist but no tools registered.")
        return 1
    else:
        print(f"   ✓ Registry is healthy: {len(capabilities)} capabilities, {len(tools)} tools")
        return 0

if __name__ == "__main__":
    sys.exit(main())

"""
Diagnostic script to check capability registry loading status
Run this script to verify that capabilities are loaded correctly
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir.parent))

from backend.app.capabilities.registry import load_capabilities, get_registry

def main():
    """Diagnose capability registry loading"""
    print("=" * 60)
    print("Capability Registry Diagnostic")
    print("=" * 60)

    # Get capabilities directory
    app_dir = Path(__file__).parent.parent / "backend" / "app"
    capabilities_dir = (app_dir / "capabilities").resolve()

    print(f"\n1. Checking capabilities directory...")
    print(f"   Path: {capabilities_dir}")
    print(f"   Exists: {capabilities_dir.exists()}")

    if not capabilities_dir.exists():
        print("   ❌ ERROR: Capabilities directory does not exist!")
        return 1

    # List capability directories
    capability_dirs = [d for d in capabilities_dir.iterdir() if d.is_dir() and not d.name.startswith('_')]
    print(f"   Found {len(capability_dirs)} capability directories:")
    for cap_dir in capability_dirs:
        manifest_path = cap_dir / "manifest.yaml"
        has_manifest = manifest_path.exists()
        print(f"     - {cap_dir.name}: manifest.yaml {'✓' if has_manifest else '✗'}")

    print(f"\n2. Loading capabilities...")
    try:
        load_capabilities(capabilities_dir)
        print("   ✓ Load completed")
    except Exception as e:
        print(f"   ❌ ERROR: Failed to load capabilities: {e}")
        import traceback
        print(f"   Traceback:\n{traceback.format_exc()}")
        return 1

    print(f"\n3. Checking registry status...")
    registry = get_registry()

    capabilities = registry.list_capabilities()
    tools = registry.list_tools()

    print(f"   Loaded capabilities: {len(capabilities)}")
    for cap in capabilities:
        cap_info = registry.get_capability(cap)
        tool_count = len([t for t in tools if t.startswith(f"{cap}.")])
        print(f"     - {cap}: {tool_count} tools")

    print(f"\n   Total tools: {len(tools)}")
    if len(tools) > 0:
        print(f"   Sample tools (first 10):")
        for tool in tools[:10]:
            tool_info = registry.get_tool(tool)
            backend = tool_info.get('backend', 'N/A') if tool_info else 'N/A'
            print(f"     - {tool}: {backend}")

    # Check for core_llm.structured_extract
    print(f"\n4. Checking critical tools...")
    critical_tools = [
        "core_llm.structured_extract",
        "core_llm.generate",
        "content_vault.write_posts"
    ]

    for tool_name in critical_tools:
        tool_info = registry.get_tool(tool_name)
        if tool_info:
            print(f"   ✓ {tool_name}: {tool_info.get('backend', 'N/A')}")
        else:
            print(f"   ✗ {tool_name}: NOT FOUND")

    print(f"\n5. Summary...")
    if len(capabilities) == 0:
        print("   ❌ WARNING: No capabilities loaded!")
        print("   This indicates a serious problem. Check:")
        print("     - Service needs to be restarted")
        print("     - Check startup logs for errors")
        print("     - Verify capabilities directory permissions")
        return 1
    elif len(tools) == 0:
        print("   ❌ WARNING: No tools loaded!")
        print("   Capabilities exist but no tools registered.")
        return 1
    else:
        print(f"   ✓ Registry is healthy: {len(capabilities)} capabilities, {len(tools)} tools")
        return 0

if __name__ == "__main__":
    sys.exit(main())

"""
Diagnostic script to check capability registry loading status
Run this script to verify that capabilities are loaded correctly
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir.parent))

from backend.app.capabilities.registry import load_capabilities, get_registry

def main():
    """Diagnose capability registry loading"""
    print("=" * 60)
    print("Capability Registry Diagnostic")
    print("=" * 60)

    # Get capabilities directory
    app_dir = Path(__file__).parent.parent / "backend" / "app"
    capabilities_dir = (app_dir / "capabilities").resolve()

    print(f"\n1. Checking capabilities directory...")
    print(f"   Path: {capabilities_dir}")
    print(f"   Exists: {capabilities_dir.exists()}")

    if not capabilities_dir.exists():
        print("   ❌ ERROR: Capabilities directory does not exist!")
        return 1

    # List capability directories
    capability_dirs = [d for d in capabilities_dir.iterdir() if d.is_dir() and not d.name.startswith('_')]
    print(f"   Found {len(capability_dirs)} capability directories:")
    for cap_dir in capability_dirs:
        manifest_path = cap_dir / "manifest.yaml"
        has_manifest = manifest_path.exists()
        print(f"     - {cap_dir.name}: manifest.yaml {'✓' if has_manifest else '✗'}")

    print(f"\n2. Loading capabilities...")
    try:
        load_capabilities(capabilities_dir)
        print("   ✓ Load completed")
    except Exception as e:
        print(f"   ❌ ERROR: Failed to load capabilities: {e}")
        import traceback
        print(f"   Traceback:\n{traceback.format_exc()}")
        return 1

    print(f"\n3. Checking registry status...")
    registry = get_registry()

    capabilities = registry.list_capabilities()
    tools = registry.list_tools()

    print(f"   Loaded capabilities: {len(capabilities)}")
    for cap in capabilities:
        cap_info = registry.get_capability(cap)
        tool_count = len([t for t in tools if t.startswith(f"{cap}.")])
        print(f"     - {cap}: {tool_count} tools")

    print(f"\n   Total tools: {len(tools)}")
    if len(tools) > 0:
        print(f"   Sample tools (first 10):")
        for tool in tools[:10]:
            tool_info = registry.get_tool(tool)
            backend = tool_info.get('backend', 'N/A') if tool_info else 'N/A'
            print(f"     - {tool}: {backend}")

    # Check for core_llm.structured_extract
    print(f"\n4. Checking critical tools...")
    critical_tools = [
        "core_llm.structured_extract",
        "core_llm.generate",
        "content_vault.write_posts"
    ]

    for tool_name in critical_tools:
        tool_info = registry.get_tool(tool_name)
        if tool_info:
            print(f"   ✓ {tool_name}: {tool_info.get('backend', 'N/A')}")
        else:
            print(f"   ✗ {tool_name}: NOT FOUND")

    print(f"\n5. Summary...")
    if len(capabilities) == 0:
        print("   ❌ WARNING: No capabilities loaded!")
        print("   This indicates a serious problem. Check:")
        print("     - Service needs to be restarted")
        print("     - Check startup logs for errors")
        print("     - Verify capabilities directory permissions")
        return 1
    elif len(tools) == 0:
        print("   ❌ WARNING: No tools loaded!")
        print("   Capabilities exist but no tools registered.")
        return 1
    else:
        print(f"   ✓ Registry is healthy: {len(capabilities)} capabilities, {len(tools)} tools")
        return 0

if __name__ == "__main__":
    sys.exit(main())

