"""
CLI Token Endpoint

Returns auth environment variables for CLI bridge processes.
Reads the configured auth mode and credentials from system_settings,
returning them as env-var key-value pairs that the bridge or runtime
injects into CLI subprocesses.

Supported modes:
  - Gemini CLI:
      - gca             : GOOGLE_CLOUD_ACCESS_TOKEN + GOOGLE_GENAI_USE_GCA
      - gemini_api_key  : GEMINI_API_KEY
      - vertex_ai       : GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION
  - Codex CLI:
      - openai_api_key  : OPENAI_API_KEY
      - host_session    : host login, optionally isolated via runtime pool env
  - Claude Code CLI:
      - anthropic_api_key: ANTHROPIC_API_KEY
      - host_session     : empty env, host token is expected
"""

import hashlib
import logging
import os
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterHostSessionRuntimeRequest(BaseModel):
    workspace_id: str = Field(..., description="Workspace that owns this runtime")
    surface: str = Field(..., description="CLI surface, e.g. codex_cli")
    owner_user_id: Optional[str] = Field(
        default=None,
        description="Optional workspace owner hint to avoid reloading workspace state",
    )
    client_id: Optional[str] = Field(
        default=None,
        description="Connected bridge client id for traceability",
    )
    runtime_id: Optional[str] = Field(
        default=None,
        description="Optional explicit runtime id override",
    )
    runtime_name: Optional[str] = Field(
        default=None,
        description="Optional display name override",
    )
    pool_group: Optional[str] = Field(
        default=None,
        description="Optional pool group override",
    )
    pool_enabled: bool = Field(
        default=True,
        description="Whether this runtime participates in pool rotation",
    )
    pool_priority: int = Field(
        default=0,
        description="Lower values are selected earlier within a pool",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime metadata such as CODEX_HOME/HOME/XDG paths",
    )


def _default_pool_group_for_surface(surface: str) -> Optional[str]:
    normalized = (surface or "").strip().lower()
    if normalized == "codex_cli":
        return "codex-cli-pool"
    if normalized == "gemini_cli":
        return "gca-pool"
    return None


def _load_workspace_owner_user_id(workspace_id: str) -> Optional[str]:
    if not workspace_id:
        return None
    try:
        from ...services.stores.postgres.workspaces_store import PostgresWorkspacesStore

        workspace = PostgresWorkspacesStore().get_workspace_sync(workspace_id)
        return getattr(workspace, "owner_user_id", None) if workspace else None
    except Exception:
        logger.exception(
            "Failed to resolve workspace owner for host-session runtime registration: %s",
            workspace_id,
        )
        return None


def _stable_host_session_runtime_id(
    *,
    owner_user_id: str,
    surface: str,
    client_id: Optional[str],
    metadata: dict[str, Any],
    explicit_runtime_id: Optional[str] = None,
) -> str:
    explicit = str(explicit_runtime_id or "").strip()
    if explicit:
        return explicit

    home_hint = ""
    for key in (
        "CODEX_HOME",
        "codex_home",
        "host_session_home",
        "HOME",
        "XDG_CONFIG_HOME",
    ):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            home_hint = value.strip()
            break
    if not home_hint:
        home_hint = str(client_id or "default").strip() or "default"

    digest = hashlib.sha1(
        f"{owner_user_id}|{surface}|{home_hint}".encode("utf-8")
    ).hexdigest()[:12]
    normalized_surface = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "-"
        for ch in (surface or "cli")
    ).strip("-") or "cli"
    return f"runtime-{normalized_surface}-{digest}"


