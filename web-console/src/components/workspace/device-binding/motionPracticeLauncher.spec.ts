import { describe, expect, it } from 'vitest';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import {
  buildMotionPracticeCommandMetadata,
  buildMotionPracticeCommandParameters,
  resolveMotionPracticeTarget,
  type MotionPracticeLaunchInput,
} from './motionPracticeLauncher';

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
  practiceMode: 'record_summary',
  expertLibraryRef: 'mindscape://teacher/ref',
  instructionRefs: [
    {
      source_provider: 'youtube',
      video_id: 'dQw4w9WgXcQ',
      frame_readable: false,
      motion_analysis_source: false,
    },
  ],
};

const liveSessionPayload = {
  live_session: {
    live_session_id: 'lms_motion',
  },
};

function expectNoRawPayload(payload: unknown) {
  const forbiddenKeys = new Set([
    'raw_frame',
    'raw_video',
    'video_base64',
    'frame_base64',
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

describe('motionPracticeLauncher', () => {
  it('routes practice launch commands through explicit playbook dispatch', () => {
    const metadata = buildMotionPracticeCommandMetadata(baseInput);

    expect(metadata).toMatchObject({
      dispatch_mode: 'route_playbook',
      explicit_override: true,
      motion_practice_launch: true,
      motion_practice_command: true,
      coach_pack: 'yogacoach',
      practice_mode: 'record_summary',
      resource_policy: {
        raw_media_db_writes: false,
        raw_frame_meeting_ledger_writes: false,
        ux_polling: false,
        worker_required_for_launch: false,
        transport: 'webrtc_signal_and_peer_connection',
      },
    });
    expect(metadata).not.toHaveProperty('force_meeting_orchestration');
    expect(metadata).not.toHaveProperty('forceMeetingOrchestration');
  });

  it('passes instruction refs through the Yoga live_practice_rollup metadata', () => {
    const parameters = buildMotionPracticeCommandParameters({
      input: baseInput,
      meetingId: 'mtg_motion',
      liveSessionPayload,
    });

    expect(parameters.live_practice_rollup).toMatchObject({
      metadata: {
        instruction_refs: baseInput.instructionRefs,
      },
    });
    expectNoRawPayload(parameters);
  });

  it('enables Dance record summary with compact refs only', () => {
    const target = resolveMotionPracticeTarget('dance_motion_coach', 'record_summary');
    const parameters = buildMotionPracticeCommandParameters({
      input: {
        ...baseInput,
        coachPack: 'dance_motion_coach',
        practiceMode: 'record_summary',
      },
      meetingId: 'mtg_motion',
      liveSessionPayload,
    });

    expect(target).toMatchObject({
      enabled: true,
      packCode: 'dance_motion_coach',
      playbookCode: 'dance_motion_coach_session_summary',
    });
    expect(parameters.practice_session).toMatchObject({
      workspace_id: 'ws_device',
      capture_session_id: 'session_1',
      live_motion_session_id: 'lms_motion',
    });
    expect(parameters.motion_summary).toMatchObject({
      live_session_id: 'lms_motion',
      instruction_refs: baseInput.instructionRefs,
    });
    expectNoRawPayload(parameters);
  });

  it('enables live guidance as a non-command launch target', () => {
    expect(resolveMotionPracticeTarget('yogacoach', 'live_guidance')).toMatchObject({
      enabled: true,
      packCode: 'yogacoach',
      playbookCode: null,
      launchKind: 'live_guidance',
    });
    expect(resolveMotionPracticeTarget('dance_motion_coach', 'live_guidance')).toMatchObject({
      enabled: true,
      packCode: 'dance_motion_coach',
      playbookCode: null,
      launchKind: 'live_guidance',
    });
  });
});
