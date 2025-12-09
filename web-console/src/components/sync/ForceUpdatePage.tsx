'use client';

import React from 'react';
import { t } from '@/lib/i18n';
import type { ClientUpdateInfo } from '@/lib/sync-api';

interface ForceUpdatePageProps {
  updateInfo: ClientUpdateInfo;
}

export default function ForceUpdatePage({ updateInfo }: ForceUpdatePageProps) {
  return (
    <div className="fixed inset-0 bg-white dark:bg-gray-900 flex items-center justify-center z-50">
      <div className="max-w-md w-full mx-4 text-center">
        <div className="mb-6">
          <div className="mx-auto w-16 h-16 bg-red-100 dark:bg-red-900/20 rounded-full flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-red-600 dark:text-red-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            {t('updateRequired')}
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            {t('updateRequiredDescription')}
          </p>
        </div>

        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 mb-6">
          <div className="text-sm text-gray-600 dark:text-gray-400 mb-2">
            {t('currentVersion')}: <span className="font-medium">{updateInfo.current}</span>
          </div>
          <div className="text-sm text-gray-600 dark:text-gray-400">
            {t('latestVersion')}: <span className="font-medium text-blue-600 dark:text-blue-400">{updateInfo.latest}</span>
          </div>
        </div>

        {updateInfo.changelog && (
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 mb-6 text-left">
            <h3 className="text-sm font-medium mb-2">{t('changelog')}</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
              {updateInfo.changelog}
            </p>
          </div>
        )}

        {updateInfo.download_url ? (
          <a
            href={updateInfo.download_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block w-full px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
          >
            {t('downloadUpdate')}
          </a>
        ) : (
          <div className="text-sm text-gray-500 dark:text-gray-400">
            {t('updateInstructions')}
          </div>
        )}
      </div>
    </div>
  );
}

