from .base import *


class HostBridgeSpoolMixin:

    def _has_pending_transport_work(self) -> bool:
        """Whether the bridge should tolerate temporary WS silence."""
        if self._active_tasks > 0:
            return True
        return any(not waiter.done() for waiter in self._result_ack_waiters.values())

    def _pending_result_ack_count(self) -> int:
        return sum(1 for waiter in self._result_ack_waiters.values() if not waiter.done())

    def _resolve_result_spool_path(self) -> Path:
        override = os.environ.get("MINDSCAPE_RESULT_SPOOL_PATH", "").strip()
        if override:
            path = Path(os.path.expanduser(override))
            if path.suffix:
                return path
            return path / f"{_safe_path_component(self.client_id)}.json"

        return (
            Path(tempfile.gettempdir())
            / "mindscape-bridge-results"
            / _safe_path_component(self.workspace_id)
            / _safe_path_component(self.surface)
            / f"{_safe_path_component(self.client_id)}.json"
        )

    def _load_result_spool(self) -> None:
        path = self._result_spool_path
        if not path.exists():
            return

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load result spool %s: %s", path, exc)
            return

        now_wall = time.time()
        now_monotonic = time.monotonic()

        pending_entries = payload.get("pending_rest_results") or []
        if isinstance(pending_entries, dict):
            pending_entries = [
                {
                    "execution_id": execution_id,
                    "result_message": result_message,
                }
                for execution_id, result_message in pending_entries.items()
            ]
        for entry in pending_entries:
            execution_id = str(entry.get("execution_id", "")).strip()
            result_message = entry.get("result_message")
            if not execution_id or not isinstance(result_message, dict):
                continue
            self._pending_rest_results[execution_id] = copy.deepcopy(result_message)

        recent_entries = payload.get("recent_results") or []
        if isinstance(recent_entries, dict):
            recent_entries = [
                {
                    "execution_id": execution_id,
                    "stored_at": entry.get("stored_at"),
                    "result_message": entry.get("result_message"),
                }
                for execution_id, entry in recent_entries.items()
                if isinstance(entry, dict)
            ]
        for entry in recent_entries:
            execution_id = str(entry.get("execution_id", "")).strip()
            result_message = entry.get("result_message")
            stored_at_wall = entry.get("stored_at")
            if not execution_id or not isinstance(result_message, dict):
                continue
            try:
                stored_at_wall_value = float(stored_at_wall)
            except (TypeError, ValueError):
                stored_at_wall_value = now_wall
            age_seconds = max(0.0, now_wall - stored_at_wall_value)
            if age_seconds > self.RECENT_RESULT_TTL:
                continue
            stored_at_monotonic = now_monotonic - age_seconds
            self._recent_results[execution_id] = (
                stored_at_monotonic,
                stored_at_wall_value,
                copy.deepcopy(result_message),
            )

        self._prune_recent_results()
        if self._pending_rest_results or self._recent_results:
            logger.info(
                "Loaded result spool %s (pending=%d recent=%d)",
                path,
                len(self._pending_rest_results),
                len(self._recent_results),
            )

    def _persist_result_spool(self) -> None:
        path = self._result_spool_path

        if not self._pending_rest_results and not self._recent_results:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except Exception as exc:
                logger.warning("Failed to remove empty result spool %s: %s", path, exc)
            return

        payload = {
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "surface": self.surface,
            "updated_at": time.time(),
            "pending_rest_results": [
                {
                    "execution_id": execution_id,
                    "result_message": copy.deepcopy(result_message),
                }
                for execution_id, result_message in self._pending_rest_results.items()
            ],
            "recent_results": [
                {
                    "execution_id": execution_id,
                    "stored_at": stored_at_wall,
                    "result_message": copy.deepcopy(result_message),
                }
                for execution_id, (_stored_at_monotonic, stored_at_wall, result_message) in self._recent_results.items()
            ],
        }

        tmp_path = path.with_suffix(f"{path.suffix or '.json'}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(tmp_path, path)
        except Exception as exc:
            logger.warning("Failed to persist result spool %s: %s", path, exc)
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                pass

    # ============================================================
    #  Main lifecycle
    # ============================================================
