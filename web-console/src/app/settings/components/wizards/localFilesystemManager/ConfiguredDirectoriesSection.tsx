'use client';

import { useT } from '@/lib/i18n';

import type { ConfiguredDirectory } from './types';

interface ConfiguredDirectoriesSectionProps {
  configuredDirs: ConfiguredDirectory[];
}

export function ConfiguredDirectoriesSection({ configuredDirs }: ConfiguredDirectoriesSectionProps) {
  const t = useT();
  if (configuredDirs.length === 0) {
    return null;
  }

  return (
    <div className="border-t dark:border-gray-700 pt-4">
      <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        {t('configuredDirectories' as any)}
      </h3>
      <div className="space-y-2">
        {configuredDirs.map((connection, index) => (
          <div key={index} className="p-3 bg-gray-50 dark:bg-gray-800/50 rounded">
            <div className="flex items-center justify-between mb-2">
              <div className="font-medium text-sm text-gray-900 dark:text-gray-100">{connection.name}</div>
              {connection.enabled !== undefined && (
                <span
                  className={`text-xs px-2 py-0.5 rounded ${
                    connection.enabled
                      ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                  }`}
                >
                  {connection.enabled ? t('enabled' as any) : t('disabled' as any)}
                </span>
              )}
            </div>
            <div className="space-y-1.5">
              {connection.allowed_directories.map((directory, directoryIndex) => {
                const isEnabled = connection.enabled !== false;
                return (
                  <div key={directoryIndex} className="flex items-center space-x-2">
                    {isEnabled && (
                      <span className="text-green-600 dark:text-green-400 text-sm font-semibold" title={t('enabled' as any)}>
                        ON
                      </span>
                    )}
                    {!isEnabled && (
                      <span className="text-gray-400 dark:text-gray-500 text-sm" title={t('disabled' as any)}>
                        OFF
                      </span>
                    )}
                    <span className="text-xs text-gray-600 dark:text-gray-400 flex-1 font-mono">{directory}</span>
                  </div>
                );
              })}
            </div>
            {connection.allow_write && (
              <span className="text-xs text-orange-600 dark:text-orange-400 mt-2 block">
                {t('writeEnabled' as any)}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
