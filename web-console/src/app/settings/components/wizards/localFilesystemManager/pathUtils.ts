'use client';

import type { CommonDirectory, DirectoryConfig } from './types';

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

export interface DirectoryActionResult {
  directories?: DirectoryConfig[];
  error?: string | null;
  newDirectory?: string;
  selectedCommonDirs?: Set<string>;
}

export function addDirectorySelection({
  directories,
  newDirectory,
  workspaceMode,
}: {
  directories: DirectoryConfig[];
  newDirectory: string;
  workspaceMode: boolean;
}): DirectoryActionResult {
  const trimmed = newDirectory.trim();
  if (!trimmed) {
    return {};
  }

  if (workspaceMode) {
    return {
      directories: [{ path: trimmed, allowWrite: false }],
      error: null,
      newDirectory: '',
    };
  }

  const existingPaths = directories.map((directory) => directory.path);
  if (existingPaths.includes(trimmed)) {
    return { error: 'Directory already added' };
  }

  return {
    directories: [...directories, { path: trimmed, allowWrite: false }],
    error: null,
    newDirectory: '',
  };
}

export function removeDirectorySelection({
  directories,
  index,
  selectedCommonDirs,
}: {
  directories: DirectoryConfig[];
  index: number;
  selectedCommonDirs: Set<string>;
}): DirectoryActionResult {
  const removed = directories[index];
  const result: DirectoryActionResult = {
    directories: directories.filter((_, directoryIndex) => directoryIndex !== index),
  };

  if (removed && selectedCommonDirs.has(removed.path)) {
    const nextSelected = new Set(selectedCommonDirs);
    nextSelected.delete(removed.path);
    result.selectedCommonDirs = nextSelected;
  }

  return result;
}

export function toggleCommonDirectorySelection({
  directories,
  path,
  selectedCommonDirs,
  workspaceMode,
}: {
  directories: DirectoryConfig[];
  path: string;
  selectedCommonDirs: Set<string>;
  workspaceMode: boolean;
}): DirectoryActionResult {
  if (workspaceMode) {
    return {
      directories: [{ path, allowWrite: false }],
      selectedCommonDirs: new Set([path]),
    };
  }

  const existingPaths = directories.map((directory) => directory.path);
  const nextSelected = new Set(selectedCommonDirs);
  if (nextSelected.has(path)) {
    nextSelected.delete(path);
    return {
      directories: directories.filter((directory) => directory.path !== path),
      selectedCommonDirs: nextSelected,
    };
  }

  nextSelected.add(path);
  return {
    directories: existingPaths.includes(path)
      ? directories
      : [...directories, { path, allowWrite: false }],
    selectedCommonDirs: nextSelected,
  };
}

export function isAbsoluteStoragePath(path: string): boolean {
  return path.startsWith('/') || !!path.match(/^[A-Za-z]:/);
}

export function getDirectoryPrompt(dirName: string): { defaultPath: string; promptMessage: string } {
  return {
    defaultPath: `~/Documents/${dirName}`,
    promptMessage: `Selected directory: "${dirName}"\n\nPlease enter the full directory path:\n(e.g., ~/Documents/${dirName} or C:\\Users\\...\\Documents\\${dirName})`,
  };
}

export function deriveWorkspaceDirectoryPickerPath({
  currentPath,
  dirName,
  initialStorageBasePath,
  isWindows,
  selectedPath,
}: {
  currentPath?: string;
  dirName: string;
  initialStorageBasePath?: string;
  isWindows: boolean;
  selectedPath?: string;
}): { actualPath?: string; defaultPath: string } {
  if (selectedPath) {
    return {
      actualPath: selectedPath,
      defaultPath: selectedPath,
    };
  }

  const currentPathActual = deriveActualPathFromCurrentPath({
    currentPath: currentPath?.trim() || '',
    dirName,
    isWindows,
  });
  const initialPathActual = derivePathFromInitialStorageBasePath({
    dirName,
    initialStorageBasePath,
  });
  const actualPath = currentPathActual || initialPathActual;
  if (actualPath) {
    return {
      actualPath,
      defaultPath: actualPath,
    };
  }

  return {
    defaultPath:
      deriveDefaultPathFromCurrentPath({
        currentPath: currentPath?.trim() || '',
        dirName,
        isWindows,
      }) ||
      derivePathFromInitialStorageBasePath({
        dirName,
        initialStorageBasePath,
      }) ||
      getDefaultUserPath({ dirName, isWindows }),
  };
}

export function deriveWorkspaceFileInputDefaultPath({
  dirName,
  initialStorageBasePath,
  isWindows,
}: {
  dirName: string;
  initialStorageBasePath?: string;
  isWindows: boolean;
}): string {
  if (initialStorageBasePath) {
    const pathParts = initialStorageBasePath.split('/');
    if (pathParts.length >= 3 && pathParts[0] === '' && pathParts[1] === 'Users') {
      return `${pathParts.slice(0, 3).join('/')}/${dirName}`;
    }

    if (initialStorageBasePath.includes('\\')) {
      const winParts = initialStorageBasePath.split('\\');
      if (winParts.length >= 3 && winParts[0].match(/^[A-Za-z]:$/) && winParts[1] === 'Users') {
        return `${winParts.slice(0, 3).join('\\')}\\${dirName}`;
      }
    }
  }

  return getDefaultUserPath({ dirName, isWindows });
}

function deriveActualPathFromCurrentPath({
  currentPath,
  dirName,
  isWindows,
}: {
  currentPath: string;
  dirName: string;
  isWindows: boolean;
}): string {
  if (!currentPath) {
    return '';
  }

  const separator = isWindows ? '\\' : '/';
  if (currentPath.endsWith(separator) || currentPath.endsWith('/') || currentPath.endsWith('\\')) {
    return `${currentPath}${dirName}`;
  }

  if (currentPath.includes(separator) || currentPath.includes('/') || currentPath.includes('\\')) {
    const pathParts = currentPath.split(/[/\\]/).filter((part) => part);
    pathParts[pathParts.length - 1] = dirName;
    return `${isWindows ? 'C:' : ''}${separator}${pathParts.join(separator)}`;
  }

  return `${currentPath}${separator}${dirName}`;
}

function deriveDefaultPathFromCurrentPath({
  currentPath,
  dirName,
  isWindows,
}: {
  currentPath: string;
  dirName: string;
  isWindows: boolean;
}): string {
  if (!currentPath) {
    return '';
  }

  const separator = isWindows ? '\\' : '/';
  return currentPath.endsWith(separator) || currentPath.endsWith('/') || currentPath.endsWith('\\')
    ? `${currentPath}${dirName}`
    : `${currentPath}${separator}${dirName}`;
}

function derivePathFromInitialStorageBasePath({
  dirName,
  initialStorageBasePath,
}: {
  dirName: string;
  initialStorageBasePath?: string;
}): string {
  const basePath = initialStorageBasePath?.trim();
  if (!basePath) {
    return '';
  }

  if (basePath.includes('\\')) {
    const winParts = basePath.split('\\');
    const parentPath = winParts.slice(0, -1).join('\\');
    return parentPath ? `${parentPath}\\${dirName}` : '';
  }

  const pathParts = basePath.split('/');
  const parentPath = pathParts.slice(0, -1).join('/') || '/';
  return `${parentPath}/${dirName}`;
}

function getDefaultUserPath({ dirName, isWindows }: { dirName: string; isWindows: boolean }): string {
  return isWindows ? `C:\\Users\\${dirName}` : `/Users/${dirName}`;
}
