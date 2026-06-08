import { afterEach, describe, expect, it, vi } from 'vitest';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import {
  buildMotionPracticeClosureCommandParameters,
  closeMotionPracticeLiveGuidanceSession,
  type MotionPracticeSessionRollupResponse,
} from './motionPracticeClosure';
import type { MotionPracticeLaunchInput, MotionPracticeLaunchResult } from './motionPracticeLauncher';

const mocks = vi.hoisted(() => ({
  postApiJson: vi.fn(),
  submitMeetingCommandEnvelope: vi.fn(),
}));

vi.mock('@/components/capabilities/meeting-workbench/meetingApi', () => ({
  postApiJson: mocks.postApiJson,
}));

vi.mock('@/components/capabilities/meeting-workbench/meetingCommandLedger', () => ({
  submitMeetingCommandEnvelope: mocks.submitMeetingCommandEnvelope,
}));

const sourceSession: DeviceSessionEntry = {
  session_id: 'session_1',
  workspace_id: 'ws_device',
  pairing_code: 'PAIR1234',
  device_id: 'phone_1',
  display_name: 'Phone',
  source_types: ['phone_camera'],
  state: 'active',
  created_at_epoch: 1,
  updated_at_epoch: 1,
  expires_at_epoch: 61,
};

const baseInput: MotionPracticeLaunchInput = {
  apiUrl: 'http://api.test',
  workspaceId: 'ws_device',
  sourceSession,
  coachPack: 'yogacoach',
  practiceMode: 'live_guidance',
  expertLibraryRef: 'mindscape://teacher/ref',
  instructionRefs: [
    {
      ref_type: 'youtube_instruction_ref',
      source_provider: 'youtube',
      video_ref: 'https://www.youtube.com/watch?v=demo',
      frame_readable: false,
      motion_analysis_source: false,
      course_chapters: [
        {
          chapter_id: 'chapter_1',
          title: 'Warmup',
          start_ms: 0,
          end_ms: 5000,
        },
      ],
    },
  ],
  userGoal: 'Improve balance.',
};

const launchResult: MotionPracticeLaunchResult = {
  meetingId: 'mtg_motion',
  commandId: null,
  liveSessionId: 'lms_motion',
  sourceSessionId: 'session_1',
  practiceSessionId: 'session_1:live_guidance',
  liveGuidanceEnabled: true,
  coachPack: 'yogacoach',
  practiceMode: 'live_guidance',
  status: 'active',
};

const rollupResponse: MotionPracticeSessionRollupResponse = {
  emitted: true,
  live_session_id: 'lms_motion',
  motion_rollup_ref: 'mindscape://motion_runtime/session-rollups/lms_motion',
  artifact_id: 'artifact_motion_rollup',
  artifact_registry: { backend: 'artifact_registry' },
  summary: {
    window_count: 4,
    duration_ms: 8200,
    confidence_stats: { mean_confidence: 0.82 },
    score_summary: { balance: 0.71 },
    finding_counts: { correction: 2 },
    top_findings: ['Keep the left knee tracking over the toes.'],
    motion_window_refs: ['window_1', 'window_2'],
    motion_window_digests: [
      {
        motion_window_ref: 'window_1',
        window_index: 0,
        start_ms: 0,
        end_ms: 5000,
        confidence: 0.82,
        top_findings: ['Keep the left knee tracking over the toes.'],
      },
    ],
  },
};

function expectNoRawPayload(payload: unknown) {
  const forbiddenKeys = new Set([
    'raw_frame',
    'raw_video',
    'video_base64',
    'frame_base64',
    'keypoints',
    'frames',
  ]);
  const visit = (value: unknown) => {
    if (!value || typeof value !== 'object') {
      return;
    }
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      expect(forbiddenKeys.has(key)).toBe(false);
      visit(nested);
    }
  };
  visit(payload);
}

