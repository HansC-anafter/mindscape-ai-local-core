"""Account-home Codex auth source inventory.

This service only inspects materialized auth files. It does not select a runtime,
does not probe quota, and does not treat browser state as executable auth unless
an adapter has already written an account-home auth.json.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from backend.app.services.codex_pool_health import read_health_metadata


_SUPPORTED_AUTH_TYPES = frozenset({"host_session", "none"})


@dataclass(frozen=True)
class CodexAuthSource:
    source_type: str
    login_email: Optional[str]
    account_key: Optional[str]
    codex_home: str
    auth_json_path: str
    auth_mtime_ns: Optional[int]
    auth_size: Optional[int]
    has_access: bool
    has_refresh: bool
    source_event_id: str
    runtime_id: Optional[str] = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "login_email": self.login_email,
            "account_key": self.account_key,
            "codex_home": self.codex_home,
            "auth_json_path": self.auth_json_path,
            "auth_mtime_ns": self.auth_mtime_ns,
            "auth_size": self.auth_size,
            "has_access": self.has_access,
            "has_refresh": self.has_refresh,
            "source_event_id": self.source_event_id,
            "runtime_id": self.runtime_id,
        }


class CodexAccountHomeAuthSourceService:
    """Inventory materialized Codex account-home auth.json sources."""

    def __init__(
        self,
        *,
        runtime_loader: Optional[Callable[[], list[Any]]] = None,
        runtime_commit: Optional[Callable[[list[Any]], None]] = None,
        primary_codex_home: Optional[str] = None,
        managed_pool_root: Optional[str] = None,
        include_non_runtime_sources: Optional[bool] = None,
    ) -> None:
        self._runtime_loader = runtime_loader
        self._runtime_commit = runtime_commit
        self._primary_codex_home = primary_codex_home
        self._managed_pool_root = managed_pool_root
        self._include_non_runtime_sources = (
            runtime_loader is None
            if include_non_runtime_sources is None
            else bool(include_non_runtime_sources)
        )

    def inventory_sources(
        self,
        *,
        emails: Optional[set[str]] = None,
        persist_runtime_metadata: bool = False,
    ) -> list[dict[str, Any]]:
        normalized_emails = {
            str(email or "").strip().lower()
            for email in (emails or set())
            if str(email or "").strip()
        }
        if (
            persist_runtime_metadata
            and self._runtime_loader is None
            and self._runtime_commit is None
        ):
            return self._inventory_database_sources(normalized_emails)
        runtimes = self._load_runtimes()
        updated_runtimes: list[Any] = []
        sources: list[CodexAuthSource] = []
        for runtime in runtimes:
            source = self.source_for_runtime(runtime)
            if source is None:
                continue
            if normalized_emails and str(source.login_email or "").lower() not in normalized_emails:
                continue
            sources.append(source)
            if persist_runtime_metadata:
                metadata = dict(getattr(runtime, "extra_metadata", None) or {})
                metadata.update(self.metadata_for_source(source))
                runtime.extra_metadata = metadata
                updated_runtimes.append(runtime)

        if persist_runtime_metadata and updated_runtimes and self._runtime_commit is not None:
            self._runtime_commit(updated_runtimes)

        if self._include_non_runtime_sources:
            sources.extend(self._non_runtime_sources(normalized_emails))

        return [source.to_payload() for source in self._dedupe_sources(sources)]

    def _inventory_database_sources(self, emails: set[str]) -> list[dict[str, Any]]:
        from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

        service = CodexPoolService()
        db = service._get_db()
        RuntimeEnvironment = service._get_model()
        try:
            runtimes = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                    RuntimeEnvironment.pool_enabled.is_(True),
                    RuntimeEnvironment.auth_type.in_(tuple(_SUPPORTED_AUTH_TYPES)),
                )
                .all()
            )
            payloads: list[dict[str, Any]] = []
            changed = False
            for runtime in runtimes:
                source = self.source_for_runtime(runtime)
                if source is None:
                    continue
                if emails and str(source.login_email or "").lower() not in emails:
                    continue
                metadata = dict(getattr(runtime, "extra_metadata", None) or {})
                metadata.update(self.metadata_for_source(source))
                runtime.extra_metadata = metadata
                payloads.append(source.to_payload())
                changed = True
            if changed:
                db.commit()
            else:
                db.rollback()
            if self._include_non_runtime_sources:
                payloads.extend(
                    source.to_payload()
                    for source in self._non_runtime_sources(emails)
                )
            return list({(item["source_type"], item["auth_json_path"]): item for item in payloads}.values())
        finally:
            db.close()

    def source_for_runtime(self, runtime: Any) -> Optional[CodexAuthSource]:
        auth_type = str(getattr(runtime, "auth_type", "") or "").strip().lower()
        if auth_type not in _SUPPORTED_AUTH_TYPES:
            return None
        metadata = dict(getattr(runtime, "extra_metadata", None) or {})
        health = read_health_metadata(metadata, auth_type=auth_type)
        if str(health.get("seed_kind") or "").strip().lower() != "account_home":
            return None
        codex_home = str(
            metadata.get("CODEX_HOME")
            or metadata.get("codex_home")
            or metadata.get("host_session_home")
            or ""
        ).strip()
        if not codex_home:
            return None
        source = self.source_for_codex_home(
            codex_home,
            runtime_id=str(getattr(runtime, "id", "") or "").strip() or None,
            metadata=metadata,
        )
        return source

    @classmethod
    def source_for_codex_home(
        cls,
        codex_home: str,
        *,
        runtime_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        source_type: str = "account_home_auth_json",
    ) -> Optional[CodexAuthSource]:
        normalized_home = str(Path(os.path.expanduser(str(codex_home or ""))))
        if not normalized_home:
            return None
        auth_path = Path(normalized_home) / "auth.json"
        return cls.source_for_auth_path(
            auth_path,
            codex_home=normalized_home,
            runtime_id=runtime_id,
            metadata=metadata,
            source_type=source_type,
        )

    @classmethod
    def source_for_auth_path(
        cls,
        auth_path: str | Path,
        *,
        codex_home: str | Path,
        runtime_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        source_type: str = "account_home_auth_json",
    ) -> Optional[CodexAuthSource]:
        auth_path = Path(os.path.expanduser(str(auth_path or "")))
        normalized_home = str(Path(os.path.expanduser(str(codex_home or ""))))
        if not str(auth_path) or not normalized_home:
            return None
        try:
            stat = auth_path.stat()
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None

        identity = cls._identity_from_payload(payload, metadata or {})
        login_email = str(identity.get("login_email") or "").strip().lower() or None
        account_key = str(identity.get("account_key") or "").strip() or None
        tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
        has_access = bool(
            str(payload.get("OPENAI_API_KEY") or tokens.get("access_token") or "").strip()
        )
        has_refresh = bool(str(tokens.get("refresh_token") or "").strip())
        source_event_id = cls._source_event_id(
            auth_path=str(auth_path),
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
            login_email=login_email,
            account_key=account_key,
        )
        return CodexAuthSource(
            source_type=source_type,
            login_email=login_email,
            account_key=account_key,
            codex_home=normalized_home,
            auth_json_path=str(auth_path),
            auth_mtime_ns=stat.st_mtime_ns,
            auth_size=stat.st_size,
            has_access=has_access,
            has_refresh=has_refresh,
            source_event_id=source_event_id,
            runtime_id=runtime_id,
        )

    def _primary_codex_home_path(self) -> Path:
        configured = (
            self._primary_codex_home
            or os.environ.get("CODEX_HOME")
            or str(Path.home() / ".codex")
        )
        return Path(os.path.expanduser(str(configured)))

    def _managed_pool_root_path(self) -> Path:
        configured = (
            self._managed_pool_root
            or os.environ.get("MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT")
            or str(Path.home() / ".mindscape" / "runtime" / "codex-home-pool")
        )
        return Path(os.path.expanduser(str(configured)))

    def _non_runtime_sources(self, emails: set[str]) -> list[CodexAuthSource]:
        return []

    @staticmethod
    def _dedupe_sources(sources: list[CodexAuthSource]) -> list[CodexAuthSource]:
        unique: dict[tuple[str, str], CodexAuthSource] = {}
        for source in sources:
            unique[(source.source_type, source.auth_json_path)] = source
        return list(unique.values())

    @classmethod
    def metadata_for_source(cls, source: CodexAuthSource) -> dict[str, Any]:
        payload = {
            "auth_source_type": source.source_type,
            "auth_source_path": source.auth_json_path,
            "auth_source_event_id": source.source_event_id,
            "auth_mtime_ns": str(source.auth_mtime_ns) if source.auth_mtime_ns else None,
            "auth_size": str(source.auth_size) if source.auth_size else None,
            "codex_auth_mtime_ns": (
                str(source.auth_mtime_ns) if source.auth_mtime_ns else None
            ),
            "codex_auth_size": str(source.auth_size) if source.auth_size else None,
            "codex_auth_has_runtime_credentials": source.has_access or source.has_refresh,
            "auth_source_has_access": source.has_access,
            "auth_source_has_refresh": source.has_refresh,
        }
        if source.login_email:
            payload["login_email"] = source.login_email
        if source.account_key:
            payload["account_key"] = source.account_key
        return {key: value for key, value in payload.items() if value is not None}

    @classmethod
    def metadata_for_codex_home(
        cls,
        codex_home: str,
        *,
        metadata: Optional[dict[str, Any]] = None,
        source_type: str = "account_home_auth_json",
    ) -> dict[str, Any]:
        source = cls.source_for_codex_home(
            codex_home,
            metadata=metadata,
            source_type=source_type,
        )
        return cls.metadata_for_source(source) if source else {}

    @classmethod
    def identity_details_for_codex_home(cls, codex_home: str) -> dict[str, Any]:
        auth_path = Path(os.path.expanduser(str(codex_home or ""))) / "auth.json"
        try:
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return cls.identity_details_from_payload(payload)

    @classmethod
    def identity_details_from_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
        id_token_payload = cls._decode_jwt_payload(tokens.get("id_token"))
        auth_claims = (
            id_token_payload.get("https://api.openai.com/auth")
            if isinstance(id_token_payload.get("https://api.openai.com/auth"), dict)
            else {}
        )
        account_id = str(
            tokens.get("account_id") or auth_claims.get("chatgpt_account_id") or ""
        ).strip()
        user_id = str(
            auth_claims.get("chatgpt_user_id")
            or auth_claims.get("user_id")
            or id_token_payload.get("sub")
            or ""
        ).strip()
        plan_type = str(auth_claims.get("chatgpt_plan_type") or "").strip().lower()
        organizations = (
            auth_claims.get("organizations")
            if isinstance(auth_claims.get("organizations"), list)
            else []
        )
        default_org = next(
            (
                org
                for org in organizations
                if isinstance(org, dict) and bool(org.get("is_default"))
            ),
            None,
        )
        if default_org is None:
            default_org = next((org for org in organizations if isinstance(org, dict)), {})
        org_title = str(
            default_org.get("title")
            or default_org.get("name")
            or ""
            if isinstance(default_org, dict)
            else ""
        ).strip()
        org_id = str(default_org.get("id") or "" if isinstance(default_org, dict) else "").strip()
        org_role = str(
            default_org.get("role") or "" if isinstance(default_org, dict) else ""
        ).strip()
        org_plan_type = str(
            default_org.get("plan_type") or "" if isinstance(default_org, dict) else ""
        ).strip().lower()
        effective_plan_type = plan_type or org_plan_type
        scope_type = "unknown"
        if org_title.lower() == "personal" or effective_plan_type == "free":
            scope_type = "personal"
        elif org_title or org_id or effective_plan_type:
            scope_type = "workspace"
        scope_label = org_title or (
            "Personal" if scope_type == "personal" else "Workspace" if scope_type == "workspace" else ""
        )
        details: dict[str, Any] = {
            "auth_account_id": account_id,
            "auth_chatgpt_user_id": user_id,
            "account_scope_type": scope_type,
            "account_scope_label": scope_label,
            "account_scope_role": org_role,
            "account_plan_type": effective_plan_type,
            "account_organization_id": org_id,
            "account_organization_title": org_title,
            "account_organization_count": len(organizations),
        }
        return {key: value for key, value in details.items() if value not in ("", None)}

    def _load_runtimes(self) -> list[Any]:
        if self._runtime_loader is not None:
            return list(self._runtime_loader())

        from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

        service = CodexPoolService()
        db = service._get_db()
        RuntimeEnvironment = service._get_model()
        try:
            return (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                    RuntimeEnvironment.pool_enabled.is_(True),
                    RuntimeEnvironment.auth_type.in_(tuple(_SUPPORTED_AUTH_TYPES)),
                )
                .all()
            )
        finally:
            db.close()

    @staticmethod
    def _decode_jwt_payload(token: Any) -> dict[str, Any]:
        raw = str(token or "").strip()
        if raw.count(".") < 2:
            return {}
        try:
            encoded = raw.split(".", 2)[1]
            encoded += "=" * (-len(encoded) % 4)
            decoded = base64.urlsafe_b64decode(encoded.encode("utf-8"))
            payload = json.loads(decoded.decode("utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _identity_from_payload(
        cls,
        payload: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, str]:
        tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
        id_token_payload = cls._decode_jwt_payload(tokens.get("id_token"))
        auth_claims = (
            id_token_payload.get("https://api.openai.com/auth")
            if isinstance(id_token_payload.get("https://api.openai.com/auth"), dict)
            else {}
        )
        email = str(
            id_token_payload.get("email")
            or auth_claims.get("email")
            or metadata.get("login_email")
            or metadata.get("account_email")
            or ""
        ).strip().lower()
        principal = str(
            auth_claims.get("chatgpt_user_id")
            or auth_claims.get("user_id")
            or id_token_payload.get("sub")
            or ""
        ).strip()
        account_id = str(tokens.get("account_id") or "").strip()
        if account_id and principal:
            account_key = hashlib.sha256(
                f"account:{account_id}:user:{principal}".encode("utf-8")
            ).hexdigest()[:24]
        elif principal:
            account_key = hashlib.sha256(
                f"user:{principal}".encode("utf-8")
            ).hexdigest()[:24]
        else:
            account_key = (
                hashlib.sha256(f"account:{account_id}".encode("utf-8")).hexdigest()[:24]
                if account_id
                else str(metadata.get("account_key") or "").strip()
            )
        result: dict[str, str] = {}
        if email:
            result["login_email"] = email
        if account_key:
            result["account_key"] = account_key
        return result

    @staticmethod
    def _source_event_id(
        *,
        auth_path: str,
        mtime_ns: int,
        size: int,
        login_email: Optional[str],
        account_key: Optional[str],
    ) -> str:
        seed = "::".join(
            [
                auth_path,
                str(mtime_ns),
                str(size),
                login_email or "",
                account_key or "",
            ]
        )
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
