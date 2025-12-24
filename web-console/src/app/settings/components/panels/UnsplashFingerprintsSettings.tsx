'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { showNotification } from '../../hooks/useSettingsNotification';

interface FingerprintStatus {
  total_count: number;
  has_data: boolean;
  last_updated?: string;
}

export function UnsplashFingerprintsSettings() {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<FingerprintStatus | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState<string>('');

  useEffect(() => {
    fetchStatus();
  }, []);

  const fetchStatus = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/unsplash/fingerprints/status');
      if (response.ok) {
        const data = await response.json();
        setStatus(data);
      } else {
        // Table might not exist yet, which is OK
        const errorData = await response.json().catch(() => ({}));
        if (errorData.error && 'does not exist' in errorData.error) {
          // Table doesn't exist yet, set empty status
          setStatus({ has_data: false, total_count: 0 });
        } else {
          console.error('Failed to fetch fingerprint status:', errorData);
        }
      }
    } catch (error) {
      // Network error or other issue, set empty status
      console.error('Error fetching fingerprint status:', error);
      setStatus({ has_data: false, total_count: 0 });
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadAndBuild = async () => {
    if (!confirm(t('unsplashFingerprintsConfirmDownload') || 'This will download ~6.5M photos metadata (~2-5GB) and may take 10-30 minutes. Continue?')) {
      return;
    }

    try {
      setDownloading(true);
      setProgress('');

      const response = await fetch('/api/v1/unsplash/fingerprints/setup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          auto_download: true,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to setup fingerprints');
      }

      // Poll for progress
      const pollProgress = async () => {
        try {
          const progressResponse = await fetch('/api/v1/unsplash/fingerprints/progress');
          if (progressResponse.ok) {
            const progressData = await progressResponse.json();
            setProgress(progressData.message || progressData.status || '');

            if (progressData.status === 'completed') {
              setDownloading(false);
              showNotification('success', t('unsplashFingerprintsSetupSuccess') || 'Fingerprints database setup completed successfully!');
              await fetchStatus();
            } else if (progressData.status === 'failed') {
              setDownloading(false);
              showNotification('error', progressData.error || t('unsplashFingerprintsSetupFailed') || 'Setup failed');
            } else {
              // Continue polling
              setTimeout(pollProgress, 2000);
            }
          }
        } catch (error) {
          console.error('Error polling progress:', error);
          setTimeout(pollProgress, 2000);
        }
      };

      // Start polling after initial response
      const initialData = await response.json();
      setProgress(initialData.message || 'Starting download...');
      setTimeout(pollProgress, 2000);

    } catch (error: any) {
      setDownloading(false);
      showNotification('error', error.message || t('unsplashFingerprintsSetupError') || 'Failed to setup fingerprints');
    }
  };

  if (loading) {
    return (
      <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
        {t('loading')}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
          {t('unsplashFingerprintsTitle') || 'Unsplash Dataset Fingerprints'}
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          {t('unsplashFingerprintsDescription') || 'Enhance Visual Lens extraction quality by downloading and building a fingerprint database from the Unsplash Dataset. This database contains detailed color, keyword, and metadata for millions of photos.'}
        </p>
      </div>

      {/* Status Card */}
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {t('unsplashFingerprintsStatus') || 'Database Status'}
          </h4>
          {status?.has_data && (
            <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-md">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              {t('configured')}
            </span>
          )}
        </div>

        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-600 dark:text-gray-400">
              {t('unsplashFingerprintsTotalCount') || 'Total Fingerprints:'}
            </span>
            <span className="font-medium text-gray-900 dark:text-gray-100">
              {status?.total_count?.toLocaleString() || '0'}
            </span>
          </div>
          {status?.last_updated && (
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">
                {t('unsplashFingerprintsLastUpdated') || 'Last Updated:'}
              </span>
              <span className="text-gray-900 dark:text-gray-100">
                {new Date(status.last_updated).toLocaleString()}
              </span>
            </div>
          )}
          {status?.error && !status?.has_data && (
            <div className="text-xs text-gray-500 dark:text-gray-400 italic mt-2">
              {t('unsplashFingerprintsTableNotCreated') || 'Database table not created yet. Click "Download & Build Database" to start.'}
            </div>
          )}
        </div>
      </div>

      {/* Info Card */}
      <div className="bg-accent-10 dark:bg-blue-900/20 rounded-lg p-4 border border-accent/30 dark:border-blue-800">
        <div className="flex items-start gap-3">
          <svg className="w-5 h-5 text-accent dark:text-blue-400 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
          <div className="text-sm text-accent dark:text-blue-300">
            <p className="font-medium mb-1">{t('unsplashFingerprintsInfoTitle') || 'What will be downloaded?'}</p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li>{t('unsplashFingerprintsInfo1') || '~25,000 photos metadata (colors, keywords, EXIF data) - Lite version'}</li>
              <li>{t('unsplashFingerprintsInfo2') || 'Requires approx. 200-500MB storage space'}</li>
              <li>{t('unsplashFingerprintsInfo3') || '5-15 minutes processing time'}</li>
              <li>{t('unsplashFingerprintsInfo4') || 'Requires Hugging Face account (free)'}</li>
              {t('unsplashFingerprintsInfo5') && (
                <li className="text-yellow-700 dark:text-yellow-400 font-medium">{t('unsplashFingerprintsInfo5')}</li>
              )}
            </ul>
          </div>
        </div>
      </div>

      {/* Progress Display */}
      {downloading && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-4 border border-yellow-200 dark:border-yellow-800">
          <div className="flex items-center gap-3">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-yellow-600 dark:border-yellow-400"></div>
            <div className="flex-1">
              <p className="text-sm font-medium text-yellow-800 dark:text-yellow-300">
                {t('unsplashFingerprintsDownloading') || 'Downloading and building database...'}
              </p>
              {progress && (
                <p className="text-xs text-yellow-700 dark:text-yellow-400 mt-1">
                  {progress}
                </p>
              )}
              <p className="text-xs text-yellow-600 dark:text-yellow-500 mt-2 italic">
                {t('unsplashFingerprintsProgressNote') || 'This may take 10-30 minutes. You can close this page and check back later.'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Action Button */}
      <div className="flex justify-end gap-3">
        <button
          onClick={fetchStatus}
          disabled={loading || downloading}
          className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          {t('refresh') || 'Refresh Status'}
        </button>
        <button
          onClick={handleDownloadAndBuild}
          disabled={downloading || loading}
          className="px-4 py-2 text-sm font-medium text-white bg-accent dark:bg-blue-700 rounded-md hover:bg-accent/90 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {downloading
            ? (t('unsplashFingerprintsDownloading') || 'Downloading...')
            : (t('unsplashFingerprintsDownloadButton') || 'Download & Build Database')}
        </button>
      </div>
    </div>
  );
}

