import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_e2e_module():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "e2e"
        / "pd_real_ig_storyboard_e2e.py"
    )
    spec = importlib.util.spec_from_file_location(
        "pd_real_ig_storyboard_e2e",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _args(module):
    return SimpleNamespace(
        scene_count_floor=40,
        scene_count_target=45,
        target_duration_sec=90,
        duration_tolerance_sec=4.0,
        reference_ids=",".join(module.DEFAULT_REFS),
    )


def _scene(index: int, ref_id: str) -> dict:
    scene_id = f"sc{index:02d}"
    return {
        "scene_id": scene_id,
        "duration_sec": 2,
        "reference_ids": [ref_id],
        "scene_manifest": {
            "script_layer": {
                "visual_action": f"Camera shot follows {ref_id} reference styling with a concrete audience action.",
                "voiceover_line": "Voiceover anchors the benefit in audience-facing language.",
                "on_screen_text": "A clear caption for the viewer.",
                "source_refs": [ref_id],
            },
            "storyboard_frame": {
                "composition": "Vertical frame with concrete camera composition.",
                "visual_prompt": f"Shot language grounded in reference {ref_id}.",
                "source_refs": [ref_id],
            },
        },
    }


def _passing_payload(module, *, runtime_evidence: dict | None = None) -> dict:
    refs = list(module.DEFAULT_REFS)
    scenes = [_scene(index, refs[(index - 1) % len(refs)]) for index in range(1, 46)]
    scene_scores = [
        {
            "scene_id": scene["scene_id"],
            "narrative_logic": True,
            "pacing": True,
            "visual_language": True,
            "reference_grounding": True,
            "brand_tone": True,
            "cta_fit": True,
            "cta_not_applicable_reason": "",
        }
        for scene in scenes
    ]
    scene_judge_report = {
        "schema_version": "pd_storyboard_scene_judge_report.v1",
        "model_id": "workspace_runtime_scene_judge",
        "prompt_version": "pd_storyboard_scene_judge_prompt.v1",
        "rubric_version": "pd_storyboard_scene_judge_rubric.v1",
        "output_hash": "hash_scene_judge",
        "llm_review_status": "completed_per_scene",
        "invalid_schema": False,
        "refusal": False,
        "timeout": False,
        "max_token_truncation": False,
        "passed": True,
        "failed_scene_ids": [],
        "scene_scores": scene_scores,
        "runtime_evidence": runtime_evidence
        or {
            "route_modes": ["workspace_runtime"],
            "executor_runtimes": ["codex_cli"],
            "all_scenes_workspace_runtime": True,
        },
    }
    return {
        "storyboard": {
            "storyboard_id": "sb_e2e",
            "total_duration_sec": 90,
            "scenes": scenes,
        },
        "reference_cue_map": {
            "source_reference_ids": refs,
            "grounding_status": "ready",
            "missing_reference_analysis": [],
            "reference_cues": [
                {
                    "reference_id": ref_id,
                    "cue_type": "visual_anatomy",
                    "evidence_text": "Concrete source-backed visual cue.",
                }
                for ref_id in refs
            ],
        },
        "scene_judge_report": scene_judge_report,
        "quality_gate_summary": {
            "schema_version": "pd_storyboard_quality_gate_summary.v1",
            "strict_acceptance_required": True,
            "storyboard_content_high_quality_pass": True,
            "failed_gate_ids": [],
            "gates": [
                {
                    "gate_id": "G4_LLM_SCENE_JUDGE",
                    "passed": True,
                    "checklist": [{"item_id": "judge_passed", "passed": True}],
                }
            ],
            "scene_judge_report": scene_judge_report,
        },
    }


def test_real_ig_e2e_validation_requires_true_quality_gate():
    module = _load_e2e_module()

    validation = module._validate(
        args=_args(module),
        payloads=[_passing_payload(module)],
        collected_paths=["/tmp/storyboard_manifest.json"],
    )

    assert validation["passed"] is True
    assert validation["scene_count"] == 45
    assert validation["selected_scene_judge_passed"] is True


def test_real_ig_e2e_validation_rejects_managed_provider_judge():
    module = _load_e2e_module()

    validation = module._validate(
        args=_args(module),
        payloads=[
            _passing_payload(
                module,
                runtime_evidence={
                    "route_mode": "managed_provider",
                    "executor_runtime": "codex_cli",
                    "model_name": "qwen2.5:7b",
                },
            )
        ],
        collected_paths=["/tmp/storyboard_manifest.json"],
    )

    assert validation["passed"] is False
    assert "scene_judge_runtime_not_workspace_codex" in validation["failures"]
    assert "scene_judge_runtime_mentions_managed_provider" in validation["failures"]


def test_real_ig_e2e_quota_preflight_file_includes_hard_gate_result(tmp_path, monkeypatch):
    module = _load_e2e_module()

    class Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "status": "available",
                "successful_quota_scope_count": 2,
                "codex_cli_version": "0.129.0",
                "required_flags_supported": {
                    "--output-last-message": True,
                    "--skip-git-repo-check": True,
                },
            }
        )
        stderr = ""

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: Completed())
    args = SimpleNamespace(
        skip_quota_preflight=False,
        workspace_id="ws_test",
        codex_quota_max_runtime_probes=4,
        codex_quota_timeout_seconds=90,
        codex_quota_stall_timeout_seconds=30,
        codex_quota_target_successes=2,
        required_codex_login_email="",
    )

    quota = module._run_quota_preflight(args, tmp_path)
    written = json.loads((tmp_path / "quota_preflight.json").read_text())

    assert quota["hard_gate_passed"] is True
    assert written["hard_gate_passed"] is True
    assert written["hard_gate_target_successes"] == 2


