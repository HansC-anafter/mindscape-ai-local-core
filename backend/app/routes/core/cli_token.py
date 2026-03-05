"""
CLI Token Endpoint

Returns auth environment variables for CLI bridge processes.
Reads the configured auth mode and credentials from system_settings,
returning them as env-var key-value pairs that the bridge script
injects into the Gemini CLI subprocess.

Supported modes:
  - gca           : returns GOOGLE_CLOUD_ACCESS_TOKEN + GOOGLE_GENAI_USE_GCA
                    (reads stored Google IDP token from runtime auth_config)
  - gemini_api_key: returns GEMINI_API_KEY
  - vertex_ai     : returns GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION
"""

import logging
import os
import time

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _get_gca_token() -> dict:
    """Retrieve Google IDP access token from connected GCA runtimes.

    Queries all GCA runtimes (id LIKE 'gca-%') with auth_status='connected',
    ordered by 'gca-local' first. Iterates through the pool: if one runtime's
    token is expired and refresh fails, falls through to the next runtime.

    Returns:
        dict with env vars and selected_runtime_id, or error details.
    """
    try:
        from ...database.session import get_db_postgres as get_db
    except ImportError:
        try:
            from ...database import get_db_postgres as get_db
        except ImportError:
            from mindscape.di.providers import get_db_session as get_db

    from ...models.runtime_environment import RuntimeEnvironment
    from ...services.runtime_auth_service import RuntimeAuthService

    db = next(get_db())
    try:
        # Query all connected GCA runtimes, prefer gca-local first
        runtimes = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.id.like("gca-%"),
                RuntimeEnvironment.auth_status == "connected",
            )
            .all()
        )
        # Sort: gca-local first, then alphabetical
        runtimes.sort(key=lambda r: (0 if r.id == "gca-local" else 1, r.id))

        if not runtimes:
            return {
                "error": "GCA not connected. "
                "Connect via Web Console > Settings > CLI Agent Keys > "
                "Google Account tab."
            }

        auth_service = RuntimeAuthService()
        errors = []

        for runtime in runtimes:
            token_data = auth_service.decrypt_token_blob(runtime.auth_config or {})
            if not token_data:
                errors.append(f"{runtime.id}: decrypt failed")
                continue

            idp_access_token = token_data.get("idp_access_token")
            idp_refresh_token = token_data.get("idp_refresh_token")
            idp_expiry = token_data.get("idp_token_expiry", 0)

            if not idp_access_token:
                errors.append(f"{runtime.id}: no IDP access token")
                continue

            # Refresh if expired (with 60s buffer)
            if idp_expiry and time.time() > (idp_expiry - 60):
                logger.info("IDP token expired for runtime %s, refreshing", runtime.id)
                refreshed = _refresh_google_token(
                    idp_refresh_token, runtime, auth_service, token_data, db
                )
                if refreshed:
                    idp_access_token = refreshed
                else:
                    logger.warning(
                        "Token refresh failed for runtime %s, trying next",
                        runtime.id,
                    )
                    errors.append(f"{runtime.id}: refresh failed")
                    continue

            # Resolve GCP project ID (required by cloudcode-pa)
            gcp_project = token_data.get("gcp_project") or ""
            if not gcp_project:
                try:
                    from ...services.system_settings_store import SystemSettingsStore

                    s = SystemSettingsStore()
                    gcp_project = s.get("google_cloud_project", "")
                except Exception:
                    pass
            if not gcp_project:
                gcp_project = os.getenv("GOOGLE_CLOUD_PROJECT", "")

            env = {
                "GOOGLE_GENAI_USE_GCA": "true",
                "GOOGLE_CLOUD_ACCESS_TOKEN": idp_access_token,
            }
            if gcp_project:
                env["GOOGLE_CLOUD_PROJECT"] = gcp_project

            logger.info("GCA token resolved from runtime %s", runtime.id)
            return {"env": env, "selected_runtime_id": runtime.id}

        # All runtimes failed
        return {"error": f"All GCA runtimes failed: {'; '.join(errors)}"}
    finally:
        db.close()


