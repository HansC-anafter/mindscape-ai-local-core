'use client';

import { useEffect, useState } from 'react';

import { t } from '@/lib/i18n';

import { appendWorkspaceTitleToPath } from './pathUtils';

interface EmptyPathInputWithWorkspaceNameProps {
  currentPath?: string;
  initialStorageBasePath?: string;
  isWindows: boolean;
  onPathChange: (path: string) => void;
  workspaceTitle?: string;
}

export function EmptyPathInputWithWorkspaceName({
  currentPath,
  initialStorageBasePath,
  isWindows,
  onPathChange,
  workspaceTitle,
}: EmptyPathInputWithWorkspaceNameProps) {
  const [inputValue, setInputValue] = useState(currentPath || '');

  useEffect(() => {
    if (currentPath !== undefined && currentPath !== inputValue && currentPath.trim() !== '') {
      setInputValue(currentPath);
    }
  }, [currentPath, inputValue]);

  const handleAppendWorkspaceName = (event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();

    const nextPath = appendWorkspaceTitleToPath({
      currentPath: inputValue,
      isWindows,
      workspaceTitle,
    });
    setInputValue(nextPath);
    onPathChange(nextPath);
  };

  return (
    <div className="flex items-center space-x-2 p-2 bg-gray-50 dark:bg-gray-800/50 rounded-md">
      <input
        type="text"
        value={inputValue}
        onChange={(event) => {
          const nextValue = event.target.value;
          setInputValue(nextValue);
          onPathChange(nextValue);
        }}
        className="flex-1 px-2 py-1 text-sm text-gray-700 dark:text-gray-300 font-mono border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-blue-400 focus:border-transparent placeholder-gray-400 dark:placeholder-gray-500"
        placeholder={
          initialStorageBasePath || (isWindows ? 'C:\\Users\\...\\Documents\\...' : '/Users/.../Documents/...')
        }
      />
      {workspaceTitle ? (
        <button
          type="button"
          onClick={handleAppendWorkspaceName}
          className="px-3 py-1 text-xs bg-green-100 text-green-700 border border-green-300 rounded hover:bg-green-200 transition-colors whitespace-nowrap"
          title={t('appendWorkspaceNameTooltip', { workspaceTitle: workspaceTitle || '' })}
        >
          {t('appendWorkspaceName' as any)}
        </button>
      ) : (
        <div className="text-xs text-red-500">No workspaceTitle!</div>
      )}
    </div>
  );
}
