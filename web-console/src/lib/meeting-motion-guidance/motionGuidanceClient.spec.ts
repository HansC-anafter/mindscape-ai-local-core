import { describe, expect, it, vi, afterEach } from 'vitest';

import {
  buildMotionGuidanceWebSocketUrl,
  buildMotionGuidanceWindowEvent,
  openMotionGuidanceSocket,
} from './motionGuidanceClient';

describe('motionGuidanceClient', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds workspace motion guidance WebSocket URLs', () => {
    expect(
      buildMotionGuidanceWebSocketUrl({
        apiBase: 'https://api.test',
        workspaceId: 'ws motion',
        meetingId: 'mtg/1',
        practiceSessionId: 'session:live_guidance',
      }),
    ).toBe(
      'wss://api.test/api/v1/workspaces/ws%20motion/meetings/mtg%2F1/motion-guidance/session%3Alive_guidance/stream',
    );
  });

  it('opens one socket and sends session_start on open', () => {
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
    const onEvent = vi.fn();

    const socket = openMotionGuidanceSocket({
      apiBase: 'http://api.test',
      workspaceId: 'ws_motion',
      meetingId: 'mtg_motion',
      practiceSessionId: 'practice_1',
      liveSessionId: 'lms_motion',
      onEvent,
    });

    instances[0].onopen?.();
    expect(JSON.parse(instances[0].sent[0])).toMatchObject({
      type: 'session_start',
      live_session_id: 'lms_motion',
    });

    socket.send({ type: 'interrupt', event_id: 'interrupt_1' });
    expect(JSON.parse(instances[0].sent[1])).toMatchObject({
      type: 'interrupt',
      event_id: 'interrupt_1',
    });

    instances[0].onmessage?.({
      data: JSON.stringify({
        type: 'session_ready',
        workspace_id: 'ws_motion',
        meeting_id: 'mtg_motion',
        practice_session_id: 'practice_1',
      }),
    });
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'session_ready' }),
    );
  });

  it('converts append summaries into compact guidance window events', () => {
    const event = buildMotionGuidanceWindowEvent({
      liveSessionId: 'lms_motion',
      motionWindowRef: 'window_ref',
      summary: {
        window_id: 'window_1',
        live_session_id: 'lms_motion',
        ts_start_ms: 0,
        ts_end_ms: 2000,
        skeleton_family: 'mediapipe_pose_33',
        confidence_stats: { mean_confidence: 0.82 },
        scores: {},
        findings: ['Shift weight back over the standing foot.'],
        keypoint_frame_count: 20,
        metadata: { source: 'test' },
      },
    });

    expect(event).toMatchObject({
      eventId: 'window_1:guidance',
      liveSessionId: 'lms_motion',
      motionWindowRef: 'window_ref',
      confidence: 0.82,
      findings: ['Shift weight back over the standing foot.'],
    });
  });

  it('derives actionable guidance from compact motion metric metadata', () => {
    const event = buildMotionGuidanceWindowEvent({
      liveSessionId: 'lms_motion',
      motionWindowRef: 'window_ref',
      summary: {
        window_id: 'window_2',
        live_session_id: 'lms_motion',
        ts_start_ms: 2000,
        ts_end_ms: 4000,
        skeleton_family: 'mediapipe_pose_33',
        confidence_stats: { mean_confidence: 0.91 },
        scores: {},
        findings: [],
        keypoint_frame_count: 20,
        metadata: {
          source: 'test',
          dwpose_node_deltas: [
            {
              node_label: 'Shoulder line',
              severity: 'green',
              delta_score: 0.25,
              finding: 'Shoulder line tilted with the right side lower than the left.',
              guidance: 'Level both shoulders before holding the pose.',
            },
            {
              node_label: 'Knee line',
              severity: 'red',
              delta_score: 1,
              finding: 'Knee line tilted with the right side lower than the left.',
              guidance: 'Re-balance both knees before moving to the next phase.',
            },
          ],
          sway_metrics: [
            {
              axis: 'left_right',
              severity: 'yellow',
              delta_score: 0.5,
              guidance: 'Keep the body center stacked over the base before continuing.',
            },
          ],
        },
      },
    });

    expect(event.findings).toEqual([
      'Knee line: Re-balance both knees before moving to the next phase.',
      'left_right: Keep the body center stacked over the base before continuing.',
      'Shoulder line: Level both shoulders before holding the pose.',
    ]);
  });
});
