'use client';

import React from 'react';
import { t } from '../../lib/i18n';

interface VersionSelectorProps {
  hasPersonalVariant: boolean;
  defaultVariant?: {
    variant_name: string;
  };
  systemVersion: string;
  selectedVersion: 'system' | 'personal';
  onVersionChange: (version: 'system' | 'personal') => void;
  onCopyClick: () => void;
  onLLMClick: () => void;
  activeExecutionsCount?: number;
}

export default function VersionSelector({
  hasPersonalVariant,
  defaultVariant,
  systemVersion,
  selectedVersion,
  onVersionChange,
  onCopyClick,
  onLLMClick,
  activeExecutionsCount = 0
}: VersionSelectorProps) {
  return (
    <div className="flex items-center gap-6">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 whitespace-nowrap">{t('currentExecutionVersion' as any)}</h3>

      <div className="flex items-center gap-4 flex-1">
        {!hasPersonalVariant ? (
          <>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="version"
                value="system"
                checked={selectedVersion === 'system'}
                onChange={() => onVersionChange('system')}
                className="w-4 h-4"
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">系統版本（v{systemVersion}）</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer opacity-50">
              <input
                type="radio"
                name="version"
                value="personal"
                disabled
                className="w-4 h-4"
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">{t('myVersionNotCreated' as any)}</span>
            </label>
            <div className="flex items-center gap-2 ml-auto">
              <button
                onClick={onCopyClick}
                className="px-3 py-1.5 text-xs text-primary dark:text-gray-300 hover:text-primary dark:hover:text-gray-100 border border-default dark:border-gray-600 rounded hover:bg-surface-secondary dark:hover:bg-gray-700 bg-surface-accent dark:bg-gray-800"
              >
                {t('directCopy' as any)}
              </button>
              <button
                onClick={onLLMClick}
                className="px-3 py-1.5 text-xs text-accent dark:text-blue-400 hover:text-accent dark:hover:text-blue-300 border border-accent dark:border-blue-700 rounded hover:bg-accent-10 dark:hover:bg-blue-900/20 bg-surface-accent dark:bg-gray-800"
              >
                {t('llmCustomization' as any)}
              </button>
            </div>
          </>
        ) : (
          <>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="version"
                value="personal"
                checked={selectedVersion === 'personal'}
                onChange={() => onVersionChange('personal')}
                className="w-4 h-4"
              />
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {(t as any)('playbookMyVariant', { name: defaultVariant?.variant_name || t('playbookMyVariantDefault' as any) })}
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="version"
                value="system"
                checked={selectedVersion === 'system'}
                onChange={() => onVersionChange('system')}
                className="w-4 h-4"
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">系統版本（v{systemVersion}）</span>
            </label>
            <div className="flex items-center gap-2 ml-auto">
              <button
                onClick={() => {/* TODO: Show diff */ }}
                className="px-3 py-1.5 text-xs text-primary dark:text-gray-300 hover:text-primary dark:hover:text-gray-100 border border-default dark:border-gray-600 rounded hover:bg-surface-secondary dark:hover:bg-gray-700 bg-surface-accent dark:bg-gray-800"
              >
                {t('viewDiff' as any)}
              </button>
              <button
                onClick={onLLMClick}
                className="px-3 py-1.5 text-xs text-accent dark:text-blue-400 hover:text-accent dark:hover:text-blue-300 border border-accent dark:border-blue-700 rounded hover:bg-accent-10 dark:hover:bg-blue-900/20 bg-surface-accent dark:bg-gray-800"
              >
                {t('readjust' as any)}
              </button>
            </div>
          </>
        )}
      </div>

      {/* Execution Status Summary */}
      <div className="flex items-center gap-4">
        {activeExecutionsCount > 0 ? (
          <div className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
            <span className="text-xs text-green-600 dark:text-green-400 font-medium">
              {(t as any)('activeExecutions', { count: activeExecutionsCount })}
            </span>
          </div>
        ) : (
          <span className="text-xs text-gray-500 dark:text-gray-400">{t('noExecutionRecord' as any)}</span>
        )}
      </div>
    </div>
  );
}
