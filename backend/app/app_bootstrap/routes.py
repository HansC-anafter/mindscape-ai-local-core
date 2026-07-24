import logging
import os
from fastapi import FastAPI

# Kernel routes
from backend.app.routes.core import (
    workspace,
    playbook,
    playbook_execution,
    config,
    tools,
    sandbox,
    blueprint,
    lens,
    composition,
    surface,
)
from backend.app.routes.core import cloud_sync
from backend.app.routes.core.intents import router as intents_router
from backend.app.routes.core.chapters import router as chapters_router
from backend.app.routes.core.artifacts import router as artifacts_router
from backend.app.routes.core.resources import router as resources_router
from backend.app.routes.core.host_services import router as host_services_router
from backend.app.routes.core.host_resources import router as host_resources_router
from backend.app.routes.core.resource_governance import router as resource_governance_router
from backend.app.routes.core.system_settings import router as system_settings_router
from backend.app.routes.core.settings_extensions import router as settings_extensions_router
from backend.app.routes.core.model_route_registry import (
    router as model_route_registry_router,
)
from backend.app.routes.core.workspace_runtime_config import (
    router as workspace_runtime_config_router,
)
from backend.app.routes.core.runtime_environments import router as runtime_environments_router
from backend.app.routes.core.data_sources import router as data_sources_router
from backend.app.routes.core.workspace_resource_bindings import (
    router as workspace_resource_bindings_router,
)
from backend.app.routes.core.cloud_providers import router as cloud_providers_router
from backend.app.routes.core import deployment
from backend.app.routes.core.unsplash_fingerprints import router as unsplash_fingerprints_router
from backend.app.routes.mind_lens_graph import router as graph_router
from backend.app.routes.lens import router as lens_unified_router

# Core primitives
from backend.app.routes.core import (
    vector_db,
    vector_search,
    capability_packs,
    capability_suites,
)

# Feature routes loaded via pack registry
from backend.app.core.pack_registry import load_and_register_packs
from backend.app.services.capability_reload_manager import (
    hot_reload_enabled,
    reload_capability_routes,
)
from backend.app.services.capability_api_loader import (
    activate_capability_api_code,
    get_capability_api_activation_policy,
    get_capability_api_startup_activation_allowlist,
    group_capability_api_descriptors,
    load_manifest_for_descriptor,
    seed_capability_api_descriptors,
)
from backend.app.app_bootstrap.startup_seeded_activation import (
    record_startup_seeded_activation_pending,
)
from backend.app.app_bootstrap.runtime_route_modules import register_runtime_route_modules
from backend.app.app_bootstrap.workspace_product_routes import (
    register_workspace_product_routes,
)
from backend.app.app_bootstrap.deployment_control_routes import (
    register_deployment_control_routes,
)
from app.services.pack_activation_service import PackActivationService

logger = logging.getLogger(__name__)

def _capability_hot_reload_enabled() -> bool:
    return hot_reload_enabled()

