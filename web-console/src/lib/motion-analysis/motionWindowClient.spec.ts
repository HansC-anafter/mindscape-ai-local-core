import { afterEach, describe, expect, it, vi } from 'vitest';

import { appendMotionWindow } from './motionWindowClient';
import type { MotionWindowSummary } from './livePoseWindow';

const summary: MotionWindowSummary = {
  window_id: 'lms_test:window:0:0',
  live_session_id: 'lms_test',
  ts_start_ms: 0,
  ts_end_ms: 2000,
  skeleton_family: 'mediapipe_pose_33',
  confidence_stats: {
    mean_confidence: 0.8,
    mean_visible_ratio: 0.9,
    sample_count: 30,
  },
  scores: {
    pose_confidence: 0.8,
    body_visibility: 0.9,
  },
  findings: [],
  keypoint_frame_count: 30,
  metadata: {
    source: 'workspace_webrtc_receiver',
  },
};

describe('motionWindowClient', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts compact motion windows to motion_runtime analysis append endpoint', async () => {
    const fetchMock = vi.fn(async () => Response.json({
      accepted: true,
      live_session_id: 'lms_test',
      motion_window_ref: 'lms_test:window:0:0',
    }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await appendMotionWindow({
      apiUrl: 'http://api.test/',
      summary,
      receivedAtMs: 2100,
    });

    expect(response.accepted).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/capabilities/motion_runtime/analysis/motion-windows',
      expect.objectContaining({
        method: 'POST',
        credentials: 'same-origin',
        body: JSON.stringify({
          motion_window_summary: summary,
          received_at_ms: 2100,
        }),
      }),
    );
  });

  it('surfaces backend validation errors without retry loops', async () => {
    const fetchMock = vi.fn(async () => Response.json(
      { detail: 'motion_window_summary_forbids_raw_payload' },
      { status: 422 },
    ));
    vi.stubGlobal('fetch', fetchMock);

    await expect(appendMotionWindow({
      apiUrl: 'http://api.test',
      summary,
    })).rejects.toThrow('motion_window_summary_forbids_raw_payload');

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
