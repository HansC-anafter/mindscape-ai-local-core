"""Tool inventory and query helpers for MeetingPromptsMixin."""

import logging
from typing import List

logger = logging.getLogger(__name__)


class MeetingPromptToolInventoryMixin:
    def _build_tool_inventory_block(self) -> str:
        """Build tool inventory for prompt injection."""
        workspace = getattr(self, "workspace", None)
        workspace_id = (
            getattr(workspace, "id", None)
            or getattr(self, "session", None)
            and self.session.workspace_id
        )
        if not workspace_id:
            return ""

        try:
            from backend.app.services.stores.workspace_resource_binding_store import (
                WorkspaceResourceBindingStore,
            )
            from backend.app.models.workspace_resource_binding import ResourceType

            binding_store = WorkspaceResourceBindingStore()
            bindings = binding_store.list_bindings_by_workspace(
                workspace_id, resource_type=ResourceType.TOOL
            )

            if bindings:
                allowed_ids = {b.resource_id for b in bindings}
                rag_cache = getattr(self, "_rag_tool_cache", [])
                if rag_cache:
                    hits = [t for t in rag_cache if t["tool_id"] in allowed_ids]
                    rag_ids = {t["tool_id"] for t in hits}
                    rest = [b for b in bindings if b.resource_id not in rag_ids]
                    lines = [f"- {t['tool_id']}: {t['display_name']}" for t in hits]
                    lines += [
                        f"- {b.resource_id}: {(b.overrides or {}).get('display_name', b.resource_id)}"
                        for b in rest
                    ]
                else:
                    lines = [
                        f"- {b.resource_id}: {(b.overrides or {}).get('display_name', b.resource_id)}"
                        for b in bindings
                    ]
                tool_line_count = len(lines)
                logger.debug(
                    "meeting_tool_inventory workspace=%s source=bindings+rag tool_lines=%d",
                    workspace_id,
                    tool_line_count,
                )
                return "\n".join(lines)

            rag_cache = getattr(self, "_rag_tool_cache", [])
            if rag_cache:
                lines = [f"- {t['tool_id']}: {t['display_name']}" for t in rag_cache]
                logger.debug(
                    "meeting_tool_inventory workspace=%s source=rag tool_lines=%d",
                    workspace_id,
                    len(lines),
                )
                return "\n".join(lines)

            from backend.app.services.stores.installed_packs_store import (
                InstalledPacksStore,
            )
            from pathlib import Path

            try:
                import yaml as _yaml
            except ImportError:
                _yaml = None

            if _yaml is None:
                return ""

            packs_store = InstalledPacksStore()
            pack_ids = packs_store.list_enabled_pack_ids()
            import os

            app_dir = os.getenv("APP_DIR", "/app")
            cap_dirs = [
                Path(app_dir) / "backend" / "app" / "capabilities",
                Path("backend/app/capabilities"),
                Path(os.getenv("DATA_DIR", "data")) / "capabilities",
            ]
            lines = []
            for pack_id in pack_ids:
                for cap_base in cap_dirs:
                    manifest_path = cap_base / pack_id / "manifest.yaml"
                    if not manifest_path.exists():
                        continue
                    try:
                        with manifest_path.open("r", encoding="utf-8") as mf:
                            manifest = _yaml.safe_load(mf) or {}
                        tools = manifest.get("tools", [])
                        for tool in tools:
                            if isinstance(tool, dict):
                                code = tool.get("code", tool.get("name", pack_id))
                                if not code:
                                    continue
                                display = tool.get("display_name", code)
                                code_str = str(code).strip()
                                tool_id = (
                                    code_str
                                    if "." in code_str
                                    else f"{pack_id}.{code_str}"
                                )
                                lines.append(f"- {tool_id}: {display}")
                    except Exception:
                        pass
                    break
            if lines:
                lines.append("")
                lines.append(
                    "Note: These are system-wide tools. Workspace policy gate "
                    "may restrict which tools are allowed for this workspace."
                )
                logger.debug(
                    "meeting_tool_inventory workspace=%s source=manifest tool_lines=%d",
                    workspace_id,
                    len(lines),
                )
                return "\n".join(lines)

            return ""
        except Exception as exc:
            logger.warning("Failed to build tool inventory: %s", exc)
            return ""

    def _has_workspace_tool_bindings(self) -> bool:
        """Return True when this workspace has actionable tool context."""
        workspace = getattr(self, "workspace", None)
        workspace_id = getattr(workspace, "id", None) or getattr(
            getattr(self, "session", None), "workspace_id", None
        )

        if workspace_id:
            try:
                from backend.app.services.stores.workspace_resource_binding_store import (
                    WorkspaceResourceBindingStore,
                )
                from backend.app.models.workspace_resource_binding import ResourceType

                store = WorkspaceResourceBindingStore()
                bindings = store.list_bindings_by_workspace(
                    workspace_id, resource_type=ResourceType.TOOL
                )
                if bindings:
                    return True
            except Exception as exc:
                logger.debug("_has_workspace_tool_bindings check failed: %s", exc)

        has_rag_tools = bool(getattr(self, "_rag_tool_cache", []))
        playbooks_cache = getattr(self, "_available_playbooks_cache", "")
        has_playbooks = bool(
            playbooks_cache
            and playbooks_cache
            not in (
                "(no playbooks discovered)",
                "(playbook discovery unavailable)",
            )
        )
        return has_rag_tools or has_playbooks

    _VERB_RAG_KEYWORDS: dict[str, str] = {
        "\u8abf\u7814": "research academic papers",
        "\u7814\u7a76": "research academic frontier",
        "\u8ad6\u6587": "academic papers fetch",
        "\u641c\u5c0b": "search fetch query",
        "\u641c\u7d22": "search fetch query",
        "\u88fd\u4f5c": "create generate draft content",
        "\u64b0\u5beb": "write draft generate",
        "\u751f\u6210": "generate create build",
        "\u8349\u7a3f": "draft content writing",
        "\u8cbc\u6587": "post publish content social media",
        "\u767c\u4f48": "publish post schedule",
        "\u767c\u5e03": "publish post schedule",
        "\u6392\u7a0b": "schedule calendar plan",
        "\u914d\u5716": "image photo visual unsplash",
        "\u5716\u7247": "image photo visual",
        "\u5206\u6790": "analyze assessment report",
        "\u898f\u5283": "planning strategy decomposition",
        "\u54c1\u724c": "brand identity CIS",
        "\u5f71\u7247": "video chapter ingest render",
        "\u97f3\u983b": "audio sonic embedding",
        "\u745c\u4f3d": "yoga coach pose asana",
        "\u7db2\u9801": "web generation divi wordpress",
        "SEO": "SEO optimization search engine",
        "\u88dc\u52a9": "grant scout funding",
        "\u96fb\u5b50\u5831": "newsletter email campaign",
    }

    def _verb_augment(self, text: str) -> str:
        """Return English RAG keywords matched from Chinese verbs in *text*."""
        if not text:
            return ""
        matched: list[str] = []
        for verb, eng in self._VERB_RAG_KEYWORDS.items():
            if verb in text:
                matched.append(eng)
        return " ".join(matched)

    def _build_tool_query_from_context(self) -> str:
        """Build a text query for RAG tool pre-fetch from meeting context.

        Combines session agenda with the last user message to produce a
        semantically rich query.  Falls back to a generic string.

        When the user message is non-English, matched action-verb keywords
        are appended to improve cross-lingual RAG recall.
        """
        parts: List[str] = []
        agenda = getattr(getattr(self, "session", None), "agenda", None)
        if agenda:
            parts.append(str(agenda)[:300])
        msg = getattr(self, "_last_user_message", None)
        if msg:
            parts.append(str(msg)[:200])
        project = getattr(getattr(self, "session", None), "project_id", None)
        if project:
            parts.append(f"project:{project}")

        if msg:
            aug = self._verb_augment(str(msg))
            if aug:
                parts.append(aug)

        return " ".join(parts) or "general task execution"
