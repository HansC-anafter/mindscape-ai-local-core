'use client';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';

export type MotionPracticeCoachPack = 'yogacoach' | 'dance_motion_coach';
export type MotionPracticeMode = 'record_summary' | 'teacher_assessment' | 'live_guidance';

export type MotionPracticeTarget = {
  enabled: boolean;
  packCode: string;
  playbookCode: string | null;
  launchKind: 'command' | 'live_guidance';
  readinessLabel: string;
  blockedReason?: string;
};

type MotionPracticeTargetInput = {
  sourceSession: Pick<DeviceSessionEntry, 'session_id' | 'display_name' | 'device_id'>;
  coachPack: MotionPracticeCoachPack;
  practiceMode: MotionPracticeMode;
  [key: string]: unknown;
};

const COACH_LABELS: Record<MotionPracticeCoachPack, string> = {
  yogacoach: 'AI Yoga',
  dance_motion_coach: 'Dance Coach',
};

const MODE_LABELS: Record<MotionPracticeMode, string> = {
  record_summary: 'Record + summary',
  teacher_assessment: 'Teacher assessment',
  live_guidance: 'Live guidance',
};

export function buildMotionPracticeSessionId(
  input: Pick<MotionPracticeTargetInput, 'sourceSession' | 'practiceMode'>,
): string {
  return `${input.sourceSession.session_id}:${input.practiceMode}`;
}

export function resolveMotionPracticeTarget(
  coachPack: MotionPracticeCoachPack,
  practiceMode: MotionPracticeMode,
): MotionPracticeTarget {
  if (coachPack === 'dance_motion_coach') {
    if (practiceMode === 'record_summary') {
      return {
        enabled: true,
        packCode: 'dance_motion_coach',
        playbookCode: 'dance_motion_coach_session_summary',
        launchKind: 'command',
        readinessLabel: 'Ready to submit a Dance Coach session-close summary command.',
      };
    }
    if (practiceMode === 'live_guidance') {
      return {
        enabled: true,
        packCode: 'dance_motion_coach',
        playbookCode: null,
        launchKind: 'live_guidance',
        readinessLabel: 'Ready to start bounded Dance live guidance without command ledger writes.',
      };
    }
    return {
      enabled: false,
      packCode: 'dance_motion_coach',
      playbookCode: null,
      launchKind: 'command',
      readinessLabel: 'Dance teacher assessment is pending.',
      blockedReason: 'Dance currently exposes a session-close summary playbook and bounded live guidance only.',
    };
  }
  if (practiceMode === 'live_guidance') {
    return {
      enabled: true,
      packCode: 'yogacoach',
      playbookCode: null,
      launchKind: 'live_guidance',
      readinessLabel: 'Ready to start bounded AI Yoga live guidance without command ledger writes.',
    };
  }
  if (practiceMode === 'teacher_assessment') {
    return {
      enabled: true,
      packCode: 'yogacoach',
      playbookCode: 'yogacoach_teacher_learning_assessment',
      launchKind: 'command',
      readinessLabel: 'Ready to submit a teacher-facing assessment command.',
    };
  }
  return {
    enabled: true,
    packCode: 'yogacoach',
    playbookCode: 'yogacoach_student_practice_summary',
    launchKind: 'command',
    readinessLabel: 'Ready to submit a student summary command.',
  };
}

export function buildMotionPracticeIntentText(input: MotionPracticeTargetInput): string {
  const coach = COACH_LABELS[input.coachPack];
  const mode = MODE_LABELS[input.practiceMode];
  const sourceLabel = input.sourceSession.display_name || input.sourceSession.device_id;
  return `${coach} ${mode}: use ${sourceLabel} as the motion source and create the practice record.`;
}
