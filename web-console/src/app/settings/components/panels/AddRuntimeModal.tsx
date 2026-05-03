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
  const [icon, setIcon] = useState('link');
  const [authType, setAuthType] = useState<'api_key' | 'oauth2' | 'none'>('none');
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      showNotification('error', 'Runtime name is required');
      return;
    }

    if (!configUrl.trim()) {
      showNotification('error', 'Configuration page URL is required');
      return;
    }

    // Validate URL format
    try {
      new URL(configUrl);
    } catch {
      showNotification('error', 'Enter a valid URL');
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
          icon: icon.trim() || 'link',
          auth_type: authType,
          auth_config: Object.keys(authConfig).length > 0 ? authConfig : undefined,
        }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Failed to create runtime' }));
        throw new Error(error.detail || 'Failed to create runtime');
      }

      const newRuntime = await response.json();
      showNotification('success', `Runtime "${name}" added successfully`);
      onSuccess(newRuntime);

      // Reset form
      setName('');
      setDescription('');
      setConfigUrl('');
      setIcon('link');
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
      title="Add Runtime Environment"
      maxWidth="max-w-2xl"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Runtime Name *
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
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe what this runtime environment is used for"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            rows={3}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Configuration Page URL *
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
            The configuration page will be embedded in this interface through an iframe.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Authentication Type
          </label>
          <select
            value={authType}
            onChange={(e) => setAuthType(e.target.value as 'api_key' | 'oauth2' | 'none')}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          >
            <option value="none">No Authentication</option>
            <option value="api_key">API Key</option>
            <option value="oauth2">OAuth2 (coming soon)</option>
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
              placeholder="Enter API key"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              required={authType === 'api_key'}
            />
          </div>
        )}

        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
            Icon (optional)
          </label>
          <input
            type="text"
            value={icon}
            onChange={(e) => setIcon(e.target.value)}
            placeholder="link"
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
            Cancel
          </button>
          <button
            type="submit"
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={saving}
          >
            {saving ? 'Adding...' : 'Add'}
          </button>
        </div>
      </form>
    </BaseModal>
  );
}
