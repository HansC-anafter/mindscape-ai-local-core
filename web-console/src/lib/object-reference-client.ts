import type { AddressableObjectRef, AddressableObjectSummary } from './addressable-object-layer';

export type ObjectReferencePreviewResult =
  | {
      status: 'ready';
      summary: AddressableObjectSummary;
      workspace_id: string;
    }
  | {
      status: 'not_indexed';
      code: 'object_not_indexed';
      message: string;
      details?: Record<string, unknown>;
    };

interface ReadObjectReferencePreviewParams {
  apiUrl: string;
  workspaceId: string;
  objectRef: AddressableObjectRef;
  signal?: AbortSignal;
}

interface SyncObjectReferenceIndexParams {
  apiUrl: string;
  workspaceId: string;
  objectRef: AddressableObjectRef;
  reason?: string;
  signal?: AbortSignal;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function buildApiUrl(apiUrl: string, path: string): string {
  const base = apiUrl.replace(/\/$/, '');
  return `${base}${path}`;
}

async function parseJsonBody(response: Response): Promise<unknown> {
  const text = await response.text();
  return text ? JSON.parse(text) : {};
}

function readErrorMessage(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) return fallback;
  const detail = payload.detail;
  if (typeof detail === 'string') return detail;
  if (isRecord(detail) && typeof detail.message === 'string') {
    return detail.message;
  }
  return fallback;
}

function readNotIndexedResult(payload: unknown): ObjectReferencePreviewResult | null {
  if (!isRecord(payload) || !isRecord(payload.detail)) return null;
  const { detail } = payload;
  if (detail.code !== 'object_not_indexed') return null;
  return {
    status: 'not_indexed',
    code: 'object_not_indexed',
    message: typeof detail.message === 'string' ? detail.message : 'Object is not indexed.',
    details: isRecord(detail.details) ? detail.details : undefined,
  };
}

export async function readObjectReferencePreview({
  apiUrl,
  workspaceId,
  objectRef,
  signal,
}: ReadObjectReferencePreviewParams): Promise<ObjectReferencePreviewResult> {
  const response = await fetch(
    buildApiUrl(
      apiUrl,
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/objects/read`,
    ),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        object_ref: {
          ...objectRef,
          workspace_id: objectRef.workspace_id || workspaceId,
        },
      }),
      signal,
    },
  );
  const payload = await parseJsonBody(response);

  if (!response.ok) {
    const notIndexed = readNotIndexedResult(payload);
    if (notIndexed) {
      return notIndexed;
    }
    throw new Error(readErrorMessage(payload, `Failed to read object preview: HTTP ${response.status}`));
  }

  if (!isRecord(payload) || !isRecord(payload.object)) {
    throw new Error('Object preview response did not include an object summary.');
  }

  return {
    status: 'ready',
    summary: payload.object as unknown as AddressableObjectSummary,
    workspace_id: typeof payload.workspace_id === 'string' ? payload.workspace_id : workspaceId,
  };
}

async function syncObjectReferenceIndex({
  apiUrl,
  workspaceId,
  objectRef,
  reason = 'inline_object_reference_preview',
  signal,
}: SyncObjectReferenceIndexParams): Promise<void> {
  if (!objectRef.object_id) return;

  const response = await fetch(
    buildApiUrl(
      apiUrl,
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/objects/sync`,
    ),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        owner_pack: objectRef.owner_pack,
        object_kind: objectRef.object_kind,
        object_ids: [objectRef.object_id],
        limit: 1,
        force: true,
        reason,
      }),
      signal,
    },
  );
  const payload = await parseJsonBody(response);

  if (!response.ok) {
    throw new Error(readErrorMessage(payload, `Failed to sync object preview: HTTP ${response.status}`));
  }
}

export async function readObjectReferencePreviewWithSync({
  apiUrl,
  workspaceId,
  objectRef,
  signal,
}: ReadObjectReferencePreviewParams): Promise<ObjectReferencePreviewResult> {
  const firstResult = await readObjectReferencePreview({
    apiUrl,
    workspaceId,
    objectRef,
    signal,
  });
  if (firstResult.status === 'ready') {
    return firstResult;
  }

  await syncObjectReferenceIndex({
    apiUrl,
    workspaceId,
    objectRef,
    signal,
  });
  return readObjectReferencePreview({
    apiUrl,
    workspaceId,
    objectRef,
    signal,
  });
}
