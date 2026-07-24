import json
from argparse import Namespace
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scripts.rtmp_motion_publisher import api_client
from scripts.rtmp_motion_publisher.reference_profile import (
    build_motion_reference_profile,
    compact_window_features,
    load_motion_reference_profile,
)
from reference_profile_rebuild.chapter_clip_source import ChapterClip, chapter_clip_specs
from reference_profile_rebuild.coverage import assert_chapter_sample_coverage
from reference_profile_rebuild.artifact_registration import artifact_metadata
from reference_profile_rebuild.profile_upgrade import build_upgraded_profile


def _window(index: int) -> dict:
    return {
        "window_id": f"reference:window:{index}",
        "ts_start_ms": index * 1000,
        "ts_end_ms": (index + 1) * 1000,
        "confidence_stats": {
            "mean_confidence": 0.9,
            "mean_visible_ratio": 0.95,
        },
        "scores": {"pose_confidence": 0.9, "body_visibility": 0.95},
        "metadata": {
            "dwpose_node_deltas": [
                {"node_id": "shoulder_line", "delta_score": 0.02}
            ],
            "sway_metrics": [
                {"axis": "center_stability", "delta_score": 0.03}
            ],
            "phase_metrics": [
                {"phase": "hold_stability", "delta_score": 0.04}
            ],
        },
    }


def test_compact_window_features_excludes_raw_pose_payloads() -> None:
    window = _window(0)
    window["keypoints"] = [{"x": 0.1}]

    assert compact_window_features(window) == {
        "pose_confidence": 0.9,
        "body_visibility": 0.95,
        "shoulder_line": 0.02,
        "center_stability": 0.03,
        "hold_stability": 0.04,
    }


def test_compact_window_features_includes_bounded_posture_geometry() -> None:
    window = _window(0)
    window["metadata"]["compact_motion_metrics"] = {
        "left_knee_flexion_mean": 0.62,
        "body_aspect_mean": 0.71,
    }

    features = compact_window_features(window)

    assert features["posture_left_knee_flexion_mean"] == 0.62
    assert features["posture_body_aspect_mean"] == 0.71


def test_profile_groups_independent_features_by_semantic_chapter() -> None:
    profile = build_motion_reference_profile(
        profile_id="reference-profile-1",
        source_ref="https://example.test/reference",
        chapters=[
            {
                "chapter_id": "chapter-1",
                "chapter_index": 0,
                "title": "First pose",
                "start_ms": 0,
                "end_ms": 2000,
                "scoreable": True,
            },
            {
                "chapter_id": "chapter-2",
                "chapter_index": 1,
                "title": "Second pose",
                "start_ms": 2000,
                "end_ms": 4000,
                "scoreable": True,
            },
        ],
        windows=[_window(index) for index in range(4)],
    )

    assert profile["metadata"]["comparison_provenance"] == (
        "independent_reference_asset"
    )
    assert [len(chapter["feature_series"]) for chapter in profile["chapters"]] == [2, 2]
    assert profile["chapters"][0]["evidence_refs"][0] == "reference:window:0"
    assert "keypoints" not in str(profile)


def test_rebuild_specs_require_one_registered_clip_per_chapter() -> None:
    profile = {
        "chapters": [
            {
                "chapter_id": "chapter-1",
                "ts_start_ms": 0,
                "ts_end_ms": 2000,
            },
            {
                "chapter_id": "chapter-2",
                "ts_start_ms": 2000,
                "ts_end_ms": 4000,
            },
        ],
        "visual_evidence": [
            {
                "chapter_id": "chapter-1",
                "media_kind": "video_clip",
                "artifact_id": "artifact-1",
            },
            {
                "chapter_id": "chapter-2",
                "media_kind": "video_clip",
                "artifact_id": "artifact-2",
            },
        ],
    }

    specs = chapter_clip_specs(profile)

    assert [item["artifact_id"] for item in specs] == ["artifact-1", "artifact-2"]


def test_offline_rebuild_rejects_overwritten_or_missing_sample_coverage(tmp_path) -> None:
    clip = ChapterClip(
        chapter_id="chapter-1",
        chapter_index=0,
        start_ms=0,
        end_ms=90_000,
        artifact_id="artifact-1",
        path=tmp_path / "chapter.mp4",
    )

    try:
        assert_chapter_sample_coverage(clip, frame_count=52, sample_fps=1.0)
    except ValueError as exc:
        assert str(exc).startswith(
            "reference_chapter_sample_coverage_incomplete:chapter-1:52/90"
        )
    else:
        raise AssertionError("incomplete offline sampling must fail closed")

    assert assert_chapter_sample_coverage(
        clip,
        frame_count=89,
        sample_fps=1.0,
    ) == 89 / 90


