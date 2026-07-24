'use client';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import { startLiveMediaReceiver } from '@/lib/media-transport/liveMediaReceiverClient';
import { submitMeetingCommandEnvelope } from '@/components/capabilities/meeting-workbench/meetingCommandLedger';
import {
  buildMotionPracticeCommandMetadata,
  buildMotionPracticeReferenceMetadata,
  buildMotionPracticeResourcePolicy,
  buildMotionSourceRef,
  isRecord,
  readInstructionSegmentGraphs,
  resolveMotionPracticeReference,
} from './motionPracticeLaunchMetadata';
import {
  buildMotionPracticeIntentText as buildMotionPracticeIntentTextFromTarget,
  buildMotionPracticeSessionId as buildMotionPracticeSessionIdFromTarget,
  resolveMotionPracticeTarget as resolveMotionPracticeTargetFromTarget,
  type MotionPracticeCoachPack,
  type MotionPracticeMode,
} from './motionPracticeTargets';

export {
  buildMotionPracticeIntentText,
  buildMotionPracticeSessionId,
  resolveMotionPracticeTarget,
  type MotionPracticeCoachPack,
  type MotionPracticeMode,
  type MotionPracticeTarget,
} from './motionPracticeTargets';
export {
  buildMotionPracticeCommandMetadata,
  buildMotionPracticeReferenceMetadata,
  buildMotionPracticeResourcePolicy,
  buildMotionSourceRef,
} from './motionPracticeLaunchMetadata';

export type MotionPracticeInstructionRef = Record<string, unknown>;

export type MotionPracticeLaunchInput = {
  apiUrl: string;
  workspaceId: string;
  sourceSession: DeviceSessionEntry;
  meetingSessionId?: string;
  coachPack: MotionPracticeCoachPack;
  practiceMode: MotionPracticeMode;
  expertLibraryRef?: string;
  instructionRefs?: MotionPracticeInstructionRef[];
  userGoal?: string;
  expectedDurationMs?: number;
};

export type MotionPracticeLaunchResult = {
  meetingId: string;
  commandId: string | null;
  playbookExecutionId?: string | null;
  liveSessionId: string | null;
  sourceSessionId: string;
  practiceSessionId: string;
  liveGuidanceEnabled: boolean;
  coachPack: MotionPracticeCoachPack;
  practiceMode: MotionPracticeMode;
  status: string;
};

type MeetingSessionSummary = {
  id: string;
  workspace_id?: string;
  thread_id?: string | null;
  metadata?: Record<string, unknown>;
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
          append_owner_required: true,
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
  const requestedMeetingId = input.meetingSessionId?.trim();
  if (requestedMeetingId) {
    if (!active) {
      throw new Error('motion_practice_meeting_not_active');
    }
    if (active.id !== requestedMeetingId) {
      throw new Error('motion_practice_meeting_identity_conflict');
    }
    return active;
  }
  return active || startMotionPracticeMeetingSession(apiUrl, workspaceId, input);
}

async function registerLiveMotionSession(
  input: MotionPracticeLaunchInput,
  meetingId: string,
): Promise<Record<string, unknown>> {
  const reference = resolveMotionPracticeReference(input);
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
        expert_library_ref: reference.sourceRef,
        budget: {
          max_window_writes_per_sec: 2,
          max_meeting_summaries_per_5_sec: 1,
          allow_terminal_safety_bypass: true,
        },
        metadata: {
          source_surface: 'workspace_motion_source_practice_launcher',
          append_owner_required: true,
          source_types: input.sourceSession.source_types,
          coach_pack: input.coachPack,
          practice_mode: input.practiceMode,
          expected_duration_ms: Math.max(0, input.expectedDurationMs || 0),
          ...buildMotionPracticeReferenceMetadata(input),
          resource_policy: buildMotionPracticeResourcePolicy(),
        },
      }),
    },
  );
  return isRecord(payload) ? payload : {};
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

