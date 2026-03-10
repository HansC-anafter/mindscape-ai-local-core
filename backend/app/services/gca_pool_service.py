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

    def get_active_token(
        self,
        preferred_runtime_id: Optional[str] = None,
        allow_fallback: bool = True,
    ) -> Dict[str, Any]:
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
            if preferred_runtime_id:
                preferred = next(
                    (runtime for runtime in runtimes if runtime.id == preferred_runtime_id),
                    None,
                )
                if not preferred and not allow_fallback:
                    return {
                        "error": f"Preferred GCA runtime unavailable: {preferred_runtime_id}",
                    }
                if preferred:
                    runtimes = (
                        [preferred]
                        + [runtime for runtime in runtimes if runtime.id != preferred_runtime_id]
                    )
                elif not preferred and allow_fallback:
                    logger.warning(
                        "Preferred GCA runtime %s unavailable, falling back to pool ordering",
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

            if preferred_runtime_id and not allow_fallback:
                return {
                    "error": f"Preferred GCA runtime unavailable: {preferred_runtime_id}",
                }
            return {"error": "No available GCA accounts in pool"}
        finally:
            db.close()

    def preview_active_runtime(
        self,
        preferred_runtime_id: Optional[str] = None,
        allow_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Return a safe, non-secret preview of current pool selection.

        This is intended for UI/status rendering. It does not emit auth env vars
        and does not mutate pool state.
        """
        accounts = self.list_pool()
        now = datetime.now(timezone.utc)

        available_accounts = sorted(
            [account for account in accounts if self._is_account_available(account, now)],
            key=self._pool_sort_key,
        )
        cooling_accounts = sorted(
            [account for account in accounts if self._is_account_cooling(account, now)],
            key=lambda account: self._parse_iso_timestamp(account.get("cooldown_until"))
            or datetime.max.replace(tzinfo=timezone.utc),
        )

        preferred_account = None
        if preferred_runtime_id:
            preferred_account = next(
                (account for account in accounts if account["id"] == preferred_runtime_id),
                None,
            )
            if preferred_account and self._is_account_available(preferred_account, now):
                return {
                    "selected_runtime_id": preferred_account["id"],
                    "account": preferred_account,
                    "status": "available",
                    "available_count": len(available_accounts),
                    "cooling_count": len(cooling_accounts),
                    "pool_count": len(accounts),
                    "next_reset_at": (
                        cooling_accounts[0]["cooldown_until"] if cooling_accounts else None
                    ),
                }
            if preferred_runtime_id and not allow_fallback:
                cooldown_until = (
                    preferred_account.get("cooldown_until") if preferred_account else None
                )
                return {
                    "error": f"Preferred GCA runtime unavailable: {preferred_runtime_id}",
                    "selected_runtime_id": None,
                    "account": preferred_account,
                    "status": (
                        "cooldown"
                        if preferred_account
                        and self._is_account_cooling(preferred_account, now)
                        else "unavailable"
                    ),
                    "cooldown_until": cooldown_until,
                    "available_count": len(available_accounts),
                    "cooling_count": len(cooling_accounts),
                    "pool_count": len(accounts),
                    "next_reset_at": cooldown_until
                    or (cooling_accounts[0]["cooldown_until"] if cooling_accounts else None),
                }

        if available_accounts:
            selected = available_accounts[0]
            result: Dict[str, Any] = {
                "selected_runtime_id": selected["id"],
                "account": selected,
                "status": "available",
                "available_count": len(available_accounts),
                "cooling_count": len(cooling_accounts),
                "pool_count": len(accounts),
                "next_reset_at": (
                    cooling_accounts[0]["cooldown_until"] if cooling_accounts else None
                ),
            }
            if preferred_account and preferred_runtime_id and preferred_account["id"] != selected["id"]:
                result["preferred_runtime_id"] = preferred_runtime_id
                result["preferred_status"] = (
                    "cooldown"
                    if self._is_account_cooling(preferred_account, now)
                    else "unavailable"
                )
            return result

        return {
            "error": "No enabled GCA pool account is currently available",
            "selected_runtime_id": None,
            "account": None,
            "status": "unavailable",
            "available_count": 0,
            "cooling_count": len(cooling_accounts),
            "pool_count": len(accounts),
            "next_reset_at": cooling_accounts[0]["cooldown_until"] if cooling_accounts else None,
        }

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
            runtime.auth_status = "connected"
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

    @staticmethod
    def _parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    @classmethod
    def _is_account_cooling(
        cls,
        account: Dict[str, Any],
        now: datetime,
    ) -> bool:
        cooldown_until = cls._parse_iso_timestamp(account.get("cooldown_until"))
        return bool(cooldown_until and cooldown_until > now)

    @classmethod
    def _is_account_available(
        cls,
        account: Dict[str, Any],
        now: datetime,
    ) -> bool:
        return (
            account.get("pool_enabled") is True
            and account.get("auth_status") in ("connected", "expired")
            and not cls._is_account_cooling(account, now)
        )

    @classmethod
    def _pool_sort_key(cls, account: Dict[str, Any]) -> tuple[Any, datetime]:
        last_used_at = cls._parse_iso_timestamp(account.get("last_used_at"))
        if last_used_at is None:
            last_used_at = datetime.fromtimestamp(0, tz=timezone.utc)
        return (account.get("pool_priority", 0), last_used_at)
