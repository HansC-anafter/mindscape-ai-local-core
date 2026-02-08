'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { InlineAlert } from '../InlineAlert';
import type { VectorDBConfig } from '../../types';

interface VectorDBConnectionWizardProps {
  config: VectorDBConfig | null;
  onClose: () => void;
  onSuccess: () => void;
}

interface VectorDBTestResult {
  database?: string;
  pgvector_installed?: boolean;
  pgvector_version?: string;
  dimension_check?: boolean;
  dimension?: number;
  dimension_error?: string;
}

export function VectorDBConnectionWizard({
  config,
  onClose,
  onSuccess,
}: VectorDBConnectionWizardProps) {
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [form, setForm] = useState<VectorDBConfig>({
    mode: config?.mode || 'local',
    enabled: config?.enabled !== undefined ? config.enabled : true,
    host: config?.host || '',
    port: config?.port || 5432,
    database: config?.database || 'mindscape_vectors',
    schema_name: config?.schema_name || 'public',
    username: config?.username || '',
    password: '',
    ssl_mode: config?.ssl_mode || 'prefer',
    access_mode: config?.access_mode || 'read_write',
    data_scope: config?.data_scope || 'all',
  });

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await settingsApi.put('/api/v1/vector-db/config', form);
      setSuccess(t('configSaved' as any));
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to save';
      setError(errorMessage);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setError(null);
    setTestResult(null);
    try {
      const result = await settingsApi.post<VectorDBTestResult>('/api/v1/vector-db/test', form);
      const details = [
        `✅ Successfully connected to ${result.database || 'PostgreSQL'}`,
        result.pgvector_installed
          ? `✅ pgvector installed (version ${result.pgvector_version || 'unknown'})`
          : '❌ pgvector extension not found',
        result.dimension_check
          ? `✅ Main collections dimension = ${result.dimension} (compatible with current embedding model)`
          : result.dimension_error || '⚠️ Dimension check failed',
      ]
        .filter(Boolean)
        .join('\n');

      setTestResult(`${t('testResults' as any)}:\n\n${details}`);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Test failed';
      setError(`${t('testFailed' as any)}: ${errorMessage}`);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{t('vectorDBConfig' as any)}</h2>
          <button onClick={onClose} className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
            ✕
          </button>
        </div>

        {error && (
          <InlineAlert
            type="error"
            message={error}
            onDismiss={() => setError(null)}
            className="mb-4"
          />
        )}

        {success && (
          <InlineAlert
            type="success"
            message={success}
            onDismiss={() => setSuccess(null)}
            className="mb-4"
          />
        )}

        {testResult && (
          <InlineAlert
            type="info"
            message={testResult}
            onDismiss={() => setTestResult(null)}
            className="mb-4 whitespace-pre-line"
          />
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('operationMode' as any)}
            </label>
            <div className="space-y-2">
              <label className="flex items-center">
                <input
                  type="radio"
                  name="mode"
                  value="local"
                  checked={form.mode === 'local'}
                  onChange={(e) => setForm({ ...form, mode: e.target.value as 'local' | 'custom' })}
                  className="mr-2"
                />
                <div>
                  <span className="font-medium dark:text-gray-200">{t('localMode' as any)}</span>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{t('localModeDescription' as any)}</p>
                </div>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="mode"
                  value="custom"
                  checked={form.mode === 'custom'}
                  onChange={(e) => setForm({ ...form, mode: e.target.value as 'local' | 'custom' })}
                  className="mr-2"
                />
                <div>
                  <span className="font-medium dark:text-gray-200">{t('customPostgreSQL' as any)}</span>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{t('customPostgreSQLDescription' as any)}</p>
                </div>
              </label>
            </div>
          </div>

          {form.mode === 'custom' && (
            <div className="space-y-4 border-t pt-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Host</label>
                  <input
                    type="text"
                    value={form.host || ''}
                    onChange={(e) => setForm({ ...form, host: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
                    placeholder="localhost or postgres.example.com"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Port</label>
                  <input
                    type="number"
                    value={form.port || 5432}
                    onChange={(e) => setForm({ ...form, port: parseInt(e.target.value) || 5432 })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Database name
                  </label>
                  <input
                    type="text"
                    value={form.database || ''}
                    onChange={(e) => setForm({ ...form, database: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Schema</label>
                  <input
                    type="text"
                    value={form.schema_name || ''}
                    onChange={(e) => setForm({ ...form, schema_name: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Username</label>
                  <input
                    type="text"
                    value={form.username || ''}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Password</label>
                  <input
                    type="password"
                    value={form.password || ''}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
                    placeholder="Leave empty to keep existing password"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">SSL mode</label>
                <select
                  value={form.ssl_mode || 'prefer'}
                  onChange={(e) => setForm({ ...form, ssl_mode: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
                >
                  <option value="disable">disable</option>
                  <option value="prefer">prefer</option>
                  <option value="require">require</option>
                </select>
              </div>

              <p className="text-xs text-gray-500 dark:text-gray-400">
                We only create our own schema / tables in this DB, will not touch other data.
              </p>
            </div>
          )}

          <div className="border-t dark:border-gray-700 pt-4">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">{t('accessMode' as any)}</label>
            <div className="space-y-2">
              <label className="flex items-center">
                <input
                  type="radio"
                  name="access_mode"
                  value="read_write"
                  checked={form.access_mode === 'read_write'}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      access_mode: e.target.value as 'read_write' | 'read_only' | 'disabled',
                    })
                  }
                  className="mr-2"
                />
                <span>{t('readWrite' as any)}</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="access_mode"
                  value="read_only"
                  checked={form.access_mode === 'read_only'}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      access_mode: e.target.value as 'read_write' | 'read_only' | 'disabled',
                    })
                  }
                  className="mr-2"
                />
                <span>{t('readOnly' as any)}</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="access_mode"
                  value="disabled"
                  checked={form.access_mode === 'disabled'}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      access_mode: e.target.value as 'read_write' | 'read_only' | 'disabled',
                    })
                  }
                  className="mr-2"
                />
                <span>{t('disabled' as any)}</span>
              </label>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">{t('dataScope' as any)}</label>
            <div className="space-y-2">
              <label className="flex items-center">
                <input
                  type="radio"
                  name="data_scope"
                  value="mindscape_only"
                  checked={form.data_scope === 'mindscape_only'}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      data_scope: e.target.value as 'mindscape_only' | 'with_documents' | 'all',
                    })
                  }
                  className="mr-2"
                />
                <span>Store conversation summaries and mindscape only</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="data_scope"
                  value="with_documents"
                  checked={form.data_scope === 'with_documents'}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      data_scope: e.target.value as 'mindscape_only' | 'with_documents' | 'all',
                    })
                  }
                  className="mr-2"
                />
                <span>Include documents / WordPress content</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="data_scope"
                  value="all"
                  checked={form.data_scope === 'all'}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      data_scope: e.target.value as 'mindscape_only' | 'with_documents' | 'all',
                    })
                  }
                  className="mr-2"
                />
                <span>Include all sources</span>
              </label>
            </div>
          </div>

          <div className="border-t dark:border-gray-700 pt-4">
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                className="mr-2"
              />
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('enableVectorDB' as any)}</span>
            </label>
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{t('enableVectorDBDescription' as any)}</p>
          </div>
        </div>

        <div className="flex justify-between items-center pt-4 border-t dark:border-gray-700 mt-4">
          <button
            onClick={handleTest}
            disabled={testing || saving}
            className="px-4 py-2 text-gray-600 dark:text-gray-400 border border-gray-600 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {testing ? t('testing' as any) : t('testConnection' as any)}
          </button>
          <div className="flex space-x-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
            >
              {t('cancel' as any)}
            </button>
            <button
              onClick={handleSave}
              disabled={
                saving ||
                testing ||
                (form.mode === 'custom' && (!form.host || !form.username))
              }
              className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? t('saving' as any) : t('save' as any)}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
