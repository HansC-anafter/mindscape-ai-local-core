import React from 'react';
import { vi } from 'vitest';

import { clearMotionPracticeReferenceProfileResolutionCacheForTests } from '@/components/workspace/device-binding/practice/motionPracticeResolvedLesson';
import MotionCoachWorkbenchHost from './MotionCoachWorkbenchHost';

const navigationMocksState = vi.hoisted(() => ({
  searchParams: new URLSearchParams(),
}));

const motionCoachMocksState = vi.hoisted(() => ({
  existingBridge: null as Record<string, unknown> | null,
  publishReferenceLessonState: vi.fn(),
  phoneSourcePreviewProps: null as any,
  fetchReferenceProfileSelection: vi.fn(async () => ({
    status: 'ready' as const,
    artifact_id: 'artifact-reference-v3',
    reference_profile_id: 'profile-reference-v3',
    source_ref: 'https://www.bilibili.com/video/BV13g4y1u7di/',
    chapter_count: 2,
    duration_ms: 1_809_679,
    chapters: [
      {
        chapter_id: 'chapter-warmup',
        title: 'Warm up',
        start_ms: 0,
        end_ms: 60_000,
        segment_type: 'transition',
        confidence: 0.9,
      },
      {
        chapter_id: 'chapter-flow',
        title: 'Standing flow',
        start_ms: 60_000,
        end_ms: 1_809_679,
        segment_type: 'flow',
        confidence: 0.94,
      },
    ],
  })),
  launchMotionPractice: vi.fn(async (input: any) => ({
    meetingId: 'meeting-recovered',
    commandId: null,
    playbookExecutionId: null,
    liveSessionId: 'live-session-recovered',
    sourceSessionId: input.sourceSession.session_id,
    practiceSessionId: `${input.sourceSession.session_id}:live_guidance`,
    liveGuidanceEnabled: true,
    coachPack: input.coachPack,
    practiceMode: input.practiceMode,
    status: 'active',
  })),
  sessions: [
    {
      session_id: 'session-phone',
      workspace_id: 'ws-motion',
      pairing_code: 'PAIR1234',
      device_id: 'phone_1',
      display_name: 'Phone rear camera',
      source_types: ['phone_camera'],
      state: 'active',
      created_at_epoch: 1,
      updated_at_epoch: 1,
      expires_at_epoch: 999,
    },
    {
      session_id: 'session-obs',
      workspace_id: 'ws-motion',
      pairing_code: 'PAIR9999',
      device_id: 'obs_1',
      display_name: 'OBS Virtual Camera',
      source_types: ['virtual_camera'],
      state: 'paired',
      created_at_epoch: 2,
      updated_at_epoch: 2,
      expires_at_epoch: 999,
    },
  ] as any[],
  referenceLessonState: {
    lesson_id: 'lesson-live',
    title: 'Foundation Flow',
    chapter_ref: 'chapter_alignment',
    focus_cue: 'Lift through the collarbones and stabilize center line.',
    timestamp_ms: 18000,
  },
}));

export const navigationMocks = navigationMocksState;
export const motionCoachMocks = motionCoachMocksState;
export const launchMotionPracticeMock = motionCoachMocksState.launchMotionPractice;

vi.mock('next/navigation', () => ({
  useSearchParams: () => navigationMocks.searchParams,
}));

vi.mock('@/components/workspace/device-binding/capture-bridge/CaptureSourceBridgeProvider', () => ({
  CaptureSourceBridgeProvider: ({ children }: { children: React.ReactNode }) => React.createElement(
    'div',
    { 'data-testid': 'capture-source-bridge-provider' },
    children,
  ),
  useCaptureSourceBridge: () => ({
    sessions: motionCoachMocksState.sessions,
    referenceLessonState: motionCoachMocksState.referenceLessonState,
    publishReferenceLessonState: motionCoachMocksState.publishReferenceLessonState,
  }),
  useOptionalCaptureSourceBridge: () => motionCoachMocksState.existingBridge,
}));

vi.mock('@/components/workspace/device-binding/motionPracticeLauncher', async () => {
  const actual = await vi.importActual<typeof import('@/components/workspace/device-binding/motionPracticeLauncher')>(
    '@/components/workspace/device-binding/motionPracticeLauncher',
  );
  return {
    ...actual,
    launchMotionPractice: motionCoachMocksState.launchMotionPractice,
  };
});

vi.mock('@/components/workspace/device-binding/practice/motionPracticeReferenceProfileClient', async () => {
  const actual = await vi.importActual<typeof import('@/components/workspace/device-binding/practice/motionPracticeReferenceProfileClient')>(
    '@/components/workspace/device-binding/practice/motionPracticeReferenceProfileClient',
  );
  return {
    ...actual,
    fetchMotionPracticeReferenceProfileSelection:
      motionCoachMocksState.fetchReferenceProfileSelection,
  };
});

