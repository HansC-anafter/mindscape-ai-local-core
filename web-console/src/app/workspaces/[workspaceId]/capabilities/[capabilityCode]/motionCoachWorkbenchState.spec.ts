import { describe, expect, it } from 'vitest';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import type { MotionPracticeLaunchInput, MotionPracticeLaunchResult } from '@/components/workspace/device-binding/motionPracticeLauncher';
import type { MotionPracticeClosureResult } from '@/components/workspace/device-binding/motionPracticeClosure';
import type { MotionWindowAppendEvent } from '@/components/workspace/device-binding/motionWindowAppendEvent';
import {
  buildDancePracticeWorkbenchState,
  buildYogaPracticeWorkbenchState,
} from './motionCoachWorkbenchState';

const sourceSession: DeviceSessionEntry = {
  session_id: 'session_1',
  workspace_id: 'ws_demo',
  pairing_code: 'PAIR1234',
  device_id: 'phone_1',
  display_name: 'Phone',
  source_types: ['phone_camera'],
  state: 'active',
  created_at_epoch: 1,
  updated_at_epoch: 1,
  expires_at_epoch: 100,
};

const launchInput: MotionPracticeLaunchInput = {
  apiUrl: 'http://api.test',
  workspaceId: 'ws_demo',
  sourceSession,
  coachPack: 'yogacoach',
  practiceMode: 'live_guidance',
  expertLibraryRef: 'mindscape://teacher/ref',
  instructionRefs: [
    {
      ref_type: 'manual_teacher_ref',
      teacher_ref: 'mindscape://teacher/ref',
      course_chapters: [
        {
          chapter_id: 'standing_alignment',
          title: 'Standing alignment',
          start_ms: 0,
          end_ms: 2000,
        },
      ],
    },
  ],
};

const practiceResult: MotionPracticeLaunchResult = {
  meetingId: 'mtg_1',
  commandId: null,
  playbookExecutionId: null,
  liveSessionId: 'lms_1',
  sourceSessionId: 'session_1',
  practiceSessionId: 'session_1:live_guidance',
  liveGuidanceEnabled: true,
  coachPack: 'yogacoach',
  practiceMode: 'live_guidance',
  status: 'active',
};

const motionWindowEvent: MotionWindowAppendEvent = {
  liveSessionId: 'lms_1',
  response: {
    accepted: true,
    motion_window_ref: 'window_1',
  },
  summary: {
    window_id: 'window_1',
    live_session_id: 'lms_1',
    ts_start_ms: 0,
    ts_end_ms: 2000,
    skeleton_family: 'mediapipe_pose_33',
    confidence_stats: {
      mean_confidence: 0.82,
    },
    scores: {},
    findings: ['Keep shoulders level.'],
    keypoint_frame_count: 20,
    metadata: {
      pose_provider: 'mediapipe_pose',
      keypoint_schema_id: 'mediapipe_pose_33',
      dwpose_node_deltas: [
        {
          node_id: 'shoulder_line',
          node_label: 'Shoulder line',
          learner_value: 0.04,
          reference_value: 0,
          delta_score: 0.33,
          severity: 'green',
          confidence: 0.9,
          finding: 'Shoulder line stayed level.',
          guidance: 'Keep shoulders level.',
        },
      ],
      sway_metrics: [],
      phase_metrics: [
        {
          phase: 'hold',
          learner_value: 0.02,
          reference_value: 0.02,
          delta_score: 0.12,
          severity: 'green',
          confidence: 0.88,
          finding: 'Hold stayed stable.',
          guidance: 'Maintain the same breath cadence.',
        },
      ],
    },
  },
};

