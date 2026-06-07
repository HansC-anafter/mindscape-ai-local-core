'use client';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import { submitMeetingCommandEnvelope } from '@/components/capabilities/meeting-workbench/meetingCommandLedger';

export type MotionPracticeCoachPack = 'yogacoach' | 'dance_motion_coach';
export type MotionPracticeMode = 'record_summary' | 'teacher_assessment' | 'live_guidance';

export type MotionPracticeTarget = {
  enabled: boolean;
  packCode: string;
  playbookCode: string | null;
  readinessLabel: string;
  blockedReason?: string;
};

export type MotionPracticeInstructionRef = Record<string, unknown>;

export type MotionPracticeLaunchInput = {
  apiUrl: string;
  workspaceId: string;
  sourceSession: DeviceSessionEntry;
  coachPack: MotionPracticeCoachPack;
  practiceMode: MotionPracticeMode;
  expertLibraryRef?: string;
  instructionRefs?: MotionPracticeInstructionRef[];
  userGoal?: string;
};

export type MotionPracticeLaunchResult = {
  meetingId: string;
  commandId: string;
  liveSessionId: string | null;
  sourceSessionId: string;
  status: string;
};

type MeetingSessionSummary = {
  id: string;
  workspace_id?: string;
  thread_id?: string | null;
  metadata?: Record<string, unknown>;
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

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function resolveApiBase(apiUrl: string): string {
  if (apiUrl.trim()) {
    return trimTrailingSlash(apiUrl.trim());
  }
  if (typeof window !== 'undefined') {
    return window.location.origin;
  }
  return '';
}

function buildApiUrl(apiUrl: string, path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const apiBase = resolveApiBase(apiUrl);
  return apiBase ? `${apiBase}${normalizedPath}` : normalizedPath;
}

async function fetchJson(
  apiUrl: string,
  path: string,
  init: RequestInit = {},
): Promise<unknown> {
  const response = await fetch(buildApiUrl(apiUrl, path), {
    credentials: 'same-origin',
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init.headers || {}),
    },
  });
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => null);
    const detail = typeof errorPayload === 'object' && errorPayload && 'detail' in errorPayload
      ? String((errorPayload as { detail?: unknown }).detail || '')
      : '';
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

async function fetchActiveMeetingSession(
  apiUrl: string,
  workspaceId: string,
): Promise<MeetingSessionSummary | null> {
  const response = await fetch(
    buildApiUrl(apiUrl, `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/meeting-sessions/active`),
    { credentials: 'same-origin' },
  );
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Meeting lookup failed: ${response.status}`);
  }
  const payload = await response.json();
  return isMeetingSessionSummary(payload) ? payload : null;
}

async function startMotionPracticeMeetingSession(
  apiUrl: string,
  workspaceId: string,
  input: MotionPracticeLaunchInput,
): Promise<MeetingSessionSummary> {
  const payload = await fetchJson(
    apiUrl,
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/meeting-sessions/start`,
    {
      method: 'POST',
      body: JSON.stringify({
        meeting_type: 'motion_practice',
        agenda: [
          'Bind the selected motion source to an AI practice workflow.',
          'Preserve compact motion analysis refs for guidance and practice records.',
        ],
        success_criteria: [
          'No raw media is persisted by the meeting command.',
          'Practice output references motion_runtime analysis summaries.',
        ],
        max_rounds: 5,
        metadata: {
          source_surface: 'workspace_motion_source_practice_launcher',
          motion_practice_launch: true,
          coach_pack: input.coachPack,
          practice_mode: input.practiceMode,
          capture_session_id: input.sourceSession.session_id,
        },
      }),
    },
  );
  if (!isMeetingSessionSummary(payload)) {
    throw new Error('Meeting session start returned an invalid response.');
  }
  return payload;
}

async function ensureMotionPracticeMeetingSession(
  apiUrl: string,
  workspaceId: string,
  input: MotionPracticeLaunchInput,
): Promise<MeetingSessionSummary> {
  const active = await fetchActiveMeetingSession(apiUrl, workspaceId);
  return active || startMotionPracticeMeetingSession(apiUrl, workspaceId, input);
}

