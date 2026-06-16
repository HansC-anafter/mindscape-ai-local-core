import type { MotionCoachWorkbenchStateInput, TimelineSegment } from './motionCoachWorkbenchStateTypes';
import {
  clamp01,
  dedupeStrings,
  formatTimeRangeLabel,
  isRecord,
  mapCaptureSourceType,
  mapCaptureStatus,
  mapCaptureTransport,
  readNumber,
  readOptionalNumber,
  readRecordArray,
  readString,
  readStringArray,
  resolveSegmentForWindow,
  titleFromToken,
} from './motionCoachWorkbenchStateUtils';

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

export function buildYogaMotionDigests(
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

export function buildDanceMotionDigests(
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

export function buildFeedbackState(
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

export function buildHtmlReportState(
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

export function buildConnectedCaptureSource(input: MotionCoachWorkbenchStateInput): Record<string, unknown> {
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

export function buildLiveMotionSession(input: MotionCoachWorkbenchStateInput): Record<string, unknown> {
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
