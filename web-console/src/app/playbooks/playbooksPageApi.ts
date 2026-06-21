import { getApiBaseUrl } from '../../lib/api-url';
import type { Playbook } from './playbooksPageTypes';
import { normalizePlaybookList } from './playbooksPageTransforms';

export const API_URL = getApiBaseUrl();
export const DEFAULT_PROFILE_ID = 'default-user';
export const PLAYBOOKS_REQUEST_TIMEOUT_MS = 30000;

const jsonHeaders = { 'Content-Type': 'application/json' };

export interface PlaybooksListUrlOptions {
  locale: string;
  selectedTags: string[];
  selectedWorkspaceId: string | null;
  filter: string | null;
}

export function resolveApiBaseUrl(apiBaseUrl = API_URL): string {
  return apiBaseUrl.startsWith('http') ? apiBaseUrl : '';
}

export function targetLanguageForLocale(locale: string): string {
  return locale === 'en' ? 'en' : locale === 'ja' ? 'ja' : 'zh-TW';
}

export function buildSupportedTestsUrl(apiBaseUrl = API_URL): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/playbooks/smoke-test/supported`;
}

export function buildPlaybooksListUrl(
  options: PlaybooksListUrlOptions,
  profileId = DEFAULT_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  const params = new URLSearchParams({
    tags: options.selectedTags.join(',') || '',
    target_language: targetLanguageForLocale(options.locale),
    profile_id: profileId,
  });

  if (options.selectedWorkspaceId) {
    params.append('workspace_id', options.selectedWorkspaceId);
  }

  if (options.filter) {
    params.append('filter', options.filter);
  }

  return `${apiUrl}/api/v1/playbooks?${params.toString()}`;
}

export function buildFavoriteMetaUrl(
  playbookCode: string,
  favorite: boolean,
  profileId = DEFAULT_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/playbooks/${playbookCode}/meta?profile_id=${profileId}&favorite=${favorite}`;
}

export function buildWorkspaceCreateUrl(
  ownerUserId = DEFAULT_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/workspaces?owner_user_id=${ownerUserId}`;
}

export function buildReindexUrl(apiBaseUrl = API_URL): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/playbooks/reindex`;
}

export function buildPinnedPlaybookUrl(
  workspaceId: string,
  playbookCode: string,
  isPinned: boolean,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return isPinned
    ? `${apiUrl}/api/v1/workspaces/${workspaceId}/pinned-playbooks/${playbookCode}`
    : `${apiUrl}/api/v1/workspaces/${workspaceId}/pinned-playbooks`;
}

async function fetchWithAbort(url: string, init: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), PLAYBOOKS_REQUEST_TIMEOUT_MS);

  try {
    return await fetch(url, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchSupportedTestPlaybooks(): Promise<Set<string>> {
  const response = await fetch(buildSupportedTestsUrl());
  if (!response.ok) {
    return new Set();
  }
  const data = await response.json();
  return new Set(Array.isArray(data) ? data : []);
}

export async function fetchPlaybooks(options: PlaybooksListUrlOptions): Promise<Playbook[]> {
  const response = await fetchWithAbort(buildPlaybooksListUrl(options));
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to load playbooks: ${response.status} ${errorText}`);
  }
  return normalizePlaybookList(await response.json());
}

export async function patchPlaybookFavorite(playbookCode: string, favorite: boolean): Promise<void> {
  await fetch(buildFavoriteMetaUrl(playbookCode, favorite), {
    method: 'PATCH',
    headers: jsonHeaders,
  });
}

export async function createWorkspaceForPlaybook(
  workspaceTitle: string,
  playbookName: string,
  ownerUserId = DEFAULT_PROFILE_ID
): Promise<Response> {
  return await fetch(buildWorkspaceCreateUrl(ownerUserId), {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({
      title: workspaceTitle,
      description: `Workspace for ${playbookName}`,
      execution_mode: 'hybrid',
    }),
  });
}

export async function reindexPlaybooks(): Promise<Response> {
  return await fetchWithAbort(buildReindexUrl(), { method: 'POST' });
}

export async function togglePinnedPlaybook(
  workspaceId: string,
  playbookCode: string,
  isPinned: boolean
): Promise<Response> {
  const method = isPinned ? 'DELETE' : 'POST';
  return await fetch(buildPinnedPlaybookUrl(workspaceId, playbookCode, isPinned), {
    method,
    headers: jsonHeaders,
    body: method === 'POST' ? JSON.stringify({ playbook_code: playbookCode }) : undefined,
  });
}
