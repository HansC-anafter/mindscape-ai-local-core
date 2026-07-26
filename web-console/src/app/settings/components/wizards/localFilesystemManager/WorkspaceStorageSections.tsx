'use client';

import { useT } from '@/lib/i18n';

import type { DirectoryConfig, PlaybookStorageConfig } from './types';

interface WorkspaceStorageSectionsProps {
  artifactsDir: string;
  directories: DirectoryConfig[];
  loadingPlaybooks: boolean;
  playbookStorageConfig: Record<string, PlaybookStorageConfig>;
  setArtifactsDir: (value: string) => void;
  setPlaybookStorageConfig: (value: Record<string, PlaybookStorageConfig>) => void;
  usedPlaybooks: string[];
  workspaceMode: boolean;
}

export function WorkspaceStorageSections({
  artifactsDir,
  directories,
  loadingPlaybooks,
  playbookStorageConfig,
  setArtifactsDir,
  setPlaybookStorageConfig,
  usedPlaybooks,
  workspaceMode,
}: WorkspaceStorageSectionsProps) {
  const t = useT();
  if (!workspaceMode) {
    return null;
  }

  return (
    <>
      <div className="border-t dark:border-gray-700 pt-4">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('artifactsDirectory' as any)}
        </label>
        <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
          {t('artifactsDirectoryDescription' as any)}
          <br />
          {t('artifactsDirectoryDefault' as any)}:{' '}
          <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">artifacts</code>
        </p>
        <input
          type="text"
          value={artifactsDir}
          onChange={(event) => setArtifactsDir(event.target.value)}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-blue-400 focus:border-transparent"
          placeholder="artifacts"
        />
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {t('artifactsWillBeStoredAt' as any)}{' '}
          <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">
            {directories[0]?.path || '...'}/{artifactsDir || 'artifacts'}
          </code>
        </p>
      </div>

      <div className="border-t dark:border-gray-700 pt-4">
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('playbookStorageConfiguration' as any)}
          </label>
          {loadingPlaybooks && (
            <span className="text-xs text-gray-500 dark:text-gray-400">{t('loadingPlaybooks' as any)}</span>
          )}
        </div>
        <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">
          {t('playbookStorageConfigurationDescription' as any)}
        </p>

        {usedPlaybooks.length > 0 && (
          <div className="space-y-3 mb-4">
            {usedPlaybooks.map((playbookCode) => (
              <PlaybookStorageConfigRow
                key={playbookCode}
                artifactsDir={artifactsDir}
                directories={directories}
                playbookCode={playbookCode}
                playbookStorageConfig={playbookStorageConfig}
                setPlaybookStorageConfig={setPlaybookStorageConfig}
              />
            ))}
          </div>
        )}

        {usedPlaybooks.length === 0 && !loadingPlaybooks && (
          <p className="text-xs text-gray-500 dark:text-gray-400 italic">{t('noPlaybooksUsedYet' as any)}</p>
        )}
      </div>
    </>
  );
}

interface PlaybookStorageConfigRowProps {
  artifactsDir: string;
  directories: DirectoryConfig[];
  playbookCode: string;
  playbookStorageConfig: Record<string, PlaybookStorageConfig>;
  setPlaybookStorageConfig: (value: Record<string, PlaybookStorageConfig>) => void;
}

function PlaybookStorageConfigRow({
  artifactsDir,
  directories,
  playbookCode,
  playbookStorageConfig,
  setPlaybookStorageConfig,
}: PlaybookStorageConfigRowProps) {
  const t = useT();
  const config = playbookStorageConfig[playbookCode] || {};
  const useCustom = !!(config.base_path && config.base_path.trim());

  const updateConfig = (nextConfig: PlaybookStorageConfig | null) => {
    const newConfig = { ...playbookStorageConfig };
    if (nextConfig) {
      newConfig[playbookCode] = nextConfig;
    } else {
      delete newConfig[playbookCode];
    }
    setPlaybookStorageConfig(newConfig);
  };

  return (
    <div className="p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={useCustom}
            onChange={(event) => {
              if (event.target.checked) {
                updateConfig({
                  base_path: directories[0]?.path || '',
                  artifacts_dir: artifactsDir,
                });
              } else {
                updateConfig(null);
              }
            }}
            className="rounded"
          />
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{playbookCode}</span>
        </div>
        {useCustom && (
          <button
            onClick={() => updateConfig(null)}
            className="text-xs text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
          >
            {t('remove' as any)}
          </button>
        )}
      </div>
      {useCustom && (
        <div className="space-y-2 mt-2">
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('basePath' as any)}
            </label>
            <input
              type="text"
              value={config.base_path || ''}
              onChange={(event) => updateConfig({ ...config, base_path: event.target.value })}
              className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-blue-400"
              placeholder={directories[0]?.path || 'Enter base path'}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('artifactsDirectory' as any)}
            </label>
            <input
              type="text"
              value={config.artifacts_dir || artifactsDir}
              onChange={(event) => updateConfig({ ...config, artifacts_dir: event.target.value })}
              className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-blue-400"
              placeholder={artifactsDir || 'artifacts'}
            />
          </div>
        </div>
      )}
    </div>
  );
}
