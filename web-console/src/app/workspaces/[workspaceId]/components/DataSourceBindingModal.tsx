'use client';

import React, { useState, useEffect } from 'react';
import { DataSourceWithOverlay } from '@/hooks/useDataSourceOverlay';

interface DataSourceBindingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (dataSourceId: string, overlay: {
    access_mode_override?: 'read' | 'write' | 'admin';
    display_name?: string;
    enabled?: boolean;
  }) => Promise<void>;
  dataSource?: DataSourceWithOverlay | null;
  availableDataSources?: DataSourceWithOverlay[];
}

export default function DataSourceBindingModal({
  isOpen,
  onClose,
  onSave,
  dataSource,
  availableDataSources = [],
}: DataSourceBindingModalProps) {
  const [selectedDataSourceId, setSelectedDataSourceId] = useState('');
  const [accessModeOverride, setAccessModeOverride] = useState<'read' | 'write' | 'admin' | null>(null);
  const [displayName, setDisplayName] = useState('');
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (dataSource) {
      setSelectedDataSourceId(dataSource.data_source_id);
      setAccessModeOverride(dataSource.effective_access_mode !== dataSource.original_access_mode ? dataSource.effective_access_mode : null);
      setDisplayName(dataSource.display_name || '');
      setEnabled(dataSource.enabled);
    } else {
      setSelectedDataSourceId('');
      setAccessModeOverride(null);
      setDisplayName('');
      setEnabled(null);
    }
    setError(null);
  }, [dataSource, isOpen]);

  const handleSave = async () => {
    if (!selectedDataSourceId.trim()) {
      setError('Please select a data source');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      await onSave(selectedDataSourceId, {
        access_mode_override: accessModeOverride || undefined,
        display_name: displayName.trim() || undefined,
        enabled: enabled !== null ? enabled : undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save data source binding');
    } finally {
      setSaving(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  if (!isOpen) return null;

  const selectedDataSource = availableDataSources.find(ds => ds.data_source_id === selectedDataSourceId);

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      onClick={onClose}
      onKeyDown={handleKeyPress}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
          {dataSource ? 'Edit Data Source Binding' : 'Create Data Source Binding'}
        </h2>

        {error && (
          <div className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Data Source
            </label>
            <select
              value={selectedDataSourceId}
              onChange={(e) => setSelectedDataSourceId(e.target.value)}
              disabled={!!dataSource}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="">Select a data source</option>
              {availableDataSources.map((ds) => (
                <option key={ds.data_source_id} value={ds.data_source_id}>
                  {ds.display_name || ds.data_source_name} ({ds.data_source_type})
                </option>
              ))}
            </select>
          </div>

          {selectedDataSource && (
            <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3 text-sm">
              <div className="space-y-1">
                <div>
                  <span className="text-gray-600 dark:text-gray-400">Original Access Mode:</span>
                  <span className="ml-2 font-medium">{selectedDataSource.original_access_mode}</span>
                </div>
                <div>
                  <span className="text-gray-600 dark:text-gray-400">Type:</span>
                  <span className="ml-2 font-medium">{selectedDataSource.data_source_type}</span>
                </div>
              </div>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Access Mode Override
            </label>
            <select
              value={accessModeOverride || ''}
              onChange={(e) => setAccessModeOverride(e.target.value ? e.target.value as any : null)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="">No Override (Use Original)</option>
              <option value="read">Read</option>
              <option value="write">Write</option>
              <option value="admin">Admin</option>
            </select>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Override can only be more restrictive than the original access mode
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Display Name (Optional)
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Custom display name for this workspace"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            />
          </div>

          <div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={enabled !== null ? enabled : true}
                onChange={(e) => setEnabled(e.target.checked)}
                className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">
                Enable this data source in workspace
              </span>
            </label>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !selectedDataSourceId.trim()}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}

