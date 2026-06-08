import { describe, expect, it } from 'vitest';

import {
  buildCaptureMotionWindowMetadata,
  deriveMediaPipePoseCaptureSample,
} from './captureMotionMetrics';

function buildPosePoints(centerYOffset = 0) {
  const points = Array.from({ length: 33 }, () => ({
    x: 0.5,
    y: 0.5,
    visibility: 0.92,
  }));
  points[11] = { x: 0.42, y: 0.42 + centerYOffset, visibility: 0.9 };
  points[12] = { x: 0.58, y: 0.35 + centerYOffset, visibility: 0.9 };
  points[23] = { x: 0.44, y: 0.64 + centerYOffset, visibility: 0.88 };
  points[24] = { x: 0.56, y: 0.61 + centerYOffset, visibility: 0.88 };
  points[25] = { x: 0.45, y: 0.82 + centerYOffset, visibility: 0.84 };
  points[26] = { x: 0.55, y: 0.8 + centerYOffset, visibility: 0.84 };
  return points;
}

function expectNoRawPayload(value: unknown) {
  const payload = JSON.stringify(value);
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

describe('captureMotionMetrics', () => {
  it('derives compact DWPose-compatible node, sway, and phase metrics from MediaPipe pose points', () => {
    const first = deriveMediaPipePoseCaptureSample(buildPosePoints(0));
    const second = deriveMediaPipePoseCaptureSample(buildPosePoints(0.08));

    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
    expect(first?.lineDeltas.find((item) => item.nodeId === 'shoulder_line')).toMatchObject({
      nodeLabel: 'Shoulder line',
      signedDelta: 0.07,
    });

    const metadata = buildCaptureMotionWindowMetadata([
      { captureMetrics: first },
      { captureMetrics: second },
    ]);

    expect(metadata).toMatchObject({
      pose_provider: 'mediapipe_pose',
      provider_code: 'browser_mediapipe_pose_lite',
      provider_schema_id: 'mediapipe_pose_landmarker_lite_video',
      keypoint_schema_id: 'mediapipe_pose_33',
      motion_metric_schema_version: 'capture_motion_metrics.v1',
    });
    expect(metadata.dwpose_node_deltas?.[0]).toMatchObject({
      node_id: 'shoulder_line',
      metric: 'capture_line_level_delta',
      reference_value: 0,
      direction: 'left_side_lower',
      severity: 'yellow',
    });
    expect(metadata.sway_metrics?.map((item) => item.axis)).toEqual(['left_right', 'front_back']);
    expect(metadata.phase_metrics?.[0]).toMatchObject({
      phase: 'transition',
      axis: 'front_back',
      metric: 'body_center_y_drift',
    });
    expectNoRawPayload(metadata);
  });

  it('keeps provider metadata even when no compact sample metrics are available', () => {
    const metadata = buildCaptureMotionWindowMetadata([]);

    expect(metadata).toMatchObject({
      pose_provider: 'mediapipe_pose',
      keypoint_schema_id: 'mediapipe_pose_33',
    });
    expect(metadata.dwpose_node_deltas).toBeUndefined();
    expect(metadata.sway_metrics).toBeUndefined();
    expect(metadata.phase_metrics).toBeUndefined();
    expectNoRawPayload(metadata);
  });
});