function readPlaybookExecutionId(
  dispatchResult: Record<string, unknown> | null,
): string | null {
  if (!dispatchResult || !isRecord(dispatchResult.playbook)) {
    return null;
  }
  const triggeredPlaybook = isRecord(dispatchResult.playbook.triggered_playbook)
    ? dispatchResult.playbook.triggered_playbook
    : null;
  const executionId = triggeredPlaybook?.execution_id;
  return typeof executionId === 'string' && executionId.trim()
    ? executionId.trim()
    : null;
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
  const reference = resolveMotionPracticeReference(input);
  return {
    practice_session_id: buildMotionPracticeSessionIdFromTarget(input),
    workspace_id: input.workspaceId,
    teacher_library_ref: reference.sourceRef,
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
      ...buildMotionPracticeReferenceMetadata(input),
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
  const reference = resolveMotionPracticeReference(input);
  return {
    workspace_id: input.workspaceId,
    capture_session_id: input.sourceSession.session_id,
    live_motion_session_id: liveSessionId,
    expert_library_ref: reference.sourceRef
      || 'mindscape://dance_motion_coach/expert-library/default',
    choreography_segment_ref: null,
    rhythm_rubric_ref: null,
    style_rubric_ref: null,
    metadata: {
      source_surface: 'workspace_motion_source_practice_launcher',
      source_types: input.sourceSession.source_types,
      ...buildMotionPracticeReferenceMetadata(input),
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
    ...buildMotionPracticeReferenceMetadata(input),
  };
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
  const reference = resolveMotionPracticeReference(input);
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
      expert_library_ref: reference.sourceRef,
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
    expert_library_ref: reference.sourceRef,
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
  const target = resolveMotionPracticeTargetFromTarget(input.coachPack, input.practiceMode);
  const reference = resolveMotionPracticeReference(input);
  if (!target.enabled) {
    throw new Error(target.blockedReason || 'motion_practice_target_not_ready');
  }

  const meeting = await ensureMotionPracticeMeetingSession(
    input.apiUrl,
    input.workspaceId,
    input,
  );
  const liveSessionPayload = await registerLiveMotionSession(input, meeting.id);
  const liveSessionId = readLiveSessionId(liveSessionPayload);
  const mediaSessionId = input.sourceSession.media_session_id?.trim();
  if (!liveSessionId) {
    throw new Error('motion_live_session_not_created');
  }
  if (!mediaSessionId) {
    throw new Error('live_media_session_not_connected');
  }
  await startLiveMediaReceiver({
    apiBase: input.apiUrl,
    workspaceId: input.workspaceId,
    deviceSessionId: input.sourceSession.session_id,
    mediaSessionId,
    liveMotionSessionId: liveSessionId,
    meetingSessionId: meeting.id,
    practiceSessionId: buildMotionPracticeSessionIdFromTarget(input),
    coachPack: input.coachPack,
    practiceMode: input.practiceMode,
    referenceUrl: reference.sourceRef || undefined,
    motionReferenceProfileArtifactId: reference.profileArtifactId || undefined,
    userGoal: input.userGoal,
    expectedDurationMs: input.expectedDurationMs,
  });

  if (target.launchKind === 'live_guidance') {
    return {
      meetingId: meeting.id,
      commandId: null,
      playbookExecutionId: null,
      status: 'active',
      liveSessionId,
      sourceSessionId: input.sourceSession.session_id,
      practiceSessionId: buildMotionPracticeSessionIdFromTarget(input),
      liveGuidanceEnabled: true,
      coachPack: input.coachPack,
      practiceMode: input.practiceMode,
    };
  }

  if (!target.playbookCode) {
    throw new Error(target.blockedReason || 'motion_practice_playbook_not_ready');
  }

  const parameters = buildMotionPracticeCommandParameters({
    input,
    meetingId: meeting.id,
    liveSessionPayload,
  });
  const command = await submitMeetingCommandEnvelope({
    apiUrl: input.apiUrl,
    workspaceId: input.workspaceId,
    meetingId: meeting.id,
    command: buildMotionPracticeIntentTextFromTarget(input),
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
    playbookExecutionId: readPlaybookExecutionId(command.dispatchResult),
    status: command.status,
    liveSessionId,
    sourceSessionId: input.sourceSession.session_id,
    practiceSessionId: buildMotionPracticeSessionIdFromTarget(input),
    liveGuidanceEnabled: false,
    coachPack: input.coachPack,
    practiceMode: input.practiceMode,
  };
}