describe('motionPracticeClosure', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('emits a session rollup and submits a compact Yoga summary command', async () => {
    mocks.postApiJson.mockResolvedValueOnce(rollupResponse);
    mocks.submitMeetingCommandEnvelope.mockResolvedValueOnce({
      commandId: 'cmd_summary',
      status: 'accepted',
      dispatchResult: { accepted: true },
    });

    const closure = await closeMotionPracticeLiveGuidanceSession({
      input: baseInput,
      result: launchResult,
    });

    expect(mocks.postApiJson).toHaveBeenCalledWith(
      'http://api.test',
      '/api/v1/capabilities/motion_runtime/analysis/session-rollups',
      expect.objectContaining({
        live_session_id: 'lms_motion',
        instruction_refs: baseInput.instructionRefs,
        max_window_refs: 100,
        max_top_findings: 8,
        metadata: expect.objectContaining({
          course_chapters: [
            {
              chapter_id: 'chapter_1',
              title: 'Warmup',
              start_ms: 0,
              end_ms: 5000,
            },
          ],
        }),
      }),
    );

    expect(mocks.submitMeetingCommandEnvelope).toHaveBeenCalledWith(
      expect.objectContaining({
        apiUrl: 'http://api.test',
        workspaceId: 'ws_device',
        meetingId: 'mtg_motion',
        originSurface: 'workspace_motion_source_practice_closure',
        requestedAction: expect.objectContaining({
          verb: 'execute_playbook',
          pack_code: 'yogacoach',
          playbook_code: 'yogacoach_student_practice_summary',
        }),
      }),
    );
    const commandArgs = mocks.submitMeetingCommandEnvelope.mock.calls[0][0];
    expect(commandArgs.actionParameters.live_practice_rollup).toMatchObject({
      practice_session_id: 'session_1:live_guidance',
      window_count: 4,
      duration_ms: 8200,
      score_aggregates: { balance: 0.71 },
      safety_event_counts: { correction: 2 },
      summary_confidence: 'complete',
      motion_summary_refs: [
        expect.objectContaining({
          ref_type: 'motion_session_rollup',
          motion_rollup_ref: 'mindscape://motion_runtime/session-rollups/lms_motion',
          artifact_id: 'artifact_motion_rollup',
        }),
      ],
      metadata: expect.objectContaining({
        course_chapters: [
          {
            chapter_id: 'chapter_1',
            title: 'Warmup',
            start_ms: 0,
            end_ms: 5000,
          },
        ],
        motion_window_digests: [
          expect.objectContaining({
            motion_window_ref: 'window_1',
            confidence: 0.82,
          }),
        ],
        motion_window_refs: ['window_1', 'window_2'],
      }),
    });
    expect(commandArgs.metadata).toMatchObject({
      motion_practice_close: true,
      phase: 'phase_06_close_rollup_summary',
      motion_rollup_ref: 'mindscape://motion_runtime/session-rollups/lms_motion',
    });
    expect(closure.command.commandId).toBe('cmd_summary');
    expectNoRawPayload(commandArgs);
  });

  it('maps Dance closure commands to the Dance session summary playbook', () => {
    const parameters = buildMotionPracticeClosureCommandParameters({
      input: {
        ...baseInput,
        coachPack: 'dance_motion_coach',
      },
      result: {
        ...launchResult,
        coachPack: 'dance_motion_coach',
      },
      rollup: rollupResponse,
    });

    expect(parameters.practice_session).toMatchObject({
      workspace_id: 'ws_device',
      capture_session_id: 'session_1',
      live_motion_session_id: 'lms_motion',
    });
    expect(parameters.motion_summary).toMatchObject({
      motion_summary_ref: 'mindscape://motion_runtime/session-rollups/lms_motion',
      live_session_id: 'lms_motion',
      rollup_artifact_id: 'artifact_motion_rollup',
      scores: { balance: 0.71 },
      findings: ['Keep the left knee tracking over the toes.'],
    });
    expectNoRawPayload(parameters);
  });
});
