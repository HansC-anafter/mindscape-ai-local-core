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

from backend.app.services.runtime_route_registration import (
    sync_runtime_registration_metadata,
)
from backend.app.services.gca_pool_service_core.account_state import (
    count_recent_errors,
    is_account_available,
    is_account_cooling,
    parse_iso_timestamp,
    pool_sort_key,
    to_pool_dict,
)
from backend.app.services.gca_pool_service_core.preview import (
    build_active_runtime_preview,
)
from backend.app.services.gca_pool_service_core.token_refresh import (
    try_refresh_token,
)

logger = logging.getLogger(__name__)

# Cooldown backoff: 5min -> 15min -> 30min (capped)
BASE_COOLDOWN_SECONDS = 300
MAX_COOLDOWN_SECONDS = 1800
BACKOFF_MULTIPLIER = 3


class GCAPoolService:
    """Service for managing GCA multi-account pool."""

    @staticmethod
    def _commit_runtime_updates(db, *runtimes) -> None:
        seen: set[int] = set()
        for runtime in runtimes:
            if runtime is None:
                continue
            marker = id(runtime)
            if marker in seen:
                continue
            seen.add(marker)
            sync_runtime_registration_metadata(runtime)
        db.commit()

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
            self._commit_runtime_updates(db, runtime)
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
            self._commit_runtime_updates(db, runtime)
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
            self._commit_runtime_updates(db, runtime)
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

    def get_active_token(
        self,
        preferred_runtime_id: Optional[str] = None,
        allow_runtime_substitution: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Select the best available token from the pool.

        Uses priority ordering with cooldown awareness.
        Returns dict with 'env' and 'selected_runtime_id', or 'error'.
        """
        if allow_runtime_substitution is None:
            allow_runtime_substitution = False
        else:
            allow_runtime_substitution = bool(allow_runtime_substitution)
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
                    RuntimeEnvironment.auth_status.in_(("connected", "expired")),
                    or_(
                        RuntimeEnvironment.cooldown_until.is_(None),
                        RuntimeEnvironment.cooldown_until < now,
                    ),
                )
                .order_by(
                    RuntimeEnvironment.pool_priority.asc(),
                    RuntimeEnvironment.last_used_at.asc().nullsfirst(),
                )
                # Concurrent bridge turns may legitimately share the same
                # connected GCA account; skip_locked causes false "empty pool".
                .all()
            )

            auth_service = RuntimeAuthService()
            if not preferred_runtime_id and not allow_runtime_substitution:
                return {
                    "error": "No preferred GCA runtime configured; runtime substitution is disabled.",
                }
            if preferred_runtime_id:
                preferred = next(
                    (runtime for runtime in runtimes if runtime.id == preferred_runtime_id),
                    None,
                )
                if not preferred and not allow_runtime_substitution:
                    return {
                        "error": f"Preferred GCA runtime unavailable: {preferred_runtime_id}",
                    }
                if preferred:
                    runtimes = (
                        [preferred]
                        + [runtime for runtime in runtimes if runtime.id != preferred_runtime_id]
                    )
                elif not preferred and allow_runtime_substitution:
                    logger.warning(
                        "Preferred GCA runtime %s unavailable, using ordered pool candidates",
                        preferred_runtime_id,
                    )

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

                if runtime.auth_status != "connected":
                    runtime.auth_status = "connected"
                runtime.last_used_at = func.now()
                runtime.last_error_code = None
                self._commit_runtime_updates(db, runtime)

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

            if preferred_runtime_id and not allow_runtime_substitution:
                return {
                    "error": f"Preferred GCA runtime unavailable: {preferred_runtime_id}",
                }
            return {"error": "No available GCA accounts in pool"}
        finally:
            db.close()

    def preview_active_runtime(
        self,
        preferred_runtime_id: Optional[str] = None,
        allow_runtime_substitution: bool = False,
    ) -> Dict[str, Any]:
        """Return a safe, non-secret preview of current pool selection.

        This is intended for UI/status rendering. It does not emit auth env vars
        and does not mutate pool state.
        """
        accounts = self.list_pool()
        return build_active_runtime_preview(
            accounts,
            preferred_runtime_id=preferred_runtime_id,
            allow_runtime_substitution=allow_runtime_substitution,
        )

    def _try_refresh(self, runtime, auth_service, token_data, db):
        """Attempt token refresh. Returns new access_token or None."""
        return try_refresh_token(
            runtime,
            auth_service,
            token_data,
            db,
            self._commit_runtime_updates,
        )

    @staticmethod
    def _count_recent_errors(runtime) -> int:
        """Count consecutive quota errors for backoff calculation."""
        return count_recent_errors(runtime)

    @staticmethod
    def _to_pool_dict(runtime) -> Dict[str, Any]:
        """Convert runtime to pool-specific dict."""
        return to_pool_dict(runtime)

    @staticmethod
    def _parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
        return parse_iso_timestamp(value)

    @classmethod
    def _is_account_cooling(
        cls,
        account: Dict[str, Any],
        now: datetime,
    ) -> bool:
        return is_account_cooling(account, now)

    @classmethod
    def _is_account_available(
        cls,
        account: Dict[str, Any],
        now: datetime,
    ) -> bool:
        return is_account_available(account, now)

    @classmethod
    def _pool_sort_key(cls, account: Dict[str, Any]) -> tuple[Any, datetime]:
        return pool_sort_key(account)
