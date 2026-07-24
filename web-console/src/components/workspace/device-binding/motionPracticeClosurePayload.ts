import {
  buildMotionPracticeResourcePolicy,
  buildMotionSourceRef,
  type MotionPracticeLaunchInput,
  type MotionPracticeLaunchResult,
} from './motionPracticeLauncher';
import type {
  MotionPracticeSessionRollupResponse,
  MotionPracticeSessionRollupSummary,
} from './motionPracticeClosureTypes';
import {
  compactReferenceSegmentForCommand,
  compactReferenceSegmentLedgerForCommand,
} from './motionPracticeReferenceSegmentPayload';

const MAX_COMMAND_MOTION_DIGESTS = 5000;
const MAX_COMMAND_DIGEST_FINDINGS = 2;
const MAX_COMMAND_DIGEST_METRICS = 1;
const MAX_COMMAND_TEXT_CHARS = 64;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function readString(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value.trim() : '';
}

function readNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function readBoolean(value: unknown): boolean {
  return value === true;
}

function readNumberRecord(value: unknown): Record<string, number> {
  if (!isRecord(value)) {
    return {};
  }
  return Object.entries(value).reduce<Record<string, number>>((next, [key, nested]) => {
    if (typeof nested === 'number' && Number.isFinite(nested)) {
      next[key] = nested;
    }
    return next;
  }, {});
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    .map((item) => item.trim());
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

function compactMetricRecordForCommand(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) {
    return {};
  }
  const compact: Record<string, unknown> = {};
  for (const key of [
    'node_id',
    'axis',
    'phase',
    'metric_id',
    'label',
    'finding',
    'guidance',
    'cue',
    'message',
  ]) {
    const text = truncateText(value[key]);
    if (text) {
      compact[key] = text;
    }
  }
  for (const key of ['delta_score', 'delta', 'confidence', 'score']) {
    const nested = value[key];
    if (typeof nested === 'number' && Number.isFinite(nested)) {
      compact[key] = Math.round(nested * 1000) / 1000;
    }
  }
  return compact;
}

function compactMetricListForCommand(value: unknown): Record<string, unknown>[] {
  return readRecordArray(value)
    .slice(0, MAX_COMMAND_DIGEST_METRICS)
    .map(compactMetricRecordForCommand)
    .filter((item) => Object.keys(item).length > 0);
}

function compactMotionWindowDigestForCommand(digest: Record<string, unknown>): Record<string, unknown> {
  const compact: Record<string, unknown> = {};
  for (const key of [
    'motion_window_ref',
    'source_session_id',
    'pose_provider',
    'provider_code',
    'provider_schema_id',
    'keypoint_schema_id',
    'motion_metric_schema_version',
  ]) {
    const text = readString(digest[key]);
    if (text) {
      compact[key] = text;
    }
  }
  for (const key of ['window_index', 'start_ms', 'end_ms', 'confidence']) {
    const value = digest[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      compact[key] = Math.round(value * 1000) / 1000;
    }
  }
  const findings = readStringArray(digest.top_findings)
    .slice(0, MAX_COMMAND_DIGEST_FINDINGS)
    .map((finding) => truncateText(finding));
  if (findings.length) {
    compact.top_findings = findings;
  }
  for (const key of ['dwpose_node_deltas', 'sway_metrics', 'phase_metrics']) {
    const metrics = compactMetricListForCommand(digest[key]);
    if (metrics.length) {
      compact[key] = metrics;
    }
  }
  const referenceSegment = compactReferenceSegmentForCommand(digest.reference_segment);
  if (Object.keys(referenceSegment).length > 0) {
    compact.reference_segment = referenceSegment;
  }
  return compact;
}

function compactMotionWindowDigestsForCommand(
  digests: Record<string, unknown>[],
): Record<string, unknown>[] {
  return digests
    .slice(0, MAX_COMMAND_MOTION_DIGESTS)
    .map(compactMotionWindowDigestForCommand)
    .filter((digest) => Object.keys(digest).length > 0);
}

export function readInstructionCourseChapters(
  instructionRefs: MotionPracticeLaunchInput['instructionRefs'],
): Record<string, unknown>[] {
  const chapters: Record<string, unknown>[] = [];
  for (const ref of instructionRefs || []) {
    const nested = isRecord(ref) ? ref.course_chapters : null;
    chapters.push(...readRecordArray(nested));
  }
  return chapters;
}

export function readInstructionSegmentGraphs(
  instructionRefs: MotionPracticeLaunchInput['instructionRefs'],
): Record<string, unknown>[] {
  const segmentGraphs: Record<string, unknown>[] = [];
  for (const ref of instructionRefs || []) {
    if (isRecord(ref) && isRecord(ref.segment_graph)) {
      segmentGraphs.push(ref.segment_graph);
    }
  }
  return segmentGraphs;
}

