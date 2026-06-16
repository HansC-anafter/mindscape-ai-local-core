'use client';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import type { CaptureSourceReferenceLessonState } from '@/components/workspace/device-binding/capture-bridge/CaptureSourceBridgeProvider';
import type { MotionPracticeLaunchInput, MotionPracticeLaunchResult } from '@/components/workspace/device-binding/motionPracticeLauncher';
import type { MotionPracticeClosureResult } from '@/components/workspace/device-binding/motionPracticeClosure';
import type { MotionWindowAppendEvent } from '@/components/workspace/device-binding/motionWindowAppendEvent';
import {
  buildInstructionRefsFromLessonHandoff,
  type MotionPracticeLessonHandoff,
} from '@/components/workspace/device-binding/practice/motionPracticeLessonHandoff';

export type MotionCoachCapabilityCode = 'yogacoach' | 'dance_motion_coach';

export interface MotionCoachWorkbenchStateInput {
  capabilityCode: MotionCoachCapabilityCode;
  selectedSession: DeviceSessionEntry | null;
  referenceLessonState: CaptureSourceReferenceLessonState | null;
  pendingLessonHandoff?: MotionPracticeLessonHandoff | null;
  launchInput: MotionPracticeLaunchInput | null;
  practiceResult: MotionPracticeLaunchResult | null;
  motionWindowEvents: MotionWindowAppendEvent[];
  closureResult: MotionPracticeClosureResult | null;
}

type TimelineSegment = {
  id: string;
  title: string;
  startMs: number;
  endMs: number;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readString(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value.trim() : '';
}

function readNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function readOptionalNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
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

function clamp01(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(1, value));
}

function capitalize(value: string): string {
  const normalized = value.trim();
  if (!normalized) {
    return '';
  }
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function titleFromToken(value: string, fallback: string): string {
  const normalized = value.trim();
  if (!normalized) {
    return fallback;
  }
  return normalized
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => capitalize(part))
    .join(' ');
}

