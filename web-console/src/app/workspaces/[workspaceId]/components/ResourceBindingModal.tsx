'use client';

import React, { useState, useEffect } from 'react';
import { WorkspaceResourceBinding, CreateResourceBindingRequest } from '@/hooks/useResourceBindings';
import { t } from '@/lib/i18n';

interface ResourceBindingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: CreateResourceBindingRequest) => Promise<void>;
  binding?: WorkspaceResourceBinding | null;
}

export default function ResourceBindingModal({
  isOpen,
  onClose,
  onSave,
  binding,
}: ResourceBindingModalProps) {
  const [resourceType, setResourceType] = useState<'playbook' | 'tool' | 'data_source'>('playbook');
  const [resourceId, setResourceId] = useState('');
  const [accessMode, setAccessMode] = useState<'read' | 'write' | 'admin'>('read');
  const [overrides, setOverrides] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (binding) {
      setResourceType(binding.resource_type);
      setResourceId(binding.resource_id);
      setAccessMode(binding.access_mode);
      setOverrides(binding.overrides || {});
    } else {
      setResourceType('playbook');
      setResourceId('');
      setAccessMode('read');
      setOverrides({});
    }
    setError(null);
  }, [binding, isOpen]);

  const handleSave = async () => {
    if (!resourceId.trim()) {
      setError('Resource ID is required');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      await onSave({
        resource_type: resourceType,
        resource_id: resourceId.trim(),
        access_mode: accessMode,
        overrides: Object.keys(overrides).length > 0 ? overrides : undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save binding');
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
          {binding ? t('editBinding' as any) : t('addBinding' as any)}
        </h2>

        {error && (
          <div className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('resourceType' as any)}
            </label>
            <select
              value={resourceType}
              onChange={(e) => setResourceType(e.target.value as any)}
              disabled={!!binding}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="playbook">Playbook</option>
              <option value="tool">Tool</option>
              <option value="data_source">Data Source</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('resourceId' as any)}
            </label>
            <input
              type="text"
              value={resourceId}
              onChange={(e) => setResourceId(e.target.value)}
              disabled={!!binding}
              placeholder={t('resourceId' as any)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('accessMode' as any)}
            </label>
            <select
              value={accessMode}
              onChange={(e) => setAccessMode(e.target.value as any)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="read">Read</option>
              <option value="write">Write</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('overrides' as any)}
            </label>
            <textarea
              value={JSON.stringify(overrides, null, 2)}
              onChange={(e) => {
                try {
                  const parsed = JSON.parse(e.target.value);
                  setOverrides(parsed);
                  setError(null);
                } catch {
                  setError('Invalid JSON');
                }
              }}
              rows={4}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 font-mono text-sm"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {t('overrides' as any)}
            </p>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50"
          >
            {t('cancel' as any)}
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !resourceId.trim()}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? t('saving' as any) : t('save' as any)}
          </button>
        </div>
      </div>
    </div>
  );
}

