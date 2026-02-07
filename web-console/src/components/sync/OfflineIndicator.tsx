'use client';

import React, { useState, useEffect } from 'react';
import { getSyncStatus, getChangeSummary, syncPendingChanges, type SyncStatus, type ChangeSummary } from '@/lib/sync-api';
import { t } from '@/lib/i18n';

interface OfflineIndicatorProps {
  className?: string;
}

export default function OfflineIndicator({ className = '' }: OfflineIndicatorProps) {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [summary, setSummary] = useState<ChangeSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    let isMounted = true;

    const fetchStatus = async () => {
      if (!isMounted) return;

      try {
        const statusData = await getSyncStatus();

        if (!isMounted) return;

        if (!statusData.configured) {
          setStatus(null);
          return;
        }

        setStatus(statusData);

        if (statusData.configured) {
          try {
            const summaryData = await getChangeSummary();
            if (isMounted) {
              setSummary(summaryData);
            }
          } catch {
            // Optional feature - silent fail
          }
        }
      } catch {
        if (isMounted) {
          setStatus(null);
        }
      }
    };

    const initialDelay = setTimeout(fetchStatus, 1500);
    const interval = setInterval(fetchStatus, 30000);

    return () => {
      isMounted = false;
      clearTimeout(initialDelay);
      clearInterval(interval);
    };
  }, []);

  const handleSync = async () => {
    if (!status?.online || syncing) return;

    setSyncing(true);
    try {
      await syncPendingChanges();
      const [statusData, summaryData] = await Promise.all([
        getSyncStatus(),
        getChangeSummary(),
      ]);
      setStatus(statusData);
      setSummary(summaryData);
    } catch (error) {
      console.error('Failed to sync:', error);
    } finally {
      setSyncing(false);
    }
  };

  if (!status || !status.configured) {
    return null;
  }

  const isOffline = !status.online;
  const hasPendingChanges = status.pending_changes > 0;

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="flex items-center gap-2">
        {isOffline ? (
          <div className="flex items-center gap-2 text-yellow-600 dark:text-yellow-400">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M13.477 14.89A6 6 0 015.11 6.524l8.367 8.368zm1.414-1.414L6.524 5.11a6 6 0 018.367 8.367zM18 10a8 8 0 11-16 0 8 8 0 0116 0z" clipRule="evenodd" />
            </svg>
            <span className="text-xs font-medium">{t('offline' as any)}</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            <span className="text-xs font-medium">{t('online' as any)}</span>
          </div>
        )}
      </div>

      {hasPendingChanges && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-600 dark:text-gray-400">
            {status.pending_changes} {t('pendingChanges' as any)}
          </span>
          {!isOffline && (
            <button
              onClick={handleSync}
              disabled={syncing}
              className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {syncing ? t('syncing' as any) : t('syncNow' as any)}
            </button>
          )}
        </div>
      )}

      <button
        onClick={() => setShowDetails(!showDetails)}
        className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
      >
        {showDetails ? t('hideDetails' as any) : t('showDetails' as any)}
      </button>

      {showDetails && (
        <SyncStatusDetails status={status} summary={summary} />
      )}
    </div>
  );
}

function SyncStatusDetails({ status, summary }: { status: SyncStatus; summary: ChangeSummary | null }) {
  return (
    <div className="absolute top-full right-0 mt-2 w-64 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-3 z-50">
      <div className="space-y-2 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-gray-600 dark:text-gray-400">{t('syncStatus' as any)}</span>
          <span className={status.online ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}>
            {status.online ? t('online' as any) : t('offline' as any)}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-gray-600 dark:text-gray-400">{t('pendingChanges' as any)}</span>
          <span className="font-medium">{status.pending_changes}</span>
        </div>
        {summary && (
          <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
            <div className="text-gray-600 dark:text-gray-400 mb-1">{t('affectedInstances' as any)}</div>
            <div className="space-y-1">
              {summary.instances_with_changes.map((instance) => (
                <div key={`${instance.instance_type}-${instance.instance_id}`} className="text-xs">
                  {instance.instance_type}/{instance.instance_id}: {instance.change_count} {t('changes' as any)}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

