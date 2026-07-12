"""Exact runtime/effective/public/cache acceptance for the canonical gateway."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from .io import CutoverError, write_private_json
from .secure_inputs import (
    EXPECTED_FINGERPRINT,
    EXPECTED_TARGET_CAPABILITIES,
    SecureInputs,
)


CACHE_HIT_SAMPLES = 20
CACHE_HIT_P95_LIMIT_MS = 25.0
WARM_MISS_LIMIT_MS = 500.0


def verify_workspace_api_records(runtime: Any, workspace_ids: tuple[str, str]) -> None:
    """Prove canonical local workspace detail endpoints resolve both real rows."""

    for workspace_id in workspace_ids:
        payload = runtime.http.get_json(
            f"http://localhost:8200/api/v1/workspaces/{workspace_id}/summary",
            timeout_seconds=10.0,
            max_response_bytes=262_144,
        )
        if payload.get("id") != workspace_id:
            raise CutoverError("Canonical workspace API row identity is missing")


def _health_gateway(runtime: Any) -> dict[str, Any]:
    payload = runtime.http.get_json(
        runtime.health_url,
        timeout_seconds=20.0,
        max_response_bytes=32_768,
    )
    gateway = payload.get("gateway")
    if not isinstance(gateway, dict):
        raise CutoverError("Gateway health projection is missing")
    return gateway


def _assert_snapshot_identity(
    payload: Mapping[str, Any],
    *,
    workspace_id: str,
    state: str,
    revision: int,
) -> None:
    expected = {
        "workspace_id": workspace_id,
        "access_issuer": "https://shy-resonance-542b.cloudflareaccess.com",
        "access_audience": (
            "94cce07bfe76d9b3903ee15316df231bb6b0c004e0a68114b8e965b2710e8b1f"
        ),
        "auth_config_fingerprint": EXPECTED_FINGERPRINT,
        "auth_config_source": "runtime_policy",
        "remote_access_state": state,
        "runtime_policy_revision": revision,
        "runtime_policy_source": "persisted_policy",
        "source": "effective_policy",
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise CutoverError(f"Effective policy exact readback mismatch: {key}")


def verify_pending_coherence(
    runtime: Any,
    *,
    runtime_readback: Mapping[str, Any],
    workspace_id: str,
) -> None:
    """Cross-check pending runtime, effective, and actual gateway startup state."""

    revision = runtime_readback.get("revision")
    if type(revision) is not int:
        raise CutoverError("Pending runtime revision is invalid")
    effective = runtime.get_effective_policy(workspace_id)
    _assert_snapshot_identity(
        effective,
        workspace_id=workspace_id,
        state="enrollment_only",
        revision=revision,
    )
    gateway = _health_gateway(runtime)
    expected = {
        "auth_config_fingerprint": EXPECTED_FINGERPRINT,
        "auth_config_source": "runtime_policy",
        "remote_access_state": "enrollment_only",
        "runtime_policy_revision": revision,
    }
    for key, value in expected.items():
        if gateway.get(key) != value:
            raise CutoverError(f"Pending gateway coherence mismatch: {key}")


def verify_effective_policies(
    runtime: Any,
    inputs: SecureInputs,
    *,
    target_workspace_id: str,
    inheritance_workspace_id: str,
    state: str,
    revision: int,
) -> None:
    """Require exact runtime identity and approved subjects on both workspaces."""

    expected_admins = sorted(
        inputs.policy["local_core_super_admins"],
        key=lambda item: (item["email"], item["subject"]),
    )
    expected_principals = [
        {
            "subject": item["subject"],
            "email": item["email"],
            "grant_sources": ["local_core_super_admin"],
        }
        for item in expected_admins
    ]
    expected_principals.sort(key=lambda item: item["subject"])
    for workspace_id, target in (
        (target_workspace_id, True),
        (inheritance_workspace_id, False),
    ):
        payload = runtime.get_effective_policy(workspace_id)
        _assert_snapshot_identity(
            payload,
            workspace_id=workspace_id,
            state=state,
            revision=revision,
        )
        admins = payload.get("local_core_super_admins")
        if not isinstance(admins, list) or sorted(
            admins,
            key=lambda item: (item.get("email", ""), item.get("subject", "")),
        ) != expected_admins:
            raise CutoverError("Effective policy administrator subjects mismatch")
        principals = payload.get("effective_principals")
        if not isinstance(principals, list) or sorted(
            principals,
            key=lambda item: item.get("subject", ""),
        ) != expected_principals:
            raise CutoverError("Effective policy principal subjects or grants mismatch")
        if payload.get("allowed_principals") not in ([], None):
            raise CutoverError("Workspace direct principals must remain empty")
        if target:
            capabilities = tuple(sorted(payload.get("allowed_capability_codes") or []))
            if capabilities != tuple(sorted(EXPECTED_TARGET_CAPABILITIES)):
                raise CutoverError("Target workspace capability policy changed")
            if payload.get("workspace_policy_source") != "persisted_policy":
                raise CutoverError("Target workspace policy source mismatch")
        elif (
            payload.get("workspace_policy_source") != "default_deny"
            or payload.get("allowed_capability_codes") not in ([], None)
        ):
            raise CutoverError("Inheritance workspace unexpectedly gained direct policy")


def verify_public_matrix(runtime: Any, inputs: SecureInputs, workspace_id: str) -> None:
    """Verify HTTP/upgrade tenant parity while unsupported packs stay closed."""

    for label in ("hans", "pproo"):
        for upgrade in (False, True):
            response = runtime._principal_request(  # noqa: SLF001 - canonical facade
                inputs.jwt_paths[label],
                workspace_id,
                upgrade=upgrade,
            )
            runtime._assert_principal_response(  # noqa: SLF001
                response,
                allowed=True,
                expected_reason=None,
                upgrade=upgrade,
            )
    for upgrade in (False, True):
        response = runtime._principal_request(  # noqa: SLF001
            inputs.jwt_paths["outsider"],
            workspace_id,
            upgrade=upgrade,
        )
        runtime._assert_principal_response(  # noqa: SLF001
            response,
            allowed=False,
            expected_reason="workspace_membership_required",
            upgrade=upgrade,
        )
    for upgrade in (False, True):
        response = runtime._principal_request(  # noqa: SLF001
            inputs.jwt_paths["hans"],
            workspace_id,
            upgrade=upgrade,
            denied_capability=True,
        )
        runtime._assert_principal_response(  # noqa: SLF001
            response,
            allowed=False,
            expected_reason="capability_not_allowed",
            upgrade=upgrade,
        )


def _nearest_rank(values: list[float]) -> float:
    if not values:
        raise CutoverError("Gateway latency samples are missing")
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _actual_gateway_samples(
    runtime: Any,
    *,
    token: str,
    workspace_id: str,
    samples: int,
) -> list[float]:
    script = """