async function registerLiveMotionSession(
  input: MotionPracticeLaunchInput,
  meetingId: string,
): Promise<Record<string, unknown>> {
  const payload = await fetchJson(
    input.apiUrl,
    '/api/v1/capabilities/motion_runtime/analysis/live-sessions',
    {
      method: 'POST',
      body: JSON.stringify({
        workspace_id: input.workspaceId,
        capture_session_id: input.sourceSession.session_id,
        device_profile_ref: buildMotionSourceRef(input.sourceSession),
        meeting_session_id: meetingId,
        expert_library_ref: input.expertLibraryRef?.trim() || null,
        budget: {
          max_window_writes_per_sec: 2,
          max_meeting_summaries_per_5_sec: 1,
          allow_terminal_safety_bypass: true,
        },
        metadata: {
          source_surface: 'workspace_motion_source_practice_launcher',
          source_types: input.sourceSession.source_types,
          coach_pack: input.coachPack,
          practice_mode: input.practiceMode,
          resource_policy: buildMotionPracticeResourcePolicy(),
        },
      }),
    },
  );
  return isRecord(payload) ? payload : {};
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isMeetingSessionSummary(value: unknown): value is MeetingSessionSummary {
  return isRecord(value) && typeof value.id === 'string' && value.id.trim().length > 0;
}

function readLiveSessionId(liveSessionPayload: Record<string, unknown>): string | null {
  const liveSession = liveSessionPayload.live_session;
  if (!isRecord(liveSession)) {
    return null;
  }
  const id = liveSession.live_session_id;
  return typeof id === 'string' && id.trim() ? id.trim() : null;
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
    transport: 'webrtc_signal_and_peer_connection',
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
        readinessLabel: 'Ready to submit a Dance Coach session-close summary command.',
      };
    }
    return {
      enabled: false,
      packCode: 'dance_motion_coach',
      playbookCode: null,
      readinessLabel: 'Dance live guidance and teacher assessment are pending.',
      blockedReason: 'Dance currently exposes a session-close summary playbook only.',
    };
  }
  if (practiceMode === 'live_guidance') {
    return {
      enabled: false,
      packCode: 'yogacoach',
      playbookCode: null,
      readinessLabel: 'Live guidance needs analyzer-to-cue streaming before launch.',
      blockedReason: 'Realtime pose windows are not yet bridged from WebRTC into motion_runtime.analysis cues.',
    };
  }
  if (practiceMode === 'teacher_assessment') {
    return {
      enabled: true,
      packCode: 'yogacoach',
      playbookCode: 'yogacoach_teacher_learning_assessment',
      readinessLabel: 'Ready to submit a teacher-facing assessment command.',
    };
  }
  return {
    enabled: true,
    packCode: 'yogacoach',
    playbookCode: 'yogacoach_student_practice_summary',
    readinessLabel: 'Ready to submit a student summary command.',
  };
}

export function buildYogaLivePracticeRollup({
  input,
  meetingId,
  liveSessionId,
}: {
  input: MotionPracticeLaunchInput;
  meetingId: string;
  liveSessionId: string | null;
}): Record<string, unknown> {
  const sourceRef = buildMotionSourceRef(input.sourceSession);
  return {
    practice_session_id: `${input.sourceSession.session_id}:${input.practiceMode}`,
    workspace_id: input.workspaceId,
    teacher_library_ref: input.expertLibraryRef?.trim() || null,
    asana_refs: [],
    duration_ms: 0,
    window_count: 0,
    motion_summary_refs: [
      {
        ref_type: 'live_motion_session',
        live_session_id: liveSessionId,
        capture_session_id: input.sourceSession.session_id,
        device_profile_ref: sourceRef,
        meeting_session_id: meetingId,
        source_types: input.sourceSession.source_types,
      },
    ],
    score_aggregates: {},
    safety_event_counts: {},
    top_findings: ['More live motion windows are required before scoring.'],
    summary_confidence: 'insufficient',
    metadata: {
      source_surface: 'workspace_motion_source_practice_launcher',
      coach_pack: input.coachPack,
      practice_mode: input.practiceMode,
      instruction_refs: input.instructionRefs || [],
      resource_policy: buildMotionPracticeResourcePolicy(),
    },
  };
}

function buildDancePracticeSession({
  input,
  liveSessionId,
}: {
  input: MotionPracticeLaunchInput;
  liveSessionId: string | null;
}): Record<string, unknown> {
  return {
    workspace_id: input.workspaceId,
    capture_session_id: input.sourceSession.session_id,
    live_motion_session_id: liveSessionId,
    expert_library_ref: input.expertLibraryRef?.trim()
      || 'mindscape://dance_motion_coach/expert-library/default',
    choreography_segment_ref: null,
    rhythm_rubric_ref: null,
    style_rubric_ref: null,
    metadata: {
      source_surface: 'workspace_motion_source_practice_launcher',
      source_types: input.sourceSession.source_types,
      instruction_refs: input.instructionRefs || [],
      resource_policy: buildMotionPracticeResourcePolicy(),
    },
  };
}

