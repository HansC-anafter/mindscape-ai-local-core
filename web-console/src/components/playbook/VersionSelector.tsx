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
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 whitespace-nowrap">{t('currentExecutionVersion')}</h3>

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
              <span className="text-sm text-gray-700 dark:text-gray-300">{t('myVersionNotCreated')}</span>
            </label>
            <div className="flex items-center gap-2 ml-auto">
              <button
                onClick={onCopyClick}
                className="px-3 py-1.5 text-xs text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
              >
                {t('directCopy')}
              </button>
              <button
                onClick={onLLMClick}
                className="px-3 py-1.5 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 border border-blue-300 dark:border-blue-700 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20 bg-white dark:bg-gray-800"
              >
                {t('llmCustomization')}
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
                {t('playbookMyVariant', { name: defaultVariant?.variant_name || t('playbookMyVariantDefault') })}
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
                onClick={() => {/* TODO: Show diff */}}
                className="px-3 py-1.5 text-xs text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
              >
                {t('viewDiff')}
              </button>
              <button
                onClick={onLLMClick}
                className="px-3 py-1.5 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 border border-blue-300 dark:border-blue-700 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20 bg-white dark:bg-gray-800"
              >
                {t('readjust')}
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
              {t('activeExecutions', { count: activeExecutionsCount })}
            </span>
          </div>
        ) : (
          <span className="text-xs text-gray-500 dark:text-gray-400">{t('noExecutionRecord')}</span>
        )}
      </div>
    </div>
  );
}