vi.mock('@/components/workspace/device-binding/PhoneSourcePreview', () => ({
  PhoneSourcePreview: (props: any) => {
    const emitted = React.useRef(false);
    motionCoachMocksState.phoneSourcePreviewProps = props;

    React.useEffect(() => {
      if (!props.liveMotionSessionId || emitted.current) {
        return;
      }
      emitted.current = true;
      props.onMotionWindowAppended?.({
        liveSessionId: props.liveMotionSessionId,
        response: {
          motion_window_ref: 'motion-window-1',
        },
        summary: {
          window_id: 'motion-window-1',
          ts_start_ms: 10000,
          ts_end_ms: 18000,
          findings: ['Shoulder line dropped below the teacher reference.'],
          confidence_stats: {
            mean_confidence: 0.82,
          },
          metadata: {
            pose_provider: 'mediapipe_pose',
            keypoint_schema_id: 'mediapipe_pose_33',
            dwpose_node_deltas: [
              {
                node_id: 'shoulder_line',
                node_label: 'Shoulder line',
                delta_score: 0.16,
                confidence: 0.9,
                finding: 'Shoulder line dropped below the teacher reference.',
                guidance: 'Lift through the collarbones before entering the hold.',
              },
            ],
            sway_metrics: [
              {
                axis: 'front_back_sway',
                delta_score: 0.11,
                confidence: 0.84,
                finding: 'Front/back sway stayed close to the teacher reference.',
                guidance: 'Keep the same breath cadence.',
              },
            ],
            phase_metrics: [
              {
                phase: 'entry',
                delta_score: 0.14,
                confidence: 0.8,
                finding: 'Entry into the posture is slightly rushed.',
                guidance: 'Use one more breath before locking the stance.',
              },
            ],
          },
        },
      });
    }, [props]);

    return React.createElement(
      'div',
      { 'data-testid': 'phone-source-preview' },
      `${props.session.session_id}:${props.liveMotionSessionId || 'idle'}`,
    );
  },
}));

export function createPhoneMotionSession() {
  return {
    session_id: 'session-phone',
    workspace_id: 'ws-motion',
    pairing_code: 'PAIR1234',
    device_id: 'phone_1',
    display_name: 'Phone rear camera',
    source_types: ['phone_camera'],
    state: 'active',
    created_at_epoch: 1,
    updated_at_epoch: 1,
    expires_at_epoch: 999,
  };
}

export function createObsMotionSession() {
  return {
    session_id: 'session-obs',
    workspace_id: 'ws-motion',
    pairing_code: 'PAIR9999',
    device_id: 'obs_1',
    display_name: 'OBS Virtual Camera',
    source_types: ['virtual_camera'],
    state: 'paired',
    created_at_epoch: 2,
    updated_at_epoch: 2,
    expires_at_epoch: 999,
  };
}

export function createDefaultMotionSessions() {
  return [
    createPhoneMotionSession(),
    createObsMotionSession(),
  ];
}

export function resetMotionCoachMocks() {
  clearMotionPracticeReferenceProfileResolutionCacheForTests();
  navigationMocks.searchParams = new URLSearchParams();
  motionCoachMocks.existingBridge = null;
  motionCoachMocks.publishReferenceLessonState = vi.fn();
  motionCoachMocks.phoneSourcePreviewProps = null;
  motionCoachMocks.launchMotionPractice.mockClear();
  motionCoachMocks.fetchReferenceProfileSelection.mockClear();
  motionCoachMocks.sessions = createDefaultMotionSessions();
  motionCoachMocks.referenceLessonState = {
    lesson_id: 'lesson-live',
    title: 'Foundation Flow',
    chapter_ref: 'chapter_alignment',
    focus_cue: 'Lift through the collarbones and stabilize center line.',
    timestamp_ms: 18000,
  };
}

export function createMotionCoachHostElement({
  capabilityCode = 'yogacoach',
  Component = () => React.createElement('div', { 'data-testid': 'runtime-component' }, 'Runtime'),
  aolHost = {},
  surfacePath = ['practice'],
}: {
  capabilityCode?: 'yogacoach' | 'dance_motion_coach';
  Component?: React.ComponentType<any>;
  aolHost?: any;
  surfacePath?: readonly string[];
} = {}) {
  return React.createElement(MotionCoachWorkbenchHost, {
    workspaceId: 'ws-motion',
    apiUrl: 'http://api.test',
    capabilityCode,
    Component,
    aolHost,
    surfacePath,
  });
}