describe('motionCoachWorkbenchState', () => {
  it('builds a rolling Yoga workbench state from live motion window events', () => {
    const state = buildYogaPracticeWorkbenchState({
      capabilityCode: 'yogacoach',
      selectedSession: sourceSession,
      referenceLessonState: {
        chapter_ref: 'standing_alignment',
        title: 'Foundation Flow',
        timestamp_ms: 1000,
        focus_cue: 'Lift through the collarbones.',
      },
      launchInput,
      practiceResult,
      motionWindowEvents: [motionWindowEvent],
      closureResult: null,
    }) as Record<string, any>;

    expect(state.connected_capture_source_ref).toMatchObject({
      id: 'session_1',
      type: 'phone',
      status: 'ready',
      transport: 'webrtc',
    });
    expect(state.motion_rollup_ref).toMatchObject({
      id: 'lms_1',
      status: 'rolling',
      motion_window_count: 1,
    });
    expect(state.motion_rollup_ref.digests[0]).toMatchObject({
      chapter_id: 'standing_alignment',
      phase: 'hold',
      confidence: 0.82,
    });
    expect(state.reference_lesson_import_ref).toMatchObject({
      status: 'ready',
      artifact_ref: 'mindscape://teacher/ref',
      confidence: 0.85,
      human_patch_required: false,
      ready_chapter_count: 1,
      source_provider: 'manual_teacher_ref',
      artifact_schema_id: 'vcs_instruction_video_prepared_bundle.v1',
    });
    expect(state.meeting_feedback_ref).toMatchObject({
      status: 'streaming',
    });
    expect(state.meeting_feedback_ref.cues).toContain('Keep shoulders level.');
  });

  it('keeps Yoga reference import materializing when only a live teacher cue is available', () => {
    const state = buildYogaPracticeWorkbenchState({
      capabilityCode: 'yogacoach',
      selectedSession: sourceSession,
      referenceLessonState: {
        lesson_id: 'lesson-live',
        chapter_ref: 'standing_alignment',
        title: 'Foundation Flow',
        timestamp_ms: 1000,
        focus_cue: 'Lift through the collarbones.',
      },
      launchInput: null,
      practiceResult: null,
      motionWindowEvents: [],
      closureResult: null,
    }) as Record<string, any>;

    expect(state.reference_lesson_import_ref).toMatchObject({
      id: 'reference_lesson_import_pending',
      status: 'materializing',
      confidence: 0.35,
      human_patch_required: true,
      ready_chapter_count: 0,
      source_provider: 'missing',
      artifact_schema_id: 'vcs_instruction_video_prepared_bundle.v1',
    });
    expect(state.reference_lesson_import_ref.blocked_reason).toContain('waiting for materialized course chapters');
    expect(state.reference_lesson_state.chapters[0]).toMatchObject({
      id: 'standing_alignment',
      title: 'Foundation Flow',
    });
  });

  it('builds a ready Dance workbench state from session-close rollup output', () => {
    const closureResult: MotionPracticeClosureResult = {
      rollup: {
        motion_rollup_ref: 'mindscape://motion_runtime/analysis/session-rollup/lms_1',
        summary: {
          window_count: 2,
          top_findings: ['Land the accent earlier.'],
          motion_window_digests: [
            {
              motion_window_ref: 'window_1',
              start_ms: 0,
              end_ms: 2000,
              confidence: 0.76,
              phase: 'transition',
              dwpose_node_deltas: [],
              sway_metrics: [
                {
                  axis: 'front_back',
                  learner_value: 0.07,
                  reference_value: 0.03,
                  delta_score: 0.42,
                  severity: 'yellow',
                  confidence: 0.81,
                  finding: 'Center line drifts forward.',
                  guidance: 'Stack the torso over the hips.',
                },
              ],
              phase_metrics: [],
            },
          ],
        },
      },
      command: {
        commandId: 'cmd_close',
        status: 'accepted',
        dispatchResult: {
          playbook: {
            triggered_playbook: {
              execution_id: 'exec_close_1',
            },
          },
        },
      },
    };

    const state = buildDancePracticeWorkbenchState({
      capabilityCode: 'dance_motion_coach',
      selectedSession: {
        ...sourceSession,
        source_types: ['virtual_camera'],
      },
      referenceLessonState: {
        chapter_ref: 'phrase_intro',
        title: 'Groove Phrase',
        timestamp_ms: 1000,
        focus_cue: 'Hit the accent on count four.',
      },
      launchInput: {
        ...launchInput,
        coachPack: 'dance_motion_coach',
        instructionRefs: [
          {
            ref_type: 'manual_teacher_ref',
            teacher_ref: 'mindscape://dance/ref',
            course_chapters: [
              {
                phrase_id: 'phrase_intro',
                title: 'Phrase intro',
                start_ms: 0,
                end_ms: 2000,
              },
            ],
          },
        ],
      },
      practiceResult: {
        ...practiceResult,
        coachPack: 'dance_motion_coach',
        practiceMode: 'live_guidance',
      },
      motionWindowEvents: [],
      closureResult,
    }) as Record<string, any>;

    expect(state.connected_capture_source_ref).toMatchObject({
      type: 'obs',
    });
    expect(state.motion_rollup_ref).toMatchObject({
      status: 'ready',
      motion_window_count: 2,
    });
    expect(state.motion_rollup_ref.digests[0]).toMatchObject({
      phrase_id: 'phrase_intro',
      phase: 'transition',
    });
    expect(state.meeting_feedback_ref).toMatchObject({
      status: 'ready',
      summary: 'Captured 2 motion windows and emitted a session rollup.',
    });
    expect(state.html_report_artifact_ref).toMatchObject({
      id: 'exec_close_1',
      status: 'rendering',
    });
  });
});
