'use client';

export type CapturePoseLineDelta = {
  nodeId: string;
  nodeLabel: string;
  signedDelta: number;
  confidence: number;
};

export type CapturePoseSampleMetrics = {
  bodyCenterX: number;
  bodyCenterY: number;
  confidence: number;
  lineDeltas: CapturePoseLineDelta[];
};

export type CaptureNodeDelta = {
  node_id: string;
  node_label: string;
  metric: 'capture_line_level_delta';
  direction: string;
  learner_value: number;
  reference_value: 0;
  delta_score: number;
  severity: 'green' | 'yellow' | 'red';
  confidence: number;
  finding: string;
  guidance: string;
};

export type CaptureSwayMetric = {
  axis: 'front_back' | 'left_right';
  phase: 'window';
  metric: string;
  learner_value: number;
  reference_value: number;
  delta_score: number;
  severity: 'green' | 'yellow' | 'red';
  confidence: number;
  finding: string;
  guidance: string;
};

export type CapturePhaseMetric = {
  phase: 'hold' | 'transition';
  axis: 'front_back';
  metric: 'body_center_y_drift';
  learner_value: number;
  reference_value: number;
  delta_score: number;
  severity: 'green' | 'yellow' | 'red';
  confidence: number;
  finding: string;
  guidance: string;
};

export type CaptureMotionWindowMetadata = {
  pose_provider: 'mediapipe_pose';
  provider_code: 'browser_mediapipe_pose_lite';
  provider_schema_id: 'mediapipe_pose_landmarker_lite_video';
  keypoint_schema_id: 'mediapipe_pose_33';
  motion_metric_schema_version: 'capture_motion_metrics.v1';
  dwpose_node_deltas?: CaptureNodeDelta[];
  sway_metrics?: CaptureSwayMetric[];
  phase_metrics?: CapturePhaseMetric[];
};

type NormalizedPosePoint = {
  x: number;
  y: number;
  confidence: number;
};

type PairSpec = {
  nodeId: string;
  nodeLabel: string;
  leftIndex: number;
  rightIndex: number;
  guidance: string;
};

const MIN_PAIR_CONFIDENCE = 0.35;
const LINE_DELTA_RED_THRESHOLD = 0.12;
const SWAY_RED_THRESHOLD = 0.16;
const PHASE_DRIFT_RED_THRESHOLD = 0.12;
const STABLE_SWAY_REFERENCE = 0.04;
const STABLE_DRIFT_REFERENCE = 0.02;

const PAIRS: PairSpec[] = [
  {
    nodeId: 'shoulder_line',
    nodeLabel: 'Shoulder line',
    leftIndex: 11,
    rightIndex: 12,
    guidance: 'Level both shoulders before holding the pose.',
  },
  {
    nodeId: 'hip_line',
    nodeLabel: 'Hip line',
    leftIndex: 23,
    rightIndex: 24,
    guidance: 'Square the hips and keep the pelvis level.',
  },
  {
    nodeId: 'knee_line',
    nodeLabel: 'Knee line',
    leftIndex: 25,
    rightIndex: 26,
    guidance: 'Re-balance both knees before moving to the next phase.',
  },
];

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(0, value));
}

