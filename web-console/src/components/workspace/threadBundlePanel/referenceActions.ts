import type { AddThreadReferenceParams } from './types';

export function buildThreadReferenceUrl(
  apiUrl: string,
  workspaceId: string,
  threadId: string,
): string {
  return `${apiUrl}/api/v1/workspaces/${workspaceId}/threads/${threadId}/references`;
}

export async function addThreadReference({
  apiUrl,
  workspaceId,
  threadId,
  sourceType,
  uri,
  title,
  snippet,
  reason,
}: AddThreadReferenceParams): Promise<void> {
  const response = await fetch(
    buildThreadReferenceUrl(apiUrl, workspaceId, threadId),
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        source_type: sourceType,
        uri,
        title,
        snippet: snippet || undefined,
        reason: reason || undefined,
      }),
    },
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(errorData.detail || 'Failed to add reference');
  }
}
