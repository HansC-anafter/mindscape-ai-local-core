export type LiveMediaReceiverStatus = {
  schema_version: 'live_media_receiver_control.v1';
  status: string;
  state?: string;
  workspace_id?: string;
  media_session_id: string;
  receiver_identity?: string;
};

type StartLiveMediaReceiverInput = {
  apiBase: string;
  workspaceId: string;
  deviceSessionId: string;
  mediaSessionId: string;
  liveMotionSessionId: string;
  meetingSessionId: string;
  practiceSessionId: string;
  coachPack: 'yogacoach' | 'dance_motion_coach';
  practiceMode: string;
  referenceUrl?: string;
  motionReferenceProfileArtifactId?: string;
  userGoal?: string;
  expectedDurationMs?: number;
};

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

export async function startLiveMediaReceiver(
  input: StartLiveMediaReceiverInput,
): Promise<LiveMediaReceiverStatus> {
  const response = await fetch(
    `${trimTrailingSlash(input.apiBase)}/api/v1/workspaces/${encodeURIComponent(input.workspaceId)}`
      + `/device-bindings/${encodeURIComponent(input.deviceSessionId)}`
      + `/media-sessions/${encodeURIComponent(input.mediaSessionId)}/receiver/start`,
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        live_motion_session_id: input.liveMotionSessionId,
        meeting_session_id: input.meetingSessionId,
        practice_session_id: input.practiceSessionId,
        coach_pack: input.coachPack,
        practice_mode: input.practiceMode,
        reference_url: input.referenceUrl?.trim() || null,
        motion_reference_profile_artifact_id:
          input.motionReferenceProfileArtifactId?.trim() || null,
        user_goal: input.userGoal?.trim() || null,
        expected_duration_ms: Math.max(0, input.expectedDurationMs || 0),
      }),
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || `live_media_receiver_start_failed_${response.status}`);
  }
  const status = await response.json() as LiveMediaReceiverStatus;
  if (status.status !== 'active' || status.media_session_id !== input.mediaSessionId) {
    throw new Error(`live_media_receiver_not_active:${status.status || 'unknown'}`);
  }
  return status;
}