def _upsert_host_session_runtime(
    *,
    owner_user_id: str,
    request: RegisterHostSessionRuntimeRequest,
) -> dict[str, Any]:
    try:
        from ...database.session import get_db_postgres as get_db
    except ImportError:
        try:
            from ...database import get_db_postgres as get_db
        except ImportError:
            from mindscape.di.providers import get_db_session as get_db

    from ...models.runtime_environment import RuntimeEnvironment

    db = next(get_db())
    try:
        runtime_id = _stable_host_session_runtime_id(
            owner_user_id=owner_user_id,
            surface=request.surface,
            client_id=request.client_id,
            metadata=request.metadata,
            explicit_runtime_id=request.runtime_id,
        )
        runtime = (
            db.query(RuntimeEnvironment)
            .filter(RuntimeEnvironment.id == runtime_id)
            .first()
        )
        metadata = dict(request.metadata or {})
        metadata.update(
            {
                "surface": request.surface,
                "registered_via": "host_session_bridge",
                "last_workspace_id": request.workspace_id,
                "last_client_id": request.client_id,
            }
        )
        pool_group = request.pool_group or _default_pool_group_for_surface(request.surface)
        runtime_name = (
            str(request.runtime_name or "").strip()
            or f"{request.surface} host session"
        )
        config_url = f"/settings/runtime-environments/{runtime_id}"

        if runtime is None:
            runtime = RuntimeEnvironment(
                id=runtime_id,
                user_id=owner_user_id,
                name=runtime_name,
                description=f"Auto-registered host session for {request.surface}",
                icon="terminal",
                config_url=config_url,
                auth_type="host_session",
                auth_config={},
                extra_metadata=metadata,
                status="active",
                auth_status="connected",
                is_default=False,
                supports_dispatch=True,
                supports_cell=True,
                recommended_for_dispatch=False,
                pool_group=pool_group,
                pool_enabled=request.pool_enabled,
                pool_priority=request.pool_priority,
                last_error_code=None,
            )
            db.add(runtime)
        else:
            if runtime.user_id != owner_user_id:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Runtime id collision for '{runtime_id}' while registering "
                        f"{request.surface} host session"
                    ),
                )
            runtime.name = runtime_name
            runtime.description = f"Auto-registered host session for {request.surface}"
            runtime.icon = runtime.icon or "terminal"
            runtime.config_url = config_url
            runtime.auth_type = "host_session"
            runtime.auth_config = {}
            existing_meta = dict(runtime.extra_metadata or {})
            existing_meta.update(metadata)
            runtime.extra_metadata = existing_meta
            runtime.status = "active"
            runtime.auth_status = "connected"
            runtime.pool_group = pool_group
            runtime.pool_enabled = request.pool_enabled
            runtime.pool_priority = request.pool_priority
            runtime.last_error_code = None

        home_value = str(metadata.get("HOME") or "").strip()
        codex_home_value = str(metadata.get("CODEX_HOME") or "").strip()
        if home_value and codex_home_value:
            candidates = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.user_id == owner_user_id,
                    RuntimeEnvironment.auth_type == "host_session",
                )
                .all()
            )
            for candidate in candidates:
                if candidate.id == runtime.id:
                    continue
                candidate_meta = dict(candidate.extra_metadata or {})
                candidate_surface = str(candidate_meta.get("surface") or "").strip().lower()
                candidate_home = str(candidate_meta.get("HOME") or "").strip()
                candidate_codex_home = str(candidate_meta.get("CODEX_HOME") or "").strip()
                if candidate_surface != request.surface:
                    continue
                if candidate_home != home_value:
                    continue
                if candidate_codex_home:
                    continue
                if candidate.pool_group != pool_group:
                    continue
                candidate.pool_enabled = False
                candidate_meta["shadowed_by_runtime_id"] = runtime.id
                candidate.extra_metadata = candidate_meta

        db.commit()
        db.refresh(runtime)
        payload = runtime.to_dict(include_sensitive=False)
        payload["runtime_id"] = runtime.id
        payload["owner_user_id"] = owner_user_id
        return payload
    finally:
        db.close()

def _get_codex_pool_bundle(
    workspace_id: str | None = None,
    auth_workspace_id: str | None = None,
    source_workspace_id: str | None = None,
) -> dict:
    try:
        from ...services.codex_pool_service import CodexPoolService
        from ...services.codex_workspace_resolver import CodexWorkspaceResolver

        selection = None
        if workspace_id:
            try:
                selection = CodexWorkspaceResolver().resolve(
                    workspace_id=workspace_id,
                    auth_workspace_id=auth_workspace_id,
                    source_workspace_id=source_workspace_id,
                )
            except ValueError:
                logger.debug(
                    "Workspace-scoped Codex pool selection not configured for workspace %s",
                    workspace_id,
                )

        preferred_runtime_id = selection.selected_runtime_id if selection else None
        allow_fallback = not bool(preferred_runtime_id)
        pool_result = CodexPoolService().get_active_auth_bundle(
            preferred_runtime_id=preferred_runtime_id,
            allow_fallback=allow_fallback,
        )
        if "env" in pool_result and selection:
            pool_result.update(
                {
                    "requested_workspace_id": selection.requested_workspace_id,
                    "effective_workspace_id": selection.effective_workspace_id,
                    "auth_workspace_id": selection.auth_workspace_id,
                    "source_workspace_id": selection.source_workspace_id,
                    "selection_reason": selection.selection_reason,
                    "selection_trace": list(selection.trace),
                }
            )
        return pool_result
    except Exception:
        logger.exception("Codex pool token lookup failed")
        return {
            "error": "Codex pool token lookup failed",
        }


