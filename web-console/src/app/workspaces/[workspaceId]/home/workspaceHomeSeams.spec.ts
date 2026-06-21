import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  TEXT_SEED_LOCALE,
  buildLaunchpadUrl,
  buildTextSeedPayload,
  buildWorkspaceCreatePayload,
  buildWorkspaceCreateUrl,
  buildWorkspaceSeedUrl,
  createEmptyLaunchpadData,
} from './workspaceHomeApi';
import {
  canCompleteWorkspaceWizard,
  deriveWorkspaceHomeState,
  hasLaunchpadContent,
} from './workspaceHomeState';
import type { LaunchpadData } from './workspaceHomeTypes';

const routeDir = dirname(fileURLToPath(import.meta.url));
const touchedFiles = [
  'page.tsx',
  'workspaceHomeTypes.ts',
  'workspaceHomeApi.ts',
  'workspaceHomeState.ts',
  'WorkspaceHomeCreateView.tsx',
  'WorkspaceHomeLaunchpadView.tsx',
  'workspaceHomeSeams.spec.ts',
];
const implementationFiles = touchedFiles.filter((fileName) => fileName !== 'workspaceHomeSeams.spec.ts');
const viewFiles = ['WorkspaceHomeCreateView.tsx', 'WorkspaceHomeLaunchpadView.tsx'];

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

function launchpad(overrides: Partial<LaunchpadData>): LaunchpadData {
  return {
    brief: null,
    initial_intents: [],
    first_playbook: null,
    tool_connections: [],
    launch_status: 'pending',
    ...overrides,
  };
}

describe('workspace home seams', () => {
  it('builds existing endpoint shapes', () => {
    expect(buildLaunchpadUrl('workspace-1', '')).toBe('/api/v1/workspaces/workspace-1/launchpad');
    expect(buildWorkspaceCreateUrl('profile-a', '')).toBe('/api/v1/workspaces?owner_user_id=profile-a');
    expect(buildWorkspaceSeedUrl('workspace-1', '')).toBe('/api/v1/workspaces/workspace-1/seed');
  });

  it('preserves empty launchpad fallback', () => {
    expect(createEmptyLaunchpadData()).toEqual({
      brief: null,
      initial_intents: [],
      first_playbook: null,
      tool_connections: [],
      launch_status: 'pending',
    });
  });

  it('preserves workspace create and seed payloads', () => {
    expect(buildWorkspaceCreatePayload({ method: 'quick', title: 'Demo' })).toEqual({
      title: 'Demo',
      description: '',
      execution_mode: 'hybrid',
    });
    expect(buildTextSeedPayload('  seed text  ', false)).toEqual({
      seed_type: 'text',
      payload: '  seed text  ',
      locale: TEXT_SEED_LOCALE,
    });
    expect(buildTextSeedPayload('  seed text  ', true)).toEqual({
      seed_type: 'text',
      payload: 'seed text',
      locale: TEXT_SEED_LOCALE,
    });
  });

  it('preserves launchpad content and status derivation', () => {
    expect(hasLaunchpadContent(null)).toBe(false);
    expect(hasLaunchpadContent(launchpad({ brief: '  ' }))).toBe(false);
    expect(hasLaunchpadContent(launchpad({ brief: 'Brief' }))).toBe(true);
    expect(hasLaunchpadContent(launchpad({ initial_intents: [{ title: 'Next', description: '', priority: 'high' }] }))).toBe(true);

    expect(deriveWorkspaceHomeState(null, { launch_status: 'ready' })).toMatchObject({
      launchStatus: 'ready',
      hasActualContent: false,
      isPending: false,
      isReady: true,
      hasContent: false,
    });
    expect(deriveWorkspaceHomeState(launchpad({ brief: 'Brief' }), { launch_status: 'pending' })).toMatchObject({
      launchStatus: 'pending',
      hasActualContent: true,
      isPending: false,
      isReady: true,
      hasContent: true,
    });
  });

  it('preserves wizard completion rules', () => {
    expect(canCompleteWorkspaceWizard({})).toBe(false);
    expect(canCompleteWorkspaceWizard({ method: 'quick' })).toBe(false);
    expect(canCompleteWorkspaceWizard({ method: 'quick', title: 'Demo' })).toBe(true);
    expect(canCompleteWorkspaceWizard({ method: 'llm-guided', title: 'Demo' })).toBe(false);
    expect(canCompleteWorkspaceWizard({ method: 'llm-guided', title: 'Demo', description: 'Context' })).toBe(true);
  });

  it('keeps touched route files below the line gate', () => {
    for (const fileName of touchedFiles) {
      const lineCount = readRouteFile(fileName).split(/\r?\n/).length;
      expect(lineCount, fileName).toBeLessThanOrEqual(500);
    }
  });

  it('does not add polling or persistent browser resource paths', () => {
    for (const fileName of implementationFiles) {
      const source = readRouteFile(fileName);
      expect(source, fileName).not.toContain('setInterval(');
      expect(source, fileName).not.toContain('EventSource');
      expect(source, fileName).not.toContain('WebSocket');
      expect(source, fileName).not.toMatch(/\bpoll/i);
    }
  });

  it('keeps view files resource passive', () => {
    for (const fileName of viewFiles) {
      const source = readRouteFile(fileName);
      expect(source, fileName).not.toMatch(/\bfetch\s*\(/);
      expect(source, fileName).not.toContain('AbortController');
      expect(source, fileName).not.toContain('setTimeout(');
      expect(source, fileName).not.toContain('localStorage');
      expect(source, fileName).not.toContain('/api/v1/');
    }
  });

  it('keeps API ownership in the API helper', () => {
    const apiSource = readRouteFile('workspaceHomeApi.ts');
    expect(apiSource).toContain('fetch(');
    expect(apiSource).toContain('/api/v1/workspaces/${workspaceId}/launchpad');
    expect(apiSource).toContain('/api/v1/workspaces?owner_user_id=${ownerUserId}');
    expect(apiSource).toContain('/api/v1/workspaces/${workspaceId}/seed');

    for (const fileName of implementationFiles.filter((name) => name !== 'workspaceHomeApi.ts')) {
      const source = readRouteFile(fileName);
      expect(source, fileName).not.toMatch(/\bfetch\s*\(/);
      expect(source, fileName).not.toContain('/api/v1/');
    }
  });

  it('keeps workspace home route inventory single-owned', () => {
    const pageFiles = listFiles(routeDir)
      .filter((fileName) => fileName.endsWith('page.tsx'))
      .sort();
    expect(pageFiles).toEqual(['page.tsx']);
  });

  it('keeps touched source files ascii only', () => {
    for (const fileName of touchedFiles) {
      expect(readRouteFile(fileName), fileName).not.toMatch(/[^\x00-\x7F]/);
    }
  });
});