function average(values: number[]): number {
  if (!values.length) {
    return 0;
  }
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function roundMetric(value: number): number {
  return Math.round(value * 1000) / 1000;
}

function normalizePoint(point: unknown): NormalizedPosePoint | null {
  if (!point || typeof point !== 'object') {
    return null;
  }
  const payload = point as {
    x?: unknown;
    y?: unknown;
    visibility?: unknown;
    presence?: unknown;
  };
  const x = asNumber(payload.x);
  const y = asNumber(payload.y);
  if (x === null || y === null) {
    return null;
  }
  const visibility = asNumber(payload.visibility);
  const presence = asNumber(payload.presence);
  return {
    x,
    y,
    confidence: clamp01(visibility ?? presence ?? 1),
  };
}

function readPoint(points: unknown[], index: number): NormalizedPosePoint | null {
  return normalizePoint(points[index]);
}

function severityFromScore(score: number): 'green' | 'yellow' | 'red' {
  if (score >= 0.67) {
    return 'red';
  }
  if (score >= 0.34) {
    return 'yellow';
  }
  return 'green';
}

function directionFromSignedDelta(value: number): string {
  if (Math.abs(value) < 0.015) {
    return 'level';
  }
  return value > 0 ? 'left_side_lower' : 'right_side_lower';
}

function lineFinding(nodeLabel: string, signedDelta: number): string {
  const direction = directionFromSignedDelta(signedDelta);
  if (direction === 'level') {
    return `${nodeLabel} stayed close to level.`;
  }
  if (direction === 'left_side_lower') {
    return `${nodeLabel} tilted with the left side lower than the right.`;
  }
  return `${nodeLabel} tilted with the right side lower than the left.`;
}

function range(values: number[]): number {
  if (values.length < 2) {
    return 0;
  }
  return Math.max(...values) - Math.min(...values);
}

function buildLineDelta(points: unknown[], pair: PairSpec): CapturePoseLineDelta | null {
  const left = readPoint(points, pair.leftIndex);
  const right = readPoint(points, pair.rightIndex);
  if (!left || !right) {
    return null;
  }
  const confidence = Math.min(left.confidence, right.confidence);
  if (confidence < MIN_PAIR_CONFIDENCE) {
    return null;
  }
  return {
    nodeId: pair.nodeId,
    nodeLabel: pair.nodeLabel,
    signedDelta: roundMetric(left.y - right.y),
    confidence: roundMetric(confidence),
  };
}

export function deriveMediaPipePoseCaptureSample(points: unknown): CapturePoseSampleMetrics | null {
  if (!Array.isArray(points) || points.length < 29) {
    return null;
  }
  const centerPoints = [11, 12, 23, 24]
    .map((index) => readPoint(points, index))
    .filter((point): point is NormalizedPosePoint => Boolean(point));
  if (!centerPoints.length) {
    return null;
  }
  const lineDeltas = PAIRS
    .map((pair) => buildLineDelta(points, pair))
    .filter((delta): delta is CapturePoseLineDelta => Boolean(delta));
  return {
    bodyCenterX: roundMetric(average(centerPoints.map((point) => point.x))),
    bodyCenterY: roundMetric(average(centerPoints.map((point) => point.y))),
    confidence: roundMetric(average([
      ...centerPoints.map((point) => point.confidence),
      ...lineDeltas.map((delta) => delta.confidence),
    ])),
    lineDeltas,
  };
}

function buildNodeDeltas(samples: CapturePoseSampleMetrics[]): CaptureNodeDelta[] {
  return PAIRS.flatMap((pair) => {
    const matching = samples
      .flatMap((sample) => sample.lineDeltas)
      .filter((delta) => delta.nodeId === pair.nodeId);
    if (!matching.length) {
      return [];
    }
    const signedDelta = roundMetric(average(matching.map((delta) => delta.signedDelta)));
    const confidence = roundMetric(average(matching.map((delta) => delta.confidence)));
    const deltaScore = roundMetric(clamp01(Math.abs(signedDelta) / LINE_DELTA_RED_THRESHOLD));
    return [{
      node_id: pair.nodeId,
      node_label: pair.nodeLabel,
      metric: 'capture_line_level_delta' as const,
      direction: directionFromSignedDelta(signedDelta),
      learner_value: signedDelta,
      reference_value: 0 as const,
      delta_score: deltaScore,
      severity: severityFromScore(deltaScore),
      confidence,
      finding: lineFinding(pair.nodeLabel, signedDelta),
      guidance: pair.guidance,
    }];
  });
}

function buildSwayMetrics(samples: CapturePoseSampleMetrics[]): CaptureSwayMetric[] {
  if (samples.length < 2) {
    return [];
  }
  const confidence = roundMetric(average(samples.map((sample) => sample.confidence)));
  const xRange = roundMetric(range(samples.map((sample) => sample.bodyCenterX)));
  const yRange = roundMetric(range(samples.map((sample) => sample.bodyCenterY)));
  const leftRightScore = roundMetric(clamp01(xRange / SWAY_RED_THRESHOLD));
  const frontBackScore = roundMetric(clamp01(yRange / SWAY_RED_THRESHOLD));
  return [
    {
      axis: 'left_right',
      phase: 'window',
      metric: 'body_center_x_range',
      learner_value: xRange,
      reference_value: STABLE_SWAY_REFERENCE,
      delta_score: leftRightScore,
      severity: severityFromScore(leftRightScore),
      confidence,
      finding: 'Body center moved side to side during this capture window.',
      guidance: 'Keep the body center stacked over the base before continuing.',
    },
    {
      axis: 'front_back',
      phase: 'window',
      metric: 'body_center_y_range',
      learner_value: yRange,
      reference_value: STABLE_SWAY_REFERENCE,
      delta_score: frontBackScore,
      severity: severityFromScore(frontBackScore),
      confidence,
      finding: 'Body center shifted forward and back during this capture window.',
      guidance: 'Reduce forward/back sway while holding the key posture.',
    },
  ];
}

function buildPhaseMetrics(samples: CapturePoseSampleMetrics[]): CapturePhaseMetric[] {
  if (samples.length < 2) {
    return [];
  }
  const first = samples[0];
  const last = samples[samples.length - 1];
  const confidence = roundMetric(average(samples.map((sample) => sample.confidence)));
  const drift = roundMetric(Math.abs(last.bodyCenterY - first.bodyCenterY));
  const score = roundMetric(clamp01(drift / PHASE_DRIFT_RED_THRESHOLD));
  return [{
    phase: score >= 0.34 ? 'transition' : 'hold',
    axis: 'front_back',
    metric: 'body_center_y_drift',
    learner_value: drift,
    reference_value: STABLE_DRIFT_REFERENCE,
    delta_score: score,
    severity: severityFromScore(score),
    confidence,
    finding: score >= 0.34
      ? 'Forward/back body center drift increased across the window.'
      : 'Forward/back body center drift stayed controlled across the window.',
    guidance: score >= 0.34
      ? 'Slow the transition and re-center before the next hold.'
      : 'Keep the same center control through the next breath cycle.',
  }];
}

export function buildCaptureMotionWindowMetadata(
  samples: Array<{ captureMetrics?: CapturePoseSampleMetrics | null }>,
): CaptureMotionWindowMetadata {
  const captureSamples = samples
    .map((sample) => sample.captureMetrics)
    .filter((metrics): metrics is CapturePoseSampleMetrics => Boolean(metrics));
  const nodeDeltas = buildNodeDeltas(captureSamples);
  const swayMetrics = buildSwayMetrics(captureSamples);
  const phaseMetrics = buildPhaseMetrics(captureSamples);
  return {
    pose_provider: 'mediapipe_pose',
    provider_code: 'browser_mediapipe_pose_lite',
    provider_schema_id: 'mediapipe_pose_landmarker_lite_video',
    keypoint_schema_id: 'mediapipe_pose_33',
    motion_metric_schema_version: 'capture_motion_metrics.v1',
    ...(nodeDeltas.length ? { dwpose_node_deltas: nodeDeltas } : {}),
    ...(swayMetrics.length ? { sway_metrics: swayMetrics } : {}),
    ...(phaseMetrics.length ? { phase_metrics: phaseMetrics } : {}),
  };
}
