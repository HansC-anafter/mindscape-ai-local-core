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
      const result = await settingsApi.post<{ valid: boolean; message: string; vaults: any[] }>('/api/v1/system-settings/obsidian/test', form);
      if (result.valid) {
        setTestResult(`${t('testResults' as any)}:\n\n✅ ${result.message}\n\n${result.vaults.map(v => `- ${v.path}: ${v.valid ? 'Valid' : 'Invalid'}`).join('\n')}`);
      } else {
        setError(`${t('testFailed' as any)}: ${result.message}`);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Test failed';
      setError(`${t('testFailed' as any)}: ${errorMessage}`);
    } finally {
      setTesting(false);
    }
  };

  const addVaultPath = () => {
    const trimmed = newVaultPath.trim();
    if (!trimmed) {
      setError(t('pleaseEnterVaultPath' as any));
      return;
    }
    if (form.vault_paths.includes(trimmed)) {
      setError(t('vaultPathAlreadyExists' as any));
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
      setError(t('pleaseEnterFolderName' as any));
      return;
    }
    if (form.include_folders.includes(trimmed)) {
      setError(t('folderAlreadyExists' as any));
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
      setError(t('pleaseEnterFolderName' as any));
      return;
    }
    if (form.exclude_folders.includes(trimmed)) {
      setError(t('folderAlreadyExists' as any));
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
      setError(t('pleaseEnterTag' as any));
      return;
    }
    if (form.include_tags.includes(trimmed)) {
      setError(t('tagAlreadyExists' as any));
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
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 max-w-3xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{t('obsidianConfig' as any)}</h2>
          <button onClick={onClose} className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
            ✕
          </button>
        </div>

        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('obsidianVaultPaths' as any)}
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              {t('obsidianVaultPathsDescription' as any)}
            </p>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newVaultPath}
                onChange={(e) => setNewVaultPath(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addVaultPath()}
                placeholder={t('enterVaultPath' as any)}
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              />
              <button
                type="button"
                onClick={addVaultPath}
                className="px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-600"
              >
                {t('add' as any)}
              </button>
            </div>
            <div className="space-y-1">
              {form.vault_paths.map((path) => (
                <div key={path} className="flex items-center justify-between bg-gray-50 dark:bg-gray-800/50 p-2 rounded">
                  <span className="text-sm text-gray-700 dark:text-gray-300">{path}</span>
                  <button
                    type="button"
                    onClick={() => removeVaultPath(path)}
                    className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 text-sm"
                  >
                    {t('delete' as any)}
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('obsidianIncludeFolders' as any)}
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              {t('obsidianIncludeFoldersDescription' as any)}
            </p>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newIncludeFolder}
                onChange={(e) => setNewIncludeFolder(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addIncludeFolder()}
                placeholder="e.g., Research"
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              />
              <button
                type="button"
                onClick={addIncludeFolder}
                className="px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-600"
              >
                {t('add' as any)}
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {form.include_folders.map((folder) => (
                <span
                  key={folder}
                  className="inline-flex items-center px-3 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 rounded-full text-sm"
                >
                  {folder}
                  <button
                    type="button"
                    onClick={() => removeIncludeFolder(folder)}
                    className="ml-2 text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('obsidianExcludeFolders' as any)}
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              {t('obsidianExcludeFoldersDescription' as any)}
            </p>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newExcludeFolder}
                onChange={(e) => setNewExcludeFolder(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addExcludeFolder()}
                placeholder="e.g., .obsidian"
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              />
              <button
                type="button"
                onClick={addExcludeFolder}
                className="px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-600"
              >
                {t('add' as any)}
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {form.exclude_folders.map((folder) => (
                <span
                  key={folder}
                  className="inline-flex items-center px-3 py-1 bg-gray-100 dark:bg-gray-800/30 text-gray-800 dark:text-gray-300 rounded-full text-sm"
                >
                  {folder}
                  <button
                    type="button"
                    onClick={() => removeExcludeFolder(folder)}
                    className="ml-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-300"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('obsidianIncludeTags' as any)}
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              {t('obsidianIncludeTagsDescription' as any)}
            </p>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addTag()}
                placeholder="e.g., research"
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              />
              <button
                type="button"
                onClick={addTag}
                className="px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-600"
              >
                {t('add' as any)}
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {form.include_tags.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center px-3 py-1 bg-gray-100 dark:bg-gray-800/30 text-gray-800 dark:text-gray-300 rounded-full text-sm"
                >
                  #{tag}
                  <button
                    type="button"
                    onClick={() => removeTag(tag)}
                    className="ml-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-300"
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
            <label htmlFor="obsidianEnabled" className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('enableObsidianIntegration' as any)}
            </label>
          </div>

          {error && <InlineAlert type="error" message={error} />}
          {success && <InlineAlert type="success" message={success} />}
          {testResult && (
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
              <pre className="text-sm text-blue-800 dark:text-blue-300 whitespace-pre-wrap">{testResult}</pre>
            </div>
          )}

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={handleTest}
              disabled={testing || form.vault_paths.length === 0}
              className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {testing ? t('testing' as any) : t('testConnection' as any)}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || form.vault_paths.length === 0}
              className="flex-1 px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? t('saving' as any) : t('save' as any)}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-300 dark:hover:bg-gray-600"
            >
              {t('cancel' as any)}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}




