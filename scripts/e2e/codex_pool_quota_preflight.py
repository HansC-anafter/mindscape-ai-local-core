#!/usr/bin/env python3
"""Probe Codex pool quota before expensive workspace E2E runs."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from codex_pool_quota_preflight_env import (  # noqa: E402
    _codex_cli_compatibility_check,
    _env_keys,
    _host_reachable_database_url,
    _host_session_env_class,
    _load_dotenv_defaults,
    _load_local_backend_env,
    _normalized_required_login_email,
    _parse_version_tuple,
    _repo_root,
    _bootstrap_imports,
    _with_cli_evidence,
)
from codex_pool_quota_preflight_output import (  # noqa: E402
    _compact_result,
    parse_args,
)
from codex_pool_quota_preflight_runner import (  # noqa: E402
    run_account_home_audit,
    run_preflight,
)
from codex_pool_quota_preflight_runtime import (  # noqa: E402
    _direct_account_home_runtime_bundles,
    _probe_bundle,
    _report_runtime_fault,
    _report_runtime_success,
    _resolve_bundle,
    _runtime_pool_summary,
)

__all__ = [
    "_bootstrap_imports",
    "_codex_cli_compatibility_check",
    "_compact_result",
    "_direct_account_home_runtime_bundles",
    "_env_keys",
    "_host_reachable_database_url",
    "_host_session_env_class",
    "_load_dotenv_defaults",
    "_load_local_backend_env",
    "_normalized_required_login_email",
    "_parse_version_tuple",
    "_probe_bundle",
    "_repo_root",
    "_report_runtime_fault",
    "_report_runtime_success",
    "_resolve_bundle",
    "_runtime_pool_summary",
    "_with_cli_evidence",
    "main",
    "parse_args",
    "run_account_home_audit",
    "run_preflight",
]


def main() -> int:
    _bootstrap_imports()
    args = parse_args()
    result = asyncio.run(run_preflight(args))
    if args.compact_output:
        result = _compact_result(result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "available" else 2


if __name__ == "__main__":
    raise SystemExit(main())
