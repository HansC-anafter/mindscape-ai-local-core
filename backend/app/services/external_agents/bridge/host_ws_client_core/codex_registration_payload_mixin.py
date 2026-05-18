from .base import *


class HostBridgeCodexRegistrationPayloadMixin:

    def _build_host_session_runtime_registration_payload(self) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        for key in (
            "CODEX_HOME",
            "HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
        ):
            value = os.environ.get(key, "").strip()
            if value:
                metadata[key] = value

        if "CODEX_HOME" not in metadata:
            home_dir = metadata.get("HOME") or str(Path.home())
            default_codex_home = Path(home_dir) / ".codex"
            if default_codex_home.exists():
                metadata["CODEX_HOME"] = str(default_codex_home)

        codex_home = metadata.get("CODEX_HOME") or metadata.get("HOME") or self.client_id
        runtime_name = os.environ.get("MINDSCAPE_CODEX_RUNTIME_NAME", "").strip()
        if not runtime_name:
            runtime_name = f"codex_cli host session ({Path(codex_home).name})"

        runtime_id = os.environ.get("MINDSCAPE_CODEX_RUNTIME_ID", "").strip() or None
        pool_group = os.environ.get("MINDSCAPE_CODEX_POOL_GROUP", "").strip() or "codex-cli-pool"
        pool_priority = _env_int("MINDSCAPE_CODEX_POOL_PRIORITY", 0)
        pool_enabled = _env_flag("MINDSCAPE_CODEX_POOL_ENABLED", True)
        if self.surface == "codex_cli" and isinstance(codex_home, str) and codex_home.strip():
            metadata.update(self._codex_seed_runtime_metadata(codex_home))
            metadata["codex_seed_kind"] = self._codex_home_seed_kind(codex_home)
            account_key = self._extract_codex_account_key(codex_home)
            if account_key:
                metadata["account_key"] = account_key
            metadata.update(self._extract_codex_account_identity(codex_home))
            quota_scope_home = self._codex_quota_scope_home(codex_home)
            metadata["quota_scope_home"] = quota_scope_home
            metadata["quota_scope_key"] = (
                f"account:{account_key}"
                if account_key
                else self._codex_quota_scope_key(codex_home)
            )
            if quota_scope_home != codex_home:
                metadata["managed_seed_source_home"] = quota_scope_home

        payload = {
            "workspace_id": self.workspace_id,
            "surface": self.surface,
            "client_id": self.client_id,
            "runtime_id": runtime_id,
            "runtime_name": runtime_name,
            "pool_group": pool_group,
            "pool_enabled": pool_enabled,
            "pool_priority": pool_priority,
            "metadata": metadata,
        }
        if self.owner_user_id:
            payload["owner_user_id"] = self.owner_user_id
        return payload

    def _codex_home_pool_entries(self) -> list[str]:
        entries: Dict[str, set[str]] = {}
        raw = os.environ.get("MINDSCAPE_CODEX_HOME_POOL", "").strip()
        if raw:
            parts = [
                part.strip()
                for part in re.split(r"[\n,;{}]+".format(re.escape(os.pathsep)), raw)
                if part.strip()
            ]
            for part in parts:
                path = str(Path(os.path.expanduser(part))).strip()
                if not path:
                    continue
                if not Path(path).exists():
                    logger.warning("Ignoring missing CODEX_HOME pool path: %s", path)
                    continue
                entries.setdefault(path, set()).add("env_pool")

        if _env_flag("MINDSCAPE_CODEX_HOME_AUTO_DISCOVER", True):
            for path, sources in self._discover_codex_home_candidates().items():
                entries.setdefault(path, set()).update(sources)

        entries = self._filter_executable_codex_home_entries(entries)
        self._remember_codex_home_seeds(entries)
        return list(entries.keys())

    def _build_host_session_runtime_registration_payloads(self) -> list[Dict[str, Any]]:
        base_payload = self._build_host_session_runtime_registration_payload()
        base_priority = int(base_payload.get("pool_priority", 0))
        base_metadata = dict(base_payload.get("metadata") or {})
        home_value = str(base_metadata.get("HOME") or "").strip()
        primary_codex_home = str(base_metadata.get("CODEX_HOME") or "").strip()

        codex_homes = self._codex_home_pool_entries()
        if (
            primary_codex_home
            and primary_codex_home not in codex_homes
            and not self._is_token_copy_codex_home(primary_codex_home)
            and self._codex_home_has_login_trace(primary_codex_home)
        ):
            codex_homes.insert(0, primary_codex_home)

        remembered_entries: Dict[str, set[str]] = {}
        for codex_home in codex_homes:
            remembered_entries.setdefault(codex_home, set()).add("registration")
        if primary_codex_home:
            remembered_entries.setdefault(primary_codex_home, set()).add("primary_runtime")
        self._remember_codex_home_seeds(remembered_entries)

        if not codex_homes:
            if primary_codex_home and self._is_token_copy_codex_home(primary_codex_home):
                return []
            return [base_payload]

        payloads: list[Dict[str, Any]] = []
        for offset, codex_home in enumerate(codex_homes):
            payload = dict(base_payload)
            metadata = dict(base_metadata)
            metadata["CODEX_HOME"] = codex_home
            if home_value:
                metadata["HOME"] = home_value
            if self._is_managed_codex_home(codex_home):
                self._apply_codex_home_isolated_env(metadata, codex_home)
            account_key = self._extract_codex_account_key(codex_home)
            if account_key:
                metadata["account_key"] = account_key
            metadata.update(self._codex_seed_runtime_metadata(codex_home))
            metadata["codex_seed_kind"] = self._codex_home_seed_kind(codex_home)
            metadata.update(self._extract_codex_account_identity(codex_home))
            quota_scope_home = self._codex_quota_scope_home(codex_home)
            metadata["quota_scope_home"] = quota_scope_home
            metadata["quota_scope_key"] = (
                f"account:{account_key}"
                if account_key
                else self._codex_quota_scope_key(codex_home)
            )
            if quota_scope_home != codex_home:
                metadata["managed_seed_source_home"] = quota_scope_home
            metadata["seed_capture_managed"] = True
            metadata["seed_registry_path"] = str(self._codex_seed_registry_path)
            metadata["seed_last_seen_at"] = datetime.now(timezone.utc).isoformat()
            payload["metadata"] = metadata
            payload["pool_priority"] = base_priority + offset
            payload["runtime_name"] = f"codex_cli host session ({Path(codex_home).name})"
            payloads.append(payload)

        return payloads
