"""Single facade for baseline and postflight resource evidence."""

from __future__ import annotations

from typing import Any

from .collectors import RuntimeResourceCollectors
from .contracts import validate_request


class ManagedSiteReleaseResourceProbeFacade:
    """Collect only the local half of the managed release resource contract."""

    def __init__(
        self,
        collectors: RuntimeResourceCollectors | None = None,
    ) -> None:
        self.collectors = collectors or RuntimeResourceCollectors()

    def execute(self, raw_request: Any) -> dict[str, Any]:
        request = validate_request(raw_request)
        if request["operation"] == "capture_baseline":
            pgbouncer = self.collectors.pgbouncer(
                include_samples=False
            )
            return {
                "success": True,
                "baseline": {
                    "database": self.collectors.database(),
                    "pgbouncer_config_sha256": pgbouncer[
                        "config_sha256"
                    ],
                    "worker": self.collectors.worker(),
                },
            }

        baseline = request["baseline"]
        pgbouncer = self.collectors.pgbouncer(include_samples=True)
        release_evidence = request["release_evidence"]
        return {
            "success": True,
            "checks": {
                "database": {
                    "status": "passed",
                    "baseline": baseline["database"],
                    "observed": self.collectors.database(),
                },
                "pgbouncer": {
                    "status": "passed",
                    "probe_status": "available",
                    "sample_count": pgbouncer["sample_count"],
                    "client_waiting_max": pgbouncer[
                        "client_waiting_max"
                    ],
                    "max_wait_seconds": pgbouncer[
                        "max_wait_seconds"
                    ],
                    "config_sha256_before": baseline[
                        "pgbouncer_config_sha256"
                    ],
                    "config_sha256_after": pgbouncer[
                        "config_sha256"
                    ],
                },
                "worker": {
                    "status": "passed",
                    "baseline": baseline["worker"],
                    "observed": self.collectors.worker(),
                    "retry_count": release_evidence["retry_count"],
                    "duplicate_effects": release_evidence[
                        "duplicate_effects"
                    ],
                },
            },
        }
