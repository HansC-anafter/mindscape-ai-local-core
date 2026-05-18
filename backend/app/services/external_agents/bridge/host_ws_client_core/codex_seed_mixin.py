from .base import *


class HostBridgeCodexSeedMixin:

    def _is_managed_codex_home(self, codex_home: str) -> bool:
        try:
            return Path(os.path.expanduser(codex_home)).resolve().is_relative_to(
                self._codex_managed_pool_root.resolve()
            )
        except Exception:
            return False

    @staticmethod
    def _read_codex_managed_seed_metadata(codex_home: str) -> Dict[str, Any]:
        metadata_path = Path(os.path.expanduser(codex_home)) / ".mindscape-seed.json"
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _write_codex_managed_seed_metadata(
        codex_home: str,
        metadata: Dict[str, Any],
    ) -> None:
        metadata_path = Path(os.path.expanduser(codex_home)) / ".mindscape-seed.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(metadata, ensure_ascii=True, indent=2) + "\n"
        temp_path = metadata_path.with_name(f".{metadata_path.name}.{os.getpid()}.tmp")
        temp_path.write_text(serialized, encoding="utf-8")
        os.replace(temp_path, metadata_path)

    def _is_token_copy_codex_home(self, codex_home: str) -> bool:
        metadata = self._read_codex_managed_seed_metadata(codex_home)
        if bool(metadata.get("managed_mirror")):
            return True
        return False

    def _account_snapshot_is_adopted(
        self,
        codex_home: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        from backend.app.services.codex_pool_health import account_snapshot_is_adopted

        seed_metadata = (
            dict(metadata)
            if isinstance(metadata, dict)
            else self._read_codex_managed_seed_metadata(codex_home)
        )
        return account_snapshot_is_adopted(seed_metadata, codex_home=codex_home)

    @staticmethod
    def _apply_codex_home_isolated_env(
        metadata: Dict[str, Any],
        codex_home: str,
    ) -> None:
        home = str(Path(os.path.expanduser(codex_home)))
        metadata["HOME"] = home
        metadata["XDG_CONFIG_HOME"] = str(Path(home) / ".config")
        metadata["XDG_DATA_HOME"] = str(Path(home) / ".local" / "share")
        metadata["XDG_STATE_HOME"] = str(Path(home) / ".local" / "state")

    def _codex_seed_runtime_metadata(self, codex_home: str) -> Dict[str, Any]:
        seed_metadata = self._read_codex_managed_seed_metadata(codex_home)
        if not seed_metadata:
            return {}

        runtime_metadata: Dict[str, Any] = {}
        if bool(seed_metadata.get("account_snapshot")):
            runtime_metadata["account_snapshot"] = True
            runtime_metadata["codex_pool_membership_state"] = (
                "account_home_registered"
                if self._account_snapshot_is_adopted(codex_home, seed_metadata)
                else "account_snapshot_registered"
            )
        if bool(seed_metadata.get("managed_mirror")):
            runtime_metadata["managed_mirror"] = True
            runtime_metadata["codex_pool_membership_state"] = "managed_mirror"
        source_home = str(seed_metadata.get("source_home") or "").strip()
        if source_home:
            runtime_metadata["seed_source_home"] = source_home
        updated_at = str(seed_metadata.get("updated_at") or "").strip()
        if updated_at:
            runtime_metadata["seed_updated_at"] = updated_at
        auth_synced_at = str(seed_metadata.get("auth_synced_at") or "").strip()
        if auth_synced_at:
            runtime_metadata["seed_auth_synced_at"] = auth_synced_at
        try:
            from backend.app.services.codex_account_home_auth_source_service import (
                CodexAccountHomeAuthSourceService,
            )

            runtime_metadata.update(
                CodexAccountHomeAuthSourceService.metadata_for_codex_home(
                    codex_home,
                    metadata=seed_metadata,
                )
            )
        except Exception:
            logger.debug(
                "Failed to load Codex account-home auth source metadata for %s",
                codex_home,
                exc_info=True,
            )
        return runtime_metadata

    def _codex_home_seed_kind(self, codex_home: str) -> str:
        metadata = self._read_codex_managed_seed_metadata(codex_home)
        if metadata.get("account_snapshot"):
            return (
                "account_home"
                if self._account_snapshot_is_adopted(codex_home, metadata)
                else "account_snapshot"
            )
        if metadata.get("managed_mirror"):
            return "managed_mirror"
        normalized = str(Path(os.path.expanduser(codex_home))).replace("\\", "/")
        if "/accounts/acct-" in normalized:
            return "account_home"
        return "real_home"

    def _filter_executable_codex_home_entries(
        self,
        entries: Dict[str, set[str]],
    ) -> Dict[str, set[str]]:
        filtered: Dict[str, set[str]] = {}
        for codex_home, sources in entries.items():
            normalized = str(Path(os.path.expanduser(codex_home)))
            if self._is_token_copy_codex_home(normalized):
                continue
            filtered[normalized] = set(sources)
        return filtered

    def _codex_quota_scope_home(self, codex_home: str) -> str:
        normalized_home = str(Path(os.path.expanduser(codex_home)))
        if not self._is_managed_codex_home(normalized_home):
            return normalized_home

        metadata = self._read_codex_managed_seed_metadata(normalized_home)
        if not metadata.get("managed_mirror"):
            return normalized_home
        source_home = str(metadata.get("source_home") or "").strip()
        if source_home:
            return str(Path(os.path.expanduser(source_home)))
        return normalized_home

    def _codex_quota_scope_key(self, codex_home: str) -> str:
        quota_scope_home = self._codex_quota_scope_home(codex_home)
        return hashlib.sha1(quota_scope_home.encode("utf-8")).hexdigest()[:16]

    def _discover_codex_home_candidates(self) -> Dict[str, set[str]]:
        discovered: Dict[str, set[str]] = {}
        if self.surface != "codex_cli":
            return discovered

        home_dir = Path(os.path.expanduser(os.environ.get("HOME", "").strip() or str(Path.home())))
        candidate_paths: list[tuple[str, str]] = []
        for pattern in (".codex*", "codex*"):
            for candidate in home_dir.glob(pattern):
                candidate_paths.append((str(candidate), "home_glob"))

        registry_entries = self._load_codex_seed_registry()
        for candidate_path in registry_entries.keys():
            candidate_paths.append((candidate_path, "seed_registry"))

        account_pool_root = self._codex_managed_pool_root / "accounts"
        if account_pool_root.exists():
            for candidate in account_pool_root.glob("acct-*"):
                candidate_paths.append((str(candidate), "managed_account_pool"))

        seen: set[str] = set()
        for raw_path, source in candidate_paths:
            normalized = str(Path(os.path.expanduser(raw_path)))
            if normalized in seen:
                continue
            seen.add(normalized)
            if self._is_token_copy_codex_home(normalized):
                continue
            if not self._codex_home_has_login_trace(normalized):
                continue
            discovered.setdefault(normalized, set()).add(source)
        return discovered

    def _remember_codex_home_seeds(self, entries: Dict[str, set[str]]) -> None:
        registry = self._load_codex_seed_registry()
        now_iso = datetime.now(timezone.utc).isoformat()
        changed = False
        for codex_home, sources in entries.items():
            normalized = str(Path(os.path.expanduser(codex_home)))
            existing = registry.get(normalized, {"sources": set(), "last_seen_at": ""})
            merged_sources = set(existing.get("sources") or set()) | set(sources)
            if self._codex_home_has_login_trace(normalized):
                last_seen_at = now_iso
                account_key = self._extract_codex_account_key(normalized)
                identity = self._extract_codex_account_identity(normalized)
            else:
                last_seen_at = existing.get("last_seen_at", "")
                account_key = str(existing.get("account_key") or "").strip()
                identity = {
                    "account_label": str(existing.get("account_label") or "").strip(),
                    "login_email": str(existing.get("login_email") or "").strip().lower(),
                    "auth_account_id": str(existing.get("auth_account_id") or "").strip(),
                    "auth_chatgpt_user_id": str(
                        existing.get("auth_chatgpt_user_id") or ""
                    ).strip(),
                }
            next_meta = {
                "sources": merged_sources,
                "last_seen_at": last_seen_at,
                "account_key": account_key,
                **{key: value for key, value in identity.items() if value},
            }
            if registry.get(normalized) != next_meta:
                registry[normalized] = next_meta
                changed = True

        if changed:
            self._write_codex_seed_registry(registry)

    def _codex_seed_registry_summary(self) -> Dict[str, Any]:
        registry = self._load_codex_seed_registry()
        distinct_account_keys = sorted(
            {
                str(meta.get("account_key") or "").strip()
                for meta in registry.values()
                if str(meta.get("account_key") or "").strip()
            }
        )
        real_home_count = 0
        managed_mirror_count = 0
        account_snapshot_count = 0
        for codex_home in registry.keys():
            metadata = self._read_codex_managed_seed_metadata(codex_home)
            if metadata.get("account_snapshot"):
                account_snapshot_count += 1
            elif metadata.get("managed_mirror"):
                managed_mirror_count += 1
            else:
                real_home_count += 1
        return {
            "registry_home_count": len(registry),
            "distinct_account_count": len(distinct_account_keys),
            "distinct_account_keys": distinct_account_keys,
            "real_home_count": real_home_count,
            "managed_mirror_count": managed_mirror_count,
            "account_snapshot_count": account_snapshot_count,
        }

    def refresh_codex_home_seeds(self) -> Dict[str, Any]:
        if self.surface != "codex_cli":
            return {
                "surface": self.surface,
                "refreshed": False,
                "reason": "unsupported_surface",
            }

        active_pool_homes = self._codex_home_pool_entries()
        summary = self._codex_seed_registry_summary()
        summary.update(
            {
                "surface": self.surface,
                "refreshed": True,
                "active_pool_home_count": len(active_pool_homes),
            }
        )
        logger.info(
            (
                "Codex seed refresh complete: registry_homes=%s "
                "distinct_accounts=%s real_homes=%s snapshots=%s mirrors=%s "
                "active_pool_homes=%s"
            ),
            summary["registry_home_count"],
            summary["distinct_account_count"],
            summary["real_home_count"],
            summary["account_snapshot_count"],
            summary["managed_mirror_count"],
            summary["active_pool_home_count"],
        )
        return summary
