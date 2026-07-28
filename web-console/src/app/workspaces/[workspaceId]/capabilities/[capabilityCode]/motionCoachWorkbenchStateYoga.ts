import type { MotionCoachWorkbenchStateInput } from './motionCoachWorkbenchStateTypes';
import {
  buildConnectedCaptureSource,
  buildFeedbackState,
  buildHtmlReportState,
  buildLiveMotionSession,
  buildYogaMotionDigests,
} from './motionCoachWorkbenchStateDigests';
import {
  buildYogaReferenceLessonImportRef,
  extractCourseSegments,
  formatTimeRangeLabel,
  readNumber,
  readString,
  resolveInstructionRefs,
  resolveLessonId,
  resolveLessonSourceLabel,
  resolveLessonSourceProvider,
  resolveLessonThumbnailUrl,
  resolveLessonTitle,
} from './motionCoachWorkbenchStateUtils';

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
  const lessonThumbnailUrl = resolveLessonThumbnailUrl({
    instructionRefs,
    segments,
    pendingLessonHandoff: input.pendingLessonHandoff,
  });
  const hasSelectedLesson = lessonId !== 'lesson_pending';
  const chapters = segments.length
    ? segments.map((segment, index) => ({
        id: segment.id,
        title: segment.title,
        timeRangeLabel: formatTimeRangeLabel(segment.startMs, segment.endMs),
        thumbnailUrl: segment.thumbnailUrl || lessonThumbnailUrl || undefined,
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
        thumbnailUrl: lessonThumbnailUrl || undefined,
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
      resolutionError: input.pendingLessonHandoff?.referenceProfileResolutionError,
    }),
    reference_lesson_state: {
      lesson_id: lessonId,
      title: lessonTitle,
      teacherName: 'Reference Instructor',
      sourceLabel,
      thumbnailUrl: lessonThumbnailUrl || undefined,
      activeChapterId,
      chapters,
    },
    meeting_feedback_ref: buildFeedbackState(input, digests),
    html_report_artifact_ref: buildHtmlReportState(input),
  };
}
