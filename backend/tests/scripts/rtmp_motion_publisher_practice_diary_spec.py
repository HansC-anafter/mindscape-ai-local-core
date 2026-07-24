import json
from argparse import Namespace

from scripts.rtmp_motion_publisher import practice_diary


def test_reference_visual_manifest_filters_out_learner_assets(tmp_path) -> None:
    path = tmp_path / "visuals.json"
    path.write_text(
        json.dumps(
            {
                "visual_evidence": [
                    {
                        "asset_id": "reference-1",
                        "role": "reference",
                        "source_kind": "reference_asset",
                    },
                    {
                        "asset_id": "learner-1",
                        "role": "learner",
                        "source_kind": "learner_capture",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    assert practice_diary.load_reference_visual_evidence(path) == [
        {
            "asset_id": "reference-1",
            "role": "reference",
            "source_kind": "reference_asset",
        }
    ]


def test_materialize_uses_canonical_api_and_requires_diary_id(tmp_path, monkeypatch) -> None:
    path = tmp_path / "visuals.json"
    path.write_text(
        json.dumps(
            [
                {
                    "asset_id": "reference-1",
                    "role": "reference",
                    "source_kind": "reference_asset",
                }
            ]
        ),
        encoding="utf-8",
    )
    requests = []
    monkeypatch.setattr(
        practice_diary,
        "api_post",
        lambda base, route, payload, **kwargs: requests.append(
            (base, route, payload, kwargs)
        )
        or {"summary": {"diary_id": "diary-1", "revision": 1}},
    )
    args = Namespace(
        workspace_id="workspace-1",
        meeting_id="meeting-1",
        user_goal="Practice accurately",
        api_base="http://localhost:8200",
        api_timeout_sec=5.0,
        closeout_api_timeout_sec=30.0,
        api_retry_count=2,
        api_retry_backoff_sec=0.1,
        practice_diary_reference_visual_evidence_path=str(path),
    )

    request, response = practice_diary.materialize_practice_diary(
        args,
        live_session_id="live-1",
        live_practice_rollup={
            "practice_session_id": "practice-1",
            "metadata": {"source_motion_rollup_ref": "motion-rollup-1"},
        },
        practice_review_projection={"projection_status": "complete"},
    )

    assert response["summary"]["diary_id"] == "diary-1"
    assert request["visual_evidence"][0]["role"] == "reference"
    assert requests[0][1] == (
        "/api/v1/capabilities/yogacoach/practice-diaries/materialize"
    )
    assert requests[0][3]["timeout_sec"] == 30.0
    assert requests[0][3]["retry_count"] == 2


def test_materialize_keeps_higher_configured_idempotent_retry_count(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "visuals.json"
    path.write_text(
        json.dumps(
            [
                {
                    "asset_id": "reference-1",
                    "role": "reference",
                    "source_kind": "reference_asset",
                }
            ]
        ),
        encoding="utf-8",
    )
    call_options = []
    monkeypatch.setattr(
        practice_diary,
        "api_post",
        lambda _base, _route, _payload, **kwargs: call_options.append(kwargs)
        or {"summary": {"diary_id": "diary-1"}},
    )
    args = Namespace(
        workspace_id="workspace-1",
        meeting_id="meeting-1",
        user_goal=None,
        api_base="http://localhost:8200",
        api_timeout_sec=5.0,
        closeout_api_timeout_sec=30.0,
        api_retry_count=4,
        api_retry_backoff_sec=0.1,
        practice_diary_reference_visual_evidence_path=str(path),
    )

    practice_diary.materialize_practice_diary(
        args,
        live_session_id="live-1",
        live_practice_rollup={"practice_session_id": "practice-1"},
        practice_review_projection={},
    )

    assert call_options[0]["retry_count"] == 4
