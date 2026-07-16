"""Bridge database failure classification into the durable incident journal."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

from .journal import RuntimeDatabaseIncidentJournal
from .models import IncidentReceipt


def record_failure(
    failure_code: str,
    *,
    postmaster_start_time: str = "unknown",
    evidence: Optional[Mapping[str, str]] = None,
    journal_root: Optional[Path] = None,
) -> IncidentReceipt:
    """Open or append to the one current abnormal-close incident."""

    return RuntimeDatabaseIncidentJournal(journal_root).open_incident(
        failure_code=failure_code,
        postmaster_start_time=postmaster_start_time,
        evidence=evidence,
    )
