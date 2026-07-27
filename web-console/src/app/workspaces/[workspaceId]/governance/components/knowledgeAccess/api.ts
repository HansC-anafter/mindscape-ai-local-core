import { getApiBaseUrl } from '@/lib/api-url';

import type {
  KnowledgeAccessDetail,
  KnowledgeAccessReplacement,
  KnowledgeAccessSummary,
  KnowledgeProjectionAction,
  KnowledgeProjectionActionReceipt,
} from './types';

function collectionUrl(workspaceId: string): string {
  return `${getApiBaseUrl()}/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/knowledge-access`;
}

async function readJson<T>(
  response: Response,
  fallback: string
): Promise<T> {
  if (!response.ok) {
    let detail = fallback;
    try {
      const body = await response.json();
      detail = String(body?.detail || fallback);
    } catch {
      // Preserve the bounded fallback; never issue a second request.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function loadKnowledgeAccessSummary(
  workspaceId: string,
  signal: AbortSignal
): Promise<KnowledgeAccessSummary> {
  const response = await fetch(`${collectionUrl(workspaceId)}?limit=50`, {
    cache: 'no-store',
    signal,
  });
  return readJson(response, 'knowledge_access_summary_failed');
}

export async function loadKnowledgeAccessDetail(
  workspaceId: string,
  resourceId: string,
  signal: AbortSignal
): Promise<KnowledgeAccessDetail> {
  const response = await fetch(
    `${collectionUrl(workspaceId)}/${encodeURIComponent(resourceId)}`,
    { cache: 'no-store', signal }
  );
  return readJson(response, 'knowledge_access_detail_failed');
}

export async function replaceKnowledgeAccess(
  workspaceId: string,
  resourceId: string,
  command: KnowledgeAccessReplacement
): Promise<KnowledgeAccessDetail> {
  const response = await fetch(
    `${collectionUrl(workspaceId)}/${encodeURIComponent(resourceId)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(command),
    }
  );
  return readJson(response, 'knowledge_access_replacement_failed');
}

export async function runKnowledgeProjectionAction(
  workspaceId: string,
  resourceId: string,
  action: KnowledgeProjectionAction,
  expectedAuthzRevision: number,
  expectedSourceRevision: string
): Promise<KnowledgeProjectionActionReceipt> {
  const response = await fetch(
    `${collectionUrl(workspaceId)}/${encodeURIComponent(resourceId)}/actions`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action,
        expected_authz_revision: expectedAuthzRevision,
        expected_source_revision: expectedSourceRevision,
      }),
    }
  );
  return readJson(response, 'knowledge_projection_action_failed');
}
