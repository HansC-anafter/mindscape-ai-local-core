import React from 'react';
import { vi } from 'vitest';

import MotionCoachWorkbenchHost from './MotionCoachWorkbenchHost';

const navigationMocksState = vi.hoisted(() => ({
  searchParams: new URLSearchParams(),
}));

const motionCoachMocksState = vi.hoisted(() => ({
  existingBridge: null as Record<string, unknown> | null,
  publishReferenceLessonState: vi.fn(),
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
  ],
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
    sessions: motionCoachMocks.sessions,
    referenceLessonState: motionCoachMocks.referenceLessonState,
    publishReferenceLessonState: motionCoachMocks.publishReferenceLessonState,
  }),
  useOptionalCaptureSourceBridge: () => motionCoachMocks.existingBridge,
}));

vi.mock('@/components/workspace/device-binding/PhoneSourcePreview', () => ({
  PhoneSourcePreview: (props: any) => {
    const emitted = React.useRef(false);

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
  navigationMocks.searchParams = new URLSearchParams();
  motionCoachMocks.existingBridge = null;
  motionCoachMocks.publishReferenceLessonState = vi.fn();
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
