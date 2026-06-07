import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MotionPracticeLiveGuidancePanel } from './MotionPracticeLiveGuidancePanel';
import type { MotionPracticeLaunchResult } from '../motionPracticeLauncher';

const mocks = vi.hoisted(() => ({
  fetchXttsHealth: vi.fn(async () => ({ available: true })),
  synthesizeXttsSpeech: vi.fn(async () => new Blob(['RIFF'], { type: 'audio/wav' })),
  enqueue: vi.fn(),
  interrupt: vi.fn(),
}));

vi.mock('@/lib/meeting-voice/voicePlaybackQueue', () => ({
  fetchXttsHealth: mocks.fetchXttsHealth,
  synthesizeXttsSpeech: mocks.synthesizeXttsSpeech,
  VoicePlaybackQueue: class {
    enqueue = mocks.enqueue;
    interrupt = mocks.interrupt;
  },
}));

const result: MotionPracticeLaunchResult = {
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

describe('MotionPracticeLiveGuidancePanel', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it('streams compact window events and plays speakable cues without polling', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    const instances: WebSocketMock[] = [];
    class WebSocketMock {
      static OPEN = 1;
      readyState = WebSocketMock.OPEN;
      sent: string[] = [];
      onopen: (() => void) | null = null;
      onmessage: ((event: { data: string }) => void) | null = null;
      onerror: (() => void) | null = null;
      onclose: (() => void) | null = null;

      constructor(public url: string) {
        instances.push(this);
      }

      send(message: string) {
        this.sent.push(message);
      }

      close() {
        this.onclose?.();
      }
    }
    vi.stubGlobal('WebSocket', WebSocketMock);

    const { rerender } = render(
      <MotionPracticeLiveGuidancePanel
        apiUrl="http://api.test"
        workspaceId="ws_motion"
        result={result}
        latestWindowAppend={null}
      />,
    );

    await act(async () => {
      instances[0].onopen?.();
      instances[0].onmessage?.({
        data: JSON.stringify({
          type: 'session_ready',
          workspace_id: 'ws_motion',
          meeting_id: 'mtg_motion',
          practice_session_id: 'session_1:live_guidance',
          state: 'active',
        }),
      });
      await Promise.resolve();
    });
    expect(mocks.fetchXttsHealth).toHaveBeenCalledTimes(1);

    rerender(
      <MotionPracticeLiveGuidancePanel
        apiUrl="http://api.test"
        workspaceId="ws_motion"
        result={result}
        latestWindowAppend={{
          liveSessionId: 'lms_motion',
          response: {
            accepted: true,
            live_session_id: 'lms_motion',
            motion_window_ref: 'window_ref',
          },
          summary: {
            window_id: 'window_1',
            live_session_id: 'lms_motion',
            ts_start_ms: 0,
            ts_end_ms: 2000,
            skeleton_family: 'mediapipe_pose_33',
            confidence_stats: { mean_confidence: 0.81 },
            scores: {},
            findings: ['Shift weight back over the standing foot.'],
            keypoint_frame_count: 20,
            metadata: { source: 'test' },
          },
        }}
      />,
    );

    const motionWindow = instances[0].sent
      .map((message) => JSON.parse(message))
      .find((message) => message.type === 'motion_window');
    expect(motionWindow).toMatchObject({
      live_session_id: 'lms_motion',
      motion_window_ref: 'window_ref',
      confidence: 0.81,
      top_findings: ['Shift weight back over the standing foot.'],
    });
    expect(motionWindow).not.toHaveProperty('keypoints');
    expect(motionWindow).not.toHaveProperty('frames');

    await act(async () => {
      instances[0].onmessage?.({
        data: JSON.stringify({
          type: 'guidance_cue',
          workspace_id: 'ws_motion',
          meeting_id: 'mtg_motion',
          practice_session_id: 'session_1:live_guidance',
          state: 'active',
          cue_text: 'Shift weight back over the standing foot.',
          cue_priority: 'correction',
          speakable: true,
        }),
      });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mocks.synthesizeXttsSpeech).toHaveBeenCalledTimes(1);
    expect(mocks.enqueue).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('motion-guidance-interrupt-button'));
    expect(mocks.interrupt).toHaveBeenCalled();
    expect(instances[0].sent.map((message) => JSON.parse(message))).toContainEqual(
      expect.objectContaining({ type: 'interrupt' }),
    );
    expect(setIntervalSpy).not.toHaveBeenCalled();
    setIntervalSpy.mockRestore();
  });
});
