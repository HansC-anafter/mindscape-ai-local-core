'use client';

import type { CommonDirectory } from './types';

export function getCommonDirectories(): CommonDirectory[] {
  return [
    { label: 'Documents', path: '~/Documents', platform: 'all' },
    { label: 'Downloads', path: '~/Downloads', platform: 'all' },
    { label: 'Desktop', path: '~/Desktop', platform: 'all' },
    { label: 'Pictures', path: '~/Pictures', platform: 'all' },
    { label: 'Music', path: '~/Music', platform: 'all' },
    { label: 'Videos', path: '~/Videos', platform: 'all' },
    { label: 'Documents (Win)', path: '%USERPROFILE%\\Documents', platform: 'windows' },
    { label: 'Downloads (Win)', path: '%USERPROFILE%\\Downloads', platform: 'windows' },
    { label: 'Data Directory', path: './data', platform: 'all' },
    { label: 'Data Documents', path: './data/documents', platform: 'all' },
  ];
}

export function extractUsername(path?: string): string | null {
  if (!path) {
    return null;
  }

  if (path.includes('\\')) {
    const winParts = path.split('\\');
    if (winParts.length >= 3 && winParts[0].match(/^[A-Za-z]:$/) && winParts[1] === 'Users') {
      return winParts[2];
    }
  } else {
    const pathParts = path.split('/');
    if (pathParts.length >= 3 && pathParts[0] === '' && pathParts[1] === 'Users') {
      return pathParts[2];
    }
  }

  return null;
}

export function getFilteredCommonDirectories({
  actualUsername,
  commonDirectories,
  isWindows,
  workspaceMode,
}: {
  actualUsername: string | null;
  commonDirectories: CommonDirectory[];
  isWindows: boolean;
  workspaceMode: boolean;
}): CommonDirectory[] {
  if (!workspaceMode) {
    return commonDirectories.filter(
      (directory) => directory.platform === 'all' || (directory.platform === 'windows' && isWindows)
    );
  }

  if (!actualUsername) {
    return [];
  }

  return isWindows
    ? [
        { label: 'Documents', path: `C:\\Users\\${actualUsername}\\Documents`, platform: 'windows' },
        { label: 'Downloads', path: `C:\\Users\\${actualUsername}\\Downloads`, platform: 'windows' },
        { label: 'Desktop', path: `C:\\Users\\${actualUsername}\\Desktop`, platform: 'windows' },
      ]
    : [
        { label: 'Documents', path: `/Users/${actualUsername}/Documents`, platform: 'all' },
        { label: 'Downloads', path: `/Users/${actualUsername}/Downloads`, platform: 'all' },
        { label: 'Desktop', path: `/Users/${actualUsername}/Desktop`, platform: 'all' },
        { label: 'Home', path: `/Users/${actualUsername}`, platform: 'all' },
      ];
}

export function sanitizeWorkspaceTitle(title: string): string {
  return title
    .replace(/[\/\\:*?"<>|\x00-\x1F\x7F]/g, '')
    .trim()
    .replace(/[-\s]+/g, '-');
}

export function appendWorkspaceTitleToPath({
  currentPath,
  isWindows,
  workspaceTitle,
}: {
  currentPath: string;
  isWindows: boolean;
  workspaceTitle?: string;
}): string {
  if (!workspaceTitle) {
    return currentPath;
  }

  const sanitized = sanitizeWorkspaceTitle(workspaceTitle);
  if (!sanitized) {
    return currentPath;
  }

  const trimmedPath = currentPath.trim();
  if (!trimmedPath) {
    return sanitized;
  }

  const separator = isWindows ? '\\' : '/';
  if (
    trimmedPath.endsWith(`${separator}${sanitized}`) ||
    trimmedPath.endsWith(`/${sanitized}`) ||
    trimmedPath.endsWith(`\\${sanitized}`)
  ) {
    return trimmedPath;
  }

  const pathEndsWithSeparator =
    trimmedPath.endsWith(separator) ||
    trimmedPath.endsWith('/') ||
    trimmedPath.endsWith('\\');

  return pathEndsWithSeparator
    ? `${trimmedPath}${sanitized}`
    : `${trimmedPath}${separator}${sanitized}`;
}
