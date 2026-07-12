from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.secure_inputs import load_secure_inputs


def test_runtime_policy_input_is_bounded_before_json_read(tmp_path: Path) -> None:
    secure = tmp_path / "secure"
    secure.mkdir(mode=0o700)
    os.chmod(secure, 0o700)
    policy = secure / "runtime-policy-next.json"
    policy.write_text("x" * 32_769, encoding="utf-8")
    os.chmod(policy, 0o600)

    with pytest.raises(CutoverError, match="size limit"):
        load_secure_inputs(secure)
