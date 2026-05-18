from .base import *


class OpenClawResultMixin:

    @staticmethod
    def _parse_openclaw_json_output(stdout: str) -> Dict[str, Any]:
        text = (stdout or "").strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {"output": text}

        output = (
            payload.get("output")
            or payload.get("text")
            or payload.get("message")
            or payload.get("result")
        )
        outputs = payload.get("outputs")
        if not output and isinstance(outputs, list):
            for item in outputs:
                if isinstance(item, str) and item.strip():
                    output = item
                    break
                if isinstance(item, dict):
                    candidate = (
                        item.get("text")
                        or item.get("content")
                        or item.get("output")
                        or item.get("message")
                    )
                    if candidate:
                        output = candidate
                        break

        error = payload.get("error")
        if isinstance(error, dict):
            error = error.get("message") or json.dumps(error, ensure_ascii=False)

        return {
            "ok": payload.get("ok"),
            "output": output or json.dumps(payload, ensure_ascii=False),
            "error": error,
            "raw_json": payload,
        }

    def _collect_trace(self, sandbox_path: Path) -> Dict[str, Any]:
        """Collect execution trace from OpenClaw output files."""
        trace_file = sandbox_path / ".openclaw" / "execution_trace.json"

        if trace_file.exists():
            try:
                return json.loads(trace_file.read_text())
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse execution trace: {trace_file}")

        return {"tool_calls": [], "files_modified": []}

    def _snapshot_files(self, sandbox_path: Path) -> Dict[str, float]:
        """Take a snapshot of file mtimes in the sandbox."""
        snapshot = {}
        try:
            for file_path in sandbox_path.rglob("*"):
                if file_path.is_file() and ".openclaw" not in str(file_path):
                    rel_path = str(file_path.relative_to(sandbox_path))
                    snapshot[rel_path] = file_path.stat().st_mtime
        except Exception as e:
            logger.warning(f"Failed to snapshot files: {e}")
        return snapshot

    def _diff_files(
        self, before: Dict[str, float], after: Dict[str, float]
    ) -> tuple[List[str], List[str]]:
        """Compare file snapshots to find created and modified files."""
        created = []
        modified = []

        for path, mtime in after.items():
            if path not in before:
                created.append(path)
            elif before[path] != mtime:
                modified.append(path)

        return created, modified
