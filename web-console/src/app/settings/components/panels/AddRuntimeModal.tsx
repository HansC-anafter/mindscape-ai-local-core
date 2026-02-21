'use client';

import React, { useState } from 'react';
import { BaseModal } from '../../../../components/BaseModal';
import { showNotification } from '../../hooks/useSettingsNotification';

interface AddRuntimeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (runtime: RuntimeEnvironment) => void;
}

interface RuntimeEnvironment {
  id: string;
  name: string;
  description: string;
  icon: string;
  status: 'active' | 'inactive' | 'configured' | 'not_configured';
  config_url: string;
  auth_type: 'api_key' | 'oauth2' | 'none';
  auth_config?: Record<string, any>;
}

export function AddRuntimeModal({ isOpen, onClose, onSuccess }: AddRuntimeModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [configUrl, setConfigUrl] = useState('');
  const [icon, setIcon] = useState('🔗');
  const [authType, setAuthType] = useState<'api_key' | 'oauth2' | 'none'>('none');
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      showNotification('error', 'Runtime 名稱是必填項');
      return;
    }

    if (!configUrl.trim()) {
      showNotification('error', '配置頁面 URL 是必填項');
      return;
    }

    // Validate URL format
    try {
      new URL(configUrl);
    } catch {
      showNotification('error', '請輸入有效的 URL');
      return;
    }

    setSaving(true);
    try {
      const authConfig: Record<string, any> = {};
      if (authType === 'api_key' && apiKey) {
        authConfig.api_key = apiKey;
      }

      const response = await fetch('/api/v1/runtime-environments', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || undefined,
          config_url: configUrl.trim(),
          icon: icon.trim() || '🔗',
          auth_type: authType,
          auth_config: Object.keys(authConfig).length > 0 ? authConfig : undefined,
        }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Failed to create runtime' }));
        throw new Error(error.detail || 'Failed to create runtime');
      }

      const newRuntime = await response.json();
      showNotification('success', `Runtime "${name}" 已成功添加`);
      onSuccess(newRuntime);

      // Reset form
      setName('');
      setDescription('');
      setConfigUrl('');
      setIcon('🔗');
      setAuthType('none');
      setApiKey('');
      onClose();
    } catch (error: any) {
      console.error('Failed to create runtime:', error);
      showNotification('error', error.message || 'Failed to create runtime');
    } finally {
      setSaving(false);
    }
  };

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title="添加 Runtime 環境"
      maxWidth="max-w-2xl"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Runtime 名稱 *
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. My-Cloud-Runner, Custom Runtime"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            描述
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="描述這個 Runtime 環境的用途"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            rows={3}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            配置頁面 URL *
          </label>
          <input
            type="url"
            value={configUrl}
            onChange={(e) => setConfigUrl(e.target.value)}
            placeholder="https://example.com/settings/runtime"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            required
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            配置頁面將通過 iframe 嵌入到此界面
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            認證方式
          </label>
          <select
            value={authType}
            onChange={(e) => setAuthType(e.target.value as 'api_key' | 'oauth2' | 'none')}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          >
            <option value="none">無認證</option>
            <option value="api_key">API Key</option>
            <option value="oauth2">OAuth2 (未來支持)</option>
          </select>
        </div>

        {authType === 'api_key' && (
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
              API Key *
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="輸入 API Key"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              required={authType === 'api_key'}
            />
          </div>
        )}

        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            圖標（可選）
          </label>
          <input
            type="text"
            value={icon}
            onChange={(e) => setIcon(e.target.value)}
            placeholder="🔗"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
        </div>

        <div className="flex justify-end space-x-2 pt-4">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
            disabled={saving}
          >
            取消
          </button>
          <button
            type="submit"
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={saving}
          >
            {saving ? '添加中...' : '添加'}
          </button>
        </div>
      </form>
    </BaseModal>
  );
}

