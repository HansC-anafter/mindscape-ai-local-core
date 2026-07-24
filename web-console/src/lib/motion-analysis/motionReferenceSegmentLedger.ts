'use client';

export const DEFAULT_REFERENCE_CHECKPOINT_MS = 10_000;
export const DEFAULT_ADAPTIVE_MIN_SEGMENT_MS = 8_000;
export const DEFAULT_ADAPTIVE_MAX_SEGMENT_MS = 90_000;
export const DEFAULT_ADAPTIVE_CHANGE_THRESHOLD = 0.22;
export const DEFAULT_ADAPTIVE_GAP_TOLERANCE_MS = 5_000;

export type MotionReferenceSegment = {
  segment_id: string;
  segment_index: number;
  segment_ms: number;
  segment_start_ms: number;
  segment_end_ms: number;
  segment_duration_ms: number;
  window_start_ms: number;
  window_end_ms: number;
  boundary_reason: 'fixed_interval';
  segmentation_mode: 'fixed_interval';
  scoreable: true;
  guidance_mode: 'score';
  match_role: 'instruction';
  source: 'motion_reference_segment_ledger.v2';
};

export type MotionReferenceSegmentPolicy = {
  schema_version: 'motion_reference_segment_ledger.v2';
  segmentation_mode: 'adaptive_semantic';
  checkpoint_ms: number;
  min_segment_ms: number;
  max_segment_ms: number;
  change_threshold: number;
  gap_tolerance_ms: number;
  validation_duration_ms?: number;
  expected_validation_checkpoint_count?: number;
  expected_validation_segment_count?: number;
};

export type BuildMotionReferenceSegmentInput = {
  liveSessionId: string;
  sessionStartMs: number;
  windowStartMs: number;
  windowEndMs: number;
  checkpointMs?: number;
  validationDurationMs?: number;
};

function finiteNumber(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback;
}

function roundMs(value: number): number {
  return Math.round(value * 1000) / 1000;
}

export function buildMotionReferenceSegmentPolicy({
  checkpointMs = DEFAULT_REFERENCE_CHECKPOINT_MS,
  validationDurationMs,
}: {
  checkpointMs?: number;
  validationDurationMs?: number;
} = {}): MotionReferenceSegmentPolicy {
  const boundedCheckpointMs = Math.max(
    1,
    finiteNumber(checkpointMs, DEFAULT_REFERENCE_CHECKPOINT_MS),
  );
  const policy: MotionReferenceSegmentPolicy = {
    schema_version: 'motion_reference_segment_ledger.v2',
    segmentation_mode: 'adaptive_semantic',
    checkpoint_ms: boundedCheckpointMs,
    min_segment_ms: DEFAULT_ADAPTIVE_MIN_SEGMENT_MS,
    max_segment_ms: DEFAULT_ADAPTIVE_MAX_SEGMENT_MS,
    change_threshold: DEFAULT_ADAPTIVE_CHANGE_THRESHOLD,
    gap_tolerance_ms: DEFAULT_ADAPTIVE_GAP_TOLERANCE_MS,
  };
  if (typeof validationDurationMs === 'number' && Number.isFinite(validationDurationMs) && validationDurationMs > 0) {
    const boundedValidationMs = Math.max(boundedCheckpointMs, validationDurationMs);
    policy.validation_duration_ms = boundedValidationMs;
    policy.expected_validation_checkpoint_count = Math.ceil(
      boundedValidationMs / boundedCheckpointMs,
    );
    policy.expected_validation_segment_count = policy.expected_validation_checkpoint_count;
  }
  return policy;
}

export function buildMotionReferenceSegment({
  liveSessionId,
  sessionStartMs,
  windowStartMs,
  windowEndMs,
  checkpointMs = DEFAULT_REFERENCE_CHECKPOINT_MS,
}: BuildMotionReferenceSegmentInput): MotionReferenceSegment {
  const boundedSegmentMs = Math.max(
    1,
    finiteNumber(checkpointMs, DEFAULT_REFERENCE_CHECKPOINT_MS),
  );
  const relativeStartMs = Math.max(0, finiteNumber(windowStartMs, 0) - finiteNumber(sessionStartMs, 0));
  const relativeEndMs = Math.max(relativeStartMs, finiteNumber(windowEndMs, windowStartMs) - finiteNumber(sessionStartMs, 0));
  const segmentIndex = Math.max(0, Math.floor(relativeStartMs / boundedSegmentMs));
  const segmentStartMs = segmentIndex * boundedSegmentMs;
  const segmentEndMs = segmentStartMs + boundedSegmentMs;
  return {
    segment_id: `${liveSessionId}:segment:${String(segmentIndex + 1).padStart(3, '0')}`,
    segment_index: segmentIndex,
    segment_ms: boundedSegmentMs,
    segment_start_ms: roundMs(segmentStartMs),
    segment_end_ms: roundMs(segmentEndMs),
    segment_duration_ms: roundMs(segmentEndMs - segmentStartMs),
    window_start_ms: roundMs(relativeStartMs),
    window_end_ms: roundMs(relativeEndMs),
    boundary_reason: 'fixed_interval',
    segmentation_mode: 'fixed_interval',
    scoreable: true,
    guidance_mode: 'score',
    match_role: 'instruction',
    source: 'motion_reference_segment_ledger.v2',
  };
}
