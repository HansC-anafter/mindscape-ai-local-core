from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.runtime import RuntimeGate
from remote_workbench_authorization_cutover.secure_inputs import SecureInputs


WORKSPACE_ID = "bac7ce63-e768-454d-96f3-3a00e8e1df69"


class ProbeExecutor:
    def __init__(self, samples: list[list[float]] | None = None) -> None:
        self.samples = list(samples or [[499.999], [1.0] * 20])
        self.calls: list[dict] = []

    def run(self, args, *, timeout_seconds=60.0, input_text=None) -> str:
        self.calls.append(
            {
                "args": list(args),
                "timeout_seconds": timeout_seconds,
                "input_text": input_text,
            }
        )
        return json.dumps(self.samples.pop(0))


class HealthHttp:
    def __init__(
        self,
        cache_entries: list[tuple[int, int]] | None = None,
        upstream_calls: list[tuple[int, int]] | None = None,
    ) -> None:
        self.cache_entries = list(cache_entries or [(0, 0), (1, 0), (1, 0)])
        self.upstream_calls = list(upstream_calls or [(0, 0), (1, 0), (1, 0)])
        self.calls: list[str] = []

    def get_json(self, url, **_kwargs) -> dict:
        self.calls.append(url)
        effective, capability = self.cache_entries.pop(0)
        policy_calls, support_calls = self.upstream_calls.pop(0)
        return {
            "gateway": {
                "effective_policy_cache_entries": effective,
                "capability_support_cache_entries": capability,
                "upstream_effective_policy_calls": policy_calls,
                "upstream_capability_support_calls": support_calls,
            }
        }


def _inputs(tmp_path: Path) -> SecureInputs:
    secure_dir = tmp_path / "secure"
    secure_dir.mkdir(mode=0o700)
    token_path = secure_dir / "hans.jwt"
    token_path.write_text("signed-access-token", encoding="utf-8")
    token_path.chmod(0o600)
    return SecureInputs(
        directory=secure_dir,
        policy={},
        jwt_paths={"hans": token_path},
        jwt_claims={},
    )


def _gate(executor: ProbeExecutor, http: HealthHttp) -> RuntimeGate:
    return RuntimeGate(
        repo_root=REPO_ROOT,
        executor=executor,
        http=http,
    )


def test_latency_gate_calls_actual_listener_and_persists_private_evidence(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    executor = ProbeExecutor()
    http = HealthHttp()

    result = _gate(executor, http).verify_gateway_latency(inputs, WORKSPACE_ID)

    assert result == {
        "workspace_id": WORKSPACE_ID,
        "request_path": f"/workspaces/{WORKSPACE_ID}",
        "actual_gateway": "mindscape-ai-local-core-frontend:3001",
        "warm_miss_ms": 499.999,
        "cache_hit_samples": 20,
        "cache_hit_p95_ms": 1.0,
        "cache_entries_before": [0, 0],
        "cache_entries_after_miss": [1, 0],
        "cache_entries_after_hits": [1, 0],
        "upstream_calls_before": [0, 0],
        "upstream_calls_after_miss": [1, 0],
        "upstream_calls_after_hits": [1, 0],
    }
    assert len(http.calls) == 3
    assert [call["args"][-2] for call in executor.calls] == ["1", "20"]
    for call in executor.calls:
        args = call["args"]
        assert args[:7] == [
            "docker",
            "exec",
            "-i",
            "mindscape-ai-local-core-frontend",
            "node",
            "-e",
            args[6],
        ]
        assert args[-1] == f"/workspaces/{WORKSPACE_ID}"
        assert call["timeout_seconds"] == 30.0
        assert call["input_text"] == "signed-access-token"
        assert "signed-access-token" not in args
    evidence = inputs.directory / "gateway-latency.json"
    assert evidence.stat().st_mode & 0o777 == 0o600
    assert json.loads(evidence.read_text(encoding="utf-8")) == result


@pytest.mark.parametrize(
    ("samples", "cache_entries", "message"),
    [
        ([[500.0], [1.0] * 20], None, "exceeds"),
        ([[1.0], [25.001] * 20], None, "exceeds"),
        ([[1.0], [1.0] * 19], None, "samples are invalid"),
        (None, [(1, 0), (1, 1), (1, 1)], "were not empty"),
        (None, [(0, 0), (0, 0), (1, 0)], "did not load"),
        (None, [(0, 0), (1, 0), (2, 0)], "changed cache cardinality"),
    ],
)
def test_latency_gate_fails_closed_on_threshold_sample_or_cache_mismatch(
    tmp_path: Path,
    samples: list[list[float]] | None,
    cache_entries: list[tuple[int, int]] | None,
    message: str,
) -> None:
    inputs = _inputs(tmp_path)
    with pytest.raises(CutoverError, match=message):
        _gate(ProbeExecutor(samples), HealthHttp(cache_entries)).verify_gateway_latency(
            inputs,
            WORKSPACE_ID,
        )
    assert not (inputs.directory / "gateway-latency.json").exists()


def test_latency_gate_rejects_live_upstream_counter_drift(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    http = HealthHttp(upstream_calls=[(0, 0), (1, 0), (2, 0)])
    with pytest.raises(CutoverError, match="changed cache cardinality"):
        _gate(ProbeExecutor(), http).verify_gateway_latency(inputs, WORKSPACE_ID)


def test_workflow_has_one_runtime_owned_latency_path_in_locked_order() -> None:
    source = (
        REPO_ROOT / "scripts/remote_workbench_authorization_cutover/workflow.py"
    ).read_text(encoding="utf-8")
    active = source.index("state=\"enforced\"")
    latency = source.index("self.runtime.verify_gateway_latency", active)
    public = source.index("self.runtime.verify_public_matrix", latency)
    database = source.index("self.release.verify_database_pools()", public)

    assert active < latency < public < database
    assert source.count("verify_gateway_latency") == 1
    assert "self.release.verify_gateway_latency" not in source
    acceptance = (
        REPO_ROOT / "scripts/remote_workbench_authorization_cutover/runtime_acceptance.py"
    ).read_text(encoding="utf-8")
    assert "installed-capabilities/yogacoach" not in acceptance
    assert 'f"/workspaces/{workspace_id}"' in acceptance