def register_core_routes(app: FastAPI) -> None:
    """Register kernel routes"""
    app.include_router(workspace.router, tags=["workspace"])
    # Workspace groups (independent resource: /api/v1/workspace-groups)
    from backend.app.routes.core.workspace.groups import router as workspace_groups_router
    from backend.app.routes.core.knowledge_foundation import router as knowledge_foundation_router

    app.include_router(workspace_groups_router, tags=["workspace-groups"])
    app.include_router(knowledge_foundation_router, tags=["knowledge-foundation"])
    register_workspace_product_routes(app)
    register_deployment_control_routes(app)
    app.include_router(playbook.router, tags=["playbook"])
    app.include_router(playbook_execution.router, tags=["playbook"])
    try:
        from backend.app.routes.core.remote_execution_callbacks import (
            router as remote_execution_callbacks_router,
        )

        app.include_router(remote_execution_callbacks_router, tags=["remote-execution"])
        logger.info("Remote execution callback routes registered")
    except Exception as e:
        logger.warning(f"Failed to register remote execution callback routes: {e}")
    app.include_router(config.router, tags=["config"])
    app.include_router(system_settings_router, tags=["system"])
    app.include_router(settings_extensions_router)
    app.include_router(model_route_registry_router)
    app.include_router(runtime_environments_router, tags=["runtime-environments"])
    app.include_router(
        workspace_runtime_config_router, tags=["workspace-runtime-config"]
    )

    try:
        from backend.app.routes.core.runtime_source_identity import (
            router as runtime_source_identity_router,
        )

        app.include_router(runtime_source_identity_router, tags=["runtime"])
        logger.info("Runtime source identity routes registered")
    except Exception as e:
        logger.warning(f"Failed to register runtime source identity routes: {e}")

    # Runtime proxy routes (proxied external runtime settings)
    try:
        from backend.app.routes.core.runtime_proxy import router as runtime_proxy_router

        app.include_router(runtime_proxy_router, tags=["runtime-proxy"])
        logger.info("Runtime Proxy routes registered")
    except Exception as e:
        logger.debug(f"Runtime Proxy routes not registered: {e}")

    # Runtime OAuth routes (OAuth2 authorization flow)
    try:
        from backend.app.routes.core.runtime_oauth import router as runtime_oauth_router

        app.include_router(runtime_oauth_router, tags=["runtime-oauth"])
        logger.info("Runtime OAuth routes registered")
    except Exception as e:
        logger.debug(f"Runtime OAuth routes not registered: {e}")

    # CLI token endpoint (GCA auth token for bridge processes)
    try:
        from backend.app.routes.core.cli_token import router as cli_token_router

        app.include_router(cli_token_router, tags=["auth"])
        logger.info("CLI token routes registered")
    except Exception as e:
        logger.debug(f"CLI token routes not registered: {e}")

    # GCA Pool API (multi-account pool management and quota reporting)
    try:
        from backend.app.routes.core.gca_pool_api import router as gca_pool_router

        app.include_router(gca_pool_router, tags=["gca-pool"])
        logger.info("GCA Pool API routes registered")
    except Exception as e:
        logger.debug(f"GCA Pool API routes not registered: {e}")

    app.include_router(tools.router, tags=["tools"])
    app.include_router(sandbox.router, tags=["sandboxes"])
    app.include_router(deployment.router, tags=["deployment"])
    app.include_router(data_sources_router, tags=["data-sources"])
    app.include_router(lens.router, tags=["lenses"])
    app.include_router(composition.router, tags=["compositions"])
    app.include_router(surface.router, tags=["surface"])

    # Dashboard routes
    from backend.app.routes.core.dashboard import router as dashboard_router

    app.include_router(dashboard_router, tags=["dashboard"])

    # Skills listing routes (agent skills + capability pack skills)
    try:
        from backend.app.routes.core.skills import router as skills_router

        app.include_router(skills_router, tags=["skills"])
        logger.info("Skills listing routes registered")
    except Exception as e:
        logger.debug(f"Skills listing routes not registered: {e}")

    # Meeting session routes (Phase 2 - pipeline unification)
    try:
        from backend.app.routes.meeting_sessions import router as meeting_sessions_router

        app.include_router(meeting_sessions_router, tags=["meeting-sessions"])
        logger.info("Meeting session routes registered")
    except Exception as e:
        logger.debug(f"Meeting session routes not registered: {e}")

    # Admin reload routes (pre-restart validation, reload trigger)
    try:
        from backend.app.routes.core.admin_reload import router as admin_reload_router

        app.include_router(admin_reload_router, tags=["admin"])
        logger.info("Admin reload routes registered")
    except Exception as e:
        logger.warning(f"Failed to register admin reload routes: {e}")

    try:
        from backend.app.routes.core.admin_pack_activation import (
            router as admin_pack_activation_router,
        )

        app.include_router(admin_pack_activation_router, tags=["admin"])
        logger.info("Admin capability runtime activation routes registered")
    except Exception as e:
        logger.warning(f"Failed to register admin capability runtime activation routes: {e}")

    if not _capability_hot_reload_enabled():
        try:
            from backend.app.services.capability_api_loader import (
                activate_seeded_capability_apis,
            )

            allowlist_env = os.getenv("CAPABILITY_ALLOWLIST")
            allowlist = allowlist_env.split(",") if allowlist_env else None
            descriptors = seed_capability_api_descriptors(
                app=app, allowlist=allowlist, enable_all=False
            )
            activation_policy = get_capability_api_activation_policy()
            activation_service = PackActivationService()

            if activation_policy == "startup_eager":
                capability_routers = activate_seeded_capability_apis(
                    app=app,
                    descriptors=descriptors,
                    allowlist=allowlist,
                    enable_all=False,
                    activation_mode="startup_eager",
                    activation_service=activation_service,
                )
                if allowlist:
                    logger.info(
                        "Seeded %d capability API descriptors and activated %d routers (policy=%s, allowlist=%s)",
                        len(descriptors),
                        len(capability_routers),
                        activation_policy,
                        allowlist,
                    )
                else:
                    logger.info(
                        "Seeded %d capability API descriptors and activated %d routers (policy=%s)",
                        len(descriptors),
                        len(capability_routers),
                        activation_policy,
                    )
            else:
                grouped = group_capability_api_descriptors(descriptors)
                for descriptor_group in grouped.values():
                    if not descriptor_group:
                        continue
                    descriptor = descriptor_group[0]
                    record_startup_seeded_activation_pending(
                        activation_service=activation_service,
                        pack_id=descriptor.capability_code,
                        manifest=load_manifest_for_descriptor(descriptor),
                        manifest_path=descriptor.manifest_path
                        if descriptor.manifest_path.exists()
                        else None,
                    )
                startup_activation_allowlist = (
                    get_capability_api_startup_activation_allowlist()
                )
                eagerly_activated_count = 0
                for capability_code in startup_activation_allowlist:
                    activated_routers = activate_capability_api_code(
                        app=app,
                        capability_code=capability_code,
                        activation_mode="startup_seed_only_allowlist",
                        activation_service=activation_service,
                    )
                    eagerly_activated_count += len(activated_routers)
                if allowlist:
                    logger.info(
                        "Seeded %d capability API descriptors without activation (policy=%s, allowlist=%s, startup_activation_allowlist=%s, eagerly_activated_routers=%d)",
                        len(descriptors),
                        activation_policy,
                        allowlist,
                        startup_activation_allowlist,
                        eagerly_activated_count,
                    )
                else:
                    logger.info(
                        "Seeded %d capability API descriptors without activation (policy=%s, startup_activation_allowlist=%s, eagerly_activated_routers=%d)",
                        len(descriptors),
                        activation_policy,
                        startup_activation_allowlist,
                        eagerly_activated_count,
                    )
        except Exception as e:
            logger.error(
                f"Failed to seed/activate cloud capability API routers: {e}",
                exc_info=True,
            )
    else:
        logger.info(
            "Capability hot reload enabled; capability API routers will be loaded via reload manager."
        )

    app.include_router(
        workspace_resource_bindings_router, tags=["workspace-resource-bindings"]
    )
    app.include_router(cloud_providers_router, tags=["cloud-providers"])
    app.include_router(cloud_sync.router, tags=["cloud-sync"])
    app.include_router(graph_router, tags=["graph"])
    app.include_router(lens_unified_router, tags=["lens-unified"])

    # Story Thread proxy routes (optional - requires Cloud API configuration)
    try:
        from backend.app.routes.core.story_thread import router as story_thread_router

        app.include_router(story_thread_router, tags=["story-threads"])
        logger.info("Story Thread proxy routes registered")
    except Exception as e:
        logger.debug(f"Story Thread proxy routes not registered: {e}")

    # Cloud navigation proxy routes (optional - requires Cloud frontend configuration)
    try:
        from backend.app.routes.core.cloud_navigation import router as cloud_navigation_router

        app.include_router(cloud_navigation_router, tags=["cloud-navigation"])
        logger.info("Cloud navigation proxy routes registered")
    except Exception as e:
        logger.debug(f"Cloud navigation proxy routes not registered: {e}")

    app.include_router(blueprint.router, tags=["blueprints"])
    app.include_router(unsplash_fingerprints_router)

    # Generic resource routes (neutral interface)
    app.include_router(resources_router, tags=["resources"])
    app.include_router(host_services_router)
    app.include_router(host_resources_router)
    app.include_router(resource_governance_router)

    # Legacy specific routes (kept for backward compatibility, will be deprecated)
    app.include_router(intents_router, tags=["intents"])
    app.include_router(chapters_router, tags=["chapters"])
    app.include_router(artifacts_router, tags=["artifacts"])

    # Content Vault indexing routes
    from backend.app.routes.core.content_vault_index import router as content_vault_index_router

    app.include_router(content_vault_index_router, tags=["content-vault"])

    # Decision cards routes
    from backend.app.routes.core import decision_cards as decision_cards_router

    app.include_router(decision_cards_router.router, tags=["decision-cards"])

    # Handoff bundle routes (signed bundle packaging / intake)
    from backend.app.routes.core.handoff_bundles import router as handoff_bundles_router

    app.include_router(handoff_bundles_router, tags=["handoff-bundles"])

    # MCP Bridge routes (optional - requires mcp_bridge module)
    try:
        from backend.app.routes.mcp_bridge import router as mcp_bridge_router

        app.include_router(mcp_bridge_router, tags=["mcp-bridge"])
        logger.info("MCP Bridge routes registered")
    except Exception as e:
        logger.debug(f"MCP Bridge routes not registered: {e}")

    # Agent dispatch routes (WebSocket + REST polling task dispatch to IDE agents)
    try:
        from backend.app.routes.agent_dispatch import router as agent_dispatch_router

        app.include_router(agent_dispatch_router, tags=["agent-dispatch"])
        logger.info("Agent dispatch routes registered")
    except Exception as e:
        logger.debug(f"Agent dispatch routes not registered: {e}")

    register_runtime_route_modules(app)

    # Device Node WebSocket + HTTP routes (host sidecar communication)
    try:
        from backend.app.routes.device_node import router as device_node_router

        app.include_router(device_node_router, prefix="/api/v1", tags=["device-node"])
        logger.info("Device Node routes registered")
    except Exception as e:
        logger.debug(f"Device Node routes not registered: {e}")

    # Agent Registry API routes (agent listing and availability)
    try:
        from backend.app.routes.core.agents import router as agents_router

        app.include_router(agents_router, tags=["agents"])
        logger.info("Agent Registry API routes registered")
    except Exception as e:
        logger.warning(f"Failed to register Agent Registry API routes: {e}")

    # Workspace-scoped agent availability (per-workspace WS check)
    try:
        from backend.app.routes.core.workspace_agents import router as workspace_agents_router

        app.include_router(workspace_agents_router, tags=["workspace-agents"])
        logger.info("Workspace Agent Availability routes registered")
    except Exception as e:
        logger.warning(f"Failed to register Workspace Agent routes: {e}")

    # Workspace Agent Configuration routes (preferred agent, sandbox config)
    try:
        from backend.app.routes.core.workspace_doer import router as workspace_doer_router

        app.include_router(workspace_doer_router, tags=["workspace-agents"])
        logger.info("Workspace Agent Configuration routes registered")
    except Exception as e:
        logger.warning(f"Failed to register Workspace Agent Configuration routes: {e}")


