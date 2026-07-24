import { describe, expect, it } from 'vitest';

import {
  buildMotionReferenceSegment,
  buildMotionReferenceSegmentPolicy,
} from './motionReferenceSegmentLedger';

describe('motionReferenceSegmentLedger', () => {
  it('keeps fixed interval segment ids only for diagnostic fallback', () => {
    expect(
      buildMotionReferenceSegment({
        liveSessionId: 'lms_live',
        sessionStartMs: 5000,
        windowStartMs: 25150,
        windowEndMs: 27150,
      }),
    ).toMatchObject({
      segment_id: 'lms_live:segment:003',
      segment_index: 2,
      segment_ms: 10000,
      segment_start_ms: 20000,
      segment_end_ms: 30000,
      segment_duration_ms: 10000,
      window_start_ms: 20150,
      window_end_ms: 22150,
      boundary_reason: 'fixed_interval',
      segmentation_mode: 'fixed_interval',
      scoreable: true,
      guidance_mode: 'score',
      match_role: 'instruction',
      source: 'motion_reference_segment_ledger.v2',
    });
  });

  it('omits validation duration unless the caller requests one', () => {
    expect(buildMotionReferenceSegmentPolicy()).toEqual({
      schema_version: 'motion_reference_segment_ledger.v2',
      segmentation_mode: 'adaptive_semantic',
      checkpoint_ms: 10000,
      min_segment_ms: 8000,
      max_segment_ms: 90000,
      change_threshold: 0.22,
      gap_tolerance_ms: 5000,
    });
  });

  it('declares expected validation checkpoint count only when requested', () => {
    expect(buildMotionReferenceSegmentPolicy({ validationDurationMs: 1800000 })).toEqual({
      schema_version: 'motion_reference_segment_ledger.v2',
      segmentation_mode: 'adaptive_semantic',
      checkpoint_ms: 10000,
      min_segment_ms: 8000,
      max_segment_ms: 90000,
      change_threshold: 0.22,
      gap_tolerance_ms: 5000,
      validation_duration_ms: 1800000,
      expected_validation_checkpoint_count: 180,
      expected_validation_segment_count: 180,
    });
  });
});
