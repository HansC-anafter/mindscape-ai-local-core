"""
Playbook API routes
Handles Playbook library management
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Path, Query, UploadFile, File

from ...models.playbook import (
    Playbook, CreatePlaybookRequest, UpdatePlaybookRequest
)
from ...services.playbook_service import PlaybookService
from ...services.tool_status_checker import ToolStatusChecker
from ...services.tool_registry import ToolRegistryService
from ...services.playbook_tool_checker import PlaybookToolChecker
from ...services.mindscape_store import MindscapeStore
from ...services.stores.playbook_executions_store import PlaybookExecutionsStore
from ...services.stores.workspace_pinned_playbooks_store import WorkspacePinnedPlaybooksStore
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])

# Initialize services
mindscape_store = MindscapeStore()
executions_store = PlaybookExecutionsStore()
pinned_playbooks_store = WorkspacePinnedPlaybooksStore()

# Initialize Cloud Extension Manager and register providers
cloud_extension_manager = None
try:
    from ...services.cloud_extension_manager import CloudExtensionManager
    from ...services.cloud_providers.generic_http import GenericHttpProvider
    from ...services.system_settings_store import SystemSettingsStore

    # Get settings store for reading cloud configuration
    settings_store = SystemSettingsStore()

    # Migrate from old settings format if needed
    def _migrate_cloud_settings(settings_store: SystemSettingsStore):
        """
        Migrate from old cloud settings format to new cloud_providers array

        Old format: cloud_enabled, cloud_api_url, cloud_license_key
        New format: cloud_providers array
        """
        try:
            # Check if migration is needed
            providers_config = settings_store.get("cloud_providers", default=[])
            if providers_config:
                # Already migrated
                return

            # Check for old settings
            old_api_url = settings_store.get("cloud_api_url", default="")
            old_license_key = settings_store.get("cloud_license_key", default="")
            old_enabled = settings_store.get("cloud_enabled", default=False)

            if old_api_url and old_license_key and old_enabled:
                # Migrate to new format
                logger.info("Migrating cloud settings from old format to new cloud_providers array")

                new_provider = {
                    "provider_id": "mindscape_official",
                    "provider_type": "generic_http",
                    "enabled": True,
                    "config": {
                        "api_url": old_api_url,
                        "name": "Mindscape AI Cloud",
                        "auth": {
                            "auth_type": "api_key",
                            "api_key": old_license_key
                        }
                    }
                }

                settings_store.set("cloud_providers", [new_provider])
                logger.info("Cloud settings migrated successfully")
        except Exception as e:
            logger.warning(f"Failed to migrate cloud settings: {e}", exc_info=True)

    _migrate_cloud_settings(settings_store)

    # Initialize Cloud Extension Manager
    cloud_extension_manager = CloudExtensionManager.instance()

    # Load all providers from system settings (neutral interface - no built-in concept)
    # All providers are configured through settings
    try:
        providers_config = settings_store.get("cloud_providers", default=[])

        if providers_config:
            logger.info(f"Loading {len(providers_config)} cloud providers from settings")

            for provider_config in providers_config:
                if not provider_config.get("enabled", False):
                    continue

                provider_id = provider_config.get("provider_id")
                provider_type = provider_config.get("provider_type")
                config = provider_config.get("config", {})

                try:
                    if provider_type == "generic_http":
                        # Generic HTTP provider
                        auth_config = config.get("auth", {})
                        if not auth_config:
                            logger.warning(f"Provider {provider_id}: Missing 'auth' configuration, skipping")
                            continue

                        provider = GenericHttpProvider(
                            provider_id=provider_id,
                            provider_name=config.get("name", provider_id),
                            api_url=config.get("api_url"),
                            auth_config=auth_config,
                            api_path_template=config.get(
                                "api_path_template",
                                "/api/v1/playbooks/{capability_code}/{playbook_code}"
                            ),
                            pack_download_path=config.get("pack_download_path")
                        )
                    else:
                        logger.warning(f"Unknown provider type: {provider_type}, skipping")
                        continue

                    cloud_extension_manager.register_provider(provider)
                    logger.info(f"Registered cloud provider: {provider_id} ({provider_type})")

                except Exception as e:
                    logger.error(f"Failed to register provider {provider_id}: {e}", exc_info=True)
        else:
            logger.debug("No cloud providers configured")

    except Exception as e:
        logger.warning(f"Failed to load cloud providers from settings: {e}", exc_info=True)

except ImportError:
    logger.debug("Cloud Extension Manager not available (httpx not installed or module not found)")
except Exception as e:
    logger.warning(f"Failed to initialize Cloud Extension Manager: {e}")

playbook_service = PlaybookService(store=mindscape_store, cloud_extension_manager=cloud_extension_manager)


@router.get("", response_model=List[Dict[str, Any]])
async def list_playbooks(
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    locale: str = Query('zh-TW', description="[DEPRECATED] Language locale. Use target_language instead."),
    target_language: Optional[str] = Query(None, description="Target language for filtering (e.g., 'zh-TW', 'en'). Playbooks are language-neutral by default."),
    scope: str = Query('system', description="system|user|all"),
    onboarding_task: Optional[str] = Query(None, description="Filter by onboarding task"),
    uses_tool: Optional[str] = Query(None, description="Filter playbooks that require this tool (e.g., 'wordpress', 'canva')"),
    profile_id: str = Query('default-user', description="User profile for personalization"),
    workspace_id: Optional[str] = Query(None, description="Filter playbooks used in this workspace"),
    filter: Optional[str] = Query(None, description="Filter type: favorites|recent|created_by_me|ready_to_run")
):
    """
    List playbooks with filtering and personalization

    Returns playbooks with user meta (favorite, use_count, etc.)
    Playbooks are language-neutral by default. The target_language parameter is informational only.
    """
    try:
        # Parse tags
        tag_list = tags.split(',') if tags else None

        all_playbook_metadata = await playbook_service.list_playbooks(
            locale=None,
            tags=tag_list
        )

        file_playbooks = []
        for metadata in all_playbook_metadata:
            playbook = Playbook(
                metadata=metadata,
                sop_content=""
            )
            file_playbooks.append(playbook)

        # Determine preferred locale from target_language or locale parameter
        preferred_locale = None
        if target_language:
            # Map target_language to locale for filtering
            if target_language.startswith('en'):
                preferred_locale = 'en'
            elif target_language.startswith('zh'):
                preferred_locale = 'zh-TW'
            elif target_language.startswith('ja') or target_language == 'ja':
                preferred_locale = 'ja'
        elif locale:
            preferred_locale = locale

        # Group playbooks by playbook_code and select preferred locale version
        playbook_dict = {}
        for playbook in file_playbooks:
            code = playbook.metadata.playbook_code
            playbook_locale = playbook.metadata.locale

            # If no preference, keep first found
            if code not in playbook_dict:
                playbook_dict[code] = playbook
            # If preference specified, prefer matching locale
            elif preferred_locale:
                # If new playbook matches preferred locale and current doesn't, replace
                if playbook_locale == preferred_locale and playbook_dict[code].metadata.locale != preferred_locale:
                    playbook_dict[code] = playbook
                # If current matches preferred locale and new doesn't, keep current
                elif playbook_dict[code].metadata.locale == preferred_locale and playbook_locale != preferred_locale:
                    continue
                # If neither matches preference, prefer zh-TW > en > ja
                elif playbook_dict[code].metadata.locale != preferred_locale and playbook_locale != preferred_locale:
                    locale_priority = {'zh-TW': 3, 'en': 2, 'ja': 1}
                    if locale_priority.get(playbook_locale, 0) > locale_priority.get(playbook_dict[code].metadata.locale, 0):
                        playbook_dict[code] = playbook
            # If no preference, prefer zh-TW > en > ja
            else:
                locale_priority = {'zh-TW': 3, 'en': 2, 'ja': 1}
                if locale_priority.get(playbook_locale, 0) > locale_priority.get(playbook_dict[code].metadata.locale, 0):
                    playbook_dict[code] = playbook

        playbooks = list(playbook_dict.values())

        # Auto-localization: If preferred locale not found, fallback to English version
        # LLM will handle translation at runtime when language_strategy='model_native' and auto_localize=True
        # No need to modify locale here - execution runtime will use target_language parameter

        # Filter by tags
        if tag_list:
            playbooks = [p for p in playbooks
                        if any(tag in p.metadata.tags for tag in tag_list)]

        # Filter by onboarding_task
        if onboarding_task:
            playbooks = [p for p in playbooks
                        if p.metadata.onboarding_task == onboarding_task]

        # Filter by uses_tool (playbooks that require this tool)
        if uses_tool:
            playbooks = [p for p in playbooks
                        if uses_tool in (p.metadata.required_tools or [])]

        # Filter by workspace_id: include both executed and pinned playbooks
        if workspace_id:
            workspace_playbook_codes = set()

            # Get playbooks executed in this workspace
            with executions_store.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT playbook_code
                    FROM playbook_executions
                    WHERE workspace_id = ?
                ''', (workspace_id,))
                workspace_playbook_codes.update({row[0] for row in cursor.fetchall()})

            # Get pinned playbooks for this workspace
            try:
                pinned_playbooks = pinned_playbooks_store.list_pinned_playbooks(workspace_id)
                workspace_playbook_codes.update({pb['playbook_code'] for pb in pinned_playbooks})
            except Exception as e:
                logger.warning(f"Failed to get pinned playbooks for workspace {workspace_id}: {e}")

            playbooks = [p for p in playbooks if p.metadata.playbook_code in workspace_playbook_codes]

        # Aggregate workspace usage count for all playbooks
        playbook_codes = [p.metadata.playbook_code for p in playbooks]
        workspace_usage_counts = {}
        if playbook_codes:
            with executions_store.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join(['?'] * len(playbook_codes))
                cursor.execute(f'''
                    SELECT playbook_code, COUNT(DISTINCT workspace_id) as usage_count
                    FROM playbook_executions
                    WHERE playbook_code IN ({placeholders})
                    GROUP BY playbook_code
                ''', playbook_codes)
                for row in cursor.fetchall():
                    workspace_usage_counts[row[0]] = row[1]

        # Query pinned workspaces for all playbooks
        pinned_workspaces_map = {}
        if playbook_codes:
            for playbook_code in playbook_codes:
                pinned_workspaces = pinned_playbooks_store.get_pinned_workspaces_for_playbook(playbook_code, limit=3)
                pinned_workspaces_map[playbook_code] = pinned_workspaces

        # Apply filter parameter
        if filter == 'favorites':
            # Filter by favorites
            favorite_codes = mindscape_store.user_playbook_meta.list_favorites(profile_id)
            playbooks = [p for p in playbooks if p.metadata.playbook_code in favorite_codes]
        elif filter == 'recent':
            # Filter by recent usage
            recent_codes = mindscape_store.user_playbook_meta.list_recent(profile_id, limit=50)
            playbooks = [p for p in playbooks if p.metadata.playbook_code in recent_codes]
        elif filter == 'created_by_me':
            # Filter by created_by_me (not yet implemented - would need owner field in playbook metadata)
            # For now, skip filtering
            pass
        elif filter == 'ready_to_run':
            # Filter by ready_to_run: all required tools are available
            tool_registry = ToolRegistryService()
            available_tools = set(tool_registry.list_tools().keys())

            ready_playbooks = []
            for playbook in playbooks:
                required_tools = playbook.metadata.required_tools or []
                if all(tool in available_tools for tool in required_tools):
                    ready_playbooks.append(playbook)
            playbooks = ready_playbooks

        results = []
        for playbook in playbooks:
            # Load user_meta from store
            user_meta = mindscape_store.get_user_meta(profile_id, playbook.metadata.playbook_code)
            has_personal_variant = False
            default_variant = None

            playbook_code = playbook.metadata.playbook_code
            result = {
                "playbook_code": playbook_code,
                "version": playbook.metadata.version,
                "locale": playbook.metadata.locale,
                "name": playbook.metadata.name,
                "description": playbook.metadata.description,
                "tags": playbook.metadata.tags,
                "entry_agent_type": playbook.metadata.entry_agent_type,
                "onboarding_task": playbook.metadata.onboarding_task,
                "icon": playbook.metadata.icon,
                "required_tools": playbook.metadata.required_tools,
                "kind": playbook.metadata.kind.value if playbook.metadata.kind else None,
                "capability_code": playbook.metadata.capability_code,
                "user_meta": user_meta or {
                    "favorite": False,
                    "use_count": 0
                },
                "has_personal_variant": has_personal_variant,
                "default_variant_name": default_variant.get("variant_name") if default_variant else None,
                "workspace_usage_count": workspace_usage_counts.get(playbook_code, 0),
                "pinned_workspaces": pinned_workspaces_map.get(playbook_code, [])
            }
            results.append(result)

        results.sort(key=lambda x: (
            -int(x['user_meta'].get('favorite', False)),
            -x['user_meta'].get('use_count', 0)
        ))

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{playbook_code}/variants", response_model=List[Dict[str, Any]])
async def get_playbook_variants(
    playbook_code: str = Path(..., description="Playbook code"),
    profile_id: str = Query('default-user', description="User profile ID")
):
    """
    Get personalized variants for a playbook
    Returns empty list if no variants exist
    """
    try:
        variants = store.list_personalized_variants(profile_id, playbook_code, active_only=True)
        return variants
    except Exception as e:
        logger.debug(f"Failed to load variants for {playbook_code}: {e}")
        return []


@router.post("/discover", response_model=Dict[str, Any])
async def discover_playbook(
    request: Dict[str, Any]
):
    """
    Discover playbook based on user query using LLM
    Supports filtering by capability_code and workspace_id for context-aware search
    """
    try:
        query = request.get('query', '')
        profile_id = request.get('profile_id', 'default-user')
        capability_code = request.get('capability_code')
        workspace_id = request.get('workspace_id')

        if not query:
            return {
                'suggestion': 'Please describe your needs, for example: "I want to analyze data", "I need to generate Instagram posts", etc.',
                'recommended_playbooks': []
            }

        # Get all playbooks via PlaybookService
        all_playbook_metadata = await playbook_service.list_playbooks()
        # Convert to Playbook objects for compatibility
        all_playbooks = [Playbook(metadata=m, sop_content="") for m in all_playbook_metadata]

        # Filter by capability_code if provided
        if capability_code:
            all_playbooks = [p for p in all_playbooks if p.metadata.capability_code == capability_code]

        # Filter by workspace_id if provided (include pinned playbooks)
        if workspace_id:
            pinned_codes = set()
            try:
                pinned_playbooks = pinned_playbooks_store.list_pinned_playbooks(workspace_id)
                pinned_codes = {pb['playbook_code'] for pb in pinned_playbooks}
            except Exception as e:
                logger.warning(f"Failed to get pinned playbooks for workspace {workspace_id}: {e}")

            workspace_execution_codes = set()
            try:
                with executions_store.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT DISTINCT playbook_code
                        FROM playbook_executions
                        WHERE workspace_id = ?
                    ''', (workspace_id,))
                    workspace_execution_codes = {row[0] for row in cursor.fetchall()}
            except Exception as e:
                logger.warning(f"Failed to get execution playbooks for workspace {workspace_id}: {e}")

            workspace_playbook_codes = pinned_codes | workspace_execution_codes
            all_playbooks = [p for p in all_playbooks if p.metadata.playbook_code in workspace_playbook_codes]

        # Simple keyword matching for now (can be enhanced with LLM later)
        query_lower = query.lower()
        matched_playbooks = []

        for playbook in all_playbooks:
            name = playbook.metadata.name.lower()
            description = playbook.metadata.description.lower()
            tags = ' '.join([tag.lower() for tag in playbook.metadata.tags or []])

            # Simple keyword matching
            if (query_lower in name or
                query_lower in description or
                any(query_lower in tag for tag in playbook.metadata.tags or [])):
                matched_playbooks.append({
                    'playbook_code': playbook.metadata.playbook_code,
                    'name': playbook.metadata.name,
                    'description': playbook.metadata.description,
                    'icon': playbook.metadata.icon
                })

        # Limit to top 5 matches
        matched_playbooks = matched_playbooks[:5]

        if matched_playbooks:
            playbook_list = '\n\n'.join([
                f"{i + 1}. {p.get('icon', '📋')} {p.get('name', '')}\n   {p.get('description', '')}"
                for i, p in enumerate(matched_playbooks)
            ])
            suggestion = f'Based on your needs "{query}", I found {len(matched_playbooks)} relevant Playbook(s):\n\n{playbook_list}'
        else:
            suggestion = f'Sorry, I could not find any Playbook related to "{query}". Please try other keywords or view the complete Playbook list.'

        return {
            'suggestion': suggestion,
            'recommended_playbooks': matched_playbooks
        }
    except Exception as e:
        logger.error(f"Failed to discover playbook: {e}")
        return {
            'suggestion': 'Sorry, I am temporarily unable to process your request. Please try again later.',
            'recommended_playbooks': []
        }


@router.get("/{playbook_code}", response_model=Dict[str, Any])
async def get_playbook(
    playbook_code: str,
    version: Optional[str] = Query(None),
    locale: str = Query('zh-TW', description="[DEPRECATED] Language locale. Use target_language instead."),
    target_language: Optional[str] = Query(None, description="Target language for content (e.g., 'zh-TW', 'en'). Playbooks are language-neutral."),
    profile_id: str = Query('default-user')
):
    """
    Get playbook detail with user meta and associated intents

    Playbooks are language-neutral. The target_language parameter is used for execution,
    but the SOP content is returned as-is from the Playbook file.
    """
    try:
        # Remove .en suffix if present in playbook_code
        base_code = playbook_code.replace('.en', '')

        # Determine preferred locale from target_language or locale parameter
        preferred_locale = None
        if target_language:
            # Map target_language to locale for file selection
            if target_language.startswith('en'):
                preferred_locale = 'en'
            elif target_language.startswith('zh'):
                preferred_locale = 'zh-TW'
            elif target_language.startswith('ja') or target_language == 'ja':
                preferred_locale = 'ja'
        elif locale:
            preferred_locale = locale

        # Load playbook with preferred locale (if specified)
        # This allows selecting the correct language version of the file
        from backend.app.services.playbook_service import PlaybookService
        from backend.app.services.mindscape_store import MindscapeStore
        store = MindscapeStore()
        playbook_service = PlaybookService(store=store)
        playbook = await playbook_service.get_playbook(
            playbook_code=base_code,
            locale=preferred_locale
        )


        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")

        user_meta = None
        intent_ids = []
        associated_intents = []
        if intent_ids:
            # Import mindscape store to get intent details
            from ...services.mindscape_store import MindscapeStore
            mindscape_store = MindscapeStore()

            for intent_id in intent_ids:
                try:
                    intent = mindscape_store.get_intent(intent_id)
                    if intent:
                        associated_intents.append({
                            "intent_id": intent.id,
                            "title": intent.title,
                            "status": intent.status.value if intent.status else "active",
                            "priority": intent.priority.value if intent.priority else "medium"
                        })
                except Exception as e:
                    logger.warning(f"Failed to fetch intent {intent_id}: {e}")
                    associated_intents.append({
                        "intent_id": intent_id,
                        "title": f"Intent {intent_id}"
                    })

        default_variant = None
        has_personal_variant = False

        # Get execution status
        active_executions = []
        recent_executions = []
        try:
            from datetime import datetime
            # Import playbook_runner from execution routes (avoid circular import by importing at runtime)
            import sys
            from types import ModuleType

            # Get playbook_runner instance safely
            try:
                execution_module = sys.modules.get('app.routes.core.playbook_execution')
                if execution_module is None:
                    from ...routes.core import playbook_execution as execution_module
                playbook_runner = execution_module.playbook_runner
            except (ImportError, AttributeError):
                # Fallback: create new instance if import fails
                from ...services.playbook_runner import PlaybookRunner
                playbook_runner = PlaybookRunner()

            # Find active executions for this playbook
            active_execution_ids = playbook_runner.list_active_executions()
            for exec_id in active_execution_ids:
                try:
                    conv_manager = playbook_runner.active_conversations.get(exec_id)
                    if conv_manager and conv_manager.playbook.metadata.playbook_code == playbook_code:
                        # Get execution start time from conversation history
                        started_at = None
                        if conv_manager.conversation_history:
                            # Approximate start time from first message
                            started_at = datetime.utcnow().isoformat()
                        active_executions.append({
                            "execution_id": exec_id,
                            "status": "running",
                            "started_at": started_at
                        })
                except Exception as e:
                    logger.debug(f"Failed to get execution info for {exec_id}: {e}")

            # Get recent execution history from events
            from ...services.mindscape_store import MindscapeStore
            mindscape_store = MindscapeStore()
            # Query events for playbook executions
            events = mindscape_store.list_events(
                profile_id=profile_id,
                limit=50
            )
            # Filter for playbook-related events
            for event in events:
                payload = event.payload if isinstance(event.payload, dict) else {}
                # Check if this event is related to this playbook
                if (event.channel == "playbook" and
                    (payload.get("playbook_code") == playbook_code or
                     event.metadata and event.metadata.get("playbook_code") == playbook_code)):
                    recent_executions.append({
                        "execution_id": payload.get("execution_id", event.id),
                        "status": payload.get("status", "completed"),
                        "started_at": event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp),
                        "completed_at": payload.get("completed_at")
                    })
            # Sort by started_at descending and limit
            recent_executions.sort(key=lambda x: x.get("started_at", ""), reverse=True)
            recent_executions = recent_executions[:5]
        except Exception as e:
            logger.warning(f"Failed to fetch execution status: {e}")

        return {
            "metadata": {
                "playbook_code": playbook.metadata.playbook_code,
                "version": playbook.metadata.version,
                "locale": playbook.metadata.locale,
                "name": playbook.metadata.name,
                "description": playbook.metadata.description,
                "tags": playbook.metadata.tags,
                "entry_agent_type": playbook.metadata.entry_agent_type,
                "onboarding_task": playbook.metadata.onboarding_task,
                "icon": playbook.metadata.icon,
                "required_tools": playbook.metadata.required_tools,
                "scope": playbook.metadata.scope,
                "owner": playbook.metadata.owner,
                "capability_code": playbook.metadata.capability_code if hasattr(playbook.metadata, 'capability_code') else None,
            },
            "sop_content": playbook.sop_content,
            "user_notes": playbook.user_notes,
            "user_meta": user_meta or {},
            "associated_intents": associated_intents,
            "execution_status": {
                "active_executions": active_executions,
                "recent_executions": recent_executions[:5]  # Limit to 5 most recent
            },
            "version_info": {
                "has_personal_variant": has_personal_variant,
                "default_variant": default_variant,
                "system_version": playbook.metadata.version
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{playbook_code}/usage-stats", response_model=Dict[str, Any])
async def get_playbook_usage_stats(
    playbook_code: str = Path(..., description="Playbook code")
):
    """
    Get usage statistics for a specific playbook across all workspaces

    Returns statistics including:
    - Total executions
    - Total workspaces using this playbook
    - Per-workspace statistics (execution count, success/failed/running counts, last executed time)
    """
    try:
        stats = executions_store.get_playbook_workspace_stats(playbook_code)
        return stats
    except Exception as e:
        logger.error(f"Failed to get usage stats for playbook {playbook_code}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get usage stats: {str(e)}")


@router.get("/{playbook_code}/ui-layout", response_model=Dict[str, Any])
async def get_playbook_ui_layout(
    playbook_code: str = Path(..., description="Playbook code"),
    profile_id: str = Query("default-user", description="Profile ID")
):
    """
    Get UI layout configuration for a playbook.

    Returns the UI layout config if the playbook has UI components,
    otherwise returns 404.

    The UI layout is returned in both snake_case (ui_layout) and camelCase (uiLayout)
    formats for compatibility.
    """
    try:
        # Remove .en suffix if present
        base_code = playbook_code.replace('.en', '')

        # Load playbook (optional - UI layout can exist without playbook spec)
        # This allows UI-only playbooks that only have UI components, no execution spec
        playbook = await playbook_service.get_playbook(
            playbook_code=base_code,
            locale="zh-TW"
        )

        ui_layout = None

        # Extract capability code (used for both spec and UI directory lookup)
        capability_code = None
        if playbook and hasattr(playbook, 'metadata') and hasattr(playbook.metadata, 'capability_code'):
            capability_code = playbook.metadata.capability_code
        # Fallback: extract from playbook code (format: {capability_code}_{name})
        if not capability_code:
            parts = base_code.split('_')
            if len(parts) > 1:
                capability_code = parts[0]

        # Option 1: Check playbook spec for ui_layout field (snake_case - source of truth)
        # Load playbook.json spec directly
        from ...services.playbook_loaders.json_loader import PlaybookJsonLoader

        playbook_json = PlaybookJsonLoader.load_playbook_json(
            playbook_code=base_code,
            capability_code=capability_code
        )

        if playbook_json:
            # Try snake_case first (JSON spec standard)
            if hasattr(playbook_json, 'ui_layout'):
                ui_layout = playbook_json.ui_layout
            elif hasattr(playbook_json, 'uiLayout'):
                ui_layout = playbook_json.uiLayout
            # Also check if it's a dict (when loaded as dict)
            elif isinstance(playbook_json, dict):
                ui_layout = playbook_json.get('ui_layout') or playbook_json.get('uiLayout')
            # Try accessing via model_dump if it's a Pydantic model
            elif hasattr(playbook_json, 'model_dump'):
                try:
                    playbook_dict = playbook_json.model_dump()
                    ui_layout = playbook_dict.get('ui_layout') or playbook_dict.get('uiLayout')
                except Exception as e:
                    logger.debug(f"Failed to dump playbook_json model: {e}")

        # Option 2: Check capability pack UI directory
        if not ui_layout and capability_code:
            ui_layout = await _load_ui_layout_from_capability(capability_code, base_code)

        # Option 3: If playbook doesn't exist but we have a UI layout file, load it directly
        # This allows UI-only playbooks (playbooks that only have UI, no execution spec)
        if not ui_layout:
            # Try to extract capability code from playbook code
            parts = base_code.split('_')
            if len(parts) > 1:
                potential_capability_code = parts[0]
                ui_layout = await _load_ui_layout_from_capability(potential_capability_code, base_code)

        if not ui_layout:
            raise HTTPException(
                status_code=404,
                detail=f"UI layout not found for playbook {playbook_code}. Checked: playbook spec, capability UI directory"
            )

        # Return UI layout with both snake_case and camelCase for compatibility
        return {
            "playbook_code": base_code,
            "ui_layout": ui_layout,   # source of truth (snake_case)
            "uiLayout": ui_layout,    # backward compatibility (camelCase)
            "version": playbook.metadata.version if playbook and hasattr(playbook, 'metadata') else "1.0.0"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load UI layout for {playbook_code}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


async def _load_ui_layout_from_capability(
    capability_code: str,
    playbook_code: str
) -> Optional[Dict[str, Any]]:
    """
    Load UI layout from capability pack.

    Checks for:
    1. playbook-specific UI layout file: capabilities/{code}/ui/{playbook_code}_layout.json
    2. capability-level UI layout: capabilities/{code}/ui/layout.json

    Uses correct capability installation path from CapabilityInstaller.
    """
    try:
        import json
        from pathlib import Path

        # Use correct capability installation path
        # Capabilities are installed to: backend/app/capabilities/{capability_code}
        backend_dir = Path(__file__).parent.parent.parent.parent
        capabilities_dir = backend_dir / "app" / "capabilities"
        capability_dir = capabilities_dir / capability_code

        if not capability_dir.exists():
            logger.debug(f"Capability directory not found: {capability_dir}")
            return None

        # Try playbook-specific layout first
        ui_dir = capability_dir / "ui"
        if ui_dir.exists():
            playbook_layout_path = ui_dir / f"{playbook_code}_layout.json"
            if playbook_layout_path.exists():
                with open(playbook_layout_path, 'r', encoding='utf-8') as f:
                    layout = json.load(f)
                    logger.info(f"Loaded UI layout from {playbook_layout_path}")
                    return layout

            # Fallback to capability-level layout
            capability_layout_path = ui_dir / "layout.json"
            if capability_layout_path.exists():
                with open(capability_layout_path, 'r', encoding='utf-8') as f:
                    layout = json.load(f)
                    logger.info(f"Loaded UI layout from {capability_layout_path}")
                    return layout

        return None
    except Exception as e:
        logger.warning(f"Failed to load UI layout from capability {capability_code}: {e}")
        return None


@router.patch("/{playbook_code}/meta", response_model=Dict[str, Any])
async def update_playbook_meta(
    playbook_code: str,
    profile_id: str = Query('default-user'),
    favorite: Optional[bool] = None,
    hidden: Optional[bool] = None,
    custom_tags: Optional[List[str]] = None,
    user_notes: Optional[str] = None
):
    """Update user's personal meta for a playbook"""
    try:
        # Check playbook exists via PlaybookService
        playbook = await playbook_service.get_playbook(playbook_code)
        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")

        updates = {}
        if favorite is not None:
            updates['favorite'] = favorite
        if hidden is not None:
            updates['hidden'] = hidden
        if custom_tags is not None:
            updates['custom_tags'] = custom_tags

        # Update user_meta
        user_meta = mindscape_store.update_user_meta(profile_id, playbook_code, updates)

        # Update user_notes (in playbooks table)
        if user_notes is not None:
            store.update_playbook(playbook_code, {'user_notes': user_notes})

        return {
            "success": True,
            "user_meta": user_meta
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reindex", response_model=Dict[str, Any])
async def reindex_playbooks():
    """Re-scan and index all playbooks from file system"""
    try:
        # Invalidate all playbook caches to force reload
        playbook_service.registry.invalidate_cache()

        # Force reload by clearing the _loaded flag
        playbook_service.registry._loaded = False

        # Trigger reload by calling list_playbooks
        await playbook_service.registry._ensure_loaded()

        # Count playbooks by capability
        all_playbooks = await playbook_service.list_playbooks()
        capability_counts: Dict[str, int] = {}
        for playbook in all_playbooks:
            cap = playbook.capability_code or 'none'
            capability_counts[cap] = capability_counts.get(cap, 0) + 1

        results = {
            "message": "Playbooks reindexed successfully",
            "total_playbooks": len(all_playbooks),
            "capability_distribution": capability_counts
        }
        return results
    except Exception as e:
        logger.error(f"Failed to reindex playbooks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=Playbook, status_code=201)
async def create_playbook(request: CreatePlaybookRequest):
    """Create a new playbook"""
    try:
        from ...models.playbook import PlaybookMetadata
        from datetime import datetime

        playbook = Playbook(
            metadata=PlaybookMetadata(
                playbook_code=request.playbook_code,
                name=request.name,
                description=request.description,
                tags=request.tags,
                owner=request.owner,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            ),
            sop_content=request.sop_content
        )

        raise HTTPException(status_code=501, detail="Create playbook not yet implemented in PlaybookService")
        return created

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create playbook: {str(e)}")


@router.put("/{playbook_code}", response_model=Playbook)
async def update_playbook(
    playbook_code: str = Path(..., description="Playbook code"),
    request: UpdatePlaybookRequest = None
):
    """Update a playbook"""
    if not request:
        raise HTTPException(status_code=400, detail="Update request required")

    updates = {}
    if request.name is not None:
        updates['name'] = request.name
    if request.description is not None:
        updates['description'] = request.description
    if request.tags is not None:
        updates['tags'] = request.tags
    if request.sop_content is not None:
        updates['sop_content'] = request.sop_content
    if request.user_notes is not None:
        updates['user_notes'] = request.user_notes

        raise HTTPException(status_code=501, detail="Update playbook not yet implemented in PlaybookService")
    if not updated:
        raise HTTPException(status_code=404, detail="Playbook not found")

    return updated


@router.post("/{playbook_code}/associate/{intent_id}", status_code=201)
async def associate_intent_playbook(
    playbook_code: str = Path(..., description="Playbook code"),
    intent_id: str = Path(..., description="Intent ID")
):
    """Associate an intent with a playbook"""
    try:
        association = store.associate_intent_playbook(intent_id, playbook_code)
        return {
            "intent_id": association.intent_id,
            "playbook_code": association.playbook_code,
            "message": "Association created"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create association: {str(e)}")


@router.delete("/{playbook_code}/associate/{intent_id}", status_code=204)
async def remove_intent_playbook_association(
    playbook_code: str = Path(..., description="Playbook code"),
    intent_id: str = Path(..., description="Intent ID")
):
    """Remove association between intent and playbook"""
    success = store.remove_intent_playbook_association(intent_id, playbook_code)
    if not success:
        raise HTTPException(status_code=404, detail="Association not found")
    return None


@router.get("/intent/{intent_id}", response_model=List[str])
async def get_intent_playbooks(intent_id: str = Path(..., description="Intent ID")):
    """Get playbook codes associated with an intent"""
    playbook_codes = store.get_intent_playbooks(intent_id)
    return playbook_codes


@router.get("/{playbook_code}/tools/check", response_model=Dict[str, Any])
async def check_playbook_tools(
    playbook_code: str = Path(..., description="Playbook code"),
    profile_id: str = Query('default-user', description="User profile ID")
):
    """
    Check playbook tool dependencies and availability

    Returns:
        {
            "playbook_code": "...",
            "tools": {
                "available": [...],
                "missing": [...],
                "can_auto_install": [...]
            }
        }
    """
    try:
        # Get playbook via PlaybookService
        playbook = await playbook_service.get_playbook(playbook_code)
        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")

        # Check tool dependencies
        from ...services.playbook_tool_resolver import ToolDependencyResolver

        resolver = ToolDependencyResolver()
        result = await resolver.resolve_dependencies(
            playbook.metadata.tool_dependencies
        )

        return {
            "playbook_code": playbook_code,
            "tools": {
                "available": result["available"],
                "missing": result["missing"],
                "can_auto_install": result["can_auto_install"],
                "errors": result["errors"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking playbook tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{playbook_code}/tools/install", response_model=Dict[str, Any])
async def install_playbook_tools(
    playbook_code: str = Path(..., description="Playbook code"),
    profile_id: str = Query('default-user', description="User profile ID")
):
    """
    Auto-install tools required by Playbook

    Returns:
        {
            "success": bool,
            "installed": [...],
            "failed": [...],
            "message": "..."
        }
    """
    try:
        # Get playbook via PlaybookService
        playbook = await playbook_service.get_playbook(playbook_code)
        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")

        # Parse dependencies
        from ...services.playbook_tool_resolver import ToolDependencyResolver

        resolver = ToolDependencyResolver()
        check_result = await resolver.resolve_dependencies(
            playbook.metadata.tool_dependencies
        )

        # If no missing tools, return directly
        if not check_result["missing"]:
            return {
                "success": True,
                "installed": [],
                "failed": [],
                "available": check_result["available"],
                "message": "All tools are already available"
            }

        # Try to auto-install installable tools
        installed = []
        failed = []

        for tool_dep in playbook.metadata.tool_dependencies:
            # Check if in can_auto_install list
            can_install = any(
                t["name"] == tool_dep.name
                for t in check_result["can_auto_install"]
            )

            if can_install:
                try:
                    install_result = await resolver.auto_install_tool(tool_dep)
                    if install_result["success"]:
                        installed.append({
                            "name": tool_dep.name,
                            "type": tool_dep.type
                        })
                        logger.info(f"Successfully installed tool: {tool_dep.name}")
                    else:
                        failed.append({
                            "name": tool_dep.name,
                            "type": tool_dep.type,
                            "error": install_result["error"]
                        })
                        logger.error(f"Failed to install tool {tool_dep.name}: {install_result['error']}")
                except Exception as e:
                    failed.append({
                        "name": tool_dep.name,
                        "type": tool_dep.type,
                        "error": str(e)
                    })
                    logger.error(f"Exception installing tool {tool_dep.name}: {e}")

        # Check if there are still required tools missing
        still_missing = [
            t for t in check_result["missing"]
            if t["required"] and t["name"] not in [i["name"] for i in installed]
        ]

        if still_missing:
            return {
                "success": False,
                "installed": installed,
                "failed": failed,
                "still_missing": still_missing,
                "message": "Some required tools could not be installed"
            }

        return {
            "success": True,
            "installed": installed,
            "failed": failed,
            "available": check_result["available"],
            "message": f"Successfully installed {len(installed)} tool(s)"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error installing playbook tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{playbook_code}/tools-check", response_model=Dict[str, Any])
async def check_playbook_tools(
    playbook_code: str = Path(..., description="Playbook code"),
    profile_id: str = Query('default-user', description="Profile ID")
):
    """
    Check playbook tool dependencies and readiness

    Returns readiness status based on tool connection status:
    - ready: All required tools are connected
    - needs_setup: One or more required tools are registered_but_not_connected
    - unsupported: One or more required tools are unavailable

    Example:
        GET /api/v1/playbooks/content_drafting/tools-check?profile_id=user123
    """
    try:
        # Get playbook
        playbook = loader.get_playbook_by_code(playbook_code)
        if not playbook:
            playbook = store.get_playbook(playbook_code)
        if not playbook:
            raise HTTPException(status_code=404, detail=f"Playbook not found: {playbook_code}")

        # Initialize services
        data_dir = os.getenv("DATA_DIR", "./data")
        tool_registry = ToolRegistryService(data_dir=data_dir)
        tool_status_checker = ToolStatusChecker(tool_registry)
        playbook_tool_checker = PlaybookToolChecker(tool_status_checker)

        # Check tool dependencies
        readiness, tool_statuses, missing_required = playbook_tool_checker.check_playbook_tools(
            playbook=playbook,
            profile_id=profile_id
        )

        # Extract required tools for response
        required_tools = playbook_tool_checker._extract_required_tools(playbook.metadata)

        return {
            "playbook_code": playbook_code,
            "readiness_status": readiness.value,
            "tool_statuses": {
                tool_type: status.value
                for tool_type, status in tool_statuses.items()
            },
            "missing_required_tools": missing_required,
            "required_tools": required_tools,
            "optional_tools": playbook.metadata.optional_tools
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking playbook tools: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/smoke-test/supported", response_model=List[str])
async def get_supported_smoke_test_playbooks():
    """
    Get list of playbooks that support smoke testing

    Returns a list of playbook codes that have smoke tests available.
    """
    return [
        "pdf_ocr_processing",
        "ig_post_generation",
        "yt_script_generation",
        "yearly_book_content_save",
    ]


@router.post("/{playbook_code}/smoke-test/upload-files", response_model=Dict[str, Any])
async def upload_test_files(
    playbook_code: str,
    files: List[UploadFile] = File(...),
    profile_id: str = Query('test-user', description="Profile ID for testing")
):
    """
    Upload test files for playbook smoke test

    This endpoint allows uploading test files (e.g., PDFs) that will be saved
    to the test data directory and used for smoke testing.
    """
    from pathlib import Path
    import shutil

    try:
        # Determine test data directory
        backend_dir = Path(__file__).parent.parent
        test_data_dir = backend_dir.parent / "test_data"

        # Create playbook-specific directory
        playbook_test_dir = test_data_dir / playbook_code
        playbook_test_dir.mkdir(parents=True, exist_ok=True)

        uploaded_files = []

        for file in files:
            # Generate safe filename
            filename = file.filename or "uploaded_file"
            # Add timestamp to avoid conflicts
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{filename}"
            file_path = playbook_test_dir / safe_filename

            # Save file
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            uploaded_files.append({
                "original_filename": filename,
                "saved_path": str(file_path),
                "size": file_path.stat().st_size
            })

            logger.info(f"Uploaded test file: {filename} -> {file_path}")

        return {
            "playbook_code": playbook_code,
            "uploaded_files": uploaded_files,
            "test_data_dir": str(playbook_test_dir),
            "message": f"Successfully uploaded {len(uploaded_files)} file(s)"
        }

    except Exception as e:
        logger.error(f"Error uploading test files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload files: {str(e)}")


@router.post("/{playbook_code}/smoke-test", response_model=Dict[str, Any])
async def run_playbook_smoke_test(
    playbook_code: str,
    profile_id: str = Query('test-user', description="Profile ID for testing"),
    use_uploaded_files: bool = Query(False, description="Use files uploaded via upload-files endpoint")
):
    """
    Run smoke test for a specific playbook

    This endpoint runs a quick smoke test to verify the playbook works correctly.
    Returns test results including status, outputs, and any errors.
    """
    # Map playbook codes to test classes - check early before any imports
    test_class_map = {
        "pdf_ocr_processing": "TestPdfOcrProcessing",
        "ig_post_generation": "TestIgPostGeneration",
        "yt_script_generation": "TestYtScriptGeneration",
        "yearly_book_content_save": "TestYearlyBookContentSave",
    }

    # Check if playbook has smoke test - return 404 immediately if not
    if playbook_code not in test_class_map:
        raise HTTPException(
            status_code=404,
            detail=f"Smoke test not available for playbook: {playbook_code}. Available playbooks: {', '.join(test_class_map.keys())}"
        )

    try:
        # Import test runner dynamically to avoid circular imports
        import sys
        from pathlib import Path

        # Add tests directory to path
        backend_dir = Path(__file__).parent.parent
        tests_dir = backend_dir.parent / "tests"
        if str(tests_dir) not in sys.path:
            sys.path.insert(0, str(tests_dir))

        # Import and run test
        try:
            if playbook_code == "pdf_ocr_processing":
                from tests.test_playbook_pdf_ocr_processing import TestPdfOcrProcessing
                test_class = TestPdfOcrProcessing
            elif playbook_code == "ig_post_generation":
                from tests.test_playbook_ig_post_generation import TestIgPostGeneration
                test_class = TestIgPostGeneration
            elif playbook_code == "yt_script_generation":
                from tests.test_playbook_yt_script_generation import TestYtScriptGeneration
                test_class = TestYtScriptGeneration
            elif playbook_code == "yearly_book_content_save":
                from tests.test_playbook_yearly_book_content_save import TestYearlyBookContentSave
                test_class = TestYearlyBookContentSave
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Test class not found for playbook: {playbook_code}"
                )

            # Create test instance
            test = test_class(profile_id=profile_id)

            # If using uploaded files, update test inputs
            if use_uploaded_files and playbook_code == "pdf_ocr_processing":
                # Find uploaded PDF files
                backend_dir = Path(__file__).parent.parent
                test_data_dir = backend_dir.parent / "test_data"
                playbook_test_dir = test_data_dir / playbook_code

                if playbook_test_dir.exists():
                    pdf_files = list(playbook_test_dir.glob("*.pdf"))
                    if pdf_files:
                        # Override test inputs with uploaded files
                        # Note: Use absolute paths inside Docker container
                        def get_test_inputs_with_uploaded():
                            # Convert to Docker container paths if needed
                            docker_paths = []
                            for f in pdf_files[:2]:
                                # If file is in test_data, use /app/backend/test_data path
                                if str(f).startswith(str(test_data_dir)):
                                    rel_path = f.relative_to(test_data_dir)
                                    docker_path = f"/app/backend/test_data/{playbook_code}/{rel_path.name}"
                                else:
                                    docker_path = str(f)
                                docker_paths.append(docker_path)
                            return {
                                "pdf_files": docker_paths,
                                "dpi": 300,
                                "output_format": "text"
                            }
                        test.get_test_inputs = get_test_inputs_with_uploaded

            result = await test.run_test()

            return {
                "playbook_code": playbook_code,
                "test_status": result.get("status", "unknown"),
                "test_results": result,
                "summary": test.get_test_summary()
            }

        except ImportError as e:
            logger.error(f"Failed to import test class: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to import test class: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Test execution failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Test execution failed: {str(e)}"
            )

    except HTTPException as he:
        # Re-raise HTTPException as-is (includes 404 for unsupported playbooks)
        raise he
    except Exception as e:
        logger.error(f"Error running smoke test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
