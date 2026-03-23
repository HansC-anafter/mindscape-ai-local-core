'use client';

import { t } from '@/lib/i18n';

import { EmptyPathInputWithWorkspaceName } from './EmptyPathInputWithWorkspaceName';
import { appendWorkspaceTitleToPath } from './pathUtils';
import type { CommonDirectory, DirectoryConfig } from './types';

interface DirectorySelectionSectionProps {
  actualUsername: string | null;
  directories: DirectoryConfig[];
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  filteredCommonDirs: CommonDirectory[];
  handleAddDirectory: () => void;
  handleDirectoryPicker: () => void | Promise<void>;
  handleFileInputChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleRemoveDirectory: (index: number) => void;
  handleToggleCommonDirectory: (path: string) => void;
  initialStorageBasePath?: string;
  isWindows: boolean;
  newDirectory: string;
  savedStorageBasePath?: string;
  selectedCommonDirs: Set<string>;
  setDirectories: React.Dispatch<React.SetStateAction<DirectoryConfig[]>>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  setNewDirectory: React.Dispatch<React.SetStateAction<string>>;
  workspaceMode: boolean;
  workspaceTitle?: string;
}

export function DirectorySelectionSection({
  actualUsername,
  directories,
  fileInputRef,
  filteredCommonDirs,
  handleAddDirectory,
  handleDirectoryPicker,
  handleFileInputChange,
  handleRemoveDirectory,
  handleToggleCommonDirectory,
  initialStorageBasePath,
  isWindows,
  newDirectory,
  savedStorageBasePath,
  selectedCommonDirs,
  setDirectories,
  setError,
  setNewDirectory,
  workspaceMode,
  workspaceTitle,
}: DirectorySelectionSectionProps) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        {workspaceMode ? t('workspaceStoragePath' as any) : t('allowedDirectories' as any)}
      </label>
      {workspaceMode && (
        <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
          {t('workspaceStoragePathDescription' as any)}
          <br />
          <span className="text-orange-600 dark:text-orange-400 font-medium">
            {t('workspaceStoragePathAbsolutePathHint', {
              example: initialStorageBasePath || (isWindows ? 'C:\\Users\\...\\Documents' : '/Users/.../Documents'),
            })}
          </span>
        </p>
      )}

      <div className="mb-4">
        {workspaceMode && (
          <div className="mb-3 p-3 bg-accent-10 dark:bg-blue-900/20 border border-accent/30 dark:border-blue-800 rounded-lg">
            <p className="text-sm font-medium text-accent dark:text-blue-300 mb-2">
              {t('selectProjectRootDirectory' as any)}
            </p>
            <p className="text-xs text-accent dark:text-blue-400">
              {t('selectProjectRootDirectoryDescription' as any)}
            </p>
          </div>
        )}
        <button
          type="button"
          onClick={handleDirectoryPicker}
          className={`px-6 py-3 ${
            workspaceMode ? 'bg-accent hover:bg-accent/90 text-lg font-medium' : 'px-4 py-2 bg-accent hover:bg-accent/90 text-sm'
          } text-white rounded-md flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-md`}
          title={
            typeof window !== 'undefined' && 'showDirectoryPicker' in window
              ? t('browseDirectoryChromeEdge' as any)
              : t('browseDirectoryNotAvailable' as any)
          }
        >
          <span>
            {t('browseDirectory' as any)}{' '}
            {typeof window !== 'undefined' && 'showDirectoryPicker' in window
              ? `(${t('browseDirectoryChromeEdge' as any).replace('Browse Directory ', '')})`
              : `(${t('browseDirectoryNotAvailable' as any).replace('Browse Directory ', '')})`}
          </span>
        </button>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {workspaceMode
            ? t('browseDirectoryDescription' as any)
            : typeof window !== 'undefined' && 'showDirectoryPicker' in window
              ? t('browseDirectoryWorkspaceDescription' as any)
              : t('browseDirectoryNotAvailable' as any)}
        </p>
        <input
          ref={fileInputRef}
          type="file"
          {...({ webkitdirectory: '' } as any)}
          {...({ directory: '' } as any)}
          multiple
          style={{ display: 'none' }}
          onChange={handleFileInputChange}
        />
      </div>

      {workspaceMode && (
        <div className="mb-2">
          <p className="text-xs text-gray-500 dark:text-gray-400 font-medium">{t('orUseQuickSelect' as any)}</p>
        </div>
      )}
      <div className="mb-4">
        <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
          {workspaceMode ? (
            <>
              {t('quickSelectWorkspaceStoragePath' as any)}
              {!actualUsername && (
                <>
                  <br />
                </>
              )}
            </>
          ) : (
            `Quick Select Common Directories (${isWindows ? 'Windows' : 'Mac/Linux'}):`
          )}
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {filteredCommonDirs.map((commonDir) => {
            const existingPaths = directories.map((directory) => directory.path);
            const isSelected =
              selectedCommonDirs.has(commonDir.path) || existingPaths.includes(commonDir.path);
            return (
              <button
                key={commonDir.path}
                type="button"
                onClick={() => handleToggleCommonDirectory(commonDir.path)}
                className={`
                  flex items-center space-x-2 px-3 py-2 rounded-md border text-sm transition-colors
                  ${
                    isSelected
                      ? 'bg-gray-100 dark:bg-gray-700 border-gray-500 dark:border-gray-500 text-gray-700 dark:text-gray-200'
                      : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }
                `}
              >
                <span className="truncate">{commonDir.label}</span>
                {isSelected && <span className="text-gray-600 dark:text-gray-300">✓</span>}
              </button>
            );
          })}
        </div>
      </div>

      {!workspaceMode && (
        <div className="mb-4">
          <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">Or Enter Custom Path:</p>
          <div className="flex space-x-2">
            <input
              type="text"
              value={newDirectory}
              onChange={(event) => setNewDirectory(event.target.value)}
              onKeyPress={(event) => event.key === 'Enter' && handleAddDirectory()}
              className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-blue-400 focus:border-transparent"
              placeholder={
                isWindows ? 'e.g., C:\\Users\\...\\Documents or .\\data' : 'e.g., ~/Documents or ./data/documents'
              }
            />
            <button
              onClick={handleAddDirectory}
              disabled={!newDirectory.trim()}
              className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
            >
              {t('add' as any)}
            </button>
          </div>
        </div>
      )}

      {(directories.length > 0 || workspaceMode) && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-gray-700 dark:text-gray-300">
              {workspaceMode ? t('workspaceStoragePathLabel' as any) : 'Selected Directories:'}
            </p>
            {workspaceMode &&
              savedStorageBasePath &&
              directories.length > 0 &&
              directories[0]?.path === savedStorageBasePath && (
                <span className="text-xs text-green-600 dark:text-green-400 font-medium flex items-center gap-1">
                  <span>✓</span>
                  {t('configured' as any)}
                </span>
              )}
          </div>
          {workspaceMode && directories.length === 0 ? (
            <EmptyPathInputWithWorkspaceName
              workspaceTitle={workspaceTitle}
              isWindows={isWindows}
              initialStorageBasePath={initialStorageBasePath}
              currentPath=""
              onPathChange={(path) => {
                const trimmedPath = path.trim();
                if (trimmedPath) {
                  setDirectories([{ path: trimmedPath, allowWrite: false }]);
                } else {
                  setDirectories([]);
                }
                setError(null);
              }}
            />
          ) : (
            directories.map((directory, index) => (
              <div
                key={`${directory.path}-${index}`}
                className="flex items-center space-x-2 p-2 bg-gray-50 dark:bg-gray-800/50 rounded-md"
              >
                {workspaceMode ? (
                  <>
                    <input
                      type="text"
                      value={directory.path}
                      onChange={(event) => {
                        const nextDirectories = [...directories];
                        nextDirectories[index] = {
                          ...nextDirectories[index],
                          path: event.target.value,
                        };
                        setDirectories(nextDirectories);
                        setError(null);
                      }}
                      className="flex-1 px-2 py-1 text-sm text-gray-700 dark:text-gray-300 font-mono border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-blue-400 focus:border-transparent placeholder-gray-400 dark:placeholder-gray-500"
                      placeholder={
                        initialStorageBasePath || (isWindows ? 'C:\\Users\\...\\Documents\\...' : '/Users/.../Documents/...')
                      }
                    />
                    {workspaceTitle ? (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          const nextDirectories = [...directories];
                          nextDirectories[index] = {
                            ...nextDirectories[index],
                            path: appendWorkspaceTitleToPath({
                              currentPath: directory.path,
                              isWindows,
                              workspaceTitle,
                            }),
                          };
                          setDirectories(nextDirectories);
                          setError(null);
                        }}
                        className="px-3 py-1 text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border border-green-300 dark:border-green-700 rounded hover:bg-green-200 dark:hover:bg-green-900/50 transition-colors whitespace-nowrap"
                        title={t('appendWorkspaceNameTooltip', { workspaceTitle: workspaceTitle || '' })}
                      >
                        {t('appendWorkspaceName' as any)}
                      </button>
                    ) : (
                      <div className="text-xs text-red-500 dark:text-red-400">No title</div>
                    )}
                  </>
                ) : (
                  <>
                    <span className="flex-1 text-sm text-gray-700 dark:text-gray-300 font-mono">
                      {directory.path}
                    </span>
                    <label className="flex items-center space-x-1 text-xs text-gray-600 dark:text-gray-400">
                      <input
                        type="checkbox"
                        checked={directory.allowWrite}
                        onChange={(event) => {
                          const nextDirectories = [...directories];
                          nextDirectories[index] = {
                            ...nextDirectories[index],
                            allowWrite: event.target.checked,
                          };
                          setDirectories(nextDirectories);
                        }}
                        className="rounded"
                        title={t('allowWriteOperations' as any)}
                      />
                      <span>{t('allowWriteOperations' as any)}</span>
                    </label>
                  </>
                )}
                {!workspaceMode && (
                  <button
                    onClick={() => handleRemoveDirectory(index)}
                    className="px-2 py-1 text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 text-sm"
                    title="Remove"
                  >
                    ×
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      )}

      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        {workspaceMode ? (
          <>
            Supported formats (must use absolute path):{' '}
            {isWindows ? (
              <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">C:\Users\...\Documents</code>
            ) : (
              <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">/Users/.../Documents</code>
            )}
          </>
        ) : (
          <>
            Supported formats:{' '}
            {isWindows ? (
              <>
                <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">C:\Users\...\Documents</code>,{' '}
                <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">%USERPROFILE%\Documents</code>,{' '}
                <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">.\data</code>
              </>
            ) : (
              <>
                <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">~/Documents</code>,{' '}
                <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">./data</code>,{' '}
                <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">/Users/.../Documents</code>
              </>
            )}
          </>
        )}
      </p>
    </div>
  );
}
