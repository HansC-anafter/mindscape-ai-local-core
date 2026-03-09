"""
Meeting engine prompt building mixin.

Handles turn prompt construction, locale resolution, project context
injection, history snippets, and convergence detection.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import EventType

logger = logging.getLogger(__name__)


class MeetingPromptsMixin:
    """Mixin providing prompt construction methods for MeetingEngine."""

    def _build_workspace_instruction_block(self) -> str:
        """Build workspace instruction block for meeting agent turns.

        Meeting agents have their own role definitions (facilitator/planner/
        critic/executor). Workspace instruction is filtered to avoid
        role conflict:
          - persona:    EXCLUDED (would override agent role)
          - anti_goals: EXCLUDED (would reject project-scoped tasks)
          - goals, style_rules, domain_context: INCLUDED as reference

        Returns raw body (no delimiters); caller wraps in its own block.
        Brief fallback is disabled to prevent unfiltered persona leaking.
        """
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        workspace = getattr(self, "workspace", None)
        block, _ = build_workspace_instruction_block(
            workspace,
            caller="meeting",
            exclude_fields=("persona", "anti_goals"),
            fallback_to_brief=False,
            raw_body=True,
        )
        return block

    def _build_tool_inventory_block(self) -> str:
        """Build tool inventory for prompt injection.

        Lookup order:
          1. Explicit TOOL bindings (workspace allowlist) — highest priority.
             If RAG cache is available, RAG hits within the allowlist are
             shown first (similarity order), remaining allowlist tools follow.
          2. RAG cache unfiltered — when no explicit bindings exist,
             replaces the 215-line manifest dump with top-K relevant tools.
          3. Installed-pack manifest fallback — unchanged, last resort.
        """
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
                # --- Tier 1: explicit allowlist — RAG reranking within it ---
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

            # --- Tier 2: RAG cache (no explicit bindings) ---
            rag_cache = getattr(self, "_rag_tool_cache", [])
            if rag_cache:
                lines = [f"- {t['tool_id']}: {t['display_name']}" for t in rag_cache]
                logger.debug(
                    "meeting_tool_inventory workspace=%s source=rag tool_lines=%d",
                    workspace_id,
                    len(lines),
                )
                return "\n".join(lines)

            # --- Tier 3: manifest fallback (unchanged) ---
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
                    break  # found manifest, skip other cap_dirs
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
        """Return True iff this workspace has explicit TOOL resource bindings.

        Explicit bindings = admin-configured allowlist.  Manifest fallback
        (the 215-line global dump) does NOT count as explicit — it is
        reference-only and should not trigger mandatory-constraint or
        null-tool retry gates.
        """
        workspace = getattr(self, "workspace", None)
        workspace_id = getattr(workspace, "id", None) or getattr(
            getattr(self, "session", None), "workspace_id", None
        )
        if not workspace_id:
            return False
        try:
            from backend.app.services.stores.workspace_resource_binding_store import (
                WorkspaceResourceBindingStore,
            )
            from backend.app.models.workspace_resource_binding import ResourceType

            store = WorkspaceResourceBindingStore()
            bindings = store.list_bindings_by_workspace(
                workspace_id, resource_type=ResourceType.TOOL
            )
            return bool(bindings)
        except Exception as exc:
            logger.debug("_has_workspace_tool_bindings check failed: %s", exc)
            return False

    # Chinese action-verb → English RAG keywords for cross-lingual recall.
    # These are matched against the user message and appended to the RAG
    # query so that domain-specific Chinese queries still surface the right
    # tool families.
    _VERB_RAG_KEYWORDS: dict[str, str] = {
        "調研": "research academic papers",
        "研究": "research academic frontier",
        "論文": "academic papers fetch",
        "搜尋": "search fetch query",
        "搜索": "search fetch query",
        "製作": "create generate draft content",
        "撰寫": "write draft generate",
        "生成": "generate create build",
        "草稿": "draft content writing",
        "貼文": "post publish content social media",
        "發佈": "publish post schedule",
        "發布": "publish post schedule",
        "排程": "schedule calendar plan",
        "配圖": "image photo visual unsplash",
        "圖片": "image photo visual",
        "分析": "analyze assessment report",
        "規劃": "planning strategy decomposition",
        "品牌": "brand identity CIS",
        "影片": "video chapter ingest render",
        "音頻": "audio sonic embedding",
        "瑜伽": "yoga coach pose asana",
        "網頁": "web generation divi wordpress",
        "SEO": "SEO optimization search engine",
        "補助": "grant scout funding",
        "電子報": "newsletter email campaign",
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
        # Enrich with project context if available
        project = getattr(getattr(self, "session", None), "project_id", None)
        if project:
            parts.append(f"project:{project}")

        # Cross-lingual augmentation
        if msg:
            aug = self._verb_augment(str(msg))
            if aug:
                parts.append(aug)

        return " ".join(parts) or "general task execution"

    def _build_project_context(self) -> str:
        """Fetch project data and recent activity to provide meeting context."""
        if not self.project_id:
            return ""

        parts: List[str] = []
        try:
            project = self.store.get_project(self.project_id)
            if project:
                parts.append(f"Project: {getattr(project, 'title', self.project_id)}")
                ptype = getattr(project, "type", None)
                if ptype:
                    parts.append(f"Type: {ptype}")
                pstate = getattr(project, "state", None)
                if pstate:
                    parts.append(f"State: {pstate}")
                pmeta = getattr(project, "metadata", None)
                if pmeta and isinstance(pmeta, dict):
                    summary_keys = [
                        "goal",
                        "goals",
                        "description",
                        "brief",
                        "scope",
                        "deliverables",
                        "requirements",
                    ]
                    for key in summary_keys:
                        val = pmeta.get(key)
                        if val:
                            parts.append(f"{key.capitalize()}: {val}")
        except Exception as exc:
            logger.warning("Failed to fetch project for meeting context: %s", exc)

        try:
            recent_events = self.store.get_events_by_project(self.project_id, limit=10)
            if recent_events:
                activity_lines = []
                for ev in recent_events[:5]:
                    ev_type = getattr(ev, "event_type", "")
                    payload = getattr(ev, "payload", {}) or {}
                    summary = (
                        payload.get("message") or payload.get("title") or str(ev_type)
                    )
                    if len(summary) > 120:
                        summary = summary[:120] + "..."
                    activity_lines.append(f"  - {summary}")
                if activity_lines:
                    parts.append(
                        "Recent project activity:\n" + "\n".join(activity_lines)
                    )
        except Exception as exc:
            logger.warning("Failed to fetch project events for meeting: %s", exc)

        return "\n".join(parts) if parts else ""

    def _build_asset_map_context(self) -> str:
        """Build workspace group asset map for cross-workspace dispatch routing.

        Queries all workspaces in the group and their registered ASSET bindings,
        then formats a context block so the planner knows which workspace owns
        which data assets. Also injects discoverable workspaces from outside the
        group (5D-3).

        Returns empty string only if no group members AND no discoverable
        workspaces exist.
        """
        workspace = getattr(self, "workspace", None)
        if not workspace:
            return ""

        try:
            from backend.app.services.stores.workspace_resource_binding_store import (
                WorkspaceResourceBindingStore,
            )
            from backend.app.models.workspace_resource_binding import ResourceType
            from backend.app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )

            binding_store = WorkspaceResourceBindingStore()
            parts: List[str] = []
            seen_ws_ids = set()
            current_ws_id = getattr(workspace, "id", None)

            # --- Path A: Group members (conditional on group_id) ---
            group_id = getattr(workspace, "group_id", None)
            if group_id:
                from backend.app.services.stores.postgres.workspace_group_store import (
                    PostgresWorkspaceGroupStore,
                )

                group_store = PostgresWorkspaceGroupStore()
                group = group_store.get(group_id)
                if group:
                    parts.append(f"Workspace Group: {group.display_name} ({group.id})")

                    workspace_role = (
                        getattr(workspace, "workspace_role", None) or "cell"
                    )
                    parts.append(f"Current workspace role: {workspace_role}")

                    for ws_id, role in group.role_map.items():
                        seen_ws_ids.add(ws_id)
                        bindings = binding_store.list_bindings_by_workspace(
                            ws_id, resource_type=ResourceType.ASSET
                        )
                        asset_lines = []
                        for b in bindings:
                            name = (b.overrides or {}).get(
                                "display_name", b.resource_id
                            )
                            asset_type = (b.overrides or {}).get(
                                "asset_type", "unknown"
                            )
                            asset_lines.append(f"    - {name} ({asset_type})")

                        ws_label = f"  [{role}] {ws_id}"
                        if ws_id == current_ws_id:
                            ws_label += " (current)"
                        parts.append(ws_label)

                        if asset_lines:
                            parts.extend(asset_lines)
                        else:
                            parts.append("    (no assets registered)")

            # --- Path B: Discoverable workspaces (always runs) ---
            ws_store = PostgresWorkspacesStore()
            discoverable = ws_store.list_discoverable_workspaces(
                visibility="discoverable"
            )
            extra = [
                ws
                for ws in discoverable
                if ws.id not in seen_ws_ids and ws.id != current_ws_id
            ]
            if extra:
                parts.append("")
                parts.append("Discoverable Workspaces (outside group):")
                for ws in extra:
                    bindings = binding_store.list_bindings_by_workspace(
                        ws.id, resource_type=ResourceType.ASSET
                    )
                    asset_lines = []
                    for b in bindings:
                        name = (b.overrides or {}).get("display_name", b.resource_id)
                        asset_type = (b.overrides or {}).get("asset_type", "unknown")
                        asset_lines.append(f"    - {name} ({asset_type})")

                    parts.append(f"  [discoverable] {ws.id} — {ws.title}")
                    if asset_lines:
                        parts.extend(asset_lines)
                    else:
                        parts.append("    (no assets registered)")

            if not parts:
                return ""
            return "\n".join(parts)
        except Exception as exc:
            logger.warning("Failed to build asset map context: %s", exc)
            return ""

    def _build_lens_context(self) -> str:
        """Build lens context block for prompt injection.

        Uses the EffectiveLens resolved at engine init. Returns a concise
        summary of non-OFF lens dimensions suitable for prompt injection.
        """
        lens = getattr(self, "_effective_lens", None)
        if not lens:
            return ""

        parts: List[str] = []
        try:
            parts.append(f"Active Lens: {lens.global_preset_name}")
            parts.append(f"Lens Hash: {lens.hash}")
            # LensNodeState values: OFF, KEEP, EMPHASIZE (not 'active')
            engaged_nodes = [n for n in lens.nodes if n.state.value != "off"]
            emphasized = [n for n in lens.nodes if n.state.value == "emphasize"]
            if emphasized:
                parts.append("Emphasized dimensions:")
                for node in emphasized[:10]:
                    parts.append(
                        f"  - {node.node_label} (scope: {node.effective_scope})"
                    )
            if engaged_nodes:
                parts.append(f"Total active dimensions: {len(engaged_nodes)}")
        except Exception as exc:
            logger.warning("Failed to build lens context: %s", exc)

        return "\n".join(parts) if parts else ""

    def _build_previous_decisions_context(self) -> str:
        """Build previous meeting decisions context from DECISION_FINAL events.

        Queries the event store for DECISION_FINAL events from the most recent
        closed session, avoiding semantic pollution from session.decisions.
        """
        if not self.project_id:
            return ""

        parts: List[str] = []
        try:
            workspace_id = (
                getattr(self.workspace, "id", None) or self.session.workspace_id
            )

            session_store = getattr(self, "session_store", None)
            if not session_store:
                return ""

            previous_sessions = session_store.list_by_workspace(
                workspace_id=workspace_id,
                project_id=self.project_id,
                limit=2,
            )
            # Skip current session, take the most recent closed one
            prev = None
            for s in previous_sessions:
                if s.id != self.session.id and not s.is_active:
                    prev = s
                    break

            if not prev:
                return ""

            # Query DECISION_FINAL events from the event store
            decision_events = []
            try:
                all_session_events = self.store.get_events_by_meeting_session(
                    meeting_session_id=prev.id,
                    limit=50,
                )
                decision_events = [
                    e
                    for e in (all_session_events or [])
                    if (
                        getattr(e, "event_type", None) == EventType.DECISION_FINAL
                        or getattr(getattr(e, "event_type", None), "value", None)
                        == "decision_final"
                    )
                ][:10]
            except Exception:
                # Store may not support meeting session query
                pass

            if decision_events:
                parts.append("Previous meeting decisions:")
                for evt in decision_events[:5]:
                    payload = getattr(evt, "payload", {}) or {}
                    decision_text = payload.get("decision", "")
                    if decision_text:
                        round_num = payload.get("round_number", "?")
                        parts.append(f"  - [R{round_num}] {decision_text[:200]}")
            elif prev.minutes_md:
                # Fallback to minutes_md if no DECISION_FINAL events found
                minutes_snippet = prev.minutes_md[:800]
                if len(prev.minutes_md) > 800:
                    minutes_snippet += "\n... (truncated)"
                parts.append("Previous meeting summary:")
                parts.append(minutes_snippet)

            if prev.action_items:
                parts.append("Previous action items:")
                for item in prev.action_items[:5]:
                    title = item.get("title", "Untitled")
                    status = item.get("status", "pending")
                    parts.append(f"  - {title} [{status}]")

        except Exception as exc:
            logger.warning("Failed to build previous decisions context: %s", exc)

        return "\n".join(parts) if parts else ""

    def _build_turn_prompt(
        self,
        agent_id: str,
        round_num: int,
        user_message: str,
        decision: Optional[str],
        planner_proposals: List[str],
        critic_notes: List[str],
    ) -> str:
        """Build the full prompt for a single agent turn."""
        history = self._history_snippet()
        agenda = self.session.agenda or [user_message]
        agenda_text = "\n".join([f"- {a}" for a in agenda])
        latest_proposal = planner_proposals[-1] if planner_proposals else "(none)"
        latest_critic = critic_notes[-1] if critic_notes else "(none)"

        locale_map = {
            "zh-TW": "Traditional Chinese (zh-TW)",
            "zh-CN": "Simplified Chinese (zh-CN)",
            "en": "English",
            "ja": "Japanese",
        }
        locale_label = locale_map.get(self._locale, self._locale)
        locale_directive = (
            f"IMPORTANT: All your responses MUST be in {locale_label}. "
            f"Do not mix languages.\n\n"
        )

        project_block = ""
        if self._project_context:
            project_block = (
                f"=== Project Context ===\n"
                f"{self._project_context}\n"
                f"=== End Project Context ===\n\n"
                f"This meeting is about the project above. "
                f"All discussion, proposals, and action items must be "
                f"relevant to this specific project.\n\n"
            )

        # Inject workspace asset map for cross-workspace dispatch routing
        asset_map_block = ""
        asset_map_ctx = getattr(self, "_asset_map_context", "")
        if asset_map_ctx:
            asset_map_block = (
                f"=== Workspace Asset Map ===\n"
                f"{asset_map_ctx}\n"
                f"=== End Asset Map ===\n\n"
                f"When proposing action items, consider which workspace "
                f"owns the relevant data assets. Assign target_workspace_id "
                f"accordingly.\n\n"
            )

        common = locale_directive + project_block + asset_map_block

        # Inject available tools block
        tool_ctx = self._build_tool_inventory_block()
        if tool_ctx:
            common += (
                f"=== Available Tools ===\n" f"{tool_ctx}\n" f"=== End Tools ===\n\n"
            )
        # P2 observability: log tool inventory size so session traces are self-contained
        _tool_line_count = len(tool_ctx.strip().splitlines()) if tool_ctx else 0
        logger.debug(
            "meeting_tool_inventory agent=%s workspace=%s tool_lines=%d session=%s",
            agent_id,
            getattr(getattr(self, "session", None), "workspace_id", "?"),
            _tool_line_count,
            getattr(getattr(self, "session", None), "id", "?"),
        )

        # Inject uploaded files block
        uploaded = getattr(self, "_uploaded_files", [])
        if uploaded:
            file_lines = []
            for f in uploaded[:10]:
                name = f.get("file_name") or f.get("file_id", "unknown")
                ftype = f.get("file_type", "")
                file_lines.append(f"  - {name} ({ftype})" if ftype else f"  - {name}")
            common += (
                f"=== Uploaded Files ===\n"
                + "\n".join(file_lines)
                + "\n=== End Files ===\n\n"
            )

        common += (
            f"Meeting session: {self.session.id}\n"
            f"Round: {round_num}/{max(1, self.session.max_rounds)}\n"
            f"Agenda:\n{agenda_text}\n\n"
            f"User request:\n{user_message}\n\n"
            f"Current decision draft:\n{decision or '(not finalized)'}\n\n"
            f"Latest planner proposal:\n{latest_proposal}\n\n"
            f"Latest critic note:\n{latest_critic}\n\n"
            f"Recent turns:\n{history}\n\n"
        )

        # A1: Inject lens context (AgentSpec Agent Core requirement)
        lens_ctx = self._build_lens_context()
        if lens_ctx:
            common += (
                f"=== Active Lens ===\n"
                f"{lens_ctx}\n"
                f"=== End Lens ===\n\n"
                f"Consider the active lens dimensions when framing your response.\n\n"
            )

        # A1: Inject active intents (AgentSpec Agent Core requirement)
        intent_ids = getattr(self, "_active_intent_ids", [])
        if intent_ids:
            try:
                intents = self.store.list_intents(
                    self.profile_id,
                    project_id=self.project_id,
                )
                active = [i for i in intents if i.id in intent_ids]
                if active:
                    intent_lines = []
                    for i in active[:5]:
                        status_val = (
                            i.status.value
                            if hasattr(i.status, "value")
                            else str(i.status)
                        )
                        intent_lines.append(
                            f"  - {i.title} [{status_val}] "
                            f"(progress: {i.progress_percentage}%)"
                        )
                    common += (
                        f"=== Active Intents ===\n"
                        + "\n".join(intent_lines)
                        + "\n=== End Intents ===\n\n"
                    )
            except Exception as exc:
                logger.warning("Failed to inject intents into prompt: %s", exc)

        # A1: Inject previous meeting decisions (Agent Core project memory)
        prev_ctx = self._build_previous_decisions_context()
        if prev_ctx:
            common += (
                f"=== Previous Meeting Decisions ===\n"
                f"{prev_ctx}\n"
                f"=== End Previous Decisions ===\n\n"
            )

        # Workspace context as reference (not system-level instruction)
        ws_ctx = self._build_workspace_instruction_block()
        if ws_ctx:
            common += (
                "=== Workspace Context (Reference) ===\n"
                "The following is background context from the workspace. "
                "It does NOT override your agent role or the project agenda.\n"
                f"{ws_ctx}\n"
                "=== End Context ===\n\n"
            )

        if agent_id == "facilitator":
            return (
                common
                + "As facilitator, synthesize progress and decide if another round is needed. "
                "If converged, include the marker [CONVERGED]. Keep concise."
            )
        if agent_id == "planner":
            file_directive = ""
            if getattr(self, "_uploaded_files", None):
                file_directive = (
                    "CONSTRAINT: Uploaded files are present. Your plan MUST include "
                    "at least one step that uses a tool or playbook from Available "
                    "Tools to process these files into structured artifacts. "
                )
            return (
                common
                + file_directive
                + "As planner, propose a concrete, executable plan with clear steps and ownership."
            )
        if agent_id == "critic":
            file_check = ""
            if getattr(self, "_uploaded_files", None):
                file_check = (
                    "MANDATORY CHECK: Verify the planner's proposal includes "
                    "tool or playbook usage for the uploaded files. If the plan "
                    "only produces text analysis without using available tools, "
                    "flag this as a critical gap. "
                )
            return (
                common
                + file_check
                + "As critic, challenge assumptions, identify risks, and suggest mitigations."
            )
        # 5A-1: Inject available playbooks for executor
        playbooks_cache = getattr(self, "_available_playbooks_cache", "")
        playbook_block = ""
        if playbooks_cache and agent_id == "executor":
            playbook_block = (
                f"=== Available Playbooks ===\n"
                f"{playbooks_cache}\n"
                f"=== End Playbooks ===\n\n"
            )

        # Hard constraint: only enforce when the workspace has EXPLICIT TOOL
        # bindings (admin-configured allowlist).  The manifest fallback is
        # reference-only — we must not force tool usage in pure-discussion
        # sessions where the LLM legitimately has nothing to invoke.
        tool_ctx = self._build_tool_inventory_block()
        has_explicit_bindings = self._has_workspace_tool_bindings()
        has_rag_tools = bool(getattr(self, "_rag_tool_cache", []))
        tool_constraint = ""
        if has_explicit_bindings or has_rag_tools or playbooks_cache:
            tool_constraint = (
                "MANDATORY: The workspace has been configured with specific tools / "
                "playbooks (see Available Tools / Available Playbooks above). "
                "At least one action item in your JSON array MUST have a non-null "
                "tool_name (chosen exactly from Available Tools) OR a non-null "
                "playbook_code (chosen exactly from Available Playbooks). "
                "Action items with both tool_name=null AND playbook_code=null are "
                "only allowed when no configured tool is relevant to that specific step. "
            )

        return (
            common
            + playbook_block
            + "As executor, produce only JSON array with up to 3 action items. "
            'Schema: [{"title":"...","description":"...","assigned_to":"executor",'
            '"priority":"low|medium|high","playbook_code":null,'
            '"target_workspace_id":null,'
            '"tool_name":null,"input_params":null,"blocked_by":null}] '
            "If a workspace asset map is provided, set target_workspace_id to the "
            "workspace that owns the relevant data assets for each action item. "
            "playbook_code MUST be selected from Available Playbooks above, or null "
            "if none match. "
            "tool_name is for direct tool invocation without a playbook. "
            "Use tool_name exactly as listed in Available Tools, including the "
            "namespace prefix (e.g., pack.tool). "
            "blocked_by is a list of action item indices (0-based) that must complete first. "
            + tool_constraint
        )

    def _history_snippet(self) -> str:
        """Return a concise summary of recent turn history."""
        if not self._turn_history:
            return "(none)"
        recent = self._turn_history[-6:]
        return "\n".join(
            [f"- R{t['round']} {t['role']}: {t['content'][:220]}" for t in recent]
        )

    def _fallback_turn_text(
        self, agent_id: str, round_num: int, user_message: str
    ) -> str:
        """Generate a deterministic fallback turn when LLM is unavailable."""
        if agent_id == "facilitator":
            return (
                f"Round {round_num} facilitation summary for '{user_message[:80]}'. "
                "Planner and critic inputs consolidated."
            )
        if agent_id == "planner":
            return f"Proposal R{round_num}: execute incrementally, track evidence, and verify outcomes."
        if agent_id == "critic":
            return f"Critique R{round_num}: verify data contract, add rollback checks, and test failure paths."
        return json.dumps(
            [
                {
                    "title": "Implement finalized decision",
                    "description": "Translate final meeting decision into executable work.",
                    "assigned_to": "executor",
                    "priority": "medium",
                    "playbook_code": None,
                }
            ]
        )

    def _is_converged(
        self, round_num: int, max_rounds: int, facilitator_text: str
    ) -> bool:
        """Check whether the meeting has converged.

        Uses RoundVerdict.try_parse() for structured convergence checking.
        Stores the parsed verdict on self._last_round_verdict for downstream
        consumers (L2/L3) to inspect confidence and remaining concerns.
        """
        from backend.app.models.layer_artifacts import RoundVerdict

        if round_num >= max_rounds:
            self._last_round_verdict = RoundVerdict(
                converged=True,
                confidence=1.0,
                reason="max_rounds_reached",
            )
            return True

        verdict = RoundVerdict.try_parse(facilitator_text)
        self._last_round_verdict = verdict

        if round_num >= 2 and verdict.converged:
            return True

        return False

    def _render_minutes(
        self,
        user_message: str,
        decision: str,
        critic_notes: List[str],
        action_items: List[Dict[str, Any]],
        converged: bool,
    ) -> str:
        """Render final meeting minutes as markdown."""
        status = "converged" if converged else "partial"

        # 1. Topic line: prefer project title, fallback to user_message
        topic = self._extract_meeting_topic(user_message)

        # 2. Decision summary: cap at 300 chars
        decision_summary = decision[:300]
        if len(decision) > 300:
            decision_summary += "\n\n_(...truncated)_"

        # 3. Risks summary: cap each critic note at 200 chars
        risk_lines = []
        for note in critic_notes:
            summary = note[:200]
            if len(note) > 200:
                summary += "..."
            risk_lines.append(f"- {summary}")
        risk_text = "\n".join(risk_lines) or "- None"

        # 4. Action Items table
        action_lines = "\n".join(
            [
                (
                    f"| {idx} | {item.get('title', 'Action Item')} | "
                    f"{item.get('assigned_to', 'executor')} | {item.get('priority', 'medium')} |"
                )
                for idx, item in enumerate(action_items, start=1)
            ]
        )
        if not action_lines:
            action_lines = "| 1 | No action item generated | executor | medium |"

        # 5. Agenda from session record (Fix 2), fallback to user_message
        agenda_items = self.session.agenda or [user_message]
        agenda_text = "\n".join([f"- {a}" for a in agenda_items])

        return (
            f"# {topic}\n"
            f"_Meeting {self.session.id[:8]} · {status} · {self.session.round_count} rounds_\n\n"
            f"## Agenda\n{agenda_text}\n\n"
            f"## Decisions\n{decision_summary}\n\n"
            f"## Risks & Concerns\n{risk_text}\n\n"
            "## Action Items\n"
            "| # | Task | Assigned To | Priority |\n"
            "|---|------|-------------|----------|\n"
            f"{action_lines}\n"
        )

    def _extract_meeting_topic(self, user_message: str) -> str:
        """Extract a concise topic line for meeting minutes title."""
        # Prefer project title from context
        project_ctx = getattr(self, "_project_context", "")
        if project_ctx:
            for line in project_ctx.split("\n"):
                if line.startswith("Project:"):
                    return line.replace("Project:", "").strip() + " — Meeting Minutes"

        # Fallback: first 60 chars of user_message
        topic = user_message[:60]
        if len(user_message) > 60:
            topic += "..."
        return f"Meeting Minutes — {topic}"
