import { describe, expect, it } from 'vitest';

import {
  appendWorkspaceTitleToPath,
  deriveWorkspaceDirectoryPickerPath,
  deriveWorkspaceFileInputDefaultPath,
  extractUsername,
  getCommonDirectories,
  getFilteredCommonDirectories,
  getDirectoryPrompt,
  isAbsoluteStoragePath,
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

  it('derives workspace picker paths from current and fallback paths', () => {
    expect(
      deriveWorkspaceDirectoryPickerPath({
        currentPath: '/Users/demo/Documents/old-project',
        dirName: 'new-project',
        isWindows: false,
      })
    ).toEqual({
      actualPath: '/Users/demo/Documents/new-project',
      defaultPath: '/Users/demo/Documents/new-project',
    });
    expect(
      deriveWorkspaceDirectoryPickerPath({
        dirName: 'new-project',
        isWindows: false,
      })
    ).toEqual({
      defaultPath: '/Users/new-project',
    });
  });

  it('derives file-input defaults and directory prompts without resource calls', () => {
    expect(
      deriveWorkspaceFileInputDefaultPath({
        dirName: 'project-root',
        initialStorageBasePath: '/Users/demo/Documents/current',
        isWindows: false,
      })
    ).toBe('/Users/demo/project-root');
    expect(
      deriveWorkspaceFileInputDefaultPath({
        dirName: 'project-root',
        initialStorageBasePath: 'C:\\Users\\demo\\Documents\\current',
        isWindows: true,
      })
    ).toBe('C:\\Users\\demo\\project-root');
    expect(getDirectoryPrompt('docs').defaultPath).toBe('~/Documents/docs');
    expect(isAbsoluteStoragePath('/Users/demo')).toBe(true);
    expect(isAbsoluteStoragePath('C:\\Users\\demo')).toBe(true);
    expect(isAbsoluteStoragePath('relative/path')).toBe(false);
  });
});
