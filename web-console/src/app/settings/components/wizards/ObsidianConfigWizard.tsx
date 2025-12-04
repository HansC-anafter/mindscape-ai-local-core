'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { InlineAlert } from '../InlineAlert';

interface ObsidianConfig {
  vault_paths: string[];
  include_folders: string[];
  exclude_folders: string[];
  include_tags: string[];
  enabled: boolean;
}

interface ObsidianConfigWizardProps {
  config: ObsidianConfig | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function ObsidianConfigWizard({
  config,
  onClose,
  onSuccess,
}: ObsidianConfigWizardProps) {
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [form, setForm] = useState<ObsidianConfig>({
    vault_paths: config?.vault_paths || [],
    include_folders: config?.include_folders || ['Research', 'Projects'],
    exclude_folders: config?.exclude_folders || ['.obsidian', 'Templates'],
    include_tags: config?.include_tags || ['research', 'paper', 'project'],
    enabled: config?.enabled !== undefined ? config.enabled : true,
  });
  const [newVaultPath, setNewVaultPath] = useState('');
  const [newIncludeFolder, setNewIncludeFolder] = useState('');
  const [newExcludeFolder, setNewExcludeFolder] = useState('');
  const [newTag, setNewTag] = useState('');

  useEffect(() => {
    const loadConfig = async () => {
      try {
        const data = await settingsApi.get<ObsidianConfig>('/api/v1/system-settings/obsidian');
        if (data) {
          setForm({
            vault_paths: data.vault_paths || [],
            include_folders: data.include_folders || ['Research', 'Projects'],
            exclude_folders: data.exclude_folders || ['.obsidian', 'Templates'],
            include_tags: data.include_tags || ['research', 'paper', 'project'],
            enabled: data.enabled !== undefined ? data.enabled : true,
          });
        }
      } catch (err) {
        console.error('Failed to load Obsidian config:', err);
      }
    };
    loadConfig();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await settingsApi.put('/api/v1/system-settings/obsidian', form);
      setSuccess(t('configSaved'));
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
      const result = await settingsApi.post<{ valid: boolean; message: string; vaults: any[] }>('/api/v1/system-settings/obsidian/test', form);
      if (result.valid) {
        setTestResult(`${t('testResults')}:\n\n✅ ${result.message}\n\n${result.vaults.map(v => `- ${v.path}: ${v.valid ? 'Valid' : 'Invalid'}`).join('\n')}`);
      } else {
        setError(`${t('testFailed')}: ${result.message}`);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Test failed';
      setError(`${t('testFailed')}: ${errorMessage}`);
    } finally {
      setTesting(false);
    }
  };

  const addVaultPath = () => {
    const trimmed = newVaultPath.trim();
    if (!trimmed) {
      setError(t('pleaseEnterVaultPath'));
      return;
    }
    if (form.vault_paths.includes(trimmed)) {
      setError(t('vaultPathAlreadyExists'));
      return;
    }
    setForm({ ...form, vault_paths: [...form.vault_paths, trimmed] });
    setNewVaultPath('');
    setError(null);
  };

  const removeVaultPath = (path: string) => {
    setForm({ ...form, vault_paths: form.vault_paths.filter(p => p !== path) });
  };

  const addIncludeFolder = () => {
    const trimmed = newIncludeFolder.trim();
    if (!trimmed) {
      setError(t('pleaseEnterFolderName'));
      return;
    }
    if (form.include_folders.includes(trimmed)) {
      setError(t('folderAlreadyExists'));
      return;
    }
    setForm({ ...form, include_folders: [...form.include_folders, trimmed] });
    setNewIncludeFolder('');
    setError(null);
  };

  const removeIncludeFolder = (folder: string) => {
    setForm({ ...form, include_folders: form.include_folders.filter(f => f !== folder) });
  };

  const addExcludeFolder = () => {
    const trimmed = newExcludeFolder.trim();
    if (!trimmed) {
      setError(t('pleaseEnterFolderName'));
      return;
    }
    if (form.exclude_folders.includes(trimmed)) {
      setError(t('folderAlreadyExists'));
      return;
    }
    setForm({ ...form, exclude_folders: [...form.exclude_folders, trimmed] });
    setNewExcludeFolder('');
    setError(null);
  };

  const removeExcludeFolder = (folder: string) => {
    setForm({ ...form, exclude_folders: form.exclude_folders.filter(f => f !== folder) });
  };

  const addTag = () => {
    const trimmed = newTag.trim();
    if (!trimmed) {
      setError(t('pleaseEnterTag'));
      return;
    }
    if (form.include_tags.includes(trimmed)) {
      setError(t('tagAlreadyExists'));
      return;
    }
    setForm({ ...form, include_tags: [...form.include_tags, trimmed] });
    setNewTag('');
    setError(null);
  };

  const removeTag = (tag: string) => {
    setForm({ ...form, include_tags: form.include_tags.filter(t => t !== tag) });
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 max-w-3xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-900">{t('obsidianConfig')}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            ✕
          </button>
        </div>

        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t('obsidianVaultPaths')}
            </label>
            <p className="text-xs text-gray-500 mb-3">
              {t('obsidianVaultPathsDescription')}
            </p>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newVaultPath}
                onChange={(e) => setNewVaultPath(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addVaultPath()}
                placeholder={t('enterVaultPath')}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={addVaultPath}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                {t('add')}
              </button>
            </div>
            <div className="space-y-1">
              {form.vault_paths.map((path) => (
                <div key={path} className="flex items-center justify-between bg-gray-50 p-2 rounded">
                  <span className="text-sm text-gray-700">{path}</span>
                  <button
                    type="button"
                    onClick={() => removeVaultPath(path)}
                    className="text-red-600 hover:text-red-800 text-sm"
                  >
                    {t('delete')}
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t('obsidianIncludeFolders')}
            </label>
            <p className="text-xs text-gray-500 mb-3">
              {t('obsidianIncludeFoldersDescription')}
            </p>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newIncludeFolder}
                onChange={(e) => setNewIncludeFolder(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addIncludeFolder()}
                placeholder="e.g., Research"
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={addIncludeFolder}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                {t('add')}
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {form.include_folders.map((folder) => (
                <span
                  key={folder}
                  className="inline-flex items-center px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm"
                >
                  {folder}
                  <button
                    type="button"
                    onClick={() => removeIncludeFolder(folder)}
                    className="ml-2 text-blue-600 hover:text-blue-800"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t('obsidianExcludeFolders')}
            </label>
            <p className="text-xs text-gray-500 mb-3">
              {t('obsidianExcludeFoldersDescription')}
            </p>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newExcludeFolder}
                onChange={(e) => setNewExcludeFolder(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addExcludeFolder()}
                placeholder="e.g., .obsidian"
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={addExcludeFolder}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                {t('add')}
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {form.exclude_folders.map((folder) => (
                <span
                  key={folder}
                  className="inline-flex items-center px-3 py-1 bg-gray-100 text-gray-800 rounded-full text-sm"
                >
                  {folder}
                  <button
                    type="button"
                    onClick={() => removeExcludeFolder(folder)}
                    className="ml-2 text-gray-600 hover:text-gray-800"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t('obsidianIncludeTags')}
            </label>
            <p className="text-xs text-gray-500 mb-3">
              {t('obsidianIncludeTagsDescription')}
            </p>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addTag()}
                placeholder="e.g., research"
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={addTag}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                {t('add')}
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {form.include_tags.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center px-3 py-1 bg-gray-100 text-gray-800 rounded-full text-sm"
                >
                  #{tag}
                  <button
                    type="button"
                    onClick={() => removeTag(tag)}
                    className="ml-2 text-gray-600 hover:text-gray-800"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="obsidianEnabled"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              className="mr-2"
            />
            <label htmlFor="obsidianEnabled" className="text-sm font-medium text-gray-700">
              {t('enableObsidianIntegration')}
            </label>
          </div>

          {error && <InlineAlert type="error" message={error} />}
          {success && <InlineAlert type="success" message={success} />}
          {testResult && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <pre className="text-sm text-blue-800 whitespace-pre-wrap">{testResult}</pre>
            </div>
          )}

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={handleTest}
              disabled={testing || form.vault_paths.length === 0}
              className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {testing ? t('testing') : t('testConnection')}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || form.vault_paths.length === 0}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? t('saving') : t('save')}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300"
            >
              {t('cancel')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}




