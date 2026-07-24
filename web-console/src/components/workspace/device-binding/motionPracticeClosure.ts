'use client';

import {
  submitMeetingCommandEnvelope,
  type MeetingCommandLedgerAcceptance,
} from '@/components/capabilities/meeting-workbench/meetingCommandLedger';
import { postApiJson } from '@/components/capabilities/meeting-workbench/meetingApi';
import {
  buildMotionPracticeClosureCommandParameters,
  isRecord,
  readInstructionCourseChapters,
  readInstructionSegmentGraphs,
  readString,
} from './motionPracticeClosurePayload';
import type {
  MotionPracticeClosureResult,
  MotionPracticeSessionRollupResponse,
} from './motionPracticeClosureTypes';
import {
  buildMotionPracticeCommandMetadata,
  buildMotionPracticeResourcePolicy,
  type MotionPracticeLaunchInput,
  type MotionPracticeLaunchResult,
} from './motionPracticeLauncher';

export {
  buildLivePracticeRollupFromSessionRollup,
  buildMotionPracticeClosureCommandParameters,
} from './motionPracticeClosurePayload';
export type {
  MotionPracticeClosureResult,
  MotionPracticeSessionRollupResponse,
  MotionPracticeSessionRollupSummary,
} from './motionPracticeClosureTypes';

const FULL_SESSION_WINDOW_REF_CAP = 5000;

type MotionPracticeClosureTarget = {
  packCode: 'yogacoach' | 'dance_motion_coach';
  playbookCode: 'yogacoach_student_practice_summary' | 'dance_motion_coach_session_summary';
};

function resolveMotionPracticeClosureTarget(
  coachPack: MotionPracticeLaunchInput['coachPack'],
): MotionPracticeClosureTarget {
  if (coachPack === 'dance_motion_coach') {
    return {
      packCode: 'dance_motion_coach',
      playbookCode: 'dance_motion_coach_session_summary',
    };
  }
  return {
    packCode: 'yogacoach',
    playbookCode: 'yogacoach_student_practice_summary',
  };
}

function buildMotionPracticeClosureIntentText({
  input,
  rollup,
}: {
  input: MotionPracticeLaunchInput;
  rollup: MotionPracticeSessionRollupResponse;
}): string {
  const coachLabel = input.coachPack === 'dance_motion_coach' ? 'Dance Coach' : 'AI Yoga';
  const rollupRef = readString(rollup.motion_rollup_ref);
  return rollupRef
    ? `${coachLabel} session close: summarize the live practice with ${rollupRef}.`
    : `${coachLabel} session close: summarize the live practice with the emitted motion_runtime rollup.`;
}

export async function emitMotionPracticeSessionRollup({
  input,
  result,
}: {
  input: MotionPracticeLaunchInput;
  result: MotionPracticeLaunchResult;
}): Promise<MotionPracticeSessionRollupResponse> {
  if (!result.liveSessionId) {
    throw new Error('motion_practice_close_missing_live_session');
  }
  const payload = await postApiJson(
    input.apiUrl,
    '/api/v1/capabilities/motion_runtime/analysis/session-rollups',
    {
      live_session_id: result.liveSessionId,
      instruction_refs: input.instructionRefs || [],
      max_window_refs: FULL_SESSION_WINDOW_REF_CAP,
      max_top_findings: 8,
      metadata: {
        source_surface: 'workspace_motion_source_practice_closure',
        coach_pack: input.coachPack,
        practice_mode: input.practiceMode,
        practice_session_id: result.practiceSessionId,
        capture_session_id: input.sourceSession.session_id,
        course_chapters: readInstructionCourseChapters(input.instructionRefs),
        reference_segment_graphs: readInstructionSegmentGraphs(input.instructionRefs),
        resource_policy: buildMotionPracticeResourcePolicy(),
      },
    },
  );
  if (!isRecord(payload)) {
    throw new Error('motion_practice_rollup_invalid_response');
  }
  return payload as MotionPracticeSessionRollupResponse;
}

export async function submitMotionPracticeClosureSummary({
  input,
  result,
  rollup,
}: {
  input: MotionPracticeLaunchInput;
  result: MotionPracticeLaunchResult;
  rollup: MotionPracticeSessionRollupResponse;
}): Promise<MeetingCommandLedgerAcceptance> {
  const target = resolveMotionPracticeClosureTarget(input.coachPack);
  const parameters = buildMotionPracticeClosureCommandParameters({ input, result, rollup });
  return submitMeetingCommandEnvelope({
    apiUrl: input.apiUrl,
    workspaceId: input.workspaceId,
    meetingId: result.meetingId,
    command: buildMotionPracticeClosureIntentText({ input, rollup }),
    originSurface: 'workspace_motion_source_practice_closure',
    threadId: result.meetingId,
    mentionRefs: [],
    objectActionEntries: [],
    selectedPackTool: null,
    actionParameters: parameters,
    requestedAction: {
      verb: 'execute_playbook',
      pack_code: target.packCode,
      playbook_code: target.playbookCode,
      write_mode: 'recommendation_only',
      parameters,
    },
    metadata: {
      ...buildMotionPracticeCommandMetadata(input),
      motion_practice_launch: false,
      motion_practice_close: true,
      motion_rollup_ref: readString(rollup.motion_rollup_ref) || null,
      rollup_artifact_id: readString(rollup.artifact_id) || null,
      phase: 'phase_06_close_rollup_summary',
    },
  });
}

export async function closeMotionPracticeLiveGuidanceSession({
  input,
  result,
}: {
  input: MotionPracticeLaunchInput;
  result: MotionPracticeLaunchResult;
}): Promise<MotionPracticeClosureResult> {
  const rollup = await emitMotionPracticeSessionRollup({ input, result });
  const command = await submitMotionPracticeClosureSummary({ input, result, rollup });
  return { rollup, command };
}
