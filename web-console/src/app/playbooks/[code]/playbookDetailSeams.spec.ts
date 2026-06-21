import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  PLAYBOOK_DETAIL_TIMEOUT_MS,
  buildOnboardingWebhookUrl,
  buildPlaybookDetailUrl,
  buildPlaybookListUrl,
  buildSuggestionVariantUrl,
  buildWorkspaceCreateUrl,
  targetLanguageForLocale,
} from './playbookDetailApi';
import {
  RECENT_PLAYBOOKS_DISPLAY_LIMIT,
  RECENT_PLAYBOOKS_STORAGE_LIMIT,
  selectRecentPlaybooks,
  upsertRecentPlaybookView,
} from './recentPlaybooks';
import type { RecentPlaybookView } from './playbookDetailTypes';

const routeDir = dirname(fileURLToPath(import.meta.url));
const playbooksDir = join(routeDir, '..');
const touchedFiles = [
  'page.tsx',
  'playbookDetailTypes.ts',
  'playbookDetailApi.ts',
  'recentPlaybooks.ts',
  'PlaybookDetailView.tsx',
  'PlaybookDetailModals.tsx',
  'playbookDetailSeams.spec.ts',
];

function readRouteFile(fileName: string): string {
  return readFileSync(join(routeDir, fileName), 'utf8');
}

function countOccurrences(source: string, pattern: string): number {
  return source.split(pattern).length - 1;
}

function listFiles(dir: string, depth = 0): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const absolutePath = join(dir, entry);
    const stats = statSync(absolutePath);
    if (stats.isDirectory() && depth < 2) {
      return listFiles(absolutePath, depth + 1);
    }
    if (!stats.isFile()) {
      return [];
    }
    return [relative(playbooksDir, absolutePath)];
  });
}

describe('playbook detail route seams', () => {
  it('maps supported locales and falls back to zh-TW', () => {
    expect(targetLanguageForLocale('en')).toBe('en');
    expect(targetLanguageForLocale('ja')).toBe('ja');
    expect(targetLanguageForLocale('zh-TW')).toBe('zh-TW');
    expect(targetLanguageForLocale('fr')).toBe('zh-TW');
  });

  it('builds existing endpoint shapes', () => {
    expect(buildPlaybookListUrl('en', 'profile-a', '')).toBe(
      '/api/v1/playbooks?target_language=en&profile_id=profile-a'
    );
    expect(buildPlaybookDetailUrl('demo-book', 'ja', 'profile-a', '')).toBe(
      '/api/v1/playbooks/demo-book?profile_id=profile-a&target_language=ja'
    );
    expect(buildSuggestionVariantUrl('demo-book', 'profile-a', '')).toBe(
      '/api/v1/playbooks/demo-book/variants/from-suggestions?profile_id=profile-a'
    );
    expect(buildWorkspaceCreateUrl('profile-a', '')).toBe('/api/v1/workspaces?owner_user_id=profile-a');
    expect(buildOnboardingWebhookUrl('exec-1', 'demo-book', 'profile-a', '')).toBe(
      '/api/v1/mindscape/playbook/webhook?execution_id=exec-1&playbook_code=demo-book&profile_id=profile-a'
    );
    expect(PLAYBOOK_DETAIL_TIMEOUT_MS).toBe(30000);
  });

  it('keeps recent playbook storage and display limits', () => {
    const existing: RecentPlaybookView[] = Array.from({ length: 12 }, (_, index) => ({
      playbook_code: `book-${index}`,
      name: `Book ${index}`,
      description: `Description ${index}`,
      viewed_at: `2026-06-21T00:00:${String(index).padStart(2, '0')}Z`,
    }));

    const stored = upsertRecentPlaybookView(existing, 'book-3', {
      name: 'Book 3',
      description: 'Updated',
    }, '2026-06-21T01:00:00Z');
    const displayed = selectRecentPlaybooks(stored, 'book-3');

    expect(stored).toHaveLength(RECENT_PLAYBOOKS_STORAGE_LIMIT);
    expect(stored[0]).toMatchObject({ playbook_code: 'book-3', description: 'Updated' });
    expect(displayed).toHaveLength(RECENT_PLAYBOOKS_DISPLAY_LIMIT);
    expect(displayed.map((item) => item.playbook_code)).not.toContain('book-3');
  });

  it('keeps touched route files below the line gate', () => {
    for (const fileName of touchedFiles) {
      const lineCount = readRouteFile(fileName).split(/\r?\n/).length;
      expect(lineCount, fileName).toBeLessThanOrEqual(500);
    }
  });

  it('keeps polling single-owned by the route shell', () => {
    const pageSource = readRouteFile('page.tsx');
    expect(countOccurrences(pageSource, 'setInterval(')).toBe(1);
    expect(pageSource).toContain('5000');

    for (const fileName of ['PlaybookDetailView.tsx', 'PlaybookDetailModals.tsx', 'playbookDetailApi.ts', 'recentPlaybooks.ts']) {
      const source = readRouteFile(fileName);
      expect(source, fileName).not.toContain('setInterval(');
    }
  });

  it('keeps view and modal seams resource passive', () => {
    for (const fileName of ['PlaybookDetailView.tsx', 'PlaybookDetailModals.tsx']) {
      const source = readRouteFile(fileName);
      expect(source, fileName).not.toMatch(/\bfetch\s*\(/);
      expect(source, fileName).not.toContain('AbortController');
      expect(source, fileName).not.toContain('localStorage');
    }
  });

  it('keeps the playbook detail route as the only detail route', () => {
    const pageFiles = listFiles(playbooksDir)
      .filter((fileName) => fileName.endsWith('page.tsx'))
      .sort();
    expect(pageFiles).toEqual(['[code]/page.tsx', 'page.tsx']);
  });

  it('keeps touched source files ascii only', () => {
    for (const fileName of touchedFiles) {
      expect(readRouteFile(fileName), fileName).not.toMatch(/[^\x00-\x7F]/);
    }
  });
});
