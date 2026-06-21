import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  DAILY_PLANNING_INTENT_PAYLOAD,
  buildContentDraftingIntentPayload,
  buildCurrentModeUrl,
  buildMindscapeIntentsUrl,
  buildMindscapeProfileUrl,
  buildOnboardingStatusUrl,
  buildPendingSuggestionsUrl,
  buildSelfIntroUrl,
  buildSuggestionReviewUrl,
  buildWorkspacesSummaryUrl,
  completeSelfIntro,
  createMindscapeIntent,
  fetchFirstWorkspace,
  reviewSuggestion,
} from './mindscapePageApi';

const routeDir = dirname(fileURLToPath(import.meta.url));
const touchedFiles = [
  'page.tsx',
  'mindscapePageTypes.ts',
  'mindscapePageApi.ts',
  'MindscapeEpisodePanel.tsx',
  'MindscapeOnboardingTasks.tsx',
  'MindscapeOverviewPanels.tsx',
  'mindscapePageSeams.spec.ts',
];
const passiveViewFiles = [
  'MindscapeEpisodePanel.tsx',
  'MindscapeOnboardingTasks.tsx',
  'MindscapeOverviewPanels.tsx',
];

function readRouteFile(fileName: string): string {
  return readFileSync(join(routeDir, fileName), 'utf8');
}

function jsonResponse(data: unknown, ok = true) {
  return Promise.resolve({
    ok,
    json: () => Promise.resolve(data),
  } as Response);
}

describe('mindscape page route seams', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds the existing Mindscape endpoint shapes', () => {
    expect(buildOnboardingStatusUrl('', 'default-user')).toBe(
      '/api/v1/mindscape/onboarding/status?user_id=default-user'
    );
    expect(buildMindscapeProfileUrl('http://api.test', 'profile-a')).toBe(
      'http://api.test/api/v1/mindscape/profiles/profile-a'
    );
    expect(buildMindscapeIntentsUrl('', 'profile-a')).toBe('/api/v1/mindscape/profiles/profile-a/intents');
    expect(buildCurrentModeUrl('', 'profile-a')).toBe('/api/v1/mindscape/profiles/profile-a/current-mode');
    expect(buildPendingSuggestionsUrl('', 'profile-a')).toBe(
      '/api/v1/mindscape/suggestions?profile_id=profile-a&status=pending'
    );
    expect(buildSelfIntroUrl('', 'profile-a')).toBe(
      '/api/v1/mindscape/onboarding/self-intro?profile_id=profile-a'
    );
    expect(buildSuggestionReviewUrl('', 'suggestion-a', 'accept')).toBe(
      '/api/v1/mindscape/suggestions/suggestion-a/review?action=accept'
    );
    expect(buildWorkspacesSummaryUrl('', 'profile-a')).toBe(
      '/api/v1/workspaces/summary?owner_user_id=profile-a&limit=1'
    );
  });

  it('preserves self-intro and suggestion review request payloads', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await completeSelfIntro('http://api.test', 'profile-a', {
      identity: 'founder',
      solving: 'launch',
      thinking: 'positioning',
    });
    await reviewSuggestion('http://api.test', 'suggestion-a', 'dismiss');

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://api.test/api/v1/mindscape/onboarding/self-intro?profile_id=profile-a',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          identity: 'founder',
          solving: 'launch',
          thinking: 'positioning',
        }),
      }
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://api.test/api/v1/mindscape/suggestions/suggestion-a/review?action=dismiss',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }
    );
  });

  it('preserves entry-intent payloads and first-workspace lookup behavior', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => jsonResponse([{ id: 'workspace-a' }]))
      .mockImplementationOnce(() => jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchFirstWorkspace('', 'profile-a')).resolves.toEqual({
      ok: true,
      workspaceId: 'workspace-a',
    });
    await expect(createMindscapeIntent('', 'profile-a', DAILY_PLANNING_INTENT_PAYLOAD)).resolves.toBe(true);

    expect(buildContentDraftingIntentPayload('IG 貼文')).toEqual({
      title: '撰寫：IG 貼文',
      description: '創作 IG 貼文 的內容',
      tags: ['content', 'writing'],
      status: 'active',
      priority: 'medium',
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/workspaces/summary?owner_user_id=profile-a&limit=1'
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/mindscape/profiles/profile-a/intents',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual(DAILY_PLANNING_INTENT_PAYLOAD);
  });

  it('keeps touched Mindscape route files below the line gate', () => {
    for (const fileName of touchedFiles) {
      const lineCount = readRouteFile(fileName).split(/\r?\n/).length;
      expect(lineCount, fileName).toBeLessThanOrEqual(500);
    }
  });

  it('keeps the route owner and passive views on a single resource path', () => {
    const pageSource = readRouteFile('page.tsx');
    const apiSource = readRouteFile('mindscapePageApi.ts');

    expect(pageSource).toContain('export default function MindscapePage');
    expect(pageSource).toContain('useEffect');
    expect(pageSource).toContain('HabitSuggestionToast');
    expect(pageSource).toContain('checkInterval={30000}');
    expect(pageSource).not.toMatch(/\bfetch\s*\(/);
    expect(apiSource).toMatch(/\bfetch\s*\(/);
    expect(apiSource).not.toContain('setInterval');
    expect(apiSource).not.toContain('setTimeout');
    expect(apiSource).not.toContain('WebSocket');
    expect(apiSource).not.toContain('EventSource');

    for (const fileName of passiveViewFiles) {
      const source = readRouteFile(fileName);
      expect(source, fileName).not.toMatch(/\bfetch\s*\(/);
      expect(source, fileName).not.toContain('/api/v1/');
      expect(source, fileName).not.toContain('setInterval');
      expect(source, fileName).not.toContain('setTimeout');
      expect(source, fileName).not.toContain('WebSocket');
      expect(source, fileName).not.toContain('EventSource');
      expect(source, fileName).not.toContain('localStorage');
      expect(source, fileName).not.toContain('sessionStorage');
      expect(source, fileName).not.toContain('router.push');
      expect(source, fileName).not.toContain('window.location');
      expect(source, fileName).not.toContain('prompt(');
      expect(source, fileName).not.toContain('alert(');
    }
  });

  it('removes the non-English code comment from the route owner', () => {
    expect(readRouteFile('page.tsx')).not.toContain('秒檢查');
  });
});
