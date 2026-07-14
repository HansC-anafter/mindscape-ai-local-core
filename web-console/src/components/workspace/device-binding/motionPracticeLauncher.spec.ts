import { afterEach, describe, expect, it, vi } from 'vitest';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import {
  buildMotionPracticeCommandMetadata,
  buildMotionPracticeCommandParameters,
  buildMotionPracticeReferenceMetadata,
  launchMotionPractice,
  resolveMotionPracticeTarget,
  type MotionPracticeLaunchInput,
} from './motionPracticeLauncher';

const mocks = vi.hoisted(() => ({
  startLiveMediaReceiver: vi.fn(async (input) => ({
    schema_version: 'live_media_receiver_control.v1',
    status: 'active',
    media_session_id: input.mediaSessionId,
  })),
}));

vi.mock('@/lib/media-transport/liveMediaReceiverClient', () => ({
  startLiveMediaReceiver: mocks.startLiveMediaReceiver,
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

const courseChapters = [
  {
    chapter_id: 'opening_chat',
    title: 'Opening chat',
    start_ms: 0,
    end_ms: 180000,
    segment_type: 'chat',
    scoreable: false,
    guidance_mode: 'suppress',
  },
  {
    chapter_id: 'sun_flow',
    title: 'Sun salutation flow',
    start_ms: 180000,
    end_ms: 480000,
    segment_type: 'practice',
    scoreable: true,
    guidance_mode: 'score',
  },
];

const segmentGraph = {
  graph_version: 'motion_reference_segment_graph.v1',
  ordered_edges: [
    { from: 'opening_chat', to: 'sun_flow', relation: 'next' },
  ],
  scoreable_segment_ids: ['sun_flow'],
  unordered_match_enabled: true,
  resync_policy: {
    ordered_prior_enabled: true,
    unordered_fallback_enabled: true,
    skip_non_scoreable_segments: true,
  },
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
      course_chapters: courseChapters,
      segment_graph: segmentGraph,
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
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

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
        transport: 'whip_rtsps_supervised_receiver',
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
        course_chapters: courseChapters,
        reference_segment_graphs: [segmentGraph],
      },
    });
    expectNoRawPayload(parameters);
  });

  it('preserves reference segment metadata for live motion runtime registration', () => {
    expect(buildMotionPracticeReferenceMetadata(baseInput)).toEqual({
      reference_source_ref: 'mindscape://teacher/ref',
      instruction_refs: baseInput.instructionRefs,
      course_chapters: courseChapters,
      reference_segment_graphs: [segmentGraph],
    });
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
      course_chapters: courseChapters,
      reference_segment_graphs: [segmentGraph],
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

  it('registers the formal motion session with append ownership before receiver start', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/meeting-sessions/active')) {
        return { ok: true, status: 200, json: async () => ({ id: 'meeting-one' }) };
      }
      if (url.endsWith('/analysis/live-sessions')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ live_session: { live_session_id: 'motion-one' } }),
        };
      }
      throw new Error(`unexpected fetch: ${url}:${init?.method || 'GET'}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    await launchMotionPractice({
      ...baseInput,
      practiceMode: 'live_guidance',
      sourceSession: {
        ...sourceSession,
        media_session_id: 'media-one',
      },
    });

    const registration = fetchMock.mock.calls.find(([url]) => (
      String(url).endsWith('/analysis/live-sessions')
    ));
    const registrationPayload = JSON.parse(String(registration?.[1]?.body));
    expect(registrationPayload.metadata.append_owner_required).toBe(true);
    expect(mocks.startLiveMediaReceiver).toHaveBeenCalledWith(expect.objectContaining({
      mediaSessionId: 'media-one',
      liveMotionSessionId: 'motion-one',
      meetingSessionId: 'meeting-one',
    }));
  });
});
