from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = (
        repo_root
        / "scripts"
        / "maintenance"
        / "reconcile_playbook_execution_status.py"
    )
    spec = spec_from_file_location("reconcile_playbook_execution_status", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _query, _params=None):
        return _Result(self.rows)


class _Store:
    def __init__(self, rows):
        self.rows = rows
        self.rolled_back = False

    @contextmanager
    def get_connection(self):
        yield _Connection(self.rows)

    @contextmanager
    def transaction(self):
        try:
            yield _Connection(self.rows)
        except Exception:
            self.rolled_back = True
            raise


def _row(target_status="queued"):
    return SimpleNamespace(
        id="execution-1",
        current_status="running",
        current_updated_at=datetime(2026, 6, 14, 1, 0, tzinfo=timezone.utc),
        target_status=target_status,
        running_count=0,
        pending_count=1 if target_status == "queued" else 0,
        succeeded_count=1 if target_status == "done" else 0,
        failed_count=1 if target_status == "failed" else 0,
    )


def test_load_candidates_preserves_exact_status_evidence():
    module = _load_module()

    rows = module.load_candidates(_Store([_row()]))

    assert rows == [
        {
            "id": "execution-1",
            "current_status": "running",
            "current_updated_at": "2026-06-14T01:00:00+00:00",
            "target_status": "queued",
            "running_count": 0,
            "pending_count": 1,
            "succeeded_count": 0,
            "failed_count": 0,
        }
    ]


def test_apply_requires_exact_live_candidate_count():
    module = _load_module()
    store = _Store([_row("failed")])

    with pytest.raises(RuntimeError, match="expected=2 actual=1"):
        module.apply_reconciliation(store, expected_count=2)

    assert store.rolled_back is True