function buildDanceMotionSummary({
  input,
  meetingId,
  liveSessionId,
}: {
  input: MotionPracticeLaunchInput;
  meetingId: string;
  liveSessionId: string | null;
}): Record<string, unknown> {
  return {
    motion_summary_ref: liveSessionId
      ? `mindscape://motion_runtime/live-session/${encodeURIComponent(liveSessionId)}`
      : buildMotionSourceRef(input.sourceSession),
    live_session_id: liveSessionId,
    meeting_session_id: meetingId,
    scores: {},
    findings: ['More live motion windows are required before scoring.'],
    instruction_refs: input.instructionRefs || [],
  };
}

export function buildMotionPracticeIntentText(input: MotionPracticeLaunchInput): string {
  const coach = COACH_LABELS[input.coachPack];
  const mode = MODE_LABELS[input.practiceMode];
  const sourceLabel = input.sourceSession.display_name || input.sourceSession.device_id;
  return `${coach} ${mode}: use ${sourceLabel} as the motion source and create the practice record.`;
}

export function buildMotionPracticeCommandParameters({
  input,
  meetingId,
  liveSessionPayload,
}: {
  input: MotionPracticeLaunchInput;
  meetingId: string;
  liveSessionPayload: Record<string, unknown>;
}): Record<string, unknown> {
  const liveSessionId = readLiveSessionId(liveSessionPayload);
  const livePracticeRollup = buildYogaLivePracticeRollup({
    input,
    meetingId,
    liveSessionId,
  });
  if (input.coachPack === 'dance_motion_coach') {
    return {
      workspace_id: input.workspaceId,
      meeting_session_id: meetingId,
      capture_session_id: input.sourceSession.session_id,
      device_profile_ref: buildMotionSourceRef(input.sourceSession),
      source_types: input.sourceSession.source_types,
      expert_library_ref: input.expertLibraryRef?.trim() || null,
      user_id: 'default-user',
      user_goal: input.userGoal?.trim() || '',
      coach_pack: input.coachPack,
      practice_mode: input.practiceMode,
      motion_runtime_live_session: liveSessionPayload.live_session || null,
      live_practice_rollup: livePracticeRollup,
      practice_session: buildDancePracticeSession({ input, liveSessionId }),
      motion_summary: buildDanceMotionSummary({ input, meetingId, liveSessionId }),
      rubric_hint: input.userGoal?.trim() || '',
      resource_policy: buildMotionPracticeResourcePolicy(),
    };
  }
  return {
    workspace_id: input.workspaceId,
    meeting_session_id: meetingId,
    capture_session_id: input.sourceSession.session_id,
    device_profile_ref: buildMotionSourceRef(input.sourceSession),
    source_types: input.sourceSession.source_types,
    expert_library_ref: input.expertLibraryRef?.trim() || null,
    user_id: 'default-user',
    user_goal: input.userGoal?.trim() || '',
    coach_pack: input.coachPack,
    practice_mode: input.practiceMode,
    motion_runtime_live_session: liveSessionPayload.live_session || null,
    live_practice_rollup: livePracticeRollup,
    resource_policy: buildMotionPracticeResourcePolicy(),
  };
}

export async function launchMotionPractice(
  input: MotionPracticeLaunchInput,
): Promise<MotionPracticeLaunchResult> {
  const target = resolveMotionPracticeTarget(input.coachPack, input.practiceMode);
  if (!target.enabled || !target.playbookCode) {
    throw new Error(target.blockedReason || 'motion_practice_target_not_ready');
  }

  const meeting = await ensureMotionPracticeMeetingSession(
    input.apiUrl,
    input.workspaceId,
    input,
  );
  const liveSessionPayload = await registerLiveMotionSession(input, meeting.id);
  const parameters = buildMotionPracticeCommandParameters({
    input,
    meetingId: meeting.id,
    liveSessionPayload,
  });
  const command = await submitMeetingCommandEnvelope({
    apiUrl: input.apiUrl,
    workspaceId: input.workspaceId,
    meetingId: meeting.id,
    command: buildMotionPracticeIntentText(input),
    originSurface: 'workspace_motion_source_practice_launcher',
    threadId: meeting.thread_id || meeting.id,
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
    metadata: buildMotionPracticeCommandMetadata(input),
  });

  return {
    meetingId: meeting.id,
    commandId: command.commandId,
    status: command.status,
    liveSessionId: readLiveSessionId(liveSessionPayload),
    sourceSessionId: input.sourceSession.session_id,
  };
}
