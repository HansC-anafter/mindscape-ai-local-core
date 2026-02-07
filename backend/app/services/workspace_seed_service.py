"""
Workspace Seed Service for Minimum File Reference (MFR)

Processes seed input (text/file/urls) and generates workspace blueprint digest
without requiring full knowledge base import or embedding.

Key rules:
1. process_seed() must pass seed_type to _generate_digest(), otherwise URL "no hallucination" rule will fail
2. urls seed: only store link + note, don't fetch webpage content
3. file seed: extract text first, then do chunking (don't use payload directly as content chunk)
4. MFR conclusion: no embedding needed, embedding can be done in "subsequent events (after output completion/user clicks save to knowledge base)"
"""

import logging
from typing import Dict, Any, List, Optional
from backend.app.services.stores.workspaces_store import WorkspacesStore
from backend.app.services.stores.intents_store import IntentsStore
from backend.app.services.stores.events_store import EventsStore
from backend.app.models.workspace import Workspace, LaunchStatus
from backend.app.models.workspace_blueprint import WorkspaceBlueprint
from backend.app.models.mindscape import IntentCard, IntentStatus, PriorityLevel
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class WorkspaceSeedService:
    """Service for processing workspace seeds and generating blueprints"""

    def __init__(self, store):
        """
        Initialize seed service

        Args:
            store: MindscapeStore instance (provides database connection)
        """
        self.store = store
        self.workspaces_store = WorkspacesStore(store.db_path)
        self.intents_store = IntentsStore(store.db_path)
        self.events_store = EventsStore(store.db_path)

    async def process_seed(
        self,
        workspace_id: str,
        seed_type: str,  # "text" | "file" | "urls"
        payload: Any,
        locale: str = "zh-TW",
    ) -> Dict[str, Any]:
        """
        Process seed and generate digest

        Args:
            workspace_id: Workspace ID
            seed_type: Seed type ("text" | "file" | "urls")
            payload: Seed payload (text string, file data, or list of {url, note} dicts)
            locale: Locale for LLM generation (default: "zh-TW")

        Returns:
            {
                "brief": str,
                "facts": List[str],
                "unknowns": List[str],
                "next_actions": List[str],
                "intents": List[Dict],
                "starter_kit_type": str,
                "first_playbook": str
            }
        """
        # 1. Extract readable text
        text_content = await self._extract_text(seed_type, payload)

        # 2. LLM generate digest (no embedding needed)
        # Important: must pass seed_type, otherwise URL "no hallucination" rule will fail
        # Important: _generate_digest() must receive seed_type parameter, otherwise URL rule will fail
        digest = await self._generate_digest(
            text_content, locale, workspace_id, seed_type=seed_type
        )

        # 3. Apply to workspace_blueprint
        await self._apply_to_blueprint(workspace_id, digest, seed_type=seed_type)

        return digest

    async def _extract_text(self, seed_type: str, payload: Any) -> str:
        """Extract readable text from seed"""
        if seed_type == "text":
            return payload  # Use directly

        elif seed_type == "file":
            # Important: extract_text_from_file first, then chunking
            # Key rule: don't use payload directly as content chunk, must extract text first
            # payload may be base64 / UploadFile / file path, need unified handling
            text_content = await self._extract_text_from_file(payload)

            # Then feed to document_processor for chunking (if needed)
            # Important: chunking's content parameter must be extracted text content, not original payload
            from backend.app.services.document_processor import (
                chunk_document_to_objects,
            )

            chunks = chunk_document_to_objects(
                content=text_content,  # Correct: use extracted text content
                max_chunk_size=100000,
                strategy="paragraph",
            )
            return "\n\n".join([chunk.content for chunk in chunks])

        elif seed_type == "urls":
            # Key rule: only store link + note, don't fetch webpage content
            # Important: URLs seed's prompt must explicitly tell LLM "don't hallucinate content"
            # This rule is implemented in _generate_digest()
            return "\n".join(
                [f"{item['url']}: {item.get('note', '')}" for item in payload]
            )

    async def _extract_text_from_file(self, payload: Any) -> str:
        """
        Extract text from file (handles base64/UploadFile/path)

        Important: unified handling of different file payload formats

        Important: this method must be independent, cannot have elif seed_type == "urls" in it
        (that's _extract_text's logic)
        """
        # TODO: Implement file text extraction
        # Handle base64 / UploadFile / file path
        # Do OCR if necessary
        # Return plain text content
        raise NotImplementedError(
            "File extraction not yet implemented. MFR v0 only supports text seed."
        )

    async def _generate_digest(
        self,
        text_content: str,
        locale: str,
        workspace_id: str,
        seed_type: str = "text",  # Important: must receive seed_type parameter
    ) -> Dict[str, Any]:
        """
        Generate seed digest using LLM (no embedding)

        Important: must receive seed_type parameter, otherwise URL "no hallucination" rule will fail
        Important: MFR goal is to let users start working immediately after entering workspace, so no embedding needed
        Important: embedding can be done in "subsequent events (after output completion/user clicks save to knowledge base)"
        """
        # Get workspace to get profile_id
        workspace = await self.workspaces_store.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        profile_id = workspace.owner_user_id

        # Get LLM provider
        from backend.app.shared.llm_provider_helper import (
            create_llm_provider_manager,
            get_llm_provider_from_settings,
        )
        from backend.app.services.config_store import ConfigStore
        from backend.app.services.system_settings_store import SystemSettingsStore

        config_store = ConfigStore(self.store.db_path)
        settings_store = SystemSettingsStore()

        config = config_store.get_or_create_config(profile_id)

        llm_manager = create_llm_provider_manager(
            openai_key=config.agent_backend.openai_api_key,
            anthropic_key=config.agent_backend.anthropic_api_key,
            vertex_api_key=config.agent_backend.vertex_api_key,
            vertex_project_id=config.agent_backend.vertex_project_id,
            vertex_location=config.agent_backend.vertex_location,
        )

        try:
            llm_provider = get_llm_provider_from_settings(llm_manager)
        except ValueError as e:
            logger.warning(f"LLM provider not available: {e}, using fallback")
            return self._generate_fallback_digest(text_content, seed_type)

        chat_setting = settings_store.get_setting("chat_model")
        if not chat_setting or not chat_setting.value:
            logger.warning("Chat model not configured, using fallback")
            return self._generate_fallback_digest(text_content, seed_type)

        # Key rule: if URLs seed, add hard rule in prompt
        if seed_type == "urls":
            prompt_rule = """
⚠️ IMPORTANT RULE: URL content cannot be inferred, can only treat it as a "to-read material list".
Do not infer webpage content from URLs, can only generate digest based on user-provided notes and the URL itself.
"""
        else:
            prompt_rule = ""

        # Build schema description
        schema_description = """A workspace blueprint digest with the following structure:
- brief: string - 1-2 paragraph workspace brief (what to do / what not to do / success criteria)
- facts: array of strings - List of known facts (5-10 items)
- unknowns: array of strings - List of unknown items that need clarification (3-7 items)
- next_actions: array of strings - List of actionable next steps (5-12 items)
- intents: array of objects - List of intent cards (3-7 items), each with:
  - title: string
  - description: string
  - priority: string (one of: "high", "medium", "low")
- starter_kit_type: string - Recommended starter kit type (content_generation / client_delivery / knowledge_base / custom)
- first_playbook: string - Recommended first playbook to run (e.g., "daily_planning", "content_drafting", "client_delivery_kickoff")
"""

        # Build text content with prompt rule
        full_text = f"""You are a workspace setup assistant. Based on the following seed material, generate a workspace blueprint digest.

{prompt_rule}

Seed material:
{text_content}

Please generate a structured digest according to the schema description.
"""

        try:
            from backend.app.capabilities.core_llm.services.structured import extract

            result = await extract(
                text=full_text,
                schema_description=schema_description,
                llm_provider=llm_provider,
                target_language=locale,
            )

            extracted_data = result.get("extracted_data", {})
            if not extracted_data:
                logger.warning("LLM extraction returned empty data, using fallback")
                return self._generate_fallback_digest(text_content, seed_type)

            return extracted_data

        except Exception as e:
            logger.error(f"Failed to generate digest with LLM: {e}", exc_info=True)
            return self._generate_fallback_digest(text_content, seed_type)

    def _generate_fallback_digest(
        self, text_content: str, seed_type: str
    ) -> Dict[str, Any]:
        """Generate fallback digest when LLM is not available"""
        return {
            "brief": f"Workspace created from {seed_type} seed. Please configure manually.",
            "facts": [],
            "unknowns": ["Need to clarify workspace goals and requirements"],
            "next_actions": [
                "Review workspace configuration",
                "Add initial intents",
                "Configure AI team",
                "Select playbooks",
            ],
            "intents": [
                {
                    "title": "Initial Setup",
                    "description": "Complete workspace configuration",
                    "priority": "high",
                }
            ],
            "starter_kit_type": "custom",
            "first_playbook": "daily_planning",
        }

    async def _apply_to_blueprint(
        self,
        workspace_id: str,
        digest: Dict[str, Any],
        seed_type: str = "text",  # Pass seed_type for event recording
    ):
        """
        Apply digest to workspace blueprint

        Important: define "minimum write set" to avoid scattered logic
        """
        workspace = await self.workspaces_store.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        # Minimum write set (blocking main flow requirements):
        # 1. workspace.workspace_blueprint (with brief, initial_intents, first_playbook, tool_connections initial state)
        # 2. workspace.launch_status = 'ready'
        # 3. intents_store.create_intent (3-7 cards)
        # 4. mind_event record "seed_applied"

        # Build workspace blueprint
        from backend.app.models.workspace_blueprint import WorkspaceGoals

        # Extract goals from brief (simple heuristic)
        goals = None
        if digest.get("brief"):
            goals = WorkspaceGoals(
                primary_goals=[digest["brief"][:100]],  # Simplified
                out_of_scope=digest.get("unknowns", [])[:3],
                success_criteria=digest.get("next_actions", [])[:3],
            )

        blueprint = WorkspaceBlueprint(
            brief=digest.get("brief"),
            goals=goals,
            initial_intents=digest.get("intents", []),
            ai_team=[],  # Will be populated later
            playbooks=[],  # Will be populated later
            tool_connections=[],  # Will be populated later
            first_playbook=digest.get("first_playbook"),
            seed_digest={
                "facts": digest.get("facts", []),
                "unknowns": digest.get("unknowns", []),
                "next_actions": digest.get("next_actions", []),
            },
        )

        # Update workspace
        workspace.workspace_blueprint = blueprint
        workspace.launch_status = LaunchStatus.READY
        workspace.starter_kit_type = digest.get("starter_kit_type")
        await self.workspaces_store.update_workspace(workspace)

        # Create intents
        profile_id = workspace.owner_user_id
        for intent_data in digest.get("intents", []):
            intent = IntentCard(
                id=str(uuid.uuid4()),
                profile_id=profile_id,
                title=intent_data.get("title", "Untitled Intent"),
                description=intent_data.get("description", ""),
                status=IntentStatus.ACTIVE,  # Use ACTIVE for newly created intents
                priority=PriorityLevel(intent_data.get("priority", "medium")),
                tags=[],
                storyline_tags=[],
                category=None,
                progress_percentage=0.0,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                started_at=None,
                completed_at=None,
                due_date=None,
                parent_intent_id=None,
                child_intent_ids=[],
                metadata={"workspace_id": workspace_id},
            )
            self.intents_store.create_intent(intent)

        # Create mind_event for "seed_applied"
        from backend.app.models.mindscape import MindEvent, EventType, EventActor

        event = MindEvent(
            id=str(uuid.uuid4()),
            profile_id=profile_id,
            workspace_id=workspace_id,
            actor=EventActor.SYSTEM,
            channel="api",
            event_type=EventType.INSIGHT,  # Use INSIGHT as closest match, or could add new event type later
            payload={
                "seed_type": seed_type,
                "digest": digest,
                "source": "workspace_seed_service",
            },
            timestamp=datetime.utcnow(),
            metadata={"source": "workspace_seed_service", "action": "seed_applied"},
        )
        self.events_store.create_event(event, generate_embedding=False)

        logger.info(
            f"Applied seed digest to workspace {workspace_id}, created {len(digest.get('intents', []))} intents"
        )