function formatTimeLabel(totalMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(totalMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function formatTimeRangeLabel(startMs: number, endMs: number): string {
  return `${formatTimeLabel(startMs)}-${formatTimeLabel(endMs)}`;
}

function dedupeStrings(values: string[], maxItems = 4): string[] {
  const seen = new Set<string>();
  const next: string[] = [];
  for (const value of values) {
    const normalized = value.trim();
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    next.push(normalized);
    if (next.length >= maxItems) {
      break;
    }
  }
  return next;
}

function mapCaptureSourceType(session: DeviceSessionEntry | null): 'phone' | 'pad' | 'desktop_camera' | 'obs' | 'file' | 'unknown' {
  if (!session) {
    return 'unknown';
  }
  if (session.source_types.includes('virtual_camera')) {
    return 'obs';
  }
  if (session.source_types.includes('phone_camera')) {
    const label = `${session.display_name || ''} ${session.device_id || ''}`.toLowerCase();
    return label.includes('ipad') || label.includes('tablet') ? 'pad' : 'phone';
  }
  if (session.source_types.includes('desktop_camera') || session.source_types.includes('usb_camera')) {
    return 'desktop_camera';
  }
  return 'unknown';
}

function mapCaptureTransport(session: DeviceSessionEntry | null): 'webrtc' | 'lan_qr' | 'local_file' | 'unknown' {
  if (!session) {
    return 'unknown';
  }
  if (session.source_types.includes('phone_camera')) {
    return 'webrtc';
  }
  if (
    session.source_types.includes('desktop_camera') ||
    session.source_types.includes('usb_camera') ||
    session.source_types.includes('virtual_camera')
  ) {
    return 'webrtc';
  }
  return 'unknown';
}

function mapCaptureStatus(session: DeviceSessionEntry | null): 'ready' | 'pairing' | 'offline' {
  if (!session) {
    return 'pairing';
  }
  if (session.state === 'active' || session.state === 'paired') {
    return 'ready';
  }
  if (session.state === 'pairing') {
    return 'pairing';
  }
  return 'offline';
}

function extractCourseSegments(instructionRefs: Record<string, unknown>[] | null | undefined): TimelineSegment[] {
  const segments: TimelineSegment[] = [];
  for (const ref of instructionRefs || []) {
    if (!isRecord(ref)) {
      continue;
    }
    for (const chapter of readRecordArray(ref.course_chapters)) {
      const id = readString(chapter.chapter_id) || readString(chapter.phrase_id);
      const title = readString(chapter.title);
      if (!id || !title) {
        continue;
      }
      segments.push({
        id,
        title,
        startMs: readNumber(chapter.start_ms),
        endMs: readNumber(chapter.end_ms),
      });
    }
  }
  return segments.sort((left, right) => left.startMs - right.startMs);
}

function resolveInstructionRefs(input: MotionCoachWorkbenchStateInput): Record<string, unknown>[] {
  if (input.launchInput?.instructionRefs?.length) {
    return input.launchInput.instructionRefs.filter(isRecord);
  }
  return buildInstructionRefsFromLessonHandoff(input.pendingLessonHandoff);
}

function resolveLessonId(
  launchInput: MotionPracticeLaunchInput | null,
  referenceLessonState: CaptureSourceReferenceLessonState | null,
  pendingLessonHandoff: MotionPracticeLessonHandoff | null | undefined,
): string {
  return launchInput?.expertLibraryRef?.trim()
    || pendingLessonHandoff?.sourceValue?.trim()
    || referenceLessonState?.lesson_id?.trim()
    || 'lesson_pending';
}

function resolveSegmentForWindow(
  startMs: number,
  endMs: number,
  segments: TimelineSegment[],
  fallbackId: string,
): TimelineSegment | null {
  const midpoint = startMs + Math.max(0, endMs - startMs) / 2;
  for (const segment of segments) {
    if (midpoint >= segment.startMs && midpoint <= segment.endMs) {
      return segment;
    }
  }
  return segments.find((segment) => segment.id === fallbackId) || null;
}

function resolveLessonTitle(
  capabilityCode: MotionCoachCapabilityCode,
  referenceLessonState: CaptureSourceReferenceLessonState | null,
  segments: TimelineSegment[],
  pendingLessonHandoff: MotionPracticeLessonHandoff | null | undefined,
): string {
  if (pendingLessonHandoff?.sourceTitle?.trim()) {
    return pendingLessonHandoff.sourceTitle.trim();
  }
  if (referenceLessonState?.title?.trim()) {
    return referenceLessonState.title.trim();
  }
  if (segments.length) {
    return capabilityCode === 'dance_motion_coach'
      ? 'Dance Practice Reference'
      : 'Yoga Practice Reference';
  }
  return capabilityCode === 'dance_motion_coach'
    ? 'Dance lesson pending'
    : 'Yoga lesson pending';
}

function resolveLessonSourceProvider(
  launchInput: MotionPracticeLaunchInput | null,
  pendingLessonHandoff: MotionPracticeLessonHandoff | null | undefined,
): string {
  const firstInstructionRef = launchInput?.instructionRefs?.find((item) => isRecord(item)) || null;
  const provider = readString(firstInstructionRef?.source_provider)
    || readString(firstInstructionRef?.provider)
    || pendingLessonHandoff?.sourceProvider?.trim()
    || '';
  if (provider) {
    return provider;
  }
  if (pendingLessonHandoff?.sourceKind === 'youtube_instruction_ref') {
    return 'youtube';
  }
  if (pendingLessonHandoff?.sourceKind === 'local_video_smoke_ref') {
    return 'local';
  }
  if (launchInput?.expertLibraryRef?.trim()) {
    return 'manual';
  }
  return 'missing';
}

function resolveLessonSourceLabel(
  launchInput: MotionPracticeLaunchInput | null,
  pendingLessonHandoff: MotionPracticeLessonHandoff | null | undefined,
): string {
  const teacherRef = launchInput?.expertLibraryRef?.trim();
  if (teacherRef) {
    return teacherRef;
  }
  const firstInstructionRef = launchInput?.instructionRefs?.find((item) => isRecord(item)) || null;
  if (firstInstructionRef) {
    return readString(firstInstructionRef.video_ref)
      || readString(firstInstructionRef.media_ref)
      || readString(firstInstructionRef.teacher_ref)
      || readString(firstInstructionRef.ref_type)
      || 'Instruction ref';
  }
  if (pendingLessonHandoff?.sourceProvider?.trim()) {
    return pendingLessonHandoff.sourceProvider.trim();
  }
  if (pendingLessonHandoff?.sourceTitle?.trim()) {
    return pendingLessonHandoff.sourceTitle.trim();
  }
  if (pendingLessonHandoff?.sourceValue?.trim()) {
    return pendingLessonHandoff.sourceValue.trim();
  }
  return 'Instruction source pending';
}

function buildYogaReferenceLessonImportRef(input: {
  lessonId: string;
  segments: TimelineSegment[];
  sourceProvider: string;
  hasSelectedLesson: boolean;
}): Record<string, unknown> {
  const importId = input.lessonId === 'lesson_pending'
    ? 'reference-lesson-import-missing'
    : `reference-lesson-import:${input.lessonId}`;
  if (input.segments.length > 0) {
    return {
      id: importId,
      status: 'ready',
      artifact_ref: input.lessonId,
      confidence: 0.84,
      human_patch_required: false,
      ready_chapter_count: input.segments.length,
      contract_version: 'yogacoach.reference_lesson_import.v1',
      artifact_schema_id: 'vcs_instruction_video_prepared_bundle.v1',
      source_provider: input.sourceProvider,
    };
  }
  if (input.hasSelectedLesson) {
    return {
      id: importId,
      status: 'materializing',
      artifact_ref: input.lessonId,
      confidence: 0.32,
      human_patch_required: true,
      ready_chapter_count: 0,
      blocked_reason: 'Reference lesson is selected, but bounded chapters are not attached yet.',
      contract_version: 'yogacoach.reference_lesson_import.v1',
      artifact_schema_id: 'vcs_instruction_video_prepared_bundle.v1',
      source_provider: input.sourceProvider,
    };
  }
  return {
    id: importId,
    status: 'missing',
    confidence: 0,
    human_patch_required: true,
    ready_chapter_count: 0,
    blocked_reason: 'Reference lesson import is not attached to this workbench state.',
    contract_version: 'yogacoach.reference_lesson_import.v1',
    artifact_schema_id: 'vcs_instruction_video_prepared_bundle.v1',
    source_provider: 'missing',
  };
}

function mapSeverity(value: unknown): 'green' | 'yellow' | 'red' | 'unknown' {
  const severity = readString(value);
  return severity === 'green' || severity === 'yellow' || severity === 'red'
    ? severity
    : 'unknown';
}

function buildMetricDelta(
  item: Record<string, unknown>,
  fallbackId: string,
  fallbackLabel: string,
): Record<string, unknown> {
  const label = readString(item.node_label)
    || titleFromToken(readString(item.axis), '')
    || titleFromToken(readString(item.phase), '')
    || fallbackLabel;
  return {
    id: readString(item.node_id) || readString(item.axis) || readString(item.phase) || fallbackId,
    label,
    value: readOptionalNumber(item.learner_value) ?? readNumber(item.delta_score),
    referenceValue: readOptionalNumber(item.reference_value),
    deltaScore: clamp01(readNumber(item.delta_score)),
    severity: mapSeverity(item.severity),
    confidence: clamp01(readNumber(item.confidence)),
    finding: readString(item.finding) || `${label} changed relative to the reference window.`,
    guidance: readString(item.guidance) || `Adjust ${label.toLowerCase()} before the next pass.`,
  };
}

function resolveYogaPhase(digest: Record<string, unknown>): 'entry' | 'hold' | 'exit' | 'transition' | 'unknown' {
  const phase = readString(digest.phase)
    || readString(readRecordArray(digest.phase_metrics)[0]?.phase);
  if (phase === 'hold' || phase === 'transition') {
    return phase;
  }
  if (phase === 'entry' || phase === 'exit') {
    return phase;
  }
  return 'unknown';
}

function resolveDancePhase(digest: Record<string, unknown>): 'setup' | 'groove' | 'accent' | 'transition' | 'unknown' {
  const phase = readString(digest.phase)
    || readString(readRecordArray(digest.phase_metrics)[0]?.phase);
  if (phase === 'setup' || phase === 'groove' || phase === 'accent' || phase === 'transition') {
    return phase;
  }
  return 'unknown';
}

function buildDigestRecords(
  input: MotionCoachWorkbenchStateInput,
): Record<string, unknown>[] {
  const closureDigests = readRecordArray(input.closureResult?.rollup.summary?.motion_window_digests);
  if (closureDigests.length) {
    return closureDigests;
  }
  return input.motionWindowEvents.map((event) => ({
    motion_window_ref: event.response.motion_window_ref || event.summary.window_id,
    start_ms: event.summary.ts_start_ms,
    end_ms: event.summary.ts_end_ms,
    confidence: readNumber(event.summary.confidence_stats.mean_confidence),
    top_findings: event.summary.findings,
    pose_provider: readString(event.summary.metadata.pose_provider),
    keypoint_schema_id: readString(event.summary.metadata.keypoint_schema_id),
    dwpose_node_deltas: readRecordArray(event.summary.metadata.dwpose_node_deltas),
    sway_metrics: readRecordArray(event.summary.metadata.sway_metrics),
    phase_metrics: readRecordArray(event.summary.metadata.phase_metrics),
  }));
}

function buildYogaMotionDigests(
  input: MotionCoachWorkbenchStateInput,
  segments: TimelineSegment[],
  activeChapterId: string,
): Record<string, unknown>[] {
  return buildDigestRecords(input).map((digest, index) => {
    const startMs = readNumber(digest.start_ms) || readNumber(digest.ts_start_ms);
    const endMs = readNumber(digest.end_ms) || readNumber(digest.ts_end_ms);
    const fallbackChapterId = readString(input.referenceLessonState?.chapter_ref) || activeChapterId || `chapter_${index + 1}`;
    const segment = resolveSegmentForWindow(startMs, endMs, segments, fallbackChapterId);
    return {
      motion_window_ref: readString(digest.motion_window_ref) || `motion_window_${index + 1}`,
      chapter_id: segment?.id || fallbackChapterId,
      phase: resolveYogaPhase(digest),
      timeRangeLabel: segment ? formatTimeRangeLabel(segment.startMs, segment.endMs) : formatTimeRangeLabel(startMs, endMs),
      confidence: clamp01(readNumber(digest.confidence)),
      dwpose_node_deltas: readRecordArray(digest.dwpose_node_deltas).map((item, metricIndex) => (
        buildMetricDelta(item, `node_${metricIndex + 1}`, 'Node delta')
      )),
      sway_metrics: readRecordArray(digest.sway_metrics).map((item, metricIndex) => (
        buildMetricDelta(item, `sway_${metricIndex + 1}`, 'Sway metric')
      )),
      phase_metrics: readRecordArray(digest.phase_metrics).map((item, metricIndex) => (
        buildMetricDelta(item, `phase_${metricIndex + 1}`, 'Phase metric')
      )),
    };
  });
}

function buildDanceMotionDigests(
  input: MotionCoachWorkbenchStateInput,
  segments: TimelineSegment[],
  activePhraseId: string,
): Record<string, unknown>[] {
  return buildDigestRecords(input).map((digest, index) => {
    const startMs = readNumber(digest.start_ms) || readNumber(digest.ts_start_ms);
    const endMs = readNumber(digest.end_ms) || readNumber(digest.ts_end_ms);
    const fallbackPhraseId = readString(input.referenceLessonState?.chapter_ref) || activePhraseId || `phrase_${index + 1}`;
    const segment = resolveSegmentForWindow(startMs, endMs, segments, fallbackPhraseId);
    return {
      motion_window_ref: readString(digest.motion_window_ref) || `motion_window_${index + 1}`,
      phrase_id: segment?.id || fallbackPhraseId,
      phase: resolveDancePhase(digest),
      timeRangeLabel: segment ? formatTimeRangeLabel(segment.startMs, segment.endMs) : formatTimeRangeLabel(startMs, endMs),
      confidence: clamp01(readNumber(digest.confidence)),
      dwpose_node_deltas: readRecordArray(digest.dwpose_node_deltas).map((item, metricIndex) => (
        buildMetricDelta(item, `node_${metricIndex + 1}`, 'Node delta')
      )),
      sway_metrics: readRecordArray(digest.sway_metrics).map((item, metricIndex) => (
        buildMetricDelta(item, `sway_${metricIndex + 1}`, 'Sway metric')
      )),
      phase_metrics: readRecordArray(digest.phase_metrics).map((item, metricIndex) => (
        buildMetricDelta(item, `phase_${metricIndex + 1}`, 'Phase metric')
      )),
    };
  });
}

function buildFeedbackState(
  input: MotionCoachWorkbenchStateInput,
  digests: Record<string, unknown>[],
): Record<string, unknown> {
  const closureSummary = isRecord(input.closureResult?.rollup.summary)
    ? input.closureResult?.rollup.summary
    : null;
  const status = input.closureResult
    ? 'ready'
    : digests.length > 0 || input.practiceResult?.liveGuidanceEnabled
      ? 'streaming'
      : 'pending';
  const digestGuidance = digests.flatMap((digest) => [
    ...readRecordArray(digest.dwpose_node_deltas).map((item) => readString(item.guidance)),
    ...readRecordArray(digest.sway_metrics).map((item) => readString(item.guidance)),
    ...readRecordArray(digest.phase_metrics).map((item) => readString(item.guidance)),
  ]);
  const closureFindings = readStringArray(closureSummary?.top_findings);
  const summary = input.closureResult
    ? `Captured ${readNumber(closureSummary?.window_count)} motion windows and emitted a session rollup.`
    : digests.length > 0
      ? `Live motion analysis is active with ${digests.length} compact windows appended.`
      : input.practiceResult
        ? 'Practice session created. Capture more motion windows before scoring.'
        : 'Launch practice to start motion analysis and meeting feedback.';
  const nextActions = input.closureResult
    ? [
        'Review the session-close meeting command output.',
        'Use the emitted motion rollup for the next practice summary step.',
      ]
    : input.practiceResult
      ? [
          'Keep the learner inside frame and continue appending compact motion windows.',
        ]
      : [
          'Connect a phone, OBS, or desktop camera and start live guidance.',
        ];
  return {
    id: input.closureResult?.command.commandId || input.practiceResult?.commandId || 'meeting_feedback_pending',
    status,
    summary,
    cues: dedupeStrings([...closureFindings, ...digestGuidance], 4),
    nextActions,
  };
}

function buildHtmlReportState(
  input: MotionCoachWorkbenchStateInput,
): Record<string, unknown> {
  const closurePlaybook = isRecord(input.closureResult?.command.dispatchResult?.playbook)
    ? input.closureResult?.command.dispatchResult?.playbook
    : null;
  const triggeredPlaybook = closurePlaybook && isRecord(closurePlaybook.triggered_playbook)
    ? closurePlaybook.triggered_playbook
    : null;
  const executionId = readString(triggeredPlaybook?.execution_id)
    || readString(input.practiceResult?.playbookExecutionId);
  if (executionId) {
    return {
      id: executionId,
      status: 'rendering',
      title: 'HTML practice report is pending runtime report emission.',
    };
  }
  return {
    id: 'html_report_not_emitted',
    status: 'missing',
    title: 'HTML practice report has not been emitted yet.',
  };
}

function buildConnectedCaptureSource(input: MotionCoachWorkbenchStateInput): Record<string, unknown> {
  const session = input.selectedSession;
  return {
    id: session?.session_id || 'capture_source_pending',
    label: session?.display_name || session?.device_id || 'Motion source pending',
    type: mapCaptureSourceType(session),
    status: mapCaptureStatus(session),
    transport: mapCaptureTransport(session),
    pairingCode: session?.pairing_code,
  };
}

function buildLiveMotionSession(input: MotionCoachWorkbenchStateInput): Record<string, unknown> {
  const sessionId = input.practiceResult?.liveSessionId || '';
  const latestDigest = buildDigestRecords(input)[0] || null;
  return {
    id: sessionId || 'live_motion_session_pending',
    status: input.closureResult
      ? 'closed'
      : sessionId
        ? 'live'
        : 'idle',
    provider: readString(latestDigest?.pose_provider) === 'mediapipe_pose' ? 'mediapipe' : 'mediapipe',
    keypointSchemaId: readString(latestDigest?.keypoint_schema_id) || 'mediapipe_pose_33',
  };
}

export function buildYogaPracticeWorkbenchState(
  input: MotionCoachWorkbenchStateInput,
): Record<string, unknown> {
  const instructionRefs = resolveInstructionRefs(input);
  const segments = extractCourseSegments(instructionRefs);
  const handoffActiveChapterId = input.pendingLessonHandoff ? segments[0]?.id : '';
  const activeChapterId = handoffActiveChapterId
    || readString(input.referenceLessonState?.chapter_ref)
    || segments[0]?.id
    || 'live_chapter';
  const digests = buildYogaMotionDigests(input, segments, activeChapterId);
  const lessonTitle = resolveLessonTitle(
    'yogacoach',
    input.referenceLessonState,
    segments,
    input.pendingLessonHandoff,
  );
  const lessonId = resolveLessonId(
    input.launchInput,
    input.referenceLessonState,
    input.pendingLessonHandoff,
  );
  const sourceProvider = resolveLessonSourceProvider(
    input.launchInput,
    input.pendingLessonHandoff,
  );
  const sourceLabel = resolveLessonSourceLabel(
    input.launchInput,
    input.pendingLessonHandoff,
  );
  const hasSelectedLesson = lessonId !== 'lesson_pending';
  const chapters = segments.length
    ? segments.map((segment, index) => ({
        id: segment.id,
        title: segment.title,
        timeRangeLabel: formatTimeRangeLabel(segment.startMs, segment.endMs),
        focus: segment.id === activeChapterId
          ? readString(input.referenceLessonState?.focus_cue) || 'Follow the active reference cue while staying centered in frame.'
          : 'Reference chapter queued for practice.',
        teacherCue: segment.id === activeChapterId
          ? readString(input.referenceLessonState?.focus_cue) || 'Keep the pose stable before advancing.'
          : 'Continue after the active chapter completes.',
        status: segment.id === activeChapterId ? 'active' : index === 0 ? 'queued' : 'queued',
      }))
    : [{
        id: activeChapterId,
        title: readString(input.referenceLessonState?.title) || 'Live reference chapter',
        timeRangeLabel: input.referenceLessonState?.timestamp_ms !== undefined
          ? formatTimeRangeLabel(
              Math.max(0, readNumber(input.referenceLessonState?.timestamp_ms) - 1000),
              readNumber(input.referenceLessonState?.timestamp_ms) + 1000,
            )
          : '--',
        focus: readString(input.referenceLessonState?.focus_cue) || 'Reference cue pending from the teacher lesson stream.',
        teacherCue: readString(input.referenceLessonState?.focus_cue) || 'Reference cue pending from the teacher lesson stream.',
        status: 'active',
      }];

  return {
    connected_capture_source_ref: buildConnectedCaptureSource(input),
    live_motion_session_ref: buildLiveMotionSession(input),
    motion_rollup_ref: {
      id: readString(input.closureResult?.rollup.motion_rollup_ref)
        || input.practiceResult?.liveSessionId
        || 'motion_rollup_pending',
      status: input.closureResult ? 'ready' : digests.length ? 'rolling' : 'empty',
      motion_window_count: readNumber(input.closureResult?.rollup.summary?.window_count) || digests.length,
      digests,
    },
    reference_lesson_import_ref: buildYogaReferenceLessonImportRef({
      lessonId,
      segments,
      sourceProvider,
      hasSelectedLesson,
    }),
    reference_lesson_state: {
      lesson_id: lessonId,
      title: lessonTitle,
      teacherName: 'Reference Instructor',
      sourceLabel,
      activeChapterId,
      chapters,
    },
    meeting_feedback_ref: buildFeedbackState(input, digests),
    html_report_artifact_ref: buildHtmlReportState(input),
  };
}

export function buildDancePracticeWorkbenchState(
  input: MotionCoachWorkbenchStateInput,
): Record<string, unknown> {
  const instructionRefs = resolveInstructionRefs(input);
  const segments = extractCourseSegments(instructionRefs);
  const handoffActivePhraseId = input.pendingLessonHandoff ? segments[0]?.id : '';
  const activePhraseId = handoffActivePhraseId
    || readString(input.referenceLessonState?.chapter_ref)
    || segments[0]?.id
    || 'live_phrase';
  const digests = buildDanceMotionDigests(input, segments, activePhraseId);
  const lessonTitle = resolveLessonTitle(
    'dance_motion_coach',
    input.referenceLessonState,
    segments,
    input.pendingLessonHandoff,
  );
  const lessonId = resolveLessonId(
    input.launchInput,
    input.referenceLessonState,
    input.pendingLessonHandoff,
  );
  const sourceLabel = resolveLessonSourceLabel(
    input.launchInput,
    input.pendingLessonHandoff,
  );
  const phrases = segments.length
    ? segments.map((segment, index) => ({
        id: segment.id,
        title: segment.title,
        timeRangeLabel: formatTimeRangeLabel(segment.startMs, segment.endMs),
        rhythmFocus: segment.id === activePhraseId
          ? readString(input.referenceLessonState?.focus_cue) || 'Hold the active phrase timing and center line.'
          : 'Phrase queued for the next pass.',
        styleCue: segment.id === activePhraseId
          ? readString(input.referenceLessonState?.focus_cue) || 'Match the phrase timing before adding more accent.'
          : 'Wait for the active phrase to complete.',
        status: segment.id === activePhraseId ? 'active' : index === 0 ? 'queued' : 'queued',
      }))
    : [{
        id: activePhraseId,
        title: readString(input.referenceLessonState?.title) || 'Live choreography phrase',
        timeRangeLabel: input.referenceLessonState?.timestamp_ms !== undefined
          ? formatTimeRangeLabel(
              Math.max(0, readNumber(input.referenceLessonState?.timestamp_ms) - 1000),
              readNumber(input.referenceLessonState?.timestamp_ms) + 1000,
            )
          : '--',
        rhythmFocus: readString(input.referenceLessonState?.focus_cue) || 'Reference choreography cue pending from the lesson stream.',
        styleCue: readString(input.referenceLessonState?.focus_cue) || 'Reference choreography cue pending from the lesson stream.',
        status: 'active',
      }];

  return {
    connected_capture_source_ref: buildConnectedCaptureSource(input),
    live_motion_session_ref: buildLiveMotionSession(input),
    motion_rollup_ref: {
      id: readString(input.closureResult?.rollup.motion_rollup_ref)
        || input.practiceResult?.liveSessionId
        || 'motion_rollup_pending',
      status: input.closureResult ? 'ready' : digests.length ? 'rolling' : 'empty',
      motion_window_count: readNumber(input.closureResult?.rollup.summary?.window_count) || digests.length,
      digests,
    },
    reference_lesson_state: {
      lesson_id: lessonId,
      title: lessonTitle,
      instructorName: 'Reference Choreographer',
      sourceLabel,
      activePhraseId,
      phrases,
    },
    meeting_feedback_ref: buildFeedbackState(input, digests),
    html_report_artifact_ref: buildHtmlReportState(input),
  };
}