def _refresh_google_token(refresh_token, runtime, auth_service, token_data, db):
    """Refresh Google IDP token using Gemini CLI's public OAuth credentials.

    Uses the CLI's installed-application Client ID/Secret (public by
    design) to refresh the access token via Google's OAuth2 endpoint.

    Returns new access_token string on success, None on failure.
    """
    if not refresh_token:
        logger.warning("No IDP refresh token available")
        return None

    # Use Gemini CLI's public OAuth credentials (installed app type).
    # These are intentionally public and safe to embed in client code.
    from .gca_constants import get_gca_client_id, get_gca_client_secret

    client_id = get_gca_client_id()
    client_secret = get_gca_client_secret()

    import urllib.request
    import urllib.parse
    import json

    try:
        data = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode()

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            method="POST",
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())

        new_access_token = result.get("access_token")
        expires_in = result.get("expires_in", 3600)

        if not new_access_token:
            logger.error("Google token refresh returned no access_token")
            return None

        # Update stored token data
        token_data["idp_access_token"] = new_access_token
        token_data["idp_token_expiry"] = time.time() + expires_in

        # Remove any leaked site-hub credentials from stored data
        token_data.pop("google_client_id", None)
        token_data.pop("google_client_secret", None)

        encrypted = auth_service.encrypt_token_blob(token_data)

        runtime.auth_config = encrypted
        db.commit()

        logger.info("IDP token refreshed successfully, expires_in=%s", expires_in)
        return new_access_token

    except Exception as e:
        logger.error("Google IDP token refresh failed: %s", e)
        return None


