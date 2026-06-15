from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store._crud_helpers import (
    coerce_task_status_enum,
    normalize_task_status_value,
)


def test_legacy_cancelled_status_normalizes_to_canonical_terminal_status():
    assert normalize_task_status_value("cancelled") == TaskStatus.CANCELLED_BY_USER.value
    assert coerce_task_status_enum("cancelled") == TaskStatus.CANCELLED_BY_USER


def test_task_status_normalization_keeps_canonical_values():
    assert normalize_task_status_value(TaskStatus.PENDING) == TaskStatus.PENDING.value
    assert coerce_task_status_enum(TaskStatus.FAILED.value) == TaskStatus.FAILED