function compactInstructionRefsForCommand(
  instructionRefs: MotionPracticeLaunchInput['instructionRefs'],
): Record<string, unknown>[] {
  return (instructionRefs || []).slice(0, 3).map((ref) => ({
    ref_type: readString(ref.ref_type) || null,
    source_provider: readString(ref.source_provider) || null,
    video_ref: truncateText(ref.video_ref, 96) || null,
    motion_analysis_source: ref.motion_analysis_source === true,
  }));
}

function readRollupSummary(rollup: MotionPracticeSessionRollupResponse): MotionPracticeSessionRollupSummary {
  return isRecord(rollup.summary)
    ? rollup.summary as MotionPracticeSessionRollupSummary
    : {};
}

function buildPhysicalDeviceEvidence({
  input,
  motionWindowDigests,
  summaryWindowCount,
}: {
  input: MotionPracticeLaunchInput;
  motionWindowDigests: Record<string, unknown>[];
  summaryWindowCount: number;
}): Record<string, unknown> {
  const sourceSessionId = input.sourceSession.session_id;
  const sourceMetadata = isRecord(input.sourceSession.metadata)
    ? input.sourceSession.metadata
    : {};
  const matchingDigests = motionWindowDigests.filter(
    (digest) => readString(digest.source_session_id) === sourceSessionId,
  );
  const receiverMetricFamilies = [
    'dwpose_node_deltas',
    'sway_metrics',
    'phase_metrics',
  ].filter((family) => matchingDigests.some((digest) => readRecordArray(digest[family]).length > 0));
  const sourceTypes = input.sourceSession.source_types;
  const deviceKind = sourceTypes.includes('phone_camera')
    ? 'phone'
    : sourceTypes.includes('external_provider_camera')
      ? 'external_provider_camera'
      : sourceTypes.includes('virtual_camera')
        ? 'virtual_camera'
        : sourceTypes.includes('usb_camera')
          ? 'usb_camera'
          : sourceTypes.includes('desktop_camera')
            ? 'desktop_camera'
            : 'unknown';
  return {
    source_session_id: sourceSessionId,
    source_types: sourceTypes,
    session_state: input.sourceSession.state,
    paired: ['paired', 'active'].includes(input.sourceSession.state),
    device_kind: deviceKind,
    transport: 'webrtc',
    capture_surface: readString(sourceMetadata.capture_surface) || 'unknown',
    secure_context: readBoolean(sourceMetadata.secure_context),
    source_origin_scheme: readString(sourceMetadata.source_origin_scheme) || 'unknown',
    remote_stream_received: summaryWindowCount > 0 || matchingDigests.length > 0,
    receiver_motion_window_count: summaryWindowCount || matchingDigests.length,
    receiver_metric_families: receiverMetricFamilies,
  };
}

function inferSummaryConfidence(summary: MotionPracticeSessionRollupSummary): string {
  const windowCount = readNumber(summary.window_count);
  const confidenceStats = readNumberRecord(summary.confidence_stats);
  const meanConfidence = readNumber(confidenceStats.mean_confidence);
  if (windowCount >= 3 && meanConfidence >= 0.5) {
    return 'complete';
  }
  if (windowCount > 0) {
    return 'partial';
  }
  return 'insufficient';
}

export function buildLivePracticeRollupFromSessionRollup({
  input,
  result,
  rollup,
}: {
  input: MotionPracticeLaunchInput;
  result: MotionPracticeLaunchResult;
  rollup: MotionPracticeSessionRollupResponse;
}): Record<string, unknown> {
  const summary = readRollupSummary(rollup);
  const sourceRef = buildMotionSourceRef(input.sourceSession);
  const motionRollupRef = readString(rollup.motion_rollup_ref);
  const artifactId = readString(rollup.artifact_id);
  const topFindings = readStringArray(summary.top_findings);
  const courseChapters = readInstructionCourseChapters(input.instructionRefs);
  const referenceSegmentGraphs = readInstructionSegmentGraphs(input.instructionRefs);
  const allMotionWindowDigests = readRecordArray(summary.motion_window_digests);
  const commandMotionWindowDigests = compactMotionWindowDigestsForCommand(allMotionWindowDigests);
  const motionWindowRefs = readStringArray(summary.motion_window_refs);
  const windowCount = readNumber(summary.window_count);
  const referenceSegmentLedger = compactReferenceSegmentLedgerForCommand({
    summary,
    motionRollupRef,
    artifactId,
  });
  const physicalDeviceEvidence = buildPhysicalDeviceEvidence({
    input,
    motionWindowDigests: commandMotionWindowDigests,
    summaryWindowCount: windowCount,
  });
  return {
    practice_session_id: result.practiceSessionId,
    workspace_id: input.workspaceId,
    teacher_library_ref: input.expertLibraryRef?.trim() || null,
    asana_refs: [],
    duration_ms: readNumber(summary.duration_ms),
    window_count: windowCount,
    motion_summary_refs: [
      {
        ref_type: 'motion_session_rollup',
        motion_rollup_ref: motionRollupRef || null,
        artifact_id: artifactId || null,
        live_session_id: result.liveSessionId,
        capture_session_id: input.sourceSession.session_id,
        device_profile_ref: sourceRef,
        meeting_session_id: result.meetingId,
        source_types: input.sourceSession.source_types,
      },
    ],
    score_aggregates: readNumberRecord(summary.score_summary),
    safety_event_counts: readNumberRecord(summary.finding_counts),
    top_findings: topFindings.length
      ? topFindings
      : ['No compact motion findings were available for this closed session.'],
    summary_confidence: inferSummaryConfidence(summary),
    metadata: {
      source_surface: 'workspace_motion_source_practice_closure',
      coach_pack: input.coachPack,
      practice_mode: input.practiceMode,
      instruction_ref_count: (input.instructionRefs || []).length,
      instruction_refs: compactInstructionRefsForCommand(input.instructionRefs),
      course_chapters: courseChapters,
      reference_segment_graphs: referenceSegmentGraphs,
      motion_window_refs: motionWindowRefs,
      motion_window_digests: commandMotionWindowDigests,
      ...(referenceSegmentLedger
        ? { reference_segment_ledger: referenceSegmentLedger }
        : {}),
      motion_window_digest_policy: {
        command_cap: MAX_COMMAND_MOTION_DIGESTS,
        original_digest_count: allMotionWindowDigests.length,
        truncated: allMotionWindowDigests.length > commandMotionWindowDigests.length,
        full_rollup_ref: motionRollupRef || null,
        full_rollup_artifact_id: artifactId || null,
      },
      motion_rollup_ref: motionRollupRef || null,
      artifact_id: artifactId || null,
      artifact_registry_available: isRecord(rollup.artifact_registry),
      rollup_emitted: Boolean(rollup.emitted),
      physical_device_evidence: physicalDeviceEvidence,
    },
  };
}

