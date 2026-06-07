'use client';

export type LocalVideoMotionResourcePolicy = {
  raw_media_db_writes: false;
  raw_frame_meeting_ledger_writes: false;
  ux_polling: false;
  worker_required_for_launch: false;
  transport: 'local_browser_file_object_url';
};

export type LocalVideoFileDescriptor = {
  name: string;
  size: number;
  type?: string;
  lastModified?: number;
};

export type LocalVideoLiveSessionRequest = {
  workspace_id: string;
  capture_session_id: string;
  device_profile_ref: string;
  meeting_session_id: null;
  expert_library_ref: null;
  budget: {
    max_window_writes_per_sec: 2;
    max_meeting_summaries_per_5_sec: 1;
    allow_terminal_safety_bypass: true;
  };
  metadata: {
    source_surface: 'workspace_local_video_motion_smoke';
    source_kind: 'local_video_file';
    file: LocalVideoFileDescriptor;
    resource_policy: LocalVideoMotionResourcePolicy;
  };
};

export type LocalVideoRegisterLiveSessionInput = {
  apiUrl: string;
  workspaceId: string;
  file: LocalVideoFileDescriptor;
};

export type LocalVideoRegisterLiveSessionResponse = {
  live_session?: {
    live_session_id?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
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

function normalizeFileName(name: string): string {
  const trimmed = name.trim() || 'local-video';
  return trimmed.replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'local-video';
}

export function buildLocalVideoCaptureSessionId(file: LocalVideoFileDescriptor): string {
  const name = normalizeFileName(file.name);
  const size = Number.isFinite(file.size) ? Math.max(0, Math.round(file.size)) : 0;
  const modified = Number.isFinite(file.lastModified || NaN)
    ? Math.max(0, Math.round(file.lastModified || 0))
    : 0;
  return `local_video:${name}:${size}:${modified}`;
}

export function buildLocalVideoSourceRef(file: LocalVideoFileDescriptor): string {
  return `mindscape://local-video/${encodeURIComponent(buildLocalVideoCaptureSessionId(file))}`;
}

export function buildLocalVideoMotionResourcePolicy(): LocalVideoMotionResourcePolicy {
  return {
    raw_media_db_writes: false,
    raw_frame_meeting_ledger_writes: false,
    ux_polling: false,
    worker_required_for_launch: false,
    transport: 'local_browser_file_object_url',
  };
}

export function buildLocalVideoLiveSessionRequest({
  workspaceId,
  file,
}: Omit<LocalVideoRegisterLiveSessionInput, 'apiUrl'>): LocalVideoLiveSessionRequest {
  return {
    workspace_id: workspaceId,
    capture_session_id: buildLocalVideoCaptureSessionId(file),
    device_profile_ref: buildLocalVideoSourceRef(file),
    meeting_session_id: null,
    expert_library_ref: null,
    budget: {
      max_window_writes_per_sec: 2,
      max_meeting_summaries_per_5_sec: 1,
      allow_terminal_safety_bypass: true,
    },
    metadata: {
      source_surface: 'workspace_local_video_motion_smoke',
      source_kind: 'local_video_file',
      file: {
        name: file.name,
        size: file.size,
        type: file.type || '',
        lastModified: file.lastModified || 0,
      },
      resource_policy: buildLocalVideoMotionResourcePolicy(),
    },
  };
}

export function readLocalVideoLiveSessionId(
  payload: LocalVideoRegisterLiveSessionResponse,
): string | null {
  const liveSessionId = payload.live_session?.live_session_id;
  return typeof liveSessionId === 'string' && liveSessionId.trim() ? liveSessionId.trim() : null;
}

export async function registerLocalVideoLiveSession({
  apiUrl,
  workspaceId,
  file,
}: LocalVideoRegisterLiveSessionInput): Promise<LocalVideoRegisterLiveSessionResponse> {
  const response = await fetch(
    buildApiUrl(apiUrl, '/api/v1/capabilities/motion_runtime/analysis/live-sessions'),
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(buildLocalVideoLiveSessionRequest({ workspaceId, file })),
    },
  );
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => null);
    const detail = typeof errorPayload === 'object' && errorPayload && 'detail' in errorPayload
      ? String((errorPayload as { detail?: unknown }).detail || '')
      : '';
    throw new Error(detail || `Local video live session registration failed: ${response.status}`);
  }
  const payload = await response.json();
  return typeof payload === 'object' && payload !== null
    ? payload as LocalVideoRegisterLiveSessionResponse
    : {};
}
