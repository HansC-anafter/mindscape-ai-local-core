import { describe, expect, it, vi } from 'vitest';

import {
  createLivePoseWindowAccumulator,
  createLivePoseWindowController,
  type LivePoseWindowAdapter,
  type MotionWindowSummary,
} from './livePoseWindow';
import type { CapturePoseSampleMetrics } from './captureMotionMetrics';

function buildCaptureMetrics(): CapturePoseSampleMetrics {
  return {
    bodyCenterX: 0.5,
    bodyCenterY: 0.45,
    confidence: 0.82,
    lineDeltas: [
      {
        nodeId: 'shoulder_line',
        nodeLabel: 'Shoulder line',
        signedDelta: 0.04,
        confidence: 0.82,
      },
    ],
  };
}

function buildSample(timestampMs: number) {
  return {
    timestampMs,
    confidence: 0.82,
    visiblePointCount: 30,
    totalPointCount: 33,
    captureMetrics: buildCaptureMetrics(),
  };
}

function expectNoRawPayload(summary: MotionWindowSummary) {
  const payload = JSON.stringify(summary);
  for (const forbidden of [
    '"frame"',
    '"frames"',
    '"keypoints"',
    '"landmark"',
    '"landmarks"',
    '"raw_frame"',
    '"raw_video"',
    '"video_bytes"',
  ]) {
    expect(payload).not.toContain(forbidden);
  }
}

describe('livePoseWindow', () => {
  it('emits bounded compact windows without raw pose payloads', () => {
    const accumulator = createLivePoseWindowAccumulator({
      liveSessionId: 'lms_test',
      windowMs: 2000,
      maxSamples: 30,
      metadata: {
        workspace_id: 'ws_test',
        source_session_id: 'session_test',
      },
    });

    let summary: MotionWindowSummary | null = null;
    for (let index = 0; index < 35; index += 1) {
      summary = accumulator.push(buildSample(index * 70)) || summary;
      if (summary) {
        break;
      }
    }

    expect(summary).not.toBeNull();
    expect(summary).toMatchObject({
      live_session_id: 'lms_test',
      skeleton_family: 'mediapipe_pose_33',
      keypoint_frame_count: 30,
      metadata: expect.objectContaining({
        source: 'workspace_webrtc_receiver',
        max_samples: 30,
      }),
    });
    expect(summary?.confidence_stats.sample_count).toBe(30);
    expect(summary?.scores.pose_confidence).toBeGreaterThan(0.8);
    expect(summary?.metadata).toMatchObject({
      pose_provider: 'mediapipe_pose',
      provider_code: 'browser_mediapipe_pose_lite',
      provider_schema_id: 'mediapipe_pose_landmarker_lite_video',
      keypoint_schema_id: 'mediapipe_pose_33',
      motion_metric_schema_version: 'capture_motion_metrics.v1',
      dwpose_node_deltas: [
        expect.objectContaining({
          node_id: 'shoulder_line',
          metric: 'capture_line_level_delta',
        }),
      ],
      sway_metrics: expect.any(Array),
      phase_metrics: expect.any(Array),
    });
    expectNoRawPayload(summary as MotionWindowSummary);
  });

  it('uses animation frames and stops without interval loops', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    const callbacks: FrameRequestCallback[] = [];
    const cancelFrame = vi.fn();
    const appendMotionWindow = vi.fn();
    const adapter: LivePoseWindowAdapter = {
      provider: 'test_pose',
      getStatus: () => ({ state: 'ready' }),
      estimate: vi.fn(async (_video, timestampMs) => buildSample(timestampMs)),
      dispose: vi.fn(),
    };
    const video = document.createElement('video');
    Object.defineProperty(video, 'readyState', {
      configurable: true,
      value: 2,
    });

    const controller = createLivePoseWindowController({
      video,
      liveSessionId: 'lms_test',
      adapter,
      appendMotionWindow,
      sampleFps: 15,
      scheduler: {
        requestFrame: (callback) => {
          callbacks.push(callback);
          return callbacks.length;
        },
        cancelFrame,
      },
      now: () => 3000,
    });

    controller.start();
    expect(callbacks).toHaveLength(1);
    for (let index = 0; index < 31; index += 1) {
      const callback = callbacks.shift();
      expect(callback).toBeDefined();
      callback?.(index * 70);
      await Promise.resolve();
    }

    expect(setIntervalSpy).not.toHaveBeenCalled();
    expect(appendMotionWindow).toHaveBeenCalledTimes(1);
    expectNoRawPayload(appendMotionWindow.mock.calls[0][0]);

    controller.stop();
    const appendCountAfterStop = appendMotionWindow.mock.calls.length;
    callbacks.shift()?.(4000);
    await Promise.resolve();

    expect(cancelFrame).toHaveBeenCalled();
    expect(appendMotionWindow).toHaveBeenCalledTimes(appendCountAfterStop);
    expect(adapter.dispose).toHaveBeenCalled();
  });
});
