"""
Meeting engine dispatch pipeline mixin.

Handles topological sort of blocked_by dependencies and
tool-name self-heal for TOOL_NOT_ALLOWED items.

Note: The actual dispatch execution has moved to DispatchOrchestrator.
This mixin retains the pre-dispatch helpers that engine.run() still
invokes directly.
"""

import json
import logging
from collections import deque
from typing import Any, Dict, List

from backend.app.models.mindscape import EventType

logger = logging.getLogger(__name__)


class MeetingDispatchMixin:
    """Mixin providing dispatch pipeline methods for MeetingEngine."""

    def _resolve_blocked_by_order(
        self, action_items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate blocked_by references and return topologically sorted list.

        Rules:
        1. blocked_by refs are 0-based indices within the same dispatch batch.
        2. Cycles → all items in the cycle marked dispatch_error.
        3. Missing refs (non-existent index) → referencing item marked dispatch_error.

        Returns:
            Topologically sorted list of action items (dependencies first).
        """
        n = len(action_items)
        # Quick exit: no blocked_by at all
        has_blocked_by = False
        for idx, item in enumerate(action_items):
            deps = item.get("blocked_by")
            if not deps or not isinstance(deps, list):
                continue
            has_blocked_by = True
            for ref in deps:
                if not isinstance(ref, int) or ref < 0 or ref >= n or ref == idx:
                    item["landing_status"] = "dispatch_error"
                    item["landing_error"] = f"missing dependency: {ref}"
                    break

        if not has_blocked_by:
            return list(action_items)

        # Kahn's algorithm: topological sort + cycle detection
        in_degree = [0] * n
        adj: Dict[int, List[int]] = {i: [] for i in range(n)}
        for idx, item in enumerate(action_items):
            if item.get("landing_status"):
                continue
            deps = item.get("blocked_by")
            if not deps or not isinstance(deps, list):
                continue
            for ref in deps:
                if isinstance(ref, int) and 0 <= ref < n and ref != idx:
                    adj[ref].append(idx)
                    in_degree[idx] += 1

        queue = deque()
        for i in range(n):
            if not action_items[i].get("landing_status") and in_degree[i] == 0:
                queue.append(i)

        sorted_indices: List[int] = []
        while queue:
            node = queue.popleft()
            sorted_indices.append(node)
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Items not in sorted output and not already marked → cycle
        visited = set(sorted_indices)
        for idx, item in enumerate(action_items):
            if item.get("landing_status"):
                continue
            deps = item.get("blocked_by")
            if deps and isinstance(deps, list) and idx not in visited:
                item["landing_status"] = "dispatch_error"
                item["landing_error"] = "dependency cycle detected"

        # Build final ordered list: topo-sorted items first, then items
        # without blocked_by (preserving original order), then errored items
        topo_order = {idx: pos for pos, idx in enumerate(sorted_indices)}

        # Assign a sort key: topo-sorted items by their topo position,
        # items without deps by original index, errored items last
        def sort_key(pair):
            idx, item = pair
            if item.get("landing_status") in ("dispatch_error", "policy_blocked"):
                return (2, idx)  # Errored items last
            if idx in topo_order:
                return (0, topo_order[idx])  # Topo-sorted position
            return (0, idx)  # No deps: original order

        result: List[Dict[str, Any]] = []
        for idx, item in sorted(enumerate(action_items), key=sort_key):
            result.append(item)

        return result

    async def _attempt_tool_name_self_heal(
        self,
        action_items: List[Dict[str, Any]],
        binding_store: Any,
    ) -> int:
        """Attempt one bounded LLM repair pass for TOOL_NOT_ALLOWED items.

        Repair path is only used after deterministic normalization in
        dispatch_policy_gate has already run. This method only clears
        policy blocks for items that can be mapped to an allowlisted tool.
        """
        try:
            from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
                _canonicalize_tool_name,
                _load_tool_allowlist,
            )

            blocked_rows: List[Dict[str, Any]] = []
            for idx, item in enumerate(action_items):
                if item.get("landing_status") != "policy_blocked":
                    continue
                if item.get("policy_reason_code") != "TOOL_NOT_ALLOWED":
                    continue
                current_tool = item.get("tool_name")
                if not isinstance(current_tool, str) or not current_tool.strip():
                    continue
                target_ws = item.get("target_workspace_id") or self.session.workspace_id
                allowlist = _load_tool_allowlist(target_ws, binding_store)
                if not allowlist:
                    continue
                blocked_rows.append(
                    {
                        "index": idx,
                        "item": item,
                        "target_workspace_id": target_ws,
                        "allowed_tools": set(allowlist),
                    }
                )

            if not blocked_rows:
                return 0

            prompt_rows = [
                {
                    "index": row["index"],
                    "title": row["item"].get("title"),
                    "tool_name": row["item"].get("tool_name"),
                    "target_workspace_id": row["target_workspace_id"],
                    "allowed_tools": sorted(list(row["allowed_tools"]))[:80],
                }
                for row in blocked_rows
            ]
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You repair tool_name fields for action items. "
                        "Only use tool names from each item's allowed_tools."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Return JSON array only. Schema: "
                        '[{"index":<int>,"tool_name":"<allowed_tool_or_null>"}]. '
                        "Use null when no valid repair exists.\n\n"
                        f"Items:\n{json.dumps(prompt_rows, ensure_ascii=False)}"
                    ),
                },
            ]

            try:
                raw = (await self._generate_text(messages, max_tokens=1200)).strip()
            except Exception as exc:
                logger.warning("Tool self-heal generation failed: %s", exc)
                return 0

            payload = None
            extract_fn = getattr(self, "_extract_json_payload", None)
            if callable(extract_fn):
                try:
                    payload = extract_fn(raw)
                except Exception:
                    payload = None
            if payload is None:
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = None
            if not isinstance(payload, list):
                logger.warning("Tool self-heal returned non-list payload")
                return 0

            row_by_index = {row["index"]: row for row in blocked_rows}
            repaired = 0
            for rec in payload:
                if not isinstance(rec, dict):
                    continue
                idx_raw = rec.get("index")
                try:
                    idx = int(idx_raw)
                except (TypeError, ValueError):
                    continue
                if idx not in row_by_index:
                    continue

                candidate_tool = rec.get("tool_name")
                if not isinstance(candidate_tool, str) or not candidate_tool.strip():
                    continue
                row = row_by_index[idx]
                canonical, _ = _canonicalize_tool_name(
                    candidate_tool, row["allowed_tools"]
                )
                if canonical is None:
                    continue

                item = row["item"]
                original = item.get("tool_name")
                item["tool_name"] = canonical
                item.setdefault("tool_name_original", original)
                item["tool_name_self_healed"] = True
                item.pop("landing_status", None)
                item.pop("landing_error", None)
                item.pop("policy_reason_code", None)
                repaired += 1

            return repaired
        except Exception as exc:
            logger.warning("Tool self-heal pipeline failed (non-fatal): %s", exc)
            return 0
