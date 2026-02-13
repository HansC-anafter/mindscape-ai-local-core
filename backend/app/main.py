"""
My Agent Console - Backend API
FastAPI application for personal AI agent platform
"""

import os
import signal
import faulthandler
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging
import uvicorn

# Kernel routes
from .routes.core import (
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
from .routes.core import cloud_sync
from .routes.core.intents import router as intents_router
from .routes.core.chapters import router as chapters_router
from .routes.core.artifacts import router as artifacts_router
from .routes.core.resources import router as resources_router
from .routes.core.system_settings import router as system_settings_router
from .routes.core.settings_extensions import router as settings_extensions_router
from .routes.core.runtime_environments import router as runtime_environments_router
from .routes.core.data_sources import router as data_sources_router
from .routes.core.workspace_resource_bindings import (
    router as workspace_resource_bindings_router,
)
from .routes.core.cloud_providers import router as cloud_providers_router
from .routes.core import deployment
from .routes.core.unsplash_fingerprints import router as unsplash_fingerprints_router
from .routes.mind_lens_graph import router as graph_router
from .routes.lens import router as lens_unified_router

# Core primitives
from .routes.core import (
    vector_db,
    vector_search,
    capability_packs,
    capability_suites,
)

# capability_installation imported lazily to avoid startup issues

# Feature routes loaded via pack registry
from .core.pack_registry import load_and_register_packs
from .core.security import security_monitor, auth_manager
from .init_db import init_mindscape_tables
from .capabilities.registry import load_capabilities
from .services.capability_reload_manager import (
    hot_reload_enabled,
    reload_capability_routes,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _capability_hot_reload_enabled() -> bool:
    return hot_reload_enabled()


def _enable_usr1_faulthandler():
    if not (os.getenv("PYTHONFAULTHANDLER") or os.getenv("ENABLE_FAULTHANDLER")):
        return
    try:
        faulthandler.enable()
        faulthandler.register(signal.SIGUSR1, all_threads=True)
        faulthandler.register(signal.SIGUSR2, all_threads=True)
        logger.info("Faulthandler enabled: SIGUSR1/SIGUSR2 will dump stack traces.")
    except Exception:
        logger.exception("Failed to enable faulthandler.")


_enable_usr1_faulthandler()

# Create FastAPI app
app = FastAPI(
    title="My Agent Console API",
    description="Personal AI agent platform with mindscape management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

if os.getenv("PYTHONFAULTHANDLER") or os.getenv("ENABLE_FAULTHANDLER"):

    @app.post("/debug/dump-stacks")
    async def _dump_stacks():
        faulthandler.dump_traceback(all_threads=True)
        return {"ok": True}


# CORS middleware - MUST be first middleware (before TrustedHostMiddleware)
# This ensures CORS headers are added to all responses, including error responses
# Dynamically get CORS allowed origins from port config service
def get_cors_origins():
    """Get CORS allowed origins from port config service"""
    try:
        from .services.port_config_service import port_config_service
        import os

        # Get current scope from environment variables or config
        current_cluster = os.getenv("CLUSTER_NAME")
        current_env = os.getenv("ENVIRONMENT")
        current_site = os.getenv("SITE_NAME")

        # Get frontend URL (automatically read hostname and port from config)
        frontend_url = port_config_service.get_service_url(
            "frontend",
            cluster=current_cluster,
            environment=current_env,
            site=current_site,
        )
        port_config = port_config_service.get_port_config(
            cluster=current_cluster, environment=current_env, site=current_site
        )
        host_config = port_config_service.get_host_config()

        # Build CORS allowed origins (automatically read hostname from config)
        allow_origins = [frontend_url]

        # If frontend hostname is not localhost, also add 127.0.0.1 variant
        if "localhost" in frontend_url:
            allow_origins.append(frontend_url.replace("localhost", "127.0.0.1"))

        # Add Cloud API if configured
        if port_config.cloud_api and host_config.cloud_api_host:
            cloud_api_url = port_config_service.get_service_url(
                "cloud_api",
                cluster=current_cluster,
                environment=current_env,
                site=current_site,
            )
            allow_origins.append(cloud_api_url)
            if "localhost" in cloud_api_url:
                allow_origins.append(cloud_api_url.replace("localhost", "127.0.0.1"))

        # Add other origins from CORS config if configured
        if host_config.cors_origins:
            allow_origins.extend(host_config.cors_origins)

        return allow_origins
    except Exception as e:
        logger.warning(
            f"Failed to get CORS origins from port config service, using defaults: {e}"
        )
        # Fallback to default values (backward compatibility)
        return [
            "http://localhost:8300",  # New default frontend port
            "http://127.0.0.1:8300",
            "http://localhost:3000",  # Keep old port for compatibility
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Trusted host middleware - AFTER CORS
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "localhost",
        "127.0.0.1",
        "host.docker.internal",
        "*",
    ],  # Allow all for development
)


def register_core_routes(app: FastAPI) -> None:
    """Register kernel routes"""
    app.include_router(workspace.router, tags=["workspace"])
    app.include_router(playbook.router, tags=["playbook"])
    app.include_router(playbook_execution.router, tags=["playbook"])
    app.include_router(config.router, tags=["config"])
    app.include_router(system_settings_router, tags=["system"])
    app.include_router(settings_extensions_router)
    app.include_router(runtime_environments_router, tags=["runtime-environments"])
    app.include_router(tools.router, tags=["tools"])
    app.include_router(sandbox.router, tags=["sandboxes"])
    app.include_router(deployment.router, tags=["deployment"])
    app.include_router(data_sources_router, tags=["data-sources"])
    app.include_router(lens.router, tags=["lenses"])
    app.include_router(composition.router, tags=["compositions"])
    app.include_router(surface.router, tags=["surface"])

    # Dashboard routes
    from .routes.core.dashboard import router as dashboard_router

    app.include_router(dashboard_router, tags=["dashboard"])

    # Admin reload routes (pre-restart validation, reload trigger)
    try:
        from .routes.core.admin_reload import router as admin_reload_router

        app.include_router(admin_reload_router, tags=["admin"])
        logger.info("Admin reload routes registered")
    except Exception as e:
        logger.warning(f"Failed to register admin reload routes: {e}")

    if not _capability_hot_reload_enabled():
        try:
            from backend.app.capabilities.api_loader import load_capability_apis
            import os

            allowlist_env = os.getenv("CAPABILITY_ALLOWLIST")
            allowlist = allowlist_env.split(",") if allowlist_env else None
            capability_routers = load_capability_apis(
                app=app, allowlist=allowlist, enable_all=False
            )
            if allowlist:
                logger.info(
                    f"Loaded {len(capability_routers)} cloud capability API routers (allowlist={allowlist})"
                )
            else:
                logger.info(
                    f"Loaded {len(capability_routers)} cloud capability API routers (using enabled_by_default from manifests)"
                )
        except Exception as e:
            logger.error(
                f"Failed to load cloud capability API routers: {e}", exc_info=True
            )
    else:
        logger.info(
            "Capability hot reload enabled; capability API routers will be loaded via reload manager."
        )

    # Register YogaCoach API routes directly (installed capability)
    try:
        from backend.app.capabilities.yogacoach.routes.api import (
            router as yogacoach_router,
        )

        app.include_router(yogacoach_router)
        logger.info("YogaCoach API routes registered")
    except ImportError as e:
        logger.debug(f"YogaCoach API routes not available: {e}")
    except Exception as e:
        logger.warning(f"Failed to register YogaCoach API routes: {e}")

    app.include_router(
        workspace_resource_bindings_router, tags=["workspace-resource-bindings"]
    )
    app.include_router(cloud_providers_router, tags=["cloud-providers"])
    app.include_router(cloud_sync.router, tags=["cloud-sync"])
    app.include_router(graph_router, tags=["graph"])
    app.include_router(lens_unified_router, tags=["lens-unified"])

    # Story Thread proxy routes (optional - requires Cloud API configuration)
    try:
        from .routes.core.story_thread import router as story_thread_router

        app.include_router(story_thread_router, tags=["story-threads"])
        logger.info("Story Thread proxy routes registered")
    except Exception as e:
        logger.debug(f"Story Thread proxy routes not registered: {e}")

    # Cloud navigation proxy routes (optional - requires Cloud frontend configuration)
    try:
        from .routes.core.cloud_navigation import router as cloud_navigation_router

        app.include_router(cloud_navigation_router, tags=["cloud-navigation"])
        logger.info("Cloud navigation proxy routes registered")
    except Exception as e:
        logger.debug(f"Cloud navigation proxy routes not registered: {e}")

    app.include_router(blueprint.router, tags=["blueprints"])
    app.include_router(unsplash_fingerprints_router)

    # Generic resource routes (neutral interface)
    app.include_router(resources_router, tags=["resources"])

    # Legacy specific routes (kept for backward compatibility, will be deprecated)
    app.include_router(intents_router, tags=["intents"])
    app.include_router(chapters_router, tags=["chapters"])
    app.include_router(artifacts_router, tags=["artifacts"])

    # Content Vault indexing routes
    from .routes.core.content_vault_index import router as content_vault_index_router

    app.include_router(content_vault_index_router, tags=["content-vault"])

    # Decision cards routes
    from backend.app.routes.core import decision_cards as decision_cards_router

    app.include_router(decision_cards_router.router, tags=["decision-cards"])

    # MCP Bridge routes (optional - requires mcp_bridge module)
    try:
        from .routes.mcp_bridge import router as mcp_bridge_router

        app.include_router(mcp_bridge_router, tags=["mcp-bridge"])
        logger.info("MCP Bridge routes registered")
    except Exception as e:
        logger.debug(f"MCP Bridge routes not registered: {e}")

    # Agent WebSocket routes (real-time task dispatch to IDE agents)
    try:
        from .routes.agent_websocket import router as agent_ws_router

        app.include_router(agent_ws_router, tags=["agent-websocket"])
        logger.info("Agent WebSocket routes registered")
    except Exception as e:
        logger.debug(f"Agent WebSocket routes not registered: {e}")


def register_core_primitives(app: FastAPI) -> None:
    """Register core primitives"""
    app.include_router(vector_db.router, tags=["vector-db"])
    app.include_router(vector_search.router, tags=["vector-search"])
    app.include_router(capability_packs.router, tags=["capability-packs"])
    app.include_router(capability_suites.router, tags=["capability-suites"])
    # Lazy import capability_installation to avoid startup issues
    try:
        from .routes.core import capability_installation

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
            load_and_register_packs(app)
    except Exception as e:
        logger.warning(
            f"Failed to load some feature packs during startup: {e}. App will continue to start."
        )


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


# Debug endpoint to list all registered routes
@app.get("/debug/routes")
async def debug_list_routes():
    """Temporary debug endpoint to list all registered routes"""
    routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            routes.append(
                {
                    "path": route.path,
                    "methods": list(route.methods) if route.methods else [],
                    "name": route.name if hasattr(route, "name") else None,
                }
            )
    # Filter to show only mindscape routes
    mindscape_routes = [r for r in routes if "mindscape" in r["path"].lower()]
    return {
        "total_routes": len(routes),
        "mindscape_routes": mindscape_routes,
        "sample_routes": routes[:20],
    }


# Workspace feature routes are loaded via pack registry
# See backend/packs/workspace-pack.yaml and backend/features/workspace/


@app.on_event("startup")
async def startup_event():
    """Initialize database tables and background tasks on startup"""

    # Register playbook handlers
    try:
        from backend.app.routes.core.playbook.handlers import register_playbook_handlers

        await register_playbook_handlers(app)
        logger.info("Playbook handlers registered successfully")
    except Exception as e:
        logger.warning(f"Failed to register playbook handlers: {e}", exc_info=True)

    # Check for dependency updates (Development Mode only)
    # Compares build-time requirements (in image) vs run-time requirements (volume mounted code)
    if os.getenv("ENVIRONMENT") == "development":
        try:
            from pathlib import Path
            import hashlib

            # Paths inside container based on Dockerfile structure
            # /app/requirements.txt is COPY'd during build (frozen state)
            # /app/backend/requirements.txt is volume mounted from host (current state)
            build_reqs_path = Path("/app/requirements.txt")
            runtime_reqs_path = Path("/app/backend/requirements.txt")

            if build_reqs_path.exists() and runtime_reqs_path.exists():
                build_hash = hashlib.md5(build_reqs_path.read_bytes()).hexdigest()
                runtime_hash = hashlib.md5(runtime_reqs_path.read_bytes()).hexdigest()

                if build_hash != runtime_hash:
                    logger.warning("\n" + "!" * 80)
                    logger.warning("DEPENDENCY MISMATCH DETECTED!")
                    logger.warning(
                        "The requirements.txt in your running container differs from your local code."
                    )
                    logger.warning(
                        "This means your Docker image is outdated and missing new dependencies."
                    )
                    logger.warning("PLEASE RUN: docker compose up --build")
                    logger.warning("!" * 80 + "\n")
            else:
                logger.debug(
                    "Could not find both requirements.txt files for dependency check. Skipping."
                )
        except Exception as e:
            logger.warning(f"Dependency check failed: {e}")

    # Initialize Cloud Connector (if enabled)
    cloud_connector_enabled = (
        os.getenv("CLOUD_CONNECTOR_ENABLED", "false").lower() == "true"
    )
    if cloud_connector_enabled:
        try:
            import asyncio
            from backend.app.services.cloud_connector import CloudConnector

            connector = CloudConnector()
            app.state.cloud_connector = connector
            asyncio.create_task(connector.connect())
            logger.info("Cloud Connector initialized and connecting...")
        except Exception as e:
            logger.warning(f"Failed to initialize Cloud Connector: {e}", exc_info=True)

    # Ensure required databases exist (handles case where postgres volume
    # was created without running init scripts, e.g. on Windows)
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

        pg_host = os.getenv(
            "POSTGRES_CORE_HOST", os.getenv("POSTGRES_HOST", "postgres")
        )
        pg_port = int(
            os.getenv("POSTGRES_CORE_PORT", os.getenv("POSTGRES_PORT", "5432"))
        )
        pg_user = os.getenv(
            "POSTGRES_CORE_USER", os.getenv("POSTGRES_USER", "mindscape")
        )
        pg_pass = os.getenv(
            "POSTGRES_CORE_PASSWORD",
            os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
        )
        core_db = os.getenv("POSTGRES_CORE_DB", "mindscape_core")
        vector_db = os.getenv("POSTGRES_VECTOR_DB", "mindscape_vectors")

        # Connect to default 'postgres' database to create missing databases
        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            user=pg_user,
            password=pg_pass,
            dbname="postgres",
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        for db_name in [core_db, vector_db]:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{db_name}"')
                logger.info(f"Created missing database: {db_name}")

        # Ensure pgvector extension exists in vector database
        cur.close()
        conn.close()
        vconn = psycopg2.connect(
            host=pg_host, port=pg_port, user=pg_user, password=pg_pass, dbname=vector_db
        )
        vconn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        vcur = vconn.cursor()
        vcur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        vcur.close()
        vconn.close()
    except Exception as e:
        logger.warning(f"Database auto-creation check failed (non-blocking): {e}")

    # Run database migrations using unified migration orchestrator
    logger.info("Running database migrations...")
    try:
        from pathlib import Path
        from app.services.migrations import MigrationOrchestrator

        capabilities_root = Path(__file__).parent / "capabilities"
        alembic_configs = {
            "postgres": Path(__file__).parent.parent / "alembic.postgres.ini",
        }

        orchestrator = MigrationOrchestrator(capabilities_root, alembic_configs)

        # Run PostgreSQL migrations
        logger.info("Checking PostgreSQL migrations...")
        postgres_result = orchestrator.apply("postgres", dry_run=False)
        if postgres_result.get("status") == "validation_failed":
            logger.error(
                f"PostgreSQL migration validation failed: {postgres_result.get('failed_checks')}"
            )
            logger.warning("Falling back to init_db.py for PostgreSQL tables...")
            # Fallback to init_db.py if migration validation fails
            try:
                init_mindscape_tables()
                logger.info("Mindscape tables initialized via init_db.py fallback")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize mindscape tables via init_db.py: {e}"
                )
        elif postgres_result.get("status") == "error":
            logger.error(f"PostgreSQL migration error: {postgres_result.get('error')}")
            logger.warning("Falling back to init_db.py for PostgreSQL tables...")
            try:
                init_mindscape_tables()
                logger.info("Mindscape tables initialized via init_db.py fallback")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize mindscape tables via init_db.py: {e}"
                )
        else:
            logger.info(
                f"PostgreSQL migrations: {postgres_result.get('status')}, applied: {postgres_result.get('migrations_applied', 0)}"
            )
            # Migration system working, init_db.py no longer needed
            logger.info("Database migrations completed via unified migration system")
    except ImportError as e:
        logger.warning(f"Migration orchestrator not available: {e}")
        logger.warning("Falling back to init_db.py...")
        # Fallback to init_db.py if migration system not available
        try:
            init_mindscape_tables()
            logger.info("Mindscape tables initialized via init_db.py fallback")
        except Exception as e:
            logger.warning(
                f"Failed to initialize mindscape tables (will retry on first use): {e}"
            )
    except Exception as e:
        logger.error(f"Migration system error: {e}", exc_info=True)
        logger.warning("Falling back to init_db.py...")
        # Fallback to init_db.py on any error
        try:
            init_mindscape_tables()
            logger.info("Mindscape tables initialized via init_db.py fallback")
        except Exception as e2:
            logger.warning(
                f"Failed to initialize mindscape tables (will retry on first use): {e2}"
            )

    # Auto-migrate SQLite data if legacy database detected
    try:
        from app.services.sqlite_auto_migrator import run_auto_migration

        migration_result = run_auto_migration()
        if migration_result.get("status") == "migrated":
            logger.info(
                f"SQLite auto migration completed: {migration_result.get('total_rows', 0)} rows, "
                f"critical tables verified: {migration_result.get('critical_verified')}"
            )
        elif migration_result.get("status") == "skipped":
            logger.debug(
                f"SQLite auto migration skipped: {migration_result.get('reason')}"
            )
        elif migration_result.get("status") == "error":
            logger.error(
                f"SQLite auto migration error: {migration_result.get('error')}"
            )
            logger.error(
                "Manual migration available: docker compose exec backend "
                "python /app/backend/scripts/migrate_all_data_to_postgres.py"
            )
    except Exception as e:
        logger.warning(f"SQLite auto migration failed (non-blocking): {e}")

    # Verify critical tables exist (last safety net)
    try:
        from sqlalchemy import text, create_engine

        _verify_db_url = os.environ.get("DATABASE_URL_CORE") or os.environ.get(
            "DATABASE_URL"
        )
        if _verify_db_url:
            _verify_engine = create_engine(_verify_db_url)
            _critical_tables = [
                "profiles",
                "workspaces",
                "system_settings",
                "user_configs",
            ]
            _missing = []
            with _verify_engine.connect() as _conn:
                for _tbl in _critical_tables:
                    _result = _conn.execute(
                        text(
                            "SELECT EXISTS ("
                            "  SELECT 1 FROM information_schema.tables"
                            "  WHERE table_name = :t AND table_schema = 'public'"
                            ")"
                        ),
                        {"t": _tbl},
                    )
                    if not _result.scalar():
                        _missing.append(_tbl)
            _verify_engine.dispose()

            if _missing:
                logger.error("=" * 60)
                logger.error("CRITICAL: Required database tables are missing!")
                logger.error(f"Missing tables: {', '.join(_missing)}")
                logger.error("")
                logger.error("The API will fail on most requests until this is fixed.")
                logger.error(
                    "Try: docker compose exec backend alembic -c "
                    "/app/backend/alembic.postgres.ini upgrade heads"
                )
                logger.error("Or:  docker compose down && docker compose up --build")
                logger.error("=" * 60)
            else:
                logger.info(
                    f"Critical table verification passed ({len(_critical_tables)} tables)"
                )
    except Exception as e:
        logger.warning(f"Critical table verification failed (non-blocking): {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    # Disconnect Cloud Connector if initialized
    if hasattr(app.state, "cloud_connector"):
        connector = app.state.cloud_connector
        if connector:
            try:
                await connector.disconnect()
                logger.info("Cloud Connector disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting Cloud Connector: {e}")


# NOTE: Duplicate register_core_routes definition was removed from here.
# The active definition is at L164, called at L292. This duplicate was
# never executed because it was defined after the call site.


def register_core_primitives(app: FastAPI) -> None:
    """Register core primitives"""
    app.include_router(vector_db.router, tags=["vector-db"])
    app.include_router(vector_search.router, tags=["vector-search"])
    app.include_router(capability_packs.router, tags=["capability-packs"])
    app.include_router(capability_suites.router, tags=["capability-suites"])
    # Lazy import capability_installation to avoid startup issues
    try:
        from .routes.core import capability_installation

        app.include_router(
            capability_installation.router, tags=["capability-installation"]
        )
    except Exception as e:
        logger.warning(f"Failed to load capability_installation router: {e}")


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

    # Workspace feature routes are loaded via pack registry
    # See backend/packs/workspace-pack.yaml and backend/features/workspace/

    logger.info("Validating routes against manifest declarations...")
    try:
        from backend.app.capabilities.route_validator import validate_on_startup

        validate_on_startup(app)
        logger.info("Route validation completed successfully")
    except FileNotFoundError as e:
        logger.error(f"Route validation failed (path not found): {e}", exc_info=True)
        import os

        if os.getenv("SKIP_ROUTE_VALIDATION") != "1":
            raise
        logger.warning(
            "SKIP_ROUTE_VALIDATION=1, skipping route validation despite path error"
        )
    except Exception as e:
        logger.error(f"Route validation failed: {e}", exc_info=True)
        import os

        # In development environment, allow startup to continue with warnings
        env = os.getenv("ENVIRONMENT", "development")
        if env == "development":
            logger.warning(
                "Route validation failed but continuing in development mode. Set SKIP_ROUTE_VALIDATION=1 to suppress this warning."
            )
        elif os.getenv("SKIP_ROUTE_VALIDATION") != "1":
            raise
        else:
            logger.warning(
                "SKIP_ROUTE_VALIDATION=1, skipping route validation despite errors"
            )

    # Initialize cloud sync service
    logger.info("Initializing cloud sync service...")
    try:
        from backend.app.services.cloud_sync.service import (
            initialize_cloud_sync_service,
        )
        import os

        base_url = os.getenv("CLOUD_SYNC_BASE_URL")
        api_key = os.getenv("CLOUD_SYNC_API_KEY")

        if base_url and api_key:
            initialize_cloud_sync_service(
                base_url=base_url,
                api_key=api_key,
                auto_start=True,
            )
            logger.info("Cloud sync service initialized successfully")
        else:
            logger.info(
                "Cloud sync service not configured (CLOUD_SYNC_BASE_URL or CLOUD_SYNC_API_KEY not set)"
            )
    except Exception as e:
        logger.warning(f"Failed to initialize cloud sync service: {e}")

    # Initialize resource handlers (for generic resource routing)
    logger.info("Initializing resource handlers...")
    try:
        from .services.resource_handlers.init_handlers import (
            initialize_resource_handlers,
        )

        initialize_resource_handlers()
        logger.info("Resource handlers initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize resource handlers: {e}", exc_info=True)

    # Load capability packages
    logger.info("Loading capability packages...")
    try:
        from pathlib import Path
        import os

        # Load local capabilities only
        # Note: Cloud capabilities should be accessed via API or installed to local-core
        # through proper installer/configuration process. Direct file system access
        # to cloud capabilities is prohibited to maintain architecture boundaries.
        app_dir = Path(__file__).parent
        local_capabilities_dir = (app_dir / "capabilities").resolve()
        logger.info(f"Loading capabilities from: {local_capabilities_dir}")
        if not local_capabilities_dir.exists():
            logger.error(
                f"Capabilities directory does not exist: {local_capabilities_dir}"
            )
        load_capabilities(local_capabilities_dir)
        from backend.app.capabilities.registry import get_registry

        registry = get_registry()
        logger.info(
            f"Local capability packages loaded successfully: {len(registry.list_capabilities())} capabilities, {len(registry.list_tools())} tools"
        )
    except Exception as e:
        logger.error(f"Failed to load capability packages: {e}", exc_info=True)
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")

    # Register workspace tools
    try:
        from backend.app.services.tools.registry import register_workspace_tools

        workspace_tools = register_workspace_tools()
        logger.info(f"Registered {len(workspace_tools)} workspace tools")
    except Exception as e:
        logger.warning(f"Failed to register workspace tools: {e}", exc_info=True)

    # Register filesystem tools
    try:
        from backend.app.services.tools.registry import register_filesystem_tools

        filesystem_tools = register_filesystem_tools()
        logger.info(f"Registered {len(filesystem_tools)} filesystem tools")
    except Exception as e:
        logger.warning(f"Failed to register filesystem tools: {e}", exc_info=True)

    # Register Content Vault tools
    try:
        from backend.app.services.tools.registry import (
            register_content_vault_tools,
            register_vector_search_tool,
        )
        import os

        vault_path = os.getenv("CONTENT_VAULT_PATH")
        content_vault_tools = register_content_vault_tools(vault_path)
        register_vector_search_tool()
        logger.info(
            f"Registered {len(content_vault_tools)} Content Vault tools and Vector Search tool"
        )
    except Exception as e:
        logger.warning(f"Failed to register Content Vault tools: {e}", exc_info=True)

    # Register External Agent tools
    try:
        from backend.app.services.tools.registry import register_external_agent_tools

        external_agent_tools = register_external_agent_tools()
        logger.info(f"Registered {len(external_agent_tools)} external agent tools")
    except Exception as e:
        logger.warning(f"Failed to register external agent tools: {e}", exc_info=True)

    # Unsplash tools are provided by cloud capability pack, not local-core
    # They are loaded via capabilities/registry from cloud capabilities/unsplash/manifest.yaml

    # IG Post and IG + Obsidian tools are registered automatically via ToolListService
    # when needed (see tool_list_service.py _get_builtin_tools method)

    # Register playbook handlers (moved to startup_event)

    try:
        from backend.app.capabilities.habit_learning.services.habit_proposal_worker import (
            HabitProposalWorker,
        )
        import asyncio

        interval_hours = int(os.getenv("HABIT_PROPOSAL_INTERVAL_HOURS", "1"))

        worker = HabitProposalWorker()
        asyncio.create_task(worker.run_periodic_task(interval_hours=interval_hours))
        logger.info(f"Habit proposal worker started (interval: {interval_hours} hours)")
    except ImportError:
        logger.debug(
            "Habit learning capability not available, skipping habit proposal worker"
        )

    # Initialize Content Vault if needed (for IG-related capabilities)
    try:
        from pathlib import Path
        from backend.scripts.init_content_vault import initialize_content_vault

        vault_path = os.getenv("CONTENT_VAULT_PATH")
        if not vault_path:
            # Use default path (~/content-vault)
            import os

            vault_path = Path.home() / "content-vault"
        else:
            vault_path = Path(vault_path).expanduser().resolve()

        # Always call initialize_content_vault to ensure structure is complete
        # It will check and repair missing subdirectories even if vault exists
        if not vault_path.exists() or not (vault_path / ".vault-config.yaml").exists():
            logger.info("Content Vault not found, initializing...")
        else:
            logger.debug("Content Vault exists, checking structure completeness...")

        success = initialize_content_vault(vault_path, force=False)
        if success:
            logger.info(f"Content Vault initialized/verified at {vault_path}")
        else:
            logger.warning(
                "Content Vault initialization/verification failed, but continuing startup"
            )
    except ImportError:
        logger.debug("Content Vault init script not available, skipping initialization")
    except Exception as e:
        logger.warning(f"Failed to initialize Content Vault: {e}", exc_info=True)

    # Print startup banner — marks the end of successful initialization
    try:
        from backend.app.startup_banner import print_startup_banner

        print_startup_banner()
    except Exception as e:
        logger.debug(f"Startup banner unavailable: {e}")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to My Agent Console API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.post("/api/v1/admin/reset-rate-limit")
async def reset_rate_limit(request: Request):
    """Reset rate limit for development (only allows localhost)"""
    client_ip = request.client.host if request.client else "unknown"

    # Only allow localhost for security
    if client_ip not in ["127.0.0.1", "localhost", "::1", "unknown"]:
        # Check if it's from docker internal network (common in dev)
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if "127.0.0.1" not in forwarded_for and "localhost" not in forwarded_for:
            raise HTTPException(
                status_code=403, detail="Only localhost can reset rate limits"
            )

    security_monitor.reset_rate_limit()
    return {"status": "ok", "message": "Rate limits cleared"}


@app.get("/health")
async def health_check():
    """Overall health check with system component status"""
    from .services.system_health_checker import SystemHealthChecker

    health_checker = SystemHealthChecker()

    # Perform basic system checks (without workspace requirement)
    issues = []

    # Check LLM configuration
    llm_status = await health_checker._check_llm_configuration("default-user", issues)

    # Check Vector DB connection
    vector_db_status = await health_checker._check_vector_db(issues)

    # Check backend service
    backend_status = await health_checker._check_backend_service(issues)

    # Check OCR service
    ocr_status = await health_checker._check_ocr_service(issues)

    # Determine overall status
    overall_status = "healthy"
    if any(i.severity == "error" for i in issues):
        overall_status = "unhealthy"
    elif any(i.severity == "warning" for i in issues):
        overall_status = "degraded"

    return {
        "status": overall_status,
        "service": "my-agent-mindscape-backend",
        "version": "1.0.0",
        "components": {
            "backend": backend_status.get("status", "unknown"),
            "llm_configured": llm_status.get("configured", False),
            "llm_available": llm_status.get("available", False),
            "vector_db_connected": vector_db_status.get("connected", False),
            "ocr_service": ocr_status.get("status", "unknown"),
        },
        "llm_configured": llm_status.get("configured", False),
        "llm_available": llm_status.get("available", False),
        "llm_provider": llm_status.get("provider"),
        "vector_db_connected": vector_db_status.get("connected", False),
        "ocr_service": ocr_status,
        "issues": [issue.to_dict() for issue in issues] if issues else [],
    }


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Security monitoring middleware"""
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting check
    if security_monitor.check_rate_limit(client_ip):
        retry_after = security_monitor.rate_limit_window * 60
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={
                "Retry-After": str(retry_after),
                "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
                "Access-Control-Allow-Headers": "*",
            },
        )

    # Log request details for file upload debugging
    if "/files/upload" in str(request.url.path):
        request_id = request.headers.get("x-request-id", f"req-{id(request)}")
        content_type = request.headers.get("content-type", "N/A")
        content_length = request.headers.get("content-length", "N/A")
        client_ip = request.client.host if request.client else "unknown"

        logger.info(f"[{request_id}] === MIDDLEWARE: FILE UPLOAD REQUEST START ===")
        logger.info(f"[{request_id}] Method: {request.method}")
        logger.info(f"[{request_id}] Path: {request.url.path}")
        logger.info(f"[{request_id}] Query params: {dict(request.query_params)}")
        logger.info(f"[{request_id}] Client IP: {client_ip}")
        logger.info(f"[{request_id}] Content-Type: {content_type}")
        logger.info(f"[{request_id}] Content-Length: {content_length}")
        logger.info(f"[{request_id}] All headers: {dict(request.headers)}")

        import sys

        sys.stderr.write(f"[{request_id}] MIDDLEWARE: File upload request detected\n")
        sys.stderr.write(f"[{request_id}] Path: {request.url.path}\n")
        sys.stderr.write(f"[{request_id}] Content-Type: {content_type}\n")
        sys.stderr.flush()

    try:
        request_id = (
            request.headers.get("x-request-id", f"req-{id(request)}")
            if "/files/upload" in str(request.url.path)
            else None
        )
        response = await call_next(request)
        if "/files/upload" in str(request.url.path) and request_id:
            logger.info(f"[{request_id}] === MIDDLEWARE: RESPONSE ====")
            logger.info(f"[{request_id}] Status code: {response.status_code}")
            logger.info(f"[{request_id}] Response headers: {dict(response.headers)}")
            if response.status_code == 422:
                logger.error(f"[{request_id}] 422 ERROR in middleware")
                import sys

                sys.stderr.write(f"[{request_id}] MIDDLEWARE: 422 error detected\n")
                sys.stderr.flush()
        return response
    except RequestValidationError as e:
        if "/files/upload" in str(request.url.path):
            request_id = request.headers.get("x-request-id", f"req-{id(request)}")
            logger.error(f"[{request_id}] === MIDDLEWARE: RequestValidationError ===")
            logger.error(f"[{request_id}] Errors: {e.errors()}", exc_info=True)
            import sys

            sys.stderr.write(f"[{request_id}] MIDDLEWARE: RequestValidationError\n")
            sys.stderr.write(f"[{request_id}] Errors: {e.errors()}\n")
            sys.stderr.flush()
        raise
    except Exception as e:
        if "/files/upload" in str(request.url.path):
            request_id = request.headers.get("x-request-id", f"req-{id(request)}")
            logger.error(f"[{request_id}] === MIDDLEWARE: Exception ===")
            logger.error(f"[{request_id}] Exception: {str(e)}", exc_info=True)
            import sys

            sys.stderr.write(f"[{request_id}] MIDDLEWARE: Exception: {str(e)}\n")
            sys.stderr.flush()
        raise


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors (422) with detailed logging"""
    request_id = request.headers.get("x-request-id", f"req-{id(request)}")
    error_details = exc.errors()
    import json
    import sys

    logger.error(f"[{request_id}] === EXCEPTION HANDLER: RequestValidationError ===")
    logger.error(f"[{request_id}] Method: {request.method}")
    logger.error(f"[{request_id}] Path: {request.url.path}")
    logger.error(f"[{request_id}] Query params: {dict(request.query_params)}")

    # Log to both logger and stderr for maximum visibility
    error_json = json.dumps(error_details, indent=2, ensure_ascii=False)
    logger.error(f"[{request_id}] Error details: {error_json}")
    logger.error(f"[{request_id}] Request headers: {dict(request.headers)}")

    # Force output to stderr (will be captured by docker logs)
    error_msg = (
        f"[{request_id}] VALIDATION ERROR: {request.method} {request.url.path}\n"
    )
    error_msg += f"[{request_id}] Errors: {error_json}\n"
    error_msg += f"[{request_id}] Headers: {dict(request.headers)}\n"
    sys.stderr.write(error_msg)
    sys.stderr.flush()

    # Try to get request body for debugging (if available)
    try:
        if hasattr(request, "_body"):
            body_preview = str(request._body)[:500] if request._body else "None"
            logger.error(
                f"[{request_id}] Request body (first 500 chars): {body_preview}"
            )
            sys.stderr.write(f"[{request_id}] Request body preview: {body_preview}\n")
            sys.stderr.flush()
    except Exception as e:
        logger.error(f"[{request_id}] Could not read request body: {e}")

    logger.error(f"[{request_id}] === EXCEPTION HANDLER: Returning 422 response ===")
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=422,
        content={"detail": error_details},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
            "Access-Control-Allow-Headers": "*",
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with CORS headers"""
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
            "Access-Control-Allow-Headers": "*",
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions with CORS headers"""
    import traceback
    import sys

    exc_type, exc_value, exc_tb = exc.__class__, exc, exc.__traceback__
    full_traceback = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.error(f"Unhandled exception: {str(exc)}\n{full_traceback}")
    # Also print to stderr for immediate visibility
    print(f"ERROR: Unhandled exception: {str(exc)}", file=sys.stderr)
    print(full_traceback, file=sys.stderr)
    origin = request.headers.get("origin", "*")
    # Validate origin against allowed origins (from port config service)
    try:
        from .services.port_config_service import port_config_service
        import os

        current_cluster = os.getenv("CLUSTER_NAME")
        current_env = os.getenv("ENVIRONMENT")
        current_site = os.getenv("SITE_NAME")

        frontend_url = port_config_service.get_service_url(
            "frontend",
            cluster=current_cluster,
            environment=current_env,
            site=current_site,
        )
        host_config = port_config_service.get_host_config()

        allowed_origins = [frontend_url]
        if "localhost" in frontend_url:
            allowed_origins.append(frontend_url.replace("localhost", "127.0.0.1"))
        if host_config.cors_origins:
            allowed_origins.extend(host_config.cors_origins)
    except Exception as e:
        logger.warning(
            f"Failed to get allowed origins from port config service, using defaults: {e}"
        )
        allowed_origins = [
            "http://localhost:8300",
            "http://127.0.0.1:8300",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ]

    if origin not in allowed_origins:
        origin = allowed_origins[0] if allowed_origins else "*"
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
            "Access-Control-Allow-Headers": "*",
        },
    )


def main():
    """Main entry point for running the server"""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    workers = int(os.getenv("WORKERS", "1"))

    logger.info(f"Starting My Agent Console API on {host}:{port}")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        workers=workers,
        reload=os.getenv("ENVIRONMENT") == "development",
        log_level="info",
    )


if __name__ == "__main__":
    main()