def test_upgraded_profile_preserves_visuals_and_complete_posture_chapter_coverage() -> None:
    source_profile = {
        "reference_profile_id": "reference-profile-v1",
        "source_ref": "https://example.test/reference",
        "chapters": [
            {
                "chapter_id": "chapter-1",
                "title": "First pose",
                "ts_start_ms": 0,
                "ts_end_ms": 2000,
                "match_role": "instruction",
                "guidance_points": ["keep alignment"],
            },
            {
                "chapter_id": "chapter-2",
                "title": "Second pose",
                "ts_start_ms": 2000,
                "ts_end_ms": 4000,
                "match_role": "instruction",
            },
        ],
        "visual_evidence": [
            {
                "chapter_id": "chapter-1",
                "media_kind": "snapshot",
                "artifact_id": "snapshot-1",
            },
            {
                "chapter_id": "chapter-1",
                "media_kind": "video_clip",
                "artifact_id": "clip-1",
            },
        ],
    }
    windows = [_window(index) for index in range(4)]
    for window in windows:
        window["metadata"]["compact_motion_metrics"] = {
            "left_knee_flexion_mean": 0.4 + window["ts_start_ms"] / 10_000,
        }

    rebuilt = build_upgraded_profile(
        source_profile,
        profile_id="reference-profile-v2",
        windows=windows,
    )

    assert rebuilt["reference_profile_id"] == "reference-profile-v2"
    assert [len(chapter["feature_series"]) for chapter in rebuilt["chapters"]] == [2, 2]
    assert rebuilt["visual_evidence"] == source_profile["visual_evidence"]
    assert rebuilt["metadata"]["chapter_coverage_count"] == 2
    assert rebuilt["metadata"]["posture_feature_chapter_count"] == 2
    assert rebuilt["metadata"]["feature_schema_version"] == (
        "motion_reference_posture_geometry.v2"
    )


def test_rebuild_registration_metadata_satisfies_receiver_contract() -> None:
    profile = {
        "source_ref": "https://www.bilibili.com/video/BV13g4y1u7di/",
        "chapters": [
            {"feature_series": [{"pose_confidence": 0.9}]},
            {"feature_series": [{"pose_confidence": 0.8}]},
        ],
        "visual_evidence": [{"asset_id": "reference-one"}],
    }

    metadata = artifact_metadata(
        profile=profile,
        source_profile={"reference_profile_id": "profile-v1"},
        profile_id="profile-v3",
        checksum="a" * 64,
    )

    assert metadata["artifact_contract"] == "motion_reference_profile_artifact.v1"
    assert metadata["reference_profile_id"] == "profile-v3"
    assert metadata["source_ref"] == profile["source_ref"]
    assert metadata["comparison_provenance"] == "independent_reference_asset"
    assert metadata["motion_window_count"] == 2


def test_loader_accepts_only_independent_profiles_with_chapter_features(tmp_path) -> None:
    profile = build_motion_reference_profile(
        profile_id="reference-profile-1",
        source_ref="https://example.test/reference",
        chapters=[
            {
                "chapter_id": "chapter-1",
                "start_ms": 0,
                "end_ms": 2000,
                "scoreable": True,
            }
        ],
        windows=[_window(0), _window(1)],
    )
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")

    loaded = load_motion_reference_profile(path)

    assert loaded["reference_profile_id"] == "reference-profile-1"


def test_loader_rejects_self_reported_live_profile(tmp_path) -> None:
    profile = build_motion_reference_profile(
        profile_id="live-profile",
        source_ref="rtmp://example.test/live",
        chapters=[{"chapter_id": "chapter-1", "start_ms": 0, "end_ms": 1000}],
        windows=[_window(0)],
    )
    profile["metadata"]["comparison_provenance"] = "learner_capture"
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")

    try:
        load_motion_reference_profile(path)
    except ValueError as exc:
        assert str(exc) == "motion_reference_profile_provenance_not_independent"
    else:
        raise AssertionError("learner capture profile must be rejected")


def test_rollup_request_carries_loaded_reference_profile(monkeypatch) -> None:
    requests: list[dict] = []
    profile = build_motion_reference_profile(
        profile_id="reference-profile-1",
        source_ref="https://example.test/reference",
        chapters=[{"chapter_id": "chapter-1", "start_ms": 0, "end_ms": 1000}],
        windows=[_window(0)],
    )
    monkeypatch.setattr(
        api_client,
        "api_post",
        lambda _base, _path, payload, **_kwargs: requests.append(payload)
        or {"summary": {"metadata": {}}, "artifact_registry": {}},
    )
    args = Namespace(
        api_base="http://localhost:8200",
        expected_duration_ms=1800000,
        max_window_refs=100,
        api_timeout_sec=1.0,
        api_retry_count=1,
        api_retry_backoff_sec=0.0,
    )

    api_client.emit_rollup(
        args,
        "live-session-1",
        motion_reference_profile=profile,
    )

    assert requests[0]["metadata"]["motion_reference_profile"] == profile
    assert requests[0]["metadata"]["expected_duration_ms"] == 1800000
