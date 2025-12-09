'use client';

import React, { useState, useEffect } from 'react';
import { checkVersions, getSyncStatus, type VersionCheckResponse, type ClientUpdateInfo } from '@/lib/sync-api';
import { t } from '@/lib/i18n';

interface UpdateBannerProps {
  clientVersion: string;
  capabilities?: Array<{ code: string; version: string }>;
  assets?: Array<{ uri: string; version: string }>;
  onDismiss?: () => void;
}

export default function UpdateBanner({
  clientVersion,
  capabilities = [],
  assets = [],
  onDismiss,
}: UpdateBannerProps) {
  const [updateInfo, setUpdateInfo] = useState<VersionCheckResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [cloudConfigured, setCloudConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    let isMounted = true;

    const checkForUpdates = async () => {
      if (!isMounted) return;

      try {
        const syncStatus = await getSyncStatus();
        if (isMounted) {
          setCloudConfigured(syncStatus.configured);
        }
        if (!syncStatus.configured) {
          return;
        }
      } catch {
        if (isMounted) {
          setCloudConfigured(false);
        }
        return;
      }

      setLoading(true);
      try {
        const response = await checkVersions({
          client_version: clientVersion,
          capabilities,
          assets,
        });
        if (isMounted) {
          setUpdateInfo(response);
        }
      } catch {
        // Optional feature - silent fail
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    const initialDelay = setTimeout(checkForUpdates, 2000);
    const interval = setInterval(checkForUpdates, 5 * 60 * 1000);

    return () => {
      isMounted = false;
      clearTimeout(initialDelay);
      clearInterval(interval);
    };
  }, [clientVersion, capabilities, assets]);

  if (dismissed || !updateInfo) {
    return null;
  }

  const clientUpdate = updateInfo.client_update;
  const hasUpdates = clientUpdate.available ||
    updateInfo.capability_updates.length > 0 ||
    updateInfo.asset_updates.length > 0;

  if (!hasUpdates) {
    return null;
  }

  const isRequired = clientUpdate.priority === 'required' ||
    updateInfo.capability_updates.some(u => u.priority === 'required') ||
    updateInfo.asset_updates.some(u => u.priority === 'required');

  const handleDismiss = () => {
    setDismissed(true);
    onDismiss?.();
  };

  return (
    <div className={`w-full ${isRequired ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800' : 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800'} border-b`}>
      <div className="max-w-7xl mx-auto px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`flex-shrink-0 ${isRequired ? 'text-red-600 dark:text-red-400' : 'text-blue-600 dark:text-blue-400'}`}>
              {isRequired ? (
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                </svg>
              )}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h3 className={`text-sm font-medium ${isRequired ? 'text-red-800 dark:text-red-200' : 'text-blue-800 dark:text-blue-200'}`}>
                  {isRequired ? t('updateRequired') : t('updateAvailable')}
                </h3>
                {clientUpdate.available && (
                  <span className="text-xs px-2 py-0.5 rounded bg-white dark:bg-gray-800">
                    {clientUpdate.current} → {clientUpdate.latest}
                  </span>
                )}
              </div>
              <p className={`text-xs mt-1 ${isRequired ? 'text-red-700 dark:text-red-300' : 'text-blue-700 dark:text-blue-300'}`}>
                {updateInfo.capability_updates.length > 0 && `${updateInfo.capability_updates.length} capability updates`}
                {updateInfo.asset_updates.length > 0 && `, ${updateInfo.asset_updates.length} asset updates`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowDetails(!showDetails)}
              className={`text-xs px-3 py-1.5 rounded-md ${isRequired ? 'bg-red-100 dark:bg-red-800 text-red-700 dark:text-red-200 hover:bg-red-200 dark:hover:bg-red-700' : 'bg-blue-100 dark:bg-blue-800 text-blue-700 dark:text-blue-200 hover:bg-blue-200 dark:hover:bg-blue-700'}`}
            >
              {showDetails ? t('hideDetails') : t('showDetails')}
            </button>
            {!isRequired && (
              <button
                onClick={handleDismiss}
                className="text-xs px-3 py-1.5 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
              >
                {t('dismiss')}
              </button>
            )}
          </div>
        </div>
        {showDetails && (
          <div className={`mt-3 pt-3 border-t ${isRequired ? 'border-red-200 dark:border-red-800' : 'border-blue-200 dark:border-blue-800'}`}>
            <UpdateDetailsDialog updateInfo={updateInfo} />
          </div>
        )}
      </div>
    </div>
  );
}

function UpdateDetailsDialog({ updateInfo }: { updateInfo: VersionCheckResponse }) {
  return (
    <div className="space-y-3 text-xs">
      {updateInfo.client_update.available && (
        <div className="bg-white dark:bg-gray-800 rounded p-3">
          <h4 className="font-medium mb-2">Client Update</h4>
          <p className="text-gray-600 dark:text-gray-400">
            {updateInfo.client_update.current} → {updateInfo.client_update.latest}
          </p>
          {updateInfo.client_update.changelog && (
            <p className="mt-2 text-gray-500 dark:text-gray-500">{updateInfo.client_update.changelog}</p>
          )}
          {updateInfo.client_update.download_url && (
            <a
              href={updateInfo.client_update.download_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-block text-blue-600 dark:text-blue-400 hover:underline"
            >
              {t('downloadUpdate')}
            </a>
          )}
        </div>
      )}
      {updateInfo.capability_updates.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded p-3">
          <h4 className="font-medium mb-2">Capability Updates</h4>
          <ul className="space-y-1">
            {updateInfo.capability_updates.map((update) => (
              <li key={update.code} className="text-gray-600 dark:text-gray-400">
                {update.code}: {update.current} → {update.latest}
              </li>
            ))}
          </ul>
        </div>
      )}
      {updateInfo.asset_updates.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded p-3">
          <h4 className="font-medium mb-2">Asset Updates</h4>
          <ul className="space-y-1">
            {updateInfo.asset_updates.map((update) => (
              <li key={update.uri} className="text-gray-600 dark:text-gray-400">
                {update.uri}: {update.current} → {update.latest}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