def register_core_primitives(app: FastAPI) -> None:
    """Register core primitives"""
    app.include_router(vector_db.router, tags=["vector-db"])
    app.include_router(vector_search.router, tags=["vector-search"])
    app.include_router(capability_packs.router, tags=["capability-packs"])
    app.include_router(capability_suites.router, tags=["capability-suites"])
    # Install endpoints (extracted from capability_packs for maintainability)
    try:
        from backend.app.routes.core import capability_install

        app.include_router(capability_install.router, tags=["capability-packs"])
    except Exception as e:
        logger.warning(f"Failed to load capability_install router: {e}")
    # Lazy import capability_installation to avoid startup issues
    try:
        from backend.app.routes.core import capability_installation

        app.include_router(
            capability_installation.router, tags=["capability-installation"]
        )
    except Exception as e:
        logger.warning(f"Failed to load capability_installation router: {e}")


def initialize_feature_packs(app: FastAPI) -> None:
    """Initialize pack routes and capability APIs."""
    try:
        if _capability_hot_reload_enabled():
            reload_capability_routes(app, reason="startup")
        else:
            load_and_register_packs(
                app,
                activation_service=PackActivationService(),
                activation_mode="startup_feature_pack",
            )
    except Exception as e:
        logger.warning(
            f"Failed to load some feature packs during startup: {e}. App will continue to start."
        )


def register_all_routes(app: FastAPI) -> None:
    """Entrypoint for all route registration."""
    register_core_routes(app)
    register_core_primitives(app)
    initialize_feature_packs(app)

    # Manually register mindscape routes (if not loaded via pack registry)
    try:
        from backend.features.mindscape.routes import router as mindscape_router

        app.include_router(mindscape_router, prefix="/api/v1/mindscape", tags=["mindscape"])
        logger.info("Registered mindscape routes manually")
    except Exception as e:
        logger.warning(f"Failed to register mindscape routes: {e}", exc_info=True)

    # Register execution-graph routes (workspace execution flow visualization)
    try:
        from backend.features.workspace.execution_graph import (
            router as execution_graph_router,
        )
        from backend.app.routes.execution_graph_changelog import (
            router as graph_changelog_router,
        )

        app.include_router(execution_graph_router, tags=["execution-graph"])
        app.include_router(graph_changelog_router, tags=["execution-graph-changelog"])
        logger.info("Registered execution-graph routes")
    except Exception as e:
        logger.warning(f"Failed to register execution-graph routes: {e}", exc_info=True)
