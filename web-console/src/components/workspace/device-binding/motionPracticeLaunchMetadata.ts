import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import type { MotionPracticeLaunchInput } from './motionPracticeLauncher';

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function readRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

export function readInstructionCourseChapters(
  instructionRefs: MotionPracticeLaunchInput['instructionRefs'],
): Record<string, unknown>[] {
  const chapters: Record<string, unknown>[] = [];
  for (const ref of instructionRefs || []) {
    if (!isRecord(ref)) {
      continue;
    }
    chapters.push(...readRecordArray(ref.course_chapters));
  }
  return chapters;
}

export function readInstructionSegmentGraphs(
  instructionRefs: MotionPracticeLaunchInput['instructionRefs'],
): Record<string, unknown>[] {
  const graphs: Record<string, unknown>[] = [];
  for (const ref of instructionRefs || []) {
    if (isRecord(ref) && isRecord(ref.segment_graph)) {
      graphs.push(ref.segment_graph);
    }
  }
  return graphs;
}

export function buildMotionSourceRef(session: DeviceSessionEntry): string {
  return `mindscape://device_binding/session/${encodeURIComponent(session.session_id)}`;
}

export function buildMotionPracticeResourcePolicy(): Record<string, boolean | string> {
  return {
    raw_media_db_writes: false,
    raw_frame_meeting_ledger_writes: false,
    ux_polling: false,
    worker_required_for_launch: false,
    transport: 'whip_rtsps_supervised_receiver',
  };
}

export function buildMotionPracticeReferenceMetadata(
  input: MotionPracticeLaunchInput,
): Record<string, unknown> {
  return {
    instruction_refs: input.instructionRefs || [],
    course_chapters: readInstructionCourseChapters(input.instructionRefs),
    reference_segment_graphs: readInstructionSegmentGraphs(input.instructionRefs),
  };
}

export function buildMotionPracticeCommandMetadata(
  input: MotionPracticeLaunchInput,
): Record<string, unknown> {
  return {
    dispatch_mode: 'route_playbook',
    explicit_override: true,
    motion_practice_launch: true,
    motion_practice_command: true,
    coach_pack: input.coachPack,
    practice_mode: input.practiceMode,
    resource_policy: buildMotionPracticeResourcePolicy(),
  };
}
