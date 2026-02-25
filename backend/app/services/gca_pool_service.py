"""
GCA Pool Service

Manages multi-account GCA pool: account lifecycle, quota-exhaustion
cooldown with exponential backoff, and pool-aware token selection.
"""

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

# Cooldown backoff: 5min -> 15min -> 30min (capped)
BASE_COOLDOWN_SECONDS = 300
MAX_COOLDOWN_SECONDS = 1800
BACKOFF_MULTIPLIER = 3


class GCAPoolService:
    """Service for managing GCA multi-account pool."""

    def _get_db(self):
        try:
            from backend.app.database.session import get_db_postgres as get_db
        except ImportError:
            try:
                from backend.app.database import get_db_postgres as get_db
            except ImportError:
                from mindscape.di.providers import get_db_session as get_db
        return next(get_db())

    def _get_model(self):
        from backend.app.models.runtime_environment import RuntimeEnvironment

        return RuntimeEnvironment

    def list_pool(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all accounts in the GCA pool."""
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
            query = db.query(RuntimeEnvironment).filter(
                RuntimeEnvironment.pool_group == "gca-pool",
            )
            if user_id:
                query = query.filter(RuntimeEnvironment.user_id == user_id)
            runtimes = query.order_by(RuntimeEnvironment.pool_priority.asc()).all()
            return [self._to_pool_dict(rt) for rt in runtimes]
        finally:
            db.close()

    def add_account(self, user_id: str) -> Dict[str, Any]:
        """Create a new pool runtime for OAuth enrollment.

        Returns the runtime dict (caller should redirect to OAuth authorize).
        """
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
            short_hash = uuid.uuid4().hex[:6]
            runtime_id = f"gca-{short_hash}"

            existing_count = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.pool_group == "gca-pool",
                    RuntimeEnvironment.user_id == user_id,
                )
                .count()
            )

            runtime = RuntimeEnvironment(
                id=runtime_id,
                user_id=user_id,
                name=f"GCA Account {existing_count + 1}",
                description="GCA pool account",
                config_url="",
                auth_type="oauth2",
                auth_status="disconnected",
                pool_group="gca-pool",
                pool_enabled=True,
                pool_priority=existing_count,
            )
            db.add(runtime)
            db.commit()
            db.refresh(runtime)
            logger.info("Created pool runtime %s for user %s", runtime_id, user_id)
            return self._to_pool_dict(runtime)
        finally:
            db.close()

    def remove_account(self, runtime_id: str) -> bool:
        """Remove an account from the pool."""
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
            runtime = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.id == runtime_id,
                    RuntimeEnvironment.pool_group == "gca-pool",
                )
                .first()
            )
            if not runtime:
                return False
            db.delete(runtime)
            db.commit()
            logger.info("Removed pool runtime %s", runtime_id)
            return True
        finally:
            db.close()

    def update_account(
        self,
        runtime_id: str,
        enabled: Optional[bool] = None,
        priority: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Toggle enabled state or set priority for a pool account."""
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
            runtime = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.id == runtime_id,
                    RuntimeEnvironment.pool_group == "gca-pool",
                )
                .first()
            )
            if not runtime:
                return None
            if enabled is not None:
                runtime.pool_enabled = enabled
            if priority is not None:
                runtime.pool_priority = priority
            db.commit()
            db.refresh(runtime)
            return self._to_pool_dict(runtime)
        finally:
            db.close()

    def report_quota_exhausted(self, runtime_id: str) -> Optional[Dict[str, Any]]:
        """Mark a runtime as quota-exhausted with exponential cooldown."""
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
            runtime = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.id == runtime_id,
                    RuntimeEnvironment.pool_group == "gca-pool",
                )
                .first()
            )
            if not runtime:
                return None

            now = datetime.now(timezone.utc)
            consecutive = self._count_recent_errors(runtime)
            cooldown_secs = min(
                BASE_COOLDOWN_SECONDS * (BACKOFF_MULTIPLIER**consecutive),
                MAX_COOLDOWN_SECONDS,
            )

            runtime.cooldown_until = now + timedelta(seconds=cooldown_secs)
            runtime.last_error_code = "429"
            db.commit()
            db.refresh(runtime)

            logger.info(
                "Runtime %s quota exhausted, cooldown %ds (consecutive=%d)",
                runtime_id,
                cooldown_secs,
                consecutive + 1,
            )
            return self._to_pool_dict(runtime)
        finally:
            db.close()

    def get_active_token(self) -> Dict[str, Any]:
        """Select the best available token from the pool.

        Uses priority ordering with cooldown awareness.
        Returns dict with 'env' and 'selected_runtime_id', or 'error'.
        """
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
            from backend.app.services.runtime_auth_service import RuntimeAuthService

            now = datetime.now(timezone.utc)
            runtimes = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.pool_group == "gca-pool",
                    RuntimeEnvironment.pool_enabled.is_(True),
                    RuntimeEnvironment.auth_status == "connected",
                    or_(
                        RuntimeEnvironment.cooldown_until.is_(None),
                        RuntimeEnvironment.cooldown_until < now,
                    ),
                )
                .order_by(
                    RuntimeEnvironment.pool_priority.asc(),
                    RuntimeEnvironment.last_used_at.asc().nullsfirst(),
                )
                .with_for_update(skip_locked=True)
                .all()
            )

            auth_service = RuntimeAuthService()
            for runtime in runtimes:
                token_data = auth_service.decrypt_token_blob(runtime.auth_config or {})
                if not token_data or not token_data.get("idp_access_token"):
                    continue

                idp_access_token = token_data["idp_access_token"]
                idp_expiry = token_data.get("idp_token_expiry", 0)

                if idp_expiry and time.time() > (idp_expiry - 60):
                    refreshed = self._try_refresh(runtime, auth_service, token_data, db)
                    if not refreshed:
                        continue
                    idp_access_token = refreshed

                runtime.last_used_at = func.now()
                runtime.last_error_code = None
                db.commit()

                import os

                gcp_project = token_data.get("gcp_project") or ""
                if not gcp_project:
                    gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")

                env = {
                    "GOOGLE_GENAI_USE_GCA": "true",
                    "GOOGLE_CLOUD_ACCESS_TOKEN": idp_access_token,
                }
                if gcp_project:
                    env["GOOGLE_CLOUD_PROJECT"] = gcp_project

                return {
                    "env": env,
                    "selected_runtime_id": runtime.id,
                }

            return {"error": "No available GCA accounts in pool"}
        finally:
            db.close()

    def _try_refresh(self, runtime, auth_service, token_data, db):
        """Attempt token refresh. Returns new access_token or None."""
        refresh_token = token_data.get("idp_refresh_token")
        if not refresh_token:
            return None

        from backend.app.routes.core.gca_constants import (
            get_gca_client_id,
            get_gca_client_secret,
        )
        import json
        import urllib.request
        import urllib.parse

        client_id = get_gca_client_id()
        client_secret = get_gca_client_secret()

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

            new_token = result.get("access_token")
            if not new_token:
                return None

            token_data["idp_access_token"] = new_token
            token_data["idp_token_expiry"] = time.time() + result.get(
                "expires_in", 3600
            )
            token_data.pop("google_client_id", None)
            token_data.pop("google_client_secret", None)

            runtime.auth_config = auth_service.encrypt_token_blob(token_data)
            db.commit()
            return new_token
        except Exception as e:
            logger.error("Token refresh failed for %s: %s", runtime.id, e)
            return None

    @staticmethod
    def _count_recent_errors(runtime) -> int:
        """Count consecutive quota errors for backoff calculation."""
        if not runtime.last_error_code or runtime.last_error_code != "429":
            return 0
        if not runtime.cooldown_until:
            return 0
        return 1

    @staticmethod
    def _to_pool_dict(runtime) -> Dict[str, Any]:
        """Convert runtime to pool-specific dict."""
        identity = None
        if runtime.auth_status == "connected" and runtime.auth_config:
            identity = runtime.auth_config.get("identity")
        return {
            "id": runtime.id,
            "email": identity,
            "auth_status": runtime.auth_status or "disconnected",
            "pool_enabled": runtime.pool_enabled,
            "pool_priority": runtime.pool_priority,
            "cooldown_until": (
                runtime.cooldown_until.isoformat() if runtime.cooldown_until else None
            ),
            "last_used_at": (
                runtime.last_used_at.isoformat() if runtime.last_used_at else None
            ),
            "last_error_code": runtime.last_error_code,
        }