def _get_gca_token(
    workspace_id: str | None = None,
    auth_workspace_id: str | None = None,
    source_workspace_id: str | None = None,
) -> dict:
    """Retrieve Google IDP access token from connected GCA runtimes.

    Queries all GCA runtimes (id LIKE 'gca-%') with auth_status='connected',
    ordered by 'gca-local' first. Iterates through the pool: if one runtime's
    token is expired and refresh fails, falls through to the next runtime.

    Returns:
        dict with env vars and selected_runtime_id, or error details.
    """
    try:
        from ...services.gca_pool_service import GCAPoolService
        from ...services.gca_workspace_resolver import GCAWorkspaceResolver

        selection = None
        if workspace_id:
            selection = GCAWorkspaceResolver().resolve(
                workspace_id=workspace_id,
                auth_workspace_id=auth_workspace_id,
                source_workspace_id=source_workspace_id,
            )
            if selection.selected_runtime_id:
                pool_result = GCAPoolService().get_active_token(
                    preferred_runtime_id=selection.selected_runtime_id,
                    allow_fallback=False,
                )
            else:
                pool_result = GCAPoolService().get_active_token()
        else:
            pool_result = GCAPoolService().get_active_token()
        if "env" in pool_result:
            if selection:
                pool_result.update(
                    {
                        "requested_workspace_id": selection.requested_workspace_id,
                        "effective_workspace_id": selection.effective_workspace_id,
                        "auth_workspace_id": selection.auth_workspace_id,
                        "source_workspace_id": selection.source_workspace_id,
                        "selection_reason": selection.selection_reason,
                        "selection_trace": list(selection.trace),
                    }
                )
            return pool_result
        if selection:
            return {
                "error": pool_result.get("error", "workspace-scoped GCA selection failed"),
                "requested_workspace_id": selection.requested_workspace_id,
                "effective_workspace_id": selection.effective_workspace_id,
                "auth_workspace_id": selection.auth_workspace_id,
                "source_workspace_id": selection.source_workspace_id,
                "selection_reason": selection.selection_reason,
                "selection_trace": list(selection.trace),
            }
    except Exception:
        if workspace_id:
            logger.exception("Workspace-scoped GCA token lookup failed")
            return {
                "error": f"Workspace-scoped GCA token lookup failed for workspace {workspace_id}",
            }
        logger.exception("GCA pool token lookup failed, falling back to legacy selector")

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
                RuntimeEnvironment.auth_status.in_(("connected", "expired")),
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

            if runtime.auth_status != "connected":
                runtime.auth_status = "connected"
                db.commit()

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
        runtime.auth_status = "connected"
        db.commit()

        logger.info("IDP token refreshed successfully, expires_in=%s", expires_in)
        return new_access_token

    except Exception as e:
        logger.error("Google IDP token refresh failed: %s", e)
        return None


