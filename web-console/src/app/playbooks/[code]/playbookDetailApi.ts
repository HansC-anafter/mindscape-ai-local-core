import { getApiBaseUrl } from '../../../lib/api-url';
import type { OptimizationSuggestion, Playbook, PlaybookListItem } from './playbookDetailTypes';

export const API_URL = getApiBaseUrl();
export const DEFAULT_PROFILE_ID = 'default-user';
export const PLAYBOOK_DETAIL_TIMEOUT_MS = 30000;

const jsonHeaders = { 'Content-Type': 'application/json' };

export function resolveApiBaseUrl(apiBaseUrl = API_URL): string {
  return apiBaseUrl.startsWith('http') ? apiBaseUrl : '';
}

export function targetLanguageForLocale(locale: string): string {
  return locale === 'en' ? 'en' : locale === 'ja' ? 'ja' : 'zh-TW';
}

export function buildPlaybookListUrl(
  locale: string,
  profileId = DEFAULT_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  const targetLanguage = targetLanguageForLocale(locale);
  return `${apiUrl}/api/v1/playbooks?target_language=${targetLanguage}&profile_id=${profileId}`;
}

export function buildPlaybookDetailUrl(
  playbookCode: string,
  locale: string,
  profileId = DEFAULT_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  const targetLanguage = targetLanguageForLocale(locale);
  return `${apiUrl}/api/v1/playbooks/${playbookCode}?profile_id=${profileId}&target_language=${targetLanguage}`;
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

export function buildNotesMetaUrl(
  playbookCode: string,
  notes: string,
  profileId = DEFAULT_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/playbooks/${playbookCode}/meta?profile_id=${profileId}&user_notes=${encodeURIComponent(notes)}`;
}

export function buildPlaybookVariantsUrl(
  playbookCode: string,
  profileId = DEFAULT_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/playbooks/${playbookCode}/variants?profile_id=${profileId}`;
}

export function buildCopyVariantUrl(
  playbookCode: string,
  variantName: string,
  variantDescription: string,
  profileId = DEFAULT_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/playbooks/${playbookCode}/variants/copy?profile_id=${profileId}&variant_name=${encodeURIComponent(variantName)}&variant_description=${encodeURIComponent(variantDescription)}`;
}

export function buildOptimizeUrl(
  playbookCode: string,
  profileId = DEFAULT_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/playbooks/${playbookCode}/optimize?profile_id=${profileId}`;
}

export function buildSuggestionVariantUrl(
  playbookCode: string,
  profileId = DEFAULT_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/playbooks/${playbookCode}/variants/from-suggestions?profile_id=${profileId}`;
}

export function buildWorkspaceCreateUrl(
  profileId = DEFAULT_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/workspaces?owner_user_id=${profileId}`;
}

export function buildOnboardingWebhookUrl(
  executionId: string,
  playbookCode: string,
  profileId = DEFAULT_PROFILE_ID,
  apiBaseUrl = API_URL
): string {
  const apiUrl = resolveApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/mindscape/playbook/webhook?execution_id=${executionId}&playbook_code=${playbookCode}&profile_id=${profileId}`;
}

export async function fetchPlaybookList(locale: string): Promise<PlaybookListItem[] | null> {
  const response = await fetch(buildPlaybookListUrl(locale), { headers: jsonHeaders });
  if (!response.ok) {
    return null;
  }
  const data = await response.json();
  return data.map((playbook: any) => ({
    playbook_code: playbook.playbook_code,
    name: playbook.name,
    description: playbook.description || '',
    icon: playbook.icon,
    tags: playbook.tags || [],
    capability_code: playbook.capability_code,
  }));
}

export async function fetchPlaybookDetail(playbookCode: string, locale: string): Promise<Playbook> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), PLAYBOOK_DETAIL_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(buildPlaybookDetailUrl(playbookCode, locale), {
      headers: jsonHeaders,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    throw new Error(`Failed to load playbook: ${response.status} ${response.statusText}`);
  }

  return await response.json();
}

export async function fetchPlaybookStatus(playbookCode: string, locale: string): Promise<Playbook | null> {
  const response = await fetch(buildPlaybookDetailUrl(playbookCode, locale), { headers: jsonHeaders });
  if (!response.ok) {
    return null;
  }
  return await response.json();
}

export async function updatePlaybookFavorite(playbookCode: string, favorite: boolean): Promise<void> {
  await fetch(buildFavoriteMetaUrl(playbookCode, favorite), {
    method: 'PATCH',
    headers: jsonHeaders,
  });
}

export async function updatePlaybookNotes(playbookCode: string, notes: string): Promise<Response> {
  return await fetch(buildNotesMetaUrl(playbookCode, notes), {
    method: 'PATCH',
    headers: jsonHeaders,
  });
}

export async function fetchPlaybookVariants(playbookCode: string): Promise<{ status: number; variants: any[] }> {
  const response = await fetch(buildPlaybookVariantsUrl(playbookCode), { headers: jsonHeaders });
  if (!response.ok) {
    return { status: response.status, variants: [] };
  }
  return { status: response.status, variants: await response.json() };
}

export async function copySystemVersion(
  playbookCode: string,
  variantName: string,
  variantDescription: string
): Promise<any> {
  const response = await fetch(buildCopyVariantUrl(playbookCode, variantName, variantDescription), {
    method: 'POST',
    headers: jsonHeaders,
  });
  if (!response.ok) {
    throw new Error('Failed to create variant');
  }
  return await response.json();
}

export async function requestOptimizationSuggestions(playbookCode: string): Promise<OptimizationSuggestion[]> {
  const response = await fetch(buildOptimizeUrl(playbookCode), {
    method: 'POST',
    headers: jsonHeaders,
  });
  if (!response.ok) {
    throw new Error('Failed to get optimization suggestions');
  }
  const data = await response.json();
  return data.suggestions || [];
}

export async function createVariantFromSuggestion(
  playbookCode: string,
  suggestion: OptimizationSuggestion
): Promise<void> {
  const response = await fetch(buildSuggestionVariantUrl(playbookCode), {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({
      variant_name: `${suggestion.title} - ${new Date().toLocaleDateString()}`,
      selected_suggestions: [suggestion],
    }),
  });
  if (!response.ok) {
    throw new Error('Failed to create variant');
  }
}

export async function createPlaybookWorkspace(
  playbookCode: string,
  playbookName: string,
  targetLanguage: string,
  profileId = DEFAULT_PROFILE_ID
): Promise<any> {
  const response = await fetch(buildWorkspaceCreateUrl(profileId), {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({
      title: `${playbookName} Workspace`,
      description: `Workspace for executing ${playbookName}`,
      default_playbook_id: playbookCode,
      default_locale: targetLanguage,
      execution_mode: 'hybrid',
    }),
  });
  if (!response.ok) {
    throw new Error('Failed to create workspace');
  }
  return await response.json();
}

export async function sendOnboardingWebhook(
  executionId: string,
  playbookCode: string,
  structuredOutput: any,
  profileId = DEFAULT_PROFILE_ID
): Promise<Response> {
  return await fetch(buildOnboardingWebhookUrl(executionId, playbookCode, profileId), {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(structuredOutput),
  });
}
