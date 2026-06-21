import type {
  CurrentMode,
  FirstWorkspaceResult,
  MindscapeIntentPayload,
  MindscapeProfile,
  MindscapeSuggestion,
  MindscapeWorkspaceSummary,
  OnboardingStatusResponse,
  SelfIntroPayload,
  SuggestionReviewAction,
} from './mindscapePageTypes';

const JSON_HEADERS = { 'Content-Type': 'application/json' };

interface RawCurrentMode {
  main_mode?: string;
  weekly_focus?: string[];
  ai_assistants?: string[];
}

interface RawSuggestion {
  id: string;
  suggestion_type: MindscapeSuggestion['type'];
  title: string;
  description: string;
  source_summary?: string;
  confidence?: number;
}

interface PendingSuggestionsResponse {
  suggestions: RawSuggestion[];
}

export const DAILY_PLANNING_INTENT_PAYLOAD: MindscapeIntentPayload = {
  title: '今日工作規劃',
  description: '今天的行程與優先順序',
  tags: ['work', 'planning'],
  status: 'active',
  priority: 'medium',
};

export function buildContentDraftingIntentPayload(contentType: string): MindscapeIntentPayload {
  return {
    title: `撰寫：${contentType}`,
    description: `創作 ${contentType} 的內容`,
    tags: ['content', 'writing'],
    status: 'active',
    priority: 'medium',
  };
}

export function buildOnboardingStatusUrl(apiUrl: string, profileId: string): string {
  return `${apiUrl}/api/v1/mindscape/onboarding/status?user_id=${profileId}`;
}

export function buildMindscapeProfileUrl(apiUrl: string, profileId: string): string {
  return `${apiUrl}/api/v1/mindscape/profiles/${profileId}`;
}

export function buildMindscapeIntentsUrl(apiUrl: string, profileId: string): string {
  return `${apiUrl}/api/v1/mindscape/profiles/${profileId}/intents`;
}

export function buildCurrentModeUrl(apiUrl: string, profileId: string): string {
  return `${apiUrl}/api/v1/mindscape/profiles/${profileId}/current-mode`;
}

export function buildPendingSuggestionsUrl(apiUrl: string, profileId: string): string {
  return `${apiUrl}/api/v1/mindscape/suggestions?profile_id=${profileId}&status=pending`;
}

export function buildSelfIntroUrl(apiUrl: string, profileId: string): string {
  return `${apiUrl}/api/v1/mindscape/onboarding/self-intro?profile_id=${profileId}`;
}

export function buildSuggestionReviewUrl(
  apiUrl: string,
  suggestionId: string,
  action: SuggestionReviewAction
): string {
  return `${apiUrl}/api/v1/mindscape/suggestions/${suggestionId}/review?action=${action}`;
}

export function buildWorkspacesSummaryUrl(apiUrl: string, profileId: string): string {
  return `${apiUrl}/api/v1/workspaces/summary?owner_user_id=${profileId}&limit=1`;
}

export async function fetchOnboardingStatus(
  apiUrl: string,
  profileId: string
): Promise<OnboardingStatusResponse | null> {
  const response = await fetch(buildOnboardingStatusUrl(apiUrl, profileId));
  if (response.ok) {
    return response.json();
  }
  return null;
}

export async function fetchMindscapeProfile(
  apiUrl: string,
  profileId: string
): Promise<MindscapeProfile | null> {
  const response = await fetch(buildMindscapeProfileUrl(apiUrl, profileId));
  if (response.ok) {
    return response.json();
  }
  return null;
}

export async function fetchMindscapeIntents(apiUrl: string, profileId: string) {
  const response = await fetch(buildMindscapeIntentsUrl(apiUrl, profileId));
  if (response.ok) {
    return response.json();
  }
  return null;
}

export async function fetchCurrentMode(apiUrl: string, profileId: string): Promise<CurrentMode | null> {
  const response = await fetch(buildCurrentModeUrl(apiUrl, profileId));
  if (!response.ok) {
    return null;
  }
  const modeData = (await response.json()) as RawCurrentMode;
  return {
    mainMode: modeData.main_mode || '未設定',
    weeklyFocus: modeData.weekly_focus || [],
    aiAssistants: modeData.ai_assistants || [],
  };
}

export async function fetchPendingSuggestions(
  apiUrl: string,
  profileId: string
): Promise<MindscapeSuggestion[] | null> {
  const response = await fetch(buildPendingSuggestionsUrl(apiUrl, profileId));
  if (!response.ok) {
    return null;
  }
  const suggestionsData = (await response.json()) as PendingSuggestionsResponse;
  return suggestionsData.suggestions.map((suggestion) => ({
    id: suggestion.id,
    type: suggestion.suggestion_type,
    title: suggestion.title,
    description: suggestion.description,
    source: suggestion.source_summary || '最近使用記錄',
    confidence: suggestion.confidence || 0.5,
  }));
}

export async function completeSelfIntro(
  apiUrl: string,
  profileId: string,
  data: SelfIntroPayload
): Promise<void> {
  const response = await fetch(buildSelfIntroUrl(apiUrl, profileId), {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error('Failed to complete self intro');
  }
}

export async function reviewSuggestion(
  apiUrl: string,
  suggestionId: string,
  action: SuggestionReviewAction
): Promise<void> {
  const response = await fetch(buildSuggestionReviewUrl(apiUrl, suggestionId, action), {
    method: 'POST',
    headers: JSON_HEADERS,
  });

  if (!response.ok) {
    throw new Error(action === 'accept' ? 'Failed to accept suggestion' : 'Failed to dismiss suggestion');
  }
}

export async function fetchFirstWorkspace(apiUrl: string, profileId: string): Promise<FirstWorkspaceResult> {
  const response = await fetch(buildWorkspacesSummaryUrl(apiUrl, profileId));
  if (!response.ok) {
    return { ok: false, workspaceId: null };
  }
  const workspaces = (await response.json()) as MindscapeWorkspaceSummary[];
  return {
    ok: true,
    workspaceId: workspaces.length > 0 ? workspaces[0].id : null,
  };
}

export async function createMindscapeIntent(
  apiUrl: string,
  profileId: string,
  payload: MindscapeIntentPayload
): Promise<boolean> {
  const response = await fetch(buildMindscapeIntentsUrl(apiUrl, profileId), {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
  return response.ok;
}