@router.get("/cli-token")
async def get_cli_token():
    """Return auth env vars for CLI bridge processes.

    Queries system_settings for gemini_cli_auth_mode and the
    corresponding credentials.  Falls back to host environment
    variables when system_settings is unavailable or empty.

    Returns:
        JSON with auth_mode and env dict, or error details.
    """
    try:
        from ...services.system_settings_store import SystemSettingsStore

        settings = SystemSettingsStore()

        auth_mode = settings.get("gemini_cli_auth_mode", "gca")
        agent_model = settings.get("agent_cli_model", "gemini-2.5-pro")

        # ── GCA mode: return stored Google IDP token ──
        if auth_mode == "gca":
            result = _get_gca_token()
            if "error" in result:
                logger.warning("GCA token retrieval failed: %s", result["error"])
                return {
                    "auth_mode": "gca",
                    "env": {},
                    "error": result["error"],
                    "model": agent_model,
                }
            return {
                "auth_mode": "gca",
                "env": result["env"],
                "model": agent_model,
            }

        # ── API key mode ──
        if auth_mode == "gemini_api_key":
            api_key = settings.get("gemini_api_key", "")
            if not api_key:
                api_key = os.environ.get("GEMINI_API_KEY", "")
            if not api_key:
                return {
                    "auth_mode": auth_mode,
                    "env": {},
                    "error": "gemini_api_key not configured in system_settings",
                }
            return {
                "auth_mode": auth_mode,
                "env": {"GEMINI_API_KEY": api_key},
                "model": agent_model,
            }

        # ── Vertex AI mode ──
        if auth_mode == "vertex_ai":
            project = settings.get(
                "google_cloud_project",
                os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            )
            location = settings.get(
                "google_cloud_location",
                os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
            if not project:
                return {
                    "auth_mode": auth_mode,
                    "env": {},
                    "error": "google_cloud_project not configured",
                }
            return {
                "auth_mode": auth_mode,
                "env": {
                    "GOOGLE_GENAI_USE_VERTEXAI": "true",
                    "GOOGLE_CLOUD_PROJECT": project,
                    "GOOGLE_CLOUD_LOCATION": location,
                },
                "model": agent_model,
            }

        return {
            "auth_mode": auth_mode,
            "env": {},
            "error": f"Unknown auth_mode: {auth_mode}",
            "model": agent_model,
        }

    except Exception as e:
        logger.error("Failed to retrieve CLI auth config: %s", e)
        # Graceful fallback: check host env vars directly
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if api_key:
            return {
                "auth_mode": "gemini_api_key",
                "env": {"GEMINI_API_KEY": api_key},
                "warning": f"system_settings unavailable ({e}), using env fallback",
            }
        return {
            "auth_mode": "unknown",
            "env": {},
            "error": f"system_settings unavailable and no env fallback: {e}",
        }


@router.get("/agent-context")
async def get_agent_context():
    """Return dynamic context for agent system instruction.

    Reads available tables from WorkspaceQueryDatabaseTool which
    dynamically collects ``queryable_tables`` from installed pack
    manifests.  Each table's column schema is fetched from the DB.

    Returns:
        JSON with table schemas, role, data_tool, and data_guidance.
    """
    try:
        from ...services.tools.workspace_tools import WorkspaceQueryDatabaseTool

        # Instantiate to trigger dynamic table collection from registry
        tool = WorkspaceQueryDatabaseTool()
        tables = sorted(tool.ALLOWED_TABLES)
    except Exception as e:
        logger.warning("Failed to read ALLOWED_TABLES: %s", e)
        tables = []

    # Dynamically fetch column schemas from the database
    table_schemas = {}
    if tables:
        try:
            import psycopg2
            import psycopg2.extras
            import os

            db_url = (
                os.environ.get("DATABASE_URL_CORE")
                or os.environ.get("DATABASE_URL")
                or "postgresql://mindscape:mindscape_password@postgres:5432/mindscape_core"
            )
            conn = psycopg2.connect(db_url)
            try:
                conn.set_session(readonly=True, autocommit=True)
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                # Single query for all allowed tables
                placeholders = ",".join(["%s"] * len(tables))
                cur.execute(
                    f"SELECT table_name, column_name, data_type "
                    f"FROM information_schema.columns "
                    f"WHERE table_name IN ({placeholders}) "
                    f"ORDER BY table_name, ordinal_position",
                    tuple(tables),
                )
                for row in cur.fetchall():
                    tname = row["table_name"]
                    col = row["column_name"]
                    dtype = row["data_type"]
                    table_schemas.setdefault(tname, []).append(f"{col} ({dtype})")
                cur.close()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to fetch column schemas: %s", e)

    return {
        "tables": tables,
        "table_schemas": table_schemas,
        "role": (
            "You are a Mindscape AI workspace assistant. "
            "You have access to MCP tools to query and manage workspace data."
        ),
        "data_tool": "mindscape_tool_default_workspace_query_database",
        "data_guidance": (
            "For any question about data, analytics, accounts, targets, "
            "posts, or personas, use the mindscape_tool_default_workspace_query_database "
            "tool to query the PostgreSQL database. Do NOT browse files to find data. "
            "Always provide the actual data in your response. "
            "IMPORTANT: Always reply in the same language the user used."
        ),
        "installed_pack_guides": _get_pack_agent_guides(),
    }


def _get_pack_agent_guides() -> list:
    """Load agent_guide content from **enabled** packs only.

    Security:
      - Path traversal guard: guide_ref is resolved and checked to stay
        within the pack directory.
      - Only enabled packs are considered (via ``list_enabled_pack_ids``).
      - Total budget cap prevents prompt size explosion.
    """
    import os

    MAX_PER_GUIDE = 500
    MAX_TOTAL_CHARS = int(os.environ.get("AGENT_GUIDE_BUDGET", "3000"))

    guides: list = []
    try:
        from ...capabilities.registry import get_registry, load_capabilities
        from ...services.stores.installed_packs_store import InstalledPacksStore

        registry = get_registry()

        # Lazy-load if registry is empty (dual-import-path singleton issue)
        if not registry.capabilities:
            load_capabilities()

        store = InstalledPacksStore()
        enabled_ids = set(store.list_enabled_pack_ids())

        for code in enabled_ids:
            cap_info = registry.capabilities.get(code)
            if not cap_info:
                continue
            manifest = cap_info.get("manifest", {})
            guide_ref = manifest.get("agent_guide")
            if not guide_ref:
                continue
            directory = cap_info.get("directory")
            if not directory:
                continue

            # Path traversal guard
            guide_path = (directory / guide_ref).resolve()
            if not guide_path.is_relative_to(directory.resolve()):
                logger.warning(
                    "Blocked path traversal in agent_guide for %s: %s",
                    code,
                    guide_ref,
                )
                continue
            if not guide_path.exists():
                continue

            content = guide_path.read_text(encoding="utf-8").strip()[:MAX_PER_GUIDE]
            guides.append(
                {
                    "pack_code": code,
                    "display_name": manifest.get("display_name", code),
                    "guide": content,
                }
            )

        # Deterministic order + total budget cap
        guides.sort(key=lambda g: g["pack_code"])
        total = 0
        capped: list = []
        for g in guides:
            if total + len(g["guide"]) > MAX_TOTAL_CHARS:
                break
            capped.append(g)
            total += len(g["guide"])

        truncated_count = len(guides) - len(capped)
        if truncated_count > 0:
            logger.info(
                "Agent guide budget reached: kept %d/%d guides (%d chars)",
                len(capped),
                len(guides),
                total,
            )

        result = capped
        if truncated_count > 0:
            # Attach metadata for observability
            result = capped  # still a list; caller can check length vs total
    except Exception as e:
        logger.warning("Failed to load pack agent guides: %s", e)
        result = []
        truncated_count = 0
    return result