def test_real_ig_e2e_recovers_command_transport_error_from_events(tmp_path, monkeypatch):
    module = _load_e2e_module()
    artifact = tmp_path / "storyboard_manifest.json"
    artifact.write_text(json.dumps({"ok": True}))

    monkeypatch.setattr(
        module,
        "_run_quota_preflight",
        lambda args, output_dir: {
            "status": "available",
            "hard_gate_passed": True,
            "target_successes": 2,
            "successful_quota_scope_count": 2,
            "successful_quota_scope_keys": ["account:a", "account:b"],
            "successful_runtime_ids": ["runtime-a", "runtime-b"],
            "codex_cli_version": "0.129.0",
            "required_flags_supported": {
                "--output-last-message": True,
                "--skip-git-repo-check": True,
            },
        },
    )

    def fake_http_json(method, url, payload=None, timeout=1200):
        if url.endswith("/meeting-sessions/start") and method == "POST":
            return {"id": "meeting_1", "status": "active"}
        if url.endswith("/meetings/meeting_1/commands") and method == "POST":
            raise module.http.client.RemoteDisconnected("closed without response")
        if url.endswith("/meeting-sessions/meeting_1") and method == "GET":
            return {
                "id": "meeting_1",
                "status": "closed",
                "ended_at": "2026-05-07T22:35:23+00:00",
            }
        if url.endswith("/meeting-sessions/meeting_1/events?limit=2000") and method == "GET":
            return {
                "items": [
                    {
                        "event_type": "meeting_end",
                        "payload": _passing_payload(module),
                        "artifact_path": str(artifact),
                    }
                ]
            }
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    args = SimpleNamespace(
        api_url="http://unit.test",
        workspace_id="ws_test",
        project_id="project_test",
        lens_id="lens_test",
        thread_id="",
        run_id="RUN-TRANSPORT",
        command_id="",
        output_dir=str(tmp_path / "out"),
        reference_ids=",".join(module.DEFAULT_REFS),
        target_duration_sec=90,
        duration_tolerance_sec=4.0,
        scene_count_target=45,
        scene_count_floor=40,
        max_rounds=1,
        http_timeout_seconds=1,
        command_timeout_seconds=1,
        post_command_poll_seconds=1,
        post_command_poll_interval_seconds=0.0,
    )

    result = module.run(args)

    assert result["status"] == "passed"
    assert result["submit_transport_error"]["status"] == "transport_error"
    assert result["post_command_recovery"]["session_terminal"] is True
    assert result["validation"]["passed"] is True
    assert result["validation"]["collected_artifacts"]
