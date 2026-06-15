"""TasksStore query mixin facade.

Public import seam for all read-only list_* and find_* methods.
"""

from __future__ import annotations

from ._query_admission import TasksStoreAdmissionQueryMixin
from ._query_candidates import TasksStoreCandidateQueryMixin
from ._query_cold_release import TasksStoreColdReleaseQueryMixin
from ._query_common import TasksStoreQueryCommonMixin
from ._query_lists import TasksStoreListQueryMixin
from ._query_meeting import TasksStoreMeetingQueryMixin


class TasksStoreQueryMixin(
    TasksStoreCandidateQueryMixin,
    TasksStoreAdmissionQueryMixin,
    TasksStoreColdReleaseQueryMixin,
    TasksStoreListQueryMixin,
    TasksStoreMeetingQueryMixin,
    TasksStoreQueryCommonMixin,
):
    """Read-only query methods for TasksStore."""

    pass
