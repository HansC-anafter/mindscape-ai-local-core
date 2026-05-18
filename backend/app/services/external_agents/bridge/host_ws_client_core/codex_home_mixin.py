from .base import *


class HostBridgeCodexHomeMixin:

    def _should_auto_register_host_session_runtime(self) -> bool:
        if self.surface != "codex_cli":
            return False
        if _env_flag("MINDSCAPE_CODEX_POOL_AUTO_REGISTER", True):
            return True
        return _env_flag("MINDSCAPE_CLI_RUNTIME_AUTO_REGISTER", False)

    def _resolve_codex_seed_registry_path(self) -> Path:
        override = os.environ.get("MINDSCAPE_CODEX_HOME_SEED_REGISTRY", "").strip()
        if override:
            return Path(os.path.expanduser(override))
        return Path.home() / ".mindscape" / "codex_host_session_seeds.json"

    def _resolve_codex_managed_pool_root(self) -> Path:
        override = os.environ.get("MINDSCAPE_CODEX_HOME_MANAGED_POOL_ROOT", "").strip()
        if override:
            return Path(os.path.expanduser(override))
        return Path.home() / ".mindscape" / "runtime" / "codex-home-pool"

    def _load_codex_seed_registry(self) -> Dict[str, Dict[str, Any]]:
        path = self._codex_seed_registry_path
        if not path.exists():
            return {}

        try:
            raw_payload = path.read_text(encoding="utf-8").strip()
            if not raw_payload:
                return {}
            payload = json.loads(raw_payload)
        except Exception as exc:
            logger.warning("Failed to load Codex seed registry %s: %s", path, exc)
            return {}

        entries = payload.get("homes")
        if not isinstance(entries, list):
            return {}

        registry: Dict[str, Dict[str, Any]] = {}
        for item in entries:
            if not isinstance(item, dict):
                continue
            raw_path = str(item.get("path") or "").strip()
            if not raw_path:
                continue
            normalized = str(Path(os.path.expanduser(raw_path)))
            registry[normalized] = {
                "sources": self._normalize_seed_sources(item.get("sources")),
                "last_seen_at": str(item.get("last_seen_at") or "").strip(),
                "account_key": str(item.get("account_key") or "").strip(),
                "account_label": str(item.get("account_label") or "").strip(),
                "login_email": str(item.get("login_email") or "").strip().lower(),
                "auth_account_id": str(item.get("auth_account_id") or "").strip(),
                "auth_chatgpt_user_id": str(
                    item.get("auth_chatgpt_user_id") or ""
                ).strip(),
            }
        return registry

    def _write_codex_seed_registry(self, entries: Dict[str, Dict[str, Any]]) -> None:
        path = self._codex_seed_registry_path
        if not entries:
            return

        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "homes": [
                {
                    "path": codex_home,
                    "sources": sorted(meta.get("sources") or []),
                    "last_seen_at": meta.get("last_seen_at"),
                    "account_key": str(meta.get("account_key") or "").strip() or None,
                    "account_label": str(meta.get("account_label") or "").strip() or None,
                    "login_email": str(meta.get("login_email") or "").strip().lower()
                    or None,
                    "auth_account_id": str(meta.get("auth_account_id") or "").strip()
                    or None,
                    "auth_chatgpt_user_id": str(
                        meta.get("auth_chatgpt_user_id") or ""
                    ).strip()
                    or None,
                }
                for codex_home, meta in sorted(entries.items())
            ],
        }

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            serialized = json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
            temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temp_path.write_text(
                serialized,
                encoding="utf-8",
            )
            os.replace(temp_path, path)
        except Exception as exc:
            logger.warning("Failed to persist Codex seed registry %s: %s", path, exc)

    @staticmethod
    def _normalize_seed_sources(raw_sources: Any) -> set[str]:
        sources: set[str] = set()
        if isinstance(raw_sources, (list, tuple, set)):
            for item in raw_sources:
                value = str(item or "").strip().lower()
                if value:
                    sources.add(value)
            return sources
        value = str(raw_sources or "").strip().lower()
        if value:
            sources.add(value)
        return sources

    def _codex_home_has_login_trace(self, codex_home: str) -> bool:
        path = Path(codex_home)
        if not path.is_dir():
            return False

        auth_path = path / "auth.json"
        if not auth_path.is_file():
            return False

        try:
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Ignoring unreadable Codex auth trace: %s", auth_path)
            return False

        if not isinstance(payload, dict):
            return False

        auth_mode = str(payload.get("auth_mode") or "").strip()
        tokens = payload.get("tokens")
        api_key = str(payload.get("OPENAI_API_KEY") or "").strip()
        return bool(auth_mode or api_key or isinstance(tokens, dict))

    @staticmethod
    def _load_codex_auth_payload(codex_home: str) -> Dict[str, Any]:
        auth_path = Path(os.path.expanduser(codex_home)) / "auth.json"
        try:
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _codex_auth_file_signature(codex_home: str) -> Dict[str, Any]:
        auth_path = Path(os.path.expanduser(codex_home)) / "auth.json"
        try:
            stat = auth_path.stat()
        except OSError:
            return {}
        return {
            "codex_auth_mtime_ns": str(stat.st_mtime_ns),
            "codex_auth_size": str(stat.st_size),
        }

    @staticmethod
    def _auth_payload_has_runtime_credentials(payload: Dict[str, Any]) -> bool:
        tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
        return any(
            str(payload.get(key) or tokens.get(key) or "").strip()
            for key in ("OPENAI_API_KEY", "access_token", "refresh_token")
        )

    @staticmethod
    def _decode_jwt_payload(token: str) -> Dict[str, Any]:
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

    def _extract_codex_account_key(self, codex_home: str) -> str:
        payload = self._load_codex_auth_payload(codex_home)
        if not payload:
            return ""

        tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
        id_token_payload = self._decode_jwt_payload(tokens.get("id_token"))
        auth_claims = (
            id_token_payload.get("https://api.openai.com/auth")
            if isinstance(id_token_payload.get("https://api.openai.com/auth"), dict)
            else {}
        )

        account_id = str(tokens.get("account_id") or "").strip()
        principal_candidates = (
            str(auth_claims.get("chatgpt_user_id") or "").strip(),
            str(auth_claims.get("user_id") or "").strip(),
            str(id_token_payload.get("sub") or "").strip(),
            str(id_token_payload.get("email") or "").strip().lower(),
        )
        for principal in principal_candidates:
            if principal:
                if account_id:
                    return hashlib.sha256(
                        f"account:{account_id}:user:{principal}".encode("utf-8")
                    ).hexdigest()[:24]
                return hashlib.sha256(f"user:{principal}".encode("utf-8")).hexdigest()[:24]

        if account_id:
            return hashlib.sha256(f"account:{account_id}".encode("utf-8")).hexdigest()[:24]

        api_key = str(payload.get("OPENAI_API_KEY") or "").strip()
        if api_key:
            return hashlib.sha256(f"api_key:{api_key}".encode("utf-8")).hexdigest()[:24]

        refresh_token = str(tokens.get("refresh_token") or "").strip()
        if refresh_token:
            return hashlib.sha256(f"refresh:{refresh_token}".encode("utf-8")).hexdigest()[:24]

        return ""

    def _extract_codex_account_identity(self, codex_home: str) -> Dict[str, Any]:
        payload = self._load_codex_auth_payload(codex_home)
        seed_metadata = self._read_codex_managed_seed_metadata(codex_home)
        tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
        id_token_payload = self._decode_jwt_payload(tokens.get("id_token"))
        auth_claims = (
            id_token_payload.get("https://api.openai.com/auth")
            if isinstance(id_token_payload.get("https://api.openai.com/auth"), dict)
            else {}
        )

        email = str(
            id_token_payload.get("email")
            or auth_claims.get("email")
            or seed_metadata.get("login_email")
            or ""
        ).strip().lower()
        account_id = str(
            tokens.get("account_id")
            or auth_claims.get("chatgpt_account_id")
            or seed_metadata.get("auth_account_id")
            or ""
        ).strip()
        user_id = str(
            auth_claims.get("chatgpt_user_id")
            or auth_claims.get("user_id")
            or id_token_payload.get("sub")
            or seed_metadata.get("auth_chatgpt_user_id")
            or ""
        ).strip()
        account_label = str(
            email
            or seed_metadata.get("account_label")
            or user_id
            or account_id
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
        org_id = str(
            default_org.get("id") or "" if isinstance(default_org, dict) else ""
        ).strip()
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
            "Personal"
            if scope_type == "personal"
            else "Workspace"
            if scope_type == "workspace"
            else ""
        )

        identity: Dict[str, Any] = {}
        if account_label:
            identity["account_label"] = account_label
        if email:
            identity["login_email"] = email
        if account_id:
            identity["auth_account_id"] = account_id
        if user_id:
            identity["auth_chatgpt_user_id"] = user_id
        if scope_type:
            identity["account_scope_type"] = scope_type
        if scope_label:
            identity["account_scope_label"] = scope_label
        if org_role:
            identity["account_scope_role"] = org_role
        if effective_plan_type:
            identity["account_plan_type"] = effective_plan_type
        if org_id:
            identity["account_organization_id"] = org_id
        if org_title:
            identity["account_organization_title"] = org_title
        identity["account_organization_count"] = len(organizations)
        if self._auth_payload_has_runtime_credentials(payload):
            identity["codex_auth_has_runtime_credentials"] = True
            identity.update(self._codex_auth_file_signature(codex_home))
        if identity:
            identity["account_identity_source"] = "codex_auth_json"
        return identity

    def _codex_account_identity_for_home(self, codex_home: str) -> Dict[str, Any]:
        normalized_home = str(Path(os.path.expanduser(codex_home)))
        identity = self._extract_codex_account_identity(normalized_home)
        account_key = self._extract_codex_account_key(normalized_home)
        if account_key:
            identity["account_key"] = account_key
        return identity
