import type { MotionCoachWorkbenchStateInput } from './motionCoachWorkbenchStateTypes';
import {
  buildConnectedCaptureSource,
  buildDanceMotionDigests,
  buildFeedbackState,
  buildHtmlReportState,
  buildLiveMotionSession,
} from './motionCoachWorkbenchStateDigests';
import {
  extractCourseSegments,
  formatTimeRangeLabel,
  readNumber,
  readString,
  resolveInstructionRefs,
  resolveLessonId,
  resolveLessonSourceLabel,
  resolveLessonTitle,
} from './motionCoachWorkbenchStateUtils';

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