function buildDancePracticeSessionFromClosure({
  input,
  result,
}: {
  input: MotionPracticeLaunchInput;
  result: MotionPracticeLaunchResult;
}): Record<string, unknown> {
  return {
    workspace_id: input.workspaceId,
    capture_session_id: input.sourceSession.session_id,
    live_motion_session_id: result.liveSessionId,
    expert_library_ref: input.expertLibraryRef?.trim()
      || 'mindscape://dance_motion_coach/expert-library/default',
    choreography_segment_ref: null,
    rhythm_rubric_ref: null,
    style_rubric_ref: null,
    metadata: {
      source_surface: 'workspace_motion_source_practice_closure',
      source_types: input.sourceSession.source_types,
      instruction_refs: input.instructionRefs || [],
      course_chapters: readInstructionCourseChapters(input.instructionRefs),
      reference_segment_graphs: readInstructionSegmentGraphs(input.instructionRefs),
      resource_policy: buildMotionPracticeResourcePolicy(),
    },
  };
}

export function buildMotionPracticeClosureCommandParameters({
  input,
  result,
  rollup,
}: {
  input: MotionPracticeLaunchInput;
  result: MotionPracticeLaunchResult;
  rollup: MotionPracticeSessionRollupResponse;
}): Record<string, unknown> {
  const sourceRef = buildMotionSourceRef(input.sourceSession);
  const summary = readRollupSummary(rollup);
  const motionRollupRef = readString(rollup.motion_rollup_ref);
  const artifactId = readString(rollup.artifact_id);
  const livePracticeRollup = buildLivePracticeRollupFromSessionRollup({ input, result, rollup });
  const base = {
    workspace_id: input.workspaceId,
    meeting_session_id: result.meetingId,
    capture_session_id: input.sourceSession.session_id,
    device_profile_ref: sourceRef,
    source_types: input.sourceSession.source_types,
    expert_library_ref: input.expertLibraryRef?.trim() || null,
    user_id: 'default-user',
    user_goal: input.userGoal?.trim() || '',
    coach_pack: input.coachPack,
    practice_mode: input.practiceMode,
    motion_runtime_live_session: {
      live_session_id: result.liveSessionId,
      motion_rollup_ref: motionRollupRef || null,
      artifact_id: artifactId || null,
    },
    live_practice_rollup: livePracticeRollup,
    resource_policy: buildMotionPracticeResourcePolicy(),
  };

  if (input.coachPack === 'dance_motion_coach') {
    return {
      ...base,
      practice_session: buildDancePracticeSessionFromClosure({ input, result }),
      motion_summary: {
        motion_summary_ref: motionRollupRef || sourceRef,
        motion_rollup_ref: motionRollupRef || null,
        rollup_artifact_id: artifactId || null,
        live_session_id: result.liveSessionId,
        meeting_session_id: result.meetingId,
        scores: readNumberRecord(summary.score_summary),
        findings: readStringArray(summary.top_findings),
        instruction_refs: input.instructionRefs || [],
        course_chapters: readInstructionCourseChapters(input.instructionRefs),
        reference_segment_graphs: readInstructionSegmentGraphs(input.instructionRefs),
      },
      rubric_hint: input.userGoal?.trim() || '',
    };
  }
  return base;
}
