from .base import *
from .schemas import ExecutionContext, ExecutionResult


class CodexControlMixin:

    @staticmethod
    def _build_codex_control_command(binary: str, control_action: str) -> List[str]:
        action = (control_action or "").strip().lower()
        if not action:
            return []
        base = [binary, "-c", 'model_reasoning_effort="high"']
        if action == "codex_login_status":
            return [*base, "login", "status"]
        if action == "codex_login":
            return [*base, "login"]
        if action == "codex_logout":
            return [*base, "logout"]
        return []

    @staticmethod
    def _account_home_env(codex_home: str) -> Dict[str, str]:
        home = str(codex_home or "").strip()
        if not home:
            return {}
        return {
            "CODEX_HOME": home,
            "HOME": home,
            "XDG_CONFIG_HOME": str(Path(home) / ".config"),
            "XDG_DATA_HOME": str(Path(home) / ".local" / "share"),
            "XDG_STATE_HOME": str(Path(home) / ".local" / "state"),
        }

    @staticmethod
    def _is_managed_codex_account_home(path: Path) -> bool:
        parts = path.expanduser().parts
        if not path.name.startswith("acct-"):
            return False
        return (
            len(parts) >= 3
            and parts[-2] == "accounts"
            and parts[-3] == "codex-home-pool"
        )

    @classmethod
    def _ensure_codex_control_account_home_dirs_sync(
        cls,
        ctx: ExecutionContext,
    ) -> Optional[Path]:
        inputs = ctx.inputs if isinstance(ctx.inputs, dict) else {}
        raw_env = inputs.get("env")
        env = raw_env if isinstance(raw_env, dict) else {}
        codex_home = str(
            inputs.get("codex_home")
            or inputs.get("CODEX_HOME")
            or env.get("CODEX_HOME")
            or ""
        ).strip()
        if not codex_home:
            return None
        home_path = Path(codex_home).expanduser()
        if not cls._is_managed_codex_account_home(home_path):
            return home_path
        if home_path.exists() and home_path.is_symlink():
            raise RuntimeError(f"Refusing symlinked Codex account home: {home_path}")
        home_path.mkdir(parents=True, exist_ok=True)
        for child in (
            ".config",
            ".local/share",
            ".local/state",
        ):
            (home_path / child).mkdir(parents=True, exist_ok=True)
        seed_path = home_path / ".mindscape-seed.json"
        if not seed_path.exists():
            seed_path.write_text(
                json.dumps(
                    {
                        "account_home": True,
                        "created_by": "mindscape-host-bridge",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return home_path

    @classmethod
    def _delete_codex_control_account_home_sync(
        cls,
        ctx: ExecutionContext,
    ) -> ExecutionResult:
        inputs = ctx.inputs if isinstance(ctx.inputs, dict) else {}
        raw_env = inputs.get("env")
        env = raw_env if isinstance(raw_env, dict) else {}
        codex_home = str(
            inputs.get("codex_home")
            or inputs.get("CODEX_HOME")
            or env.get("CODEX_HOME")
            or ""
        ).strip()
        metadata = {
            "selected_runtime_id": str(inputs.get("runtime_id") or "").strip() or None,
            "workspace_id": ctx.workspace_id or None,
            "effective_workspace_id": ctx.workspace_id or None,
        }
        if not codex_home:
            return ExecutionResult(
                status="failed",
                error="missing_codex_home",
                metadata=metadata,
            )
        home_path = Path(codex_home).expanduser()
        if not cls._is_managed_codex_account_home(home_path):
            return ExecutionResult(
                status="failed",
                error=f"refusing_unmanaged_codex_account_home: {home_path}",
                metadata=metadata,
            )
        if home_path.exists():
            if home_path.is_symlink() or not home_path.is_dir():
                return ExecutionResult(
                    status="failed",
                    error=f"refusing_unsafe_codex_account_home: {home_path}",
                    metadata=metadata,
                )
            shutil.rmtree(home_path)
        return ExecutionResult(
            status="completed",
            output=json.dumps(
                {
                    "codex_home": str(home_path),
                    "home_removed": not home_path.exists(),
                },
                ensure_ascii=False,
            ),
            metadata=metadata,
        )

    @staticmethod
    def _decode_jwt_claims(token: str) -> Dict[str, Any]:
        raw = str(token or "").strip()
        parts = raw.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        try:
            decoded = base64.urlsafe_b64decode((payload + padding).encode("utf-8"))
            claims = json.loads(decoded.decode("utf-8"))
        except Exception:
            return {}
        return claims if isinstance(claims, dict) else {}

    @classmethod
    def _codex_oauth_client_id(cls, payload: Dict[str, Any]) -> str:
        configured = str(os.environ.get("MINDSCAPE_CODEX_OAUTH_CLIENT_ID") or "").strip()
        if configured:
            return configured
        tokens = payload.get("tokens") if isinstance(payload, dict) else {}
        if not isinstance(tokens, dict):
            tokens = {}
        claims = cls._decode_jwt_claims(str(tokens.get("id_token") or ""))
        audience = claims.get("aud")
        if isinstance(audience, str) and audience.strip():
            return audience.strip()
        if isinstance(audience, list):
            for item in audience:
                value = str(item or "").strip()
                if value:
                    return value
        return "codex_cli_simplified_flow"

    @classmethod
    def _codex_control_extra_env(cls, ctx: ExecutionContext) -> Dict[str, str]:
        inputs = ctx.inputs if isinstance(ctx.inputs, dict) else {}
        if not inputs:
            return {}
        raw_env = inputs.get("env")
        env = (
            {
                str(key): str(value)
                for key, value in raw_env.items()
                if value is not None and str(value).strip()
            }
            if isinstance(raw_env, dict)
            else {}
        )
        codex_home = str(
            inputs.get("codex_home")
            or inputs.get("CODEX_HOME")
            or env.get("CODEX_HOME")
            or ""
        ).strip()
        if codex_home:
            account_env = cls._account_home_env(codex_home)
            account_env.update(env)
            return account_env
        return env

    @classmethod
    def _codex_control_identity_metadata_sync(
        cls,
        ctx: ExecutionContext,
    ) -> Dict[str, Any]:
        inputs = ctx.inputs if isinstance(ctx.inputs, dict) else {}
        raw_env = inputs.get("env")
        env = raw_env if isinstance(raw_env, dict) else {}
        codex_home = str(
            inputs.get("codex_home")
            or inputs.get("CODEX_HOME")
            or env.get("CODEX_HOME")
            or ""
        ).strip()
        if not codex_home:
            return {}

        try:
            from backend.app.services.codex_account_home_auth_source_service import (
                CodexAccountHomeAuthSourceService,
            )

            observed: Dict[str, Any] = {"codex_home": codex_home}
            deadline = time.monotonic() + 5.0
            while True:
                auth_metadata = CodexAccountHomeAuthSourceService.metadata_for_codex_home(
                    codex_home
                )
                identity_details = (
                    CodexAccountHomeAuthSourceService.identity_details_for_codex_home(
                        codex_home
                    )
                )
                observed.update(auth_metadata)
                observed.update(identity_details)
                if (
                    observed.get("account_key")
                    or observed.get("login_email")
                    or time.monotonic() >= deadline
                ):
                    break
                time.sleep(0.25)
            return {"codex_account_identity": observed}
        except Exception as exc:
            logger.warning(
                "[TaskExecutor] Failed to inspect Codex account-home identity after control action: %s",
                exc,
            )
            return {
                "codex_account_identity": {
                    "codex_home": codex_home,
                    "identity_error": str(exc),
                }
            }

    @classmethod
    def _codex_probe_token_refresh_sync(
        cls,
        ctx: ExecutionContext,
    ) -> ExecutionResult:
        inputs = ctx.inputs if isinstance(ctx.inputs, dict) else {}
        raw_env = inputs.get("env")
        env = raw_env if isinstance(raw_env, dict) else {}
        codex_home = str(
            inputs.get("codex_home")
            or inputs.get("CODEX_HOME")
            or env.get("CODEX_HOME")
            or ""
        ).strip()
        metadata: Dict[str, Any] = {
            "effective_sandbox_path": codex_home or None,
            "selected_runtime_id": str(inputs.get("runtime_id") or "").strip() or None,
            "workspace_id": ctx.workspace_id or None,
            "effective_workspace_id": ctx.workspace_id or None,
        }
        if not codex_home:
            return ExecutionResult(
                status="failed",
                output='{"codex_account_home_probe":false,"probe_method":"oauth_refresh","token_usable":false}',
                error="missing_codex_home",
                metadata=metadata,
            )

        auth_path = Path(codex_home).expanduser() / "auth.json"
        try:
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ExecutionResult(
                status="failed",
                output='{"codex_account_home_probe":false,"probe_method":"oauth_refresh","token_usable":false}',
                error="missing_auth_json",
                metadata=metadata,
            )
        except Exception as exc:
            return ExecutionResult(
                status="failed",
                output='{"codex_account_home_probe":false,"probe_method":"oauth_refresh","token_usable":false}',
                error=f"auth_json_unreadable: {exc}",
                metadata=metadata,
            )

        tokens = payload.get("tokens")
        if not isinstance(tokens, dict):
            tokens = {}
        refresh_token = str(tokens.get("refresh_token") or "").strip()
        if not refresh_token:
            return ExecutionResult(
                status="failed",
                output='{"codex_account_home_probe":false,"probe_method":"oauth_refresh","token_usable":false}',
                error="missing_refresh_token",
                metadata=metadata,
            )

        token_url = os.environ.get(
            "MINDSCAPE_CODEX_OAUTH_TOKEN_URL",
            "https://auth.openai.com/oauth/token",
        ).strip() or "https://auth.openai.com/oauth/token"
        client_id = cls._codex_oauth_client_id(payload)
        form = urllib.parse.urlencode(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            token_url,
            data=form,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            lowered = body.lower()
            if exc.code in {400, 401, 403} and (
                "invalid_grant" in lowered
                or "refresh token" in lowered
                or "already used" in lowered
                or not body.strip()
            ):
                error = "stale_refresh_token: refresh token was already used or rejected"
            else:
                error = f"token_refresh_http_{exc.code}"
            return ExecutionResult(
                status="failed",
                output=json.dumps(
                    {
                        "codex_account_home_probe": False,
                        "probe_method": "oauth_refresh",
                        "token_usable": False,
                        "http_status": exc.code,
                    },
                    ensure_ascii=False,
                ),
                error=error,
                metadata=metadata,
            )
        except TimeoutError:
            return ExecutionResult(
                status="failed",
                output='{"codex_account_home_probe":false,"probe_method":"oauth_refresh","inconclusive":true}',
                error="probe_transport_error: token refresh timed out",
                metadata=metadata,
            )
        except urllib.error.URLError as exc:
            return ExecutionResult(
                status="failed",
                output='{"codex_account_home_probe":false,"probe_method":"oauth_refresh","inconclusive":true}',
                error=f"probe_transport_error: {exc.reason}",
                metadata=metadata,
            )
        except Exception as exc:
            return ExecutionResult(
                status="failed",
                output='{"codex_account_home_probe":false,"probe_method":"oauth_refresh","inconclusive":true}',
                error=f"probe_transport_error: {exc}",
                metadata=metadata,
            )

        if not isinstance(response_payload, dict):
            return ExecutionResult(
                status="failed",
                output='{"codex_account_home_probe":false,"probe_method":"oauth_refresh","token_usable":false}',
                error="token_refresh_invalid_response",
                metadata=metadata,
            )
        access_token = str(response_payload.get("access_token") or "").strip()
        if not access_token:
            return ExecutionResult(
                status="failed",
                output='{"codex_account_home_probe":false,"probe_method":"oauth_refresh","token_usable":false}',
                error="token_refresh_missing_access_token",
                metadata=metadata,
            )

        next_tokens = dict(tokens)
        for key in ("access_token", "id_token", "refresh_token"):
            value = response_payload.get(key)
            if isinstance(value, str) and value.strip():
                next_tokens[key] = value
        payload["tokens"] = next_tokens
        payload["auth_mode"] = payload.get("auth_mode") or "chatgpt"
        payload["last_refresh"] = datetime.now(timezone.utc).isoformat().replace(
            "+00:00",
            "Z",
        )

        try:
            auth_stat = auth_path.stat()
            tmp_path = auth_path.with_name(f".{auth_path.name}.tmp.{os.getpid()}")
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.chmod(tmp_path, auth_stat.st_mode)
            os.replace(tmp_path, auth_path)
        except Exception as exc:
            return ExecutionResult(
                status="failed",
                output='{"codex_account_home_probe":false,"probe_method":"oauth_refresh","inconclusive":true}',
                error=f"token_refresh_persist_failed: {exc}",
                metadata=metadata,
            )

        identity_metadata = cls._codex_control_identity_metadata_sync(ctx)
        if identity_metadata:
            metadata.update(identity_metadata)
        return ExecutionResult(
            status="completed",
            output=json.dumps(
                {
                    "codex_account_home_probe": True,
                    "probe_method": "oauth_refresh",
                    "token_usable": True,
                },
                ensure_ascii=False,
            ),
            metadata=metadata,
        )
