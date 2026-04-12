'use client';

export type IGVisionExecutionMode = 'local' | 'cloud';

export interface IGVisionRuntimePolicy {
  visionExecutionMode: IGVisionExecutionMode;
  visionTargetDeviceId: string | null;
}

function sanitizeVisionExecutionMode(rawValue?: string | null): IGVisionExecutionMode {
  return (rawValue || '').trim().toLowerCase() === 'cloud' ? 'cloud' : 'local';
}

function normalizeVisionTargetDeviceId(rawValue?: string | null): string | null {
  const normalized = (rawValue || '').trim();
  return normalized || null;
}

export async function fetchIGVisionRuntimePolicy(
  apiUrl: string,
  workspaceId: string,
): Promise<IGVisionRuntimePolicy> {
  const response = await fetch(
    `${apiUrl}/api/v1/ig/workbench/runtime-policy?workspace_id=${encodeURIComponent(workspaceId)}`,
    {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    },
  );
  if (!response.ok) {
    throw new Error(`Failed to load vision runtime policy: ${response.status}`);
  }
  const data = await response.json();
  return {
    visionExecutionMode: sanitizeVisionExecutionMode(data?.vision_execution_mode),
    visionTargetDeviceId: normalizeVisionTargetDeviceId(data?.vision_target_device_id),
  };
}

export async function saveIGVisionRuntimePolicy(
  apiUrl: string,
  params: {
    workspaceId: string;
    visionExecutionMode: IGVisionExecutionMode;
    visionTargetDeviceId?: string | null;
  },
): Promise<IGVisionRuntimePolicy> {
  const response = await fetch(`${apiUrl}/api/v1/ig/workbench/runtime-policy`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      workspace_id: params.workspaceId,
      vision_execution_mode: sanitizeVisionExecutionMode(params.visionExecutionMode),
      vision_target_device_id: normalizeVisionTargetDeviceId(params.visionTargetDeviceId),
    }),
  });
  if (!response.ok) {
    throw new Error(`Failed to save vision runtime policy: ${response.status}`);
  }
  const data = await response.json();
  return {
    visionExecutionMode: sanitizeVisionExecutionMode(data?.vision_execution_mode),
    visionTargetDeviceId: normalizeVisionTargetDeviceId(data?.vision_target_device_id),
  };
}
