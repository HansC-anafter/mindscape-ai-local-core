import type { MotionPracticeSessionRollupSummary } from './motionPracticeClosureTypes';

const MAX_COMMAND_REFERENCE_SEGMENTS = 240;
const MAX_COMMAND_SEGMENT_FINDINGS = 1;
const MAX_COMMAND_TEXT_CHARS = 96;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readString(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value.trim() : '';
}

function readNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function readBoolean(value: unknown): boolean {
  return value === true;
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    .map((item) => item.trim());
}

function readNumberArray(value: unknown): number[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is number => typeof item === 'number' && Number.isFinite(item));
}

function readRecordArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is Record<string, unknown> => isRecord(item));
}

function truncateText(value: unknown, maxChars = MAX_COMMAND_TEXT_CHARS): string {
  const text = readString(value);
  return text.length > maxChars ? `${text.slice(0, Math.max(0, maxChars - 3))}...` : text;
}

export function compactReferenceSegmentForCommand(segment: unknown): Record<string, unknown> {
  if (!isRecord(segment)) {
    return {};
  }
  const compact: Record<string, unknown> = {};
  for (const key of [
    'segment_id',
    'guidance_mode',
    'match_role',
    'boundary_reason',
    'segmentation_mode',
    'segment_kind',
  ]) {
    const text = readString(segment[key]);
    if (text) {
      compact[key] = text;
    }
  }
  for (const key of [
    'segment_index',
    'segment_ms',
    'segment_start_ms',
    'segment_end_ms',
    'segment_duration_ms',
    'window_start_ms',
    'window_end_ms',
    'window_count',
    'mean_confidence',
    'boundary_change_score',
  ]) {
    const value = segment[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      compact[key] = Math.round(value * 1000) / 1000;
    }
  }
  if (segment.scoreable === true) {
    compact.scoreable = true;
  }
  const findings = readStringArray(segment.top_findings)
    .slice(0, MAX_COMMAND_SEGMENT_FINDINGS)
    .map((finding) => truncateText(finding));
  if (findings.length) {
    compact.top_findings = findings;
  }
  return compact;
}

export function compactReferenceSegmentLedgerForCommand({
  summary,
  motionRollupRef,
  artifactId,
}: {
  summary: MotionPracticeSessionRollupSummary;
  motionRollupRef: string;
  artifactId: string;
}): Record<string, unknown> | null {
  const metadata = isRecord(summary.metadata) ? summary.metadata : {};
  const ledger = isRecord(metadata.reference_segment_ledger)
    ? metadata.reference_segment_ledger
    : {};
  const segments = readRecordArray(metadata.reference_segments);
  if (!Object.keys(ledger).length && !segments.length) {
    return null;
  }
  const compactSegments = segments
    .slice(0, MAX_COMMAND_REFERENCE_SEGMENTS)
    .map(compactReferenceSegmentForCommand)
    .filter((segment) => Object.keys(segment).length > 0);
  const compact: Record<string, unknown> = {
    schema_version: readString(ledger.schema_version) || 'motion_reference_segment_ledger.v2',
    segmentation_mode: readString(ledger.segmentation_mode) || 'adaptive_semantic',
    checkpoint_ms: readNumber(ledger.checkpoint_ms || ledger.segment_ms),
    observed_segment_count: readNumber(ledger.observed_segment_count),
    observed_checkpoint_count: readNumber(ledger.observed_checkpoint_count),
    observed_window_count: readNumber(ledger.observed_window_count),
    observed_duration_ms: readNumber(ledger.observed_duration_ms),
    missing_segment_indexes: readNumberArray(ledger.missing_segment_indexes),
    missing_checkpoint_indexes: readNumberArray(ledger.missing_checkpoint_indexes),
    validation_requested: readBoolean(ledger.validation_requested),
    segments: compactSegments,
    segment_policy: {
      command_cap: MAX_COMMAND_REFERENCE_SEGMENTS,
      original_segment_count: segments.length,
      truncated: segments.length > compactSegments.length,
      full_rollup_ref: motionRollupRef || null,
      full_rollup_artifact_id: artifactId || null,
    },
  };
  for (const key of [
    'validation_duration_ms',
    'expected_validation_checkpoint_count',
    'expected_validation_segment_count',
    'coverage_ratio',
  ]) {
    const value = ledger[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      compact[key] = Math.round(value * 1000) / 1000;
    }
  }
  for (const key of ['validation_ready', 'validation_passed']) {
    if (typeof ledger[key] === 'boolean') {
      compact[key] = ledger[key];
    }
  }
  const missingValidationIndexes = readNumberArray(ledger.missing_validation_segment_indexes);
  if (missingValidationIndexes.length) {
    compact.missing_validation_segment_indexes = missingValidationIndexes;
  }
  const missingValidationCheckpointIndexes = readNumberArray(
    ledger.missing_validation_checkpoint_indexes,
  );
  if (missingValidationCheckpointIndexes.length) {
    compact.missing_validation_checkpoint_indexes = missingValidationCheckpointIndexes;
  }
  return compact;
}
