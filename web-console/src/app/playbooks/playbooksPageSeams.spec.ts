import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  PLAYBOOKS_REQUEST_TIMEOUT_MS,
  buildFavoriteMetaUrl,
  buildPinnedPlaybookUrl,
  buildPlaybooksListUrl,
  buildReindexUrl,
  buildSupportedTestsUrl,
  buildWorkspaceCreateUrl,
  targetLanguageForLocale,
} from './playbooksPageApi';
import {
  buildWorkspaceTitle,
  extractCapabilityCode,
  filterPlaybooksBySearch,
  getAvailableCapabilityCodes,
  groupPlaybooksByCapability,
  normalizePlaybookList,
} from './playbooksPageTransforms';
import type { Playbook } from './playbooksPageTypes';

const routeDir = dirname(fileURLToPath(import.meta.url));
const touchedFiles = [
  'page.tsx',
  'playbooksPageTypes.ts',
  'playbooksPageApi.ts',
  'playbooksPageTransforms.ts',
  'PlaybooksPageView.tsx',
  'playbooksPageSeams.spec.ts',
];
const implementationFiles = touchedFiles.filter((fileName) => fileName !== 'playbooksPageSeams.spec.ts');

function readRouteFile(fileName: string): string {
  return readFileSync(join(routeDir, fileName), 'utf8');
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
    return [relative(routeDir, absolutePath)];
  });
}

function makePlaybook(overrides: Partial<Playbook>): Playbook {
  return {
    playbook_code: 'system.default',
    version: '1',
    locale: 'zh-TW',
    name: 'Default',
    description: 'Default description',
    tags: [],
    required_tools: [],
    user_meta: { favorite: false, use_count: 0 },
    ...overrides,
  };
}

describe('playbooks page seams', () => {
  it('maps supported locales and falls back to zh-TW', () => {
    expect(targetLanguageForLocale('en')).toBe('en');
    expect(targetLanguageForLocale('ja')).toBe('ja');
    expect(targetLanguageForLocale('zh-TW')).toBe('zh-TW');
    expect(targetLanguageForLocale('fr')).toBe('zh-TW');
  });

  it('builds existing endpoint shapes', () => {
    expect(buildSupportedTestsUrl('')).toBe('/api/v1/playbooks/smoke-test/supported');
    expect(buildPlaybooksListUrl({
      locale: 'ja',
      selectedTags: ['alpha', 'beta'],
      selectedWorkspaceId: 'workspace-1',
      filter: 'favorites',
    }, 'profile-a', '')).toBe(
      '/api/v1/playbooks?tags=alpha%2Cbeta&target_language=ja&profile_id=profile-a&workspace_id=workspace-1&filter=favorites'
    );
    expect(buildFavoriteMetaUrl('book-1', true, 'profile-a', '')).toBe(
      '/api/v1/playbooks/book-1/meta?profile_id=profile-a&favorite=true'
    );
    expect(buildWorkspaceCreateUrl('profile-a', '')).toBe('/api/v1/workspaces?owner_user_id=profile-a');
    expect(buildReindexUrl('')).toBe('/api/v1/playbooks/reindex');
    expect(buildPinnedPlaybookUrl('workspace-1', 'book-1', false, '')).toBe(
      '/api/v1/workspaces/workspace-1/pinned-playbooks'
    );
    expect(buildPinnedPlaybookUrl('workspace-1', 'book-1', true, '')).toBe(
      '/api/v1/workspaces/workspace-1/pinned-playbooks/book-1'
    );
    expect(PLAYBOOKS_REQUEST_TIMEOUT_MS).toBe(30000);
  });

  it('preserves workspace title timestamp shape', () => {
    expect(buildWorkspaceTitle('demo.book', new Date(2026, 5, 21, 9, 8, 7))).toBe('demo.book_20260621_090807');
  });

  it('preserves filtering, normalization, and capability grouping', () => {
    const playbooks = normalizePlaybookList([
      makePlaybook({ playbook_code: 'frontier_research.intent_sync', name: 'Intent Sync', description: 'Research flow' }),
      makePlaybook({ playbook_code: 'plain', name: 'Plain', description: 'Other', capability_code: 'custom_capability' }),
      { playbook_code: '', name: 'Invalid' },
    ]);
    const filtered = filterPlaybooksBySearch(playbooks, 'research');
    const grouped = groupPlaybooksByCapability(playbooks);

    expect(playbooks).toHaveLength(2);
    expect(filtered.map((playbook) => playbook.playbook_code)).toEqual(['frontier_research.intent_sync']);
    expect(extractCapabilityCode(playbooks[0])).toBe('frontier_research');
    expect(grouped.frontier_research).toHaveLength(1);
    expect(grouped.custom_capability).toHaveLength(1);
    expect(getAvailableCapabilityCodes(grouped)).toEqual(['frontier_research', 'custom_capability']);
  });

  it('keeps touched route files below the line gate', () => {
    for (const fileName of touchedFiles) {
      const lineCount = readRouteFile(fileName).split(/\r?\n/).length;
      expect(lineCount, fileName).toBeLessThanOrEqual(500);
    }
  });

  it('does not add polling', () => {
    for (const fileName of implementationFiles) {
      expect(readRouteFile(fileName), fileName).not.toContain('setInterval(');
    }
  });

  it('keeps the view resource passive', () => {
    const source = readRouteFile('PlaybooksPageView.tsx');
    expect(source).not.toMatch(/\bfetch\s*\(/);
    expect(source).not.toContain('AbortController');
    expect(source).not.toContain('setTimeout(');
    expect(source).not.toContain('localStorage');
    expect(source).not.toContain('/api/v1/');
  });

  it('keeps playbooks route inventory single-owned', () => {
    const pageFiles = listFiles(routeDir)
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