const http=require('http'),{performance}=require('perf_hooks');
let token='';process.stdin.setEncoding('utf8');process.stdin.on('data',(c)=>token+=c);
process.stdin.on('end',async()=>{const count=Number(process.argv[1]),path=process.argv[2];const out=[];
const one=()=>new Promise((resolve,reject)=>{const start=performance.now();const req=http.request({host:'127.0.0.1',port:3001,path,headers:{Host:'remote-workbench.mindscapeai.app','Cf-Access-Jwt-Assertion':token.trim()}},(res)=>{res.resume();res.on('end',()=>{if(res.statusCode<200||res.statusCode>=300)return reject(new Error('status'));out.push(performance.now()-start);resolve();});});req.on('error',reject);req.end();});
try{for(let i=0;i<count;i+=1)await one();process.stdout.write(JSON.stringify(out));}catch{process.exitCode=9;}});
""".strip()
    raw = runtime.executor.run(
        [
            "docker",
            "exec",
            "-i",
            "mindscape-ai-local-core-frontend",
            "node",
            "-e",
            script,
            str(samples),
            (
                f"/workspaces/{workspace_id}"
            ),
        ],
        timeout_seconds=30.0,
        input_text=token,
    )
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CutoverError("Actual gateway latency output is malformed") from error
    if (
        not isinstance(values, list)
        or len(values) != samples
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
            for value in values
        )
    ):
        raise CutoverError("Actual gateway latency samples are invalid")
    return [float(value) for value in values]


def verify_actual_gateway_cache_latency(
    runtime: Any,
    inputs: SecureInputs,
    workspace_id: str,
) -> dict[str, Any]:
    """Measure the live listener's first miss and later cache hits."""

    before = _health_gateway(runtime)
    if (
        before.get("effective_policy_cache_entries") != 0
        or before.get("capability_support_cache_entries") != 0
        or before.get("upstream_effective_policy_calls") != 0
        or before.get("upstream_capability_support_calls") != 0
    ):
        raise CutoverError("Actual gateway cache or upstream counters were not empty")
    token = inputs.jwt_paths["hans"].read_text(encoding="utf-8").strip()
    miss = _actual_gateway_samples(
        runtime,
        token=token,
        workspace_id=workspace_id,
        samples=1,
    )
    after_miss = _health_gateway(runtime)
    if (
        after_miss.get("effective_policy_cache_entries") != 1
        or after_miss.get("capability_support_cache_entries") != 0
        or after_miss.get("upstream_effective_policy_calls") != 1
        or after_miss.get("upstream_capability_support_calls") != 0
    ):
        raise CutoverError("Actual gateway first miss did not load each upstream once")
    hits = _actual_gateway_samples(
        runtime,
        token=token,
        workspace_id=workspace_id,
        samples=CACHE_HIT_SAMPLES,
    )
    after_hits = _health_gateway(runtime)
    if (
        after_hits.get("effective_policy_cache_entries") != 1
        or after_hits.get("capability_support_cache_entries") != 0
        or after_hits.get("upstream_effective_policy_calls") != 1
        or after_hits.get("upstream_capability_support_calls") != 0
    ):
        raise CutoverError("Actual gateway cache-hit window changed cache cardinality")
    hit_p95 = _nearest_rank(hits)
    if miss[0] >= WARM_MISS_LIMIT_MS or hit_p95 > CACHE_HIT_P95_LIMIT_MS:
        raise CutoverError("Actual gateway latency exceeds the Phase06 thresholds")
    evidence = {
        "workspace_id": workspace_id,
        "request_path": f"/workspaces/{workspace_id}",
        "actual_gateway": "mindscape-ai-local-core-frontend:3001",
        "warm_miss_ms": miss[0],
        "cache_hit_samples": len(hits),
        "cache_hit_p95_ms": hit_p95,
        "cache_entries_before": [0, 0],
        "cache_entries_after_miss": [1, 0],
        "cache_entries_after_hits": [1, 0],
        "upstream_calls_before": [0, 0],
        "upstream_calls_after_miss": [1, 0],
        "upstream_calls_after_hits": [1, 0],
    }
    write_private_json(inputs.directory / "gateway-latency.json", evidence)
    return evidence
