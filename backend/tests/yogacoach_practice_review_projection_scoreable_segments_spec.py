from capabilities.yogacoach.schema.live_practice_rollup import YogaLivePracticeRollup
from capabilities.yogacoach.services.practice_review_projection_builder import (
    YogaPracticeReviewProjectionBuilder,
)


def test_practice_review_projection_scores_only_scoreable_course_segments() -> None:
    rollup = YogaLivePracticeRollup(
        practice_session_id="practice_1",
        workspace_id="ws_1",
        teacher_library_ref="mindscape://teacher/ref",
        window_count=4,
        motion_summary_refs=[],
        summary_confidence="complete",
        metadata={
            "course_chapters": [
                {
                    "chapter_id": "opening_chat",
                    "title": "Opening chat",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "segment_type": "chat",
                    "scoreable": False,
                    "guidance_mode": "suppress",
                },
                {
                    "chapter_id": "sun_flow",
                    "title": "Sun salutation flow",
                    "start_ms": 1000,
                    "end_ms": 3000,
                    "segment_type": "practice",
                    "scoreable": True,
                    "guidance_mode": "score",
                },
                {
                    "chapter_id": "water_break",
                    "title": "Rest break",
                    "start_ms": 3000,
                    "end_ms": 4000,
                    "segment_type": "rest",
                    "scoreable": False,
                    "guidance_mode": "suppress",
                },
            ],
            "motion_window_digests": [
                {
                    "motion_window_ref": "window_chat",
                    "start_ms": 100,
                    "end_ms": 900,
                    "confidence": 0.9,
                    "top_findings": ["ignore chat"],
                },
                {
                    "motion_window_ref": "window_flow",
                    "start_ms": 1200,
                    "end_ms": 2800,
                    "confidence": 0.95,
                    "top_findings": ["aligned flow"],
                },
                {
                    "motion_window_ref": "window_break",
                    "start_ms": 3200,
                    "end_ms": 3800,
                    "confidence": 0.8,
                    "top_findings": ["ignore break"],
                },
            ],
        },
    )

    projection = YogaPracticeReviewProjectionBuilder().build(rollup)

    assert [chapter.chapter_id for chapter in projection.course_chapters] == [
        "opening_chat",
        "sun_flow",
        "water_break",
    ]
    assert [segment.chapter_id for segment in projection.learner_practice_segments] == [
        "sun_flow"
    ]
    assert [feedback.chapter_id for feedback in projection.chapter_feedback] == [
        "sun_flow"
    ]
    assert projection.course_chapters[0].match_role == "context"
    assert projection.course_chapters[1].match_role == "instruction"
    assert projection.course_chapters[2].guidance_mode == "suppress"
    assert projection.course_match_score is not None
    alignments = {
        alignment["chapter_id"]: alignment
        for alignment in projection.course_match_score["chapter_alignments"]
    }
    assert list(alignments) == ["opening_chat", "sun_flow", "water_break"]
    assert alignments["opening_chat"]["verdict"] == "insufficient_evidence"
    assert alignments["water_break"]["verdict"] == "insufficient_evidence"
