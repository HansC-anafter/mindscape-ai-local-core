"""
Validate IG playbook specs for contract-ish consistency (offline, no deps).

Checks:
- Every step.tool_slot that is not core.* must be in "capability.tool_name" format
- Every spec must include required_capabilities and data_locality
- If tool_slot starts with "ig.", tool_name must exist in `capabilities/ig/manifest.yaml` tools list

Run:
  python3 mindscape-ai-cloud/capabilities/ig/scripts/validate_playbook_specs.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


_SCRIPT_DIR = Path(__file__).resolve().parent
_PACK_ROOT = _SCRIPT_DIR.parent
_SPECS_DIR = _PACK_ROOT / "playbooks" / "specs"
_MANIFEST_PATH = _PACK_ROOT / "manifest.yaml"


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_ig_tool_codes_from_manifest() -> set[str]:
    """
    Load tool codes from IG manifest without YAML parsing dependencies.

    We only need the `code:` values under top-level `tools:` list.
    """
    text = _MANIFEST_PATH.read_text(encoding="utf-8").splitlines()

    codes: set[str] = set()
    in_tools = False
    tools_indent = None

    for line in text:
        if re.match(r"^\s*tools:\s*$", line):
            in_tools = True
            tools_indent = len(line) - len(line.lstrip())
            continue

        if not in_tools:
            continue

        cur_indent = len(line) - len(line.lstrip())
        # End tools section when indentation drops back to top-level and we see a new key
        if tools_indent is not None and cur_indent <= tools_indent and re.match(r"^\s*\w", line):
            break

        # Accept both YAML styles used in the manifest:
        #   - code: ig_fetch_posts
        #   - name: ig_profile_tagger
        #     code: ig_profile_tagger
        m = re.match(r"^\s*(?:-\s*)?code:\s*([^\s#]+)\s*$", line)
        if m:
            codes.add(m.group(1).strip())

    return codes


def main() -> None:
    spec_paths = sorted(_SPECS_DIR.glob("*.json"))
    errors: List[Tuple[str, str]] = []
    ig_tool_codes = _load_ig_tool_codes_from_manifest()

    for path in spec_paths:
        spec = _load_json(path)

        if "required_capabilities" not in spec:
            errors.append((path, "missing required_capabilities"))
        if "data_locality" not in spec:
            errors.append((path, "missing data_locality"))

        for step in spec.get("steps", []):
            tool_slot = step.get("tool_slot")
            if not tool_slot:
                continue
            if str(tool_slot).startswith("core."):
                continue
            tool_slot_str = str(tool_slot)
            if "." not in tool_slot_str:
                step_id = step.get("id", "<unknown>")
                errors.append((path, f"step '{step_id}' tool_slot must be 'capability.tool_name', got: {tool_slot!r}"))
                continue

            # Validate ig.* tool existence against IG manifest tool codes
            if tool_slot_str.startswith("ig."):
                tool_name = tool_slot_str.split(".", 1)[1]
                if tool_name not in ig_tool_codes:
                    step_id = step.get("id", "<unknown>")
                    errors.append((path, f"step '{step_id}' tool_slot '{tool_slot_str}' not found in ig manifest tools"))

    if errors:
        print("FAILED: playbook specs validation errors:")
        for path, msg in errors:
            print(f"- {path}: {msg}")
        raise SystemExit(1)

    print(f"OK: validated {len(spec_paths)} IG playbook specs")


if __name__ == "__main__":
    main()