@router.get("/cli-token")
async def get_cli_token(
    workspace_id: str | None = Query(None),
    auth_workspace_id: str | None = Query(None),
    source_workspace_id: str | None = Query(None),
    surface: str | None = Query(None),
):
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
        surface_name = (surface or "gemini_cli").strip().lower()

        if surface_name == "codex_cli":
            pool_result = _get_codex_pool_bundle(
                workspace_id=workspace_id,
                auth_workspace_id=auth_workspace_id,
                source_workspace_id=source_workspace_id,
            )
            if "env" in pool_result:
                return {
                    "auth_mode": pool_result.get("auth_mode", "host_session"),
                    "env": pool_result.get("env", {}),
                    "selected_runtime_id": pool_result.get("selected_runtime_id"),
                    "available_runtime_count": pool_result.get(
                        "available_runtime_count"
                    ),
                    "available_quota_scope_count": pool_result.get(
                        "available_quota_scope_count"
                    ),
                    "requested_workspace_id": pool_result.get("requested_workspace_id"),
                    "effective_workspace_id": pool_result.get("effective_workspace_id"),
                    "auth_workspace_id": pool_result.get("auth_workspace_id"),
                    "source_workspace_id": pool_result.get("source_workspace_id"),
                    "selection_reason": pool_result.get("selection_reason"),
                    "selection_trace": pool_result.get("selection_trace", []),
                }

            api_key = settings.get("openai_api_key", "")
            if not api_key:
                api_key = os.environ.get("OPENAI_API_KEY", "")
            if api_key:
                return {
                    "auth_mode": "openai_api_key",
                    "env": {"OPENAI_API_KEY": api_key},
                }
            return {
                "auth_mode": "host_session",
                "env": {},
                "warning": pool_result.get("error"),
                "note": "Codex CLI will use any credentials already stored on the host.",
            }

        if surface_name == "claude_code_cli":
            api_key = settings.get("claude_api_key", "")
            if not api_key:
                api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key:
                return {
                    "auth_mode": "anthropic_api_key",
                    "env": {"ANTHROPIC_API_KEY": api_key},
                }
            return {
                "auth_mode": "host_session",
                "env": {},
                "note": "Claude Code CLI will use any credentials already stored on the host.",
            }

        auth_mode = settings.get("gemini_cli_auth_mode", "gca")
        agent_model = settings.get("agent_cli_model", "gemini-2.5-pro")

        # ── GCA mode: return stored Google IDP token ──
        if auth_mode == "gca":
            result = _get_gca_token(
                workspace_id=workspace_id,
                auth_workspace_id=auth_workspace_id,
                source_workspace_id=source_workspace_id,
            )
            if "error" in result:
                logger.warning("GCA token retrieval failed: %s", result["error"])
                return {
                    "auth_mode": "gca",
                    "env": {},
                    "error": result["error"],
                    "model": agent_model,
                    "requested_workspace_id": result.get("requested_workspace_id"),
                    "effective_workspace_id": result.get("effective_workspace_id"),
                    "auth_workspace_id": result.get("auth_workspace_id"),
                    "source_workspace_id": result.get("source_workspace_id"),
                    "selection_reason": result.get("selection_reason"),
                    "selection_trace": result.get("selection_trace", []),
                }
            return {
                "auth_mode": "gca",
                "env": result["env"],
                "model": agent_model,
                "selected_runtime_id": result.get("selected_runtime_id"),
                "requested_workspace_id": result.get("requested_workspace_id"),
                "effective_workspace_id": result.get("effective_workspace_id"),
                "auth_workspace_id": result.get("auth_workspace_id"),
                "source_workspace_id": result.get("source_workspace_id"),
                "selection_reason": result.get("selection_reason"),
                "selection_trace": result.get("selection_trace", []),
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
        surface_name = (surface or "gemini_cli").strip().lower()
        if surface_name == "codex_cli":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            return {
                "auth_mode": "openai_api_key" if api_key else "host_session",
                "env": {"OPENAI_API_KEY": api_key} if api_key else {},
                "warning": f"system_settings unavailable ({e}), using host fallback",
            }
        if surface_name == "claude_code_cli":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            return {
                "auth_mode": "anthropic_api_key" if api_key else "host_session",
                "env": {"ANTHROPIC_API_KEY": api_key} if api_key else {},
                "warning": f"system_settings unavailable ({e}), using host fallback",
            }
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


@router.post("/cli-runtime/register-host-session")
async def register_host_session_runtime(
    request: RegisterHostSessionRuntimeRequest,
) -> dict[str, Any]:
    surface_name = (request.surface or "").strip().lower()
    if surface_name != "codex_cli":
        raise HTTPException(
            status_code=400,
            detail=f"Host-session runtime registration is not implemented for {surface_name}",
        )

    owner_user_id = str(request.owner_user_id or "").strip()
    if not owner_user_id:
        owner_user_id = _load_workspace_owner_user_id(request.workspace_id) or ""
    if not owner_user_id:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace not found or owner unavailable: {request.workspace_id}",
        )

    runtime = _upsert_host_session_runtime(
        owner_user_id=owner_user_id,
        request=request,
    )
    return {
        "registered": True,
        "runtime_id": runtime.get("runtime_id") or runtime.get("id"),
        "owner_user_id": owner_user_id,
        "runtime": runtime,
    }


@router.post("/runtime-quota-exhausted")
async def report_runtime_quota_exhausted(
    runtime_id: str = Query(...),
    surface: str = Query(...),
):
    surface_name = (surface or "").strip().lower()
    if not runtime_id.strip():
        return {"reported": False, "error": "runtime_id is required"}

    if surface_name == "codex_cli":
        from ...services.codex_pool_service import CodexPoolService

        result = CodexPoolService().report_quota_exhausted(runtime_id.strip())
        if result is None:
            return {"reported": False, "error": f"Unknown Codex runtime: {runtime_id}"}
        return {
            "reported": True,
            "surface": surface_name,
            "runtime_id": runtime_id.strip(),
            "cooldown_until": result.get("cooldown_until"),
        }

    if surface_name == "gemini_cli":
        from ...services.gca_pool_service import GCAPoolService

        result = GCAPoolService().report_quota_exhausted(runtime_id.strip())
        if result is None:
            return {"reported": False, "error": f"Unknown GCA runtime: {runtime_id}"}
        return {
            "reported": True,
            "surface": surface_name,
            "runtime_id": runtime_id.strip(),
            "cooldown_until": result.get("cooldown_until"),
        }

    return {
        "reported": False,
        "error": f"Quota reporting is not implemented for surface '{surface_name}'",
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
        from ...services.capability_registry import get_registry, load_capabilities
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
