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
    expect(extractUsername('/Users/shock/Documents/workspace')).toBe('shock');
    expect(extractUsername('C:\\Users\\shock\\Documents\\workspace')).toBe('shock');
    expect(extractUsername('/tmp/workspace')).toBeNull();
  });

  it('sanitizes workspace titles and appends them once', () => {
    expect(sanitizeWorkspaceTitle('My Workspace: Alpha')).toBe('My-Workspace-Alpha');
    expect(
      appendWorkspaceTitleToPath({
        currentPath: '/Users/shock/Documents',
        isWindows: false,
        workspaceTitle: 'My Workspace: Alpha',
      })
    ).toBe('/Users/shock/Documents/My-Workspace-Alpha');
    expect(
      appendWorkspaceTitleToPath({
        currentPath: '/Users/shock/Documents/My-Workspace-Alpha',
        isWindows: false,
        workspaceTitle: 'My Workspace: Alpha',
      })
    ).toBe('/Users/shock/Documents/My-Workspace-Alpha');
  });

  it('filters workspace quick-select directories from the active username', () => {
    const commonDirectories = getCommonDirectories();
    const workspaceResult = getFilteredCommonDirectories({
      actualUsername: 'shock',
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
      '/Users/shock/Documents',
      '/Users/shock/Downloads',
      '/Users/shock/Desktop',
      '/Users/shock',
    ]);
    expect(standardResult.some((directory) => directory.path === '~/Documents')).toBe(true);
  });
});
