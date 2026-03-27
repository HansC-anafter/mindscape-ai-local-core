import { describe, expect, it } from 'vitest';

import {
  appendWorkspaceTitleToPath,
  extractUsername,
  getCommonDirectories,
  getFilteredCommonDirectories,
  sanitizeWorkspaceTitle,
} from './pathUtils';

describe('localFilesystemManager path utils', () => {
  it('extracts usernames from macOS and Windows paths', () => {
    expect(extractUsername('/Users/demo/Documents/workspace')).toBe('demo');
    expect(extractUsername('C:\\Users\\demo\\Documents\\workspace')).toBe('demo');
    expect(extractUsername('/tmp/workspace')).toBeNull();
  });

  it('sanitizes workspace titles and appends them once', () => {
    expect(sanitizeWorkspaceTitle('My Workspace: Alpha')).toBe('My-Workspace-Alpha');
    expect(
      appendWorkspaceTitleToPath({
        currentPath: '/Users/demo/Documents',
        isWindows: false,
        workspaceTitle: 'My Workspace: Alpha',
      })
    ).toBe('/Users/demo/Documents/My-Workspace-Alpha');
    expect(
      appendWorkspaceTitleToPath({
        currentPath: '/Users/demo/Documents/My-Workspace-Alpha',
        isWindows: false,
        workspaceTitle: 'My Workspace: Alpha',
      })
    ).toBe('/Users/demo/Documents/My-Workspace-Alpha');
  });

  it('filters workspace quick-select directories from the active username', () => {
    const commonDirectories = getCommonDirectories();
    const workspaceResult = getFilteredCommonDirectories({
      actualUsername: 'demo',
      commonDirectories,
      isWindows: false,
      workspaceMode: true,
    });
    const standardResult = getFilteredCommonDirectories({
      actualUsername: null,
      commonDirectories,
      isWindows: false,
      workspaceMode: false,
    });

    expect(workspaceResult.map((directory) => directory.path)).toEqual([
      '/Users/demo/Documents',
      '/Users/demo/Downloads',
      '/Users/demo/Desktop',
      '/Users/demo',
    ]);
    expect(standardResult.some((directory) => directory.path === '~/Documents')).toBe(true);
  });
});
