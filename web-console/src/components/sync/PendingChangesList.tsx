'use client';

import React, { useState, useEffect } from 'react';
import { getPendingChanges, type PendingChange } from '@/lib/sync-api';
import { t } from '@/lib/i18n';

interface PendingChangesListProps {
  onSync?: () => void;
}

export default function PendingChangesList({ onSync }: PendingChangesListProps) {
  const [changes, setChanges] = useState<PendingChange[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchChanges = async () => {
      try {
        const data = await getPendingChanges();
        setChanges(data);
      } catch (error) {
        console.error('Failed to fetch pending changes:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchChanges();
    const interval = setInterval(fetchChanges, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="text-sm text-gray-500 dark:text-gray-400">
        {t('loading')}...
      </div>
    );
  }

  if (changes.length === 0) {
    return (
      <div className="text-sm text-gray-500 dark:text-gray-400">
        {t('noPendingChanges')}
      </div>
    );
  }

  const groupedChanges = changes.reduce((acc, change) => {
    const key = `${change.instance_type}-${change.instance_id}`;
    if (!acc[key]) {
      acc[key] = {
        instance_type: change.instance_type || '',
        instance_id: change.instance_id || '',
        changes: [],
      };
    }
    acc[key].changes.push(change);
    return acc;
  }, {} as Record<string, { instance_type: string; instance_id: string; changes: PendingChange[] }>);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
          {t('pendingChanges')} ({changes.length})
        </h3>
        {onSync && (
          <button
            onClick={onSync}
            className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            {t('syncAll')}
          </button>
        )}
      </div>
      <div className="space-y-2">
        {Object.values(groupedChanges).map((group) => (
          <div
            key={`${group.instance_type}-${group.instance_id}`}
            className="border rounded p-3 bg-white dark:bg-gray-800"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {group.instance_type}/{group.instance_id}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {group.changes.length} {t('changes')}
              </div>
            </div>
            <div className="space-y-1">
              {group.changes.slice(0, 3).map((change) => (
                <div key={change.change_id} className="text-xs text-gray-600 dark:text-gray-400">
                  <span className="text-gray-400 dark:text-gray-500">
                    {new Date(change.created_at).toLocaleString()}
                  </span>
                  {' - '}
                  <span>{change.type}</span>
                </div>
              ))}
              {group.changes.length > 3 && (
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  +{group.changes.length - 3} {t('moreChanges')}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

